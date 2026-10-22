"""Explicit H3 generated-row plain LoRA residuals, without changing base weights.

Inspired by baslack/scripts_nodes PR2 (MIT). The fc2 residual is observed at
the native MLP boundary: Core's fused linear_input_act remains untouched.
"""
from __future__ import annotations

from collections import Counter
from contextvars import ContextVar
from dataclasses import dataclass, field
import hashlib
import json
import logging
import math
from pathlib import Path
import re
import threading
import weakref

import comfy.lora
import comfy.lora_convert
import comfy.ops
import comfy.utils
from comfy.ldm.minimax.model import Attention, DiTBlock, MLP, MiniMaxH3Model, PackedLayout
from comfy.weight_adapter import LoRAAdapter
import torch

from .h3_lora_compat_advanced import (build_minimax_h3_lora_key_map,
    convert_fastvideo_h3_adapter, _extract_fastvideo_vsa_gate_weights)
from .h3_weight_diagnostics import lora_mapping_diagnostics

SCHEMA = 't8.h14.token-lora.v1'
ATTACHMENT = 't8_h14_token_lora_state'
POLICIES = {'generated_audio': {'audio'}, 'generated_video': {'video'},
            'all_eligible_rows': {'text','cond','cond_audio','ref_img','ref_audio','audio','video'}}
TARGET = re.compile(r'^diffusion_model\.blocks\.(\d+)\.(attn\.(?:qkv_proj|out_proj)|mlp\.fc[12])\.weight$')
_ACTIVE = ContextVar('t8_h14_token_lora_call', default=None)
_LOCKS = weakref.WeakKeyDictionary()
_LOCKS_GUARD = threading.Lock()
LOG = logging.getLogger(__name__)


def _lock(block):
    with _LOCKS_GUARD:
        if block not in _LOCKS:
            _LOCKS[block] = threading.RLock()
        return _LOCKS[block]


def _sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream,'sha256').hexdigest()


def _tensor_sha(tensor):
    value = tensor.detach().cpu().contiguous()
    return hashlib.sha256(value.view(torch.uint8).numpy().tobytes()).hexdigest()


@dataclass(frozen=True)
class Delta:
    target: str
    up: torch.Tensor
    down: torch.Tensor
    scale: float
    source_sha256: str = ''

    def signature(self):
        return {'target':self.target,'up_sha256':_tensor_sha(self.up),'down_sha256':_tensor_sha(self.down),
                'up_shape':list(self.up.shape),'down_shape':list(self.down.shape),'scale':self.scale,
                'source_sha256':self.source_sha256}


def spans(layout, sequence, policy):
    if not isinstance(layout,PackedLayout) or policy not in POLICIES or layout.seq_len != sequence:
        raise ValueError('Token LoRA requires the actual matching H3 PackedLayout')
    selected, cursor, counts = [], 0, Counter()
    known = POLICIES['all_eligible_rows']
    for entry in layout.segments:
        if not isinstance(entry,(tuple,list)) or len(entry) != 3:
            raise ValueError('Invalid packed row segment')
        a,b,kind = entry
        if type(a) is not int or type(b) is not int or a != cursor or not a <= b <= sequence or kind not in known:
            raise ValueError('Unknown, overlapping or out-of-range H3 packed rows')
        cursor = b
        counts[kind] += b-a
        if kind in POLICIES[policy] and b > a:
            selected.append((a,b))
    if cursor != sequence or not selected:
        raise ValueError('Packed layout must cover the actual sequence and selected generated rows')
    return selected, dict(counts)


def _plain_delta(target, adapter, module, strength):
    if type(adapter) is not LoRAAdapter or len(adapter.weights) != 6:
        raise ValueError('Token scope supports only complete plain LoRA adapters: '+target)
    up,down,alpha,mid,dora,reshape = adapter.weights
    if any(value is not None for value in (mid,dora,reshape)):
        raise ValueError('LoCon/DoRA/reshape is not a plain token-row adapter: '+target)
    if (not torch.is_tensor(up) or not torch.is_tensor(down) or up.ndim != 2 or down.ndim != 2
            or down.shape[0] < 1 or up.shape[1] != down.shape[0]
            or down.shape[1] != module.in_features or up.shape[0] != module.out_features
            or not up.is_floating_point() or not down.is_floating_point()
            or not bool(torch.isfinite(up).all()) or not bool(torch.isfinite(down).all())):
        raise ValueError('Plain LoRA A/B shape, dtype or finite contract failed: '+target)
    scale = float(strength) * (float(alpha)/down.shape[0] if alpha is not None else 1.)
    if not math.isfinite(scale):
        raise ValueError('Nonfinite LoRA alpha/strength: '+target)
    return Delta(target,up.detach().cpu().clone(),down.detach().cpu().clone(),scale)


@dataclass
class TokenLoRAState:
    policy: str
    sources: list
    deltas: dict
    owner_policy: str = 'delegate_without_scope'
    installed: list = field(default_factory=list)
    calls: Counter = field(default_factory=Counter)
    reasons: Counter = field(default_factory=Counter)
    targets_seen: Counter = field(default_factory=Counter)
    row_counts: Counter = field(default_factory=Counter)
    errors: list = field(default_factory=list)
    device_cache: dict = field(default_factory=dict)
    run: int = 0
    handles_active: int = 0
    peak_handles: int = 0
    max_residual: float = 0.

    def __post_init__(self):
        if self.policy not in POLICIES or self.owner_policy not in {'delegate_without_scope','require_scope'}:
            raise ValueError('Invalid explicit token scope/owner policy')
        self.signatures = {key:[d.signature() for d in values] for key,values in self.deltas.items()}

    def pre_run(self,model=None,*_):
        if self.handles_active:
            raise ValueError('A previous Token LoRA invocation still owns hooks')
        for key,values in self.deltas.items():
            if [d.signature() for d in values] != self.signatures[key]:
                raise ValueError('Scoped LoRA tensor content changed after preparation')
        if model is not None and _ordinary_duplicate(model,self.deltas):
            raise ValueError('Same scoped LoRA was applied again by a later ordinary loader')
        self.run += 1
        for value in (self.calls,self.reasons,self.targets_seen,self.row_counts):
            value.clear()
        self.errors.clear()
        self.device_cache.clear()
        self.peak_handles = 0
        self.max_residual = 0.

    def cleanup(self,*_):
        self.device_cache.clear()
        if self.handles_active:
            raise ValueError('Scoped LoRA cleanup found active transaction handles')

    def delta(self, target, x):
        result = None
        for ordinal,d in enumerate(self.deltas[target]):
            key = (target,ordinal,str(x.device),x.dtype)
            if key not in self.device_cache:
                self.device_cache[key] = (d.up.to(x.device,x.dtype),d.down.to(x.device,x.dtype))
            up,down = self.device_cache[key]
            value = ((x @ down.t()) @ up.t()) * d.scale
            if not bool(torch.isfinite(value).all()):
                raise ValueError('Nonfinite scoped LoRA residual: '+target)
            self.max_residual = max(self.max_residual,float(value.abs().max()))
            result = value if result is None else result+value
        return result

    def report(self):
        effective = (bool(self.calls['scoped']) and not self.reasons and not self.errors
                     and set(self.targets_seen) == set(self.deltas) and not self.handles_active)
        return {'schema':SCHEMA,'policy':self.policy,'selected_row_kinds':sorted(POLICIES[self.policy]),
            'sources':self.sources,'target_signatures':self.signatures,'installed_blocks':self.installed,
            'run':self.run,'actual_scoped_block_calls':self.calls['scoped'],
            'delegated_without_scope':self.calls['delegated'],'delegate_reasons':dict(self.reasons),
            'actual_target_calls':dict(self.targets_seen),'observed_rows':dict(self.row_counts),
            'handles_active':self.handles_active,'peak_handles':self.peak_handles,
            'alias_output_copies':self.calls['alias_copy'],'errors':self.errors,
            'maximum_observed_direct_residual':self.max_residual,
            'nonzero_direct_residual_observed':self.max_residual > 0,
            'scope_effective':effective,'fc2_method':'native_MLP_output_residual_original_fusion_unchanged',
            'base_weights_changed':False,'global_ops_replaced':False,'fusion_disabled':False,
            'other_modality_final_output_unchanged':False,'full_sampler_completion_proven':False,
            'perceptual_or_speed_qualified':False,'persistent_cache_portable':False}


def _owner_reason(block, previous):
    if previous is not None:
        return 'existing_block_owner_preserved'
    for module,expected in ((block,DiTBlock.forward),(block.attn,Attention.forward),(block.mlp,MLP.forward)):
        if getattr(module.forward,'__func__',None) is not expected:
            return 'non_native_forward_preserved'
    modules = [block,block.attn,block.mlp,block.attn.qkv_proj,block.attn.out_proj,block.mlp.fc1,block.mlp.fc2]
    if any(module._forward_hooks or module._forward_pre_hooks for module in modules):
        return 'existing_module_hooks_preserved'
    return None


class TokenBlock:
    def __init__(self,state,block,index,previous=None):
        self.state,self.block,self.index,self.previous = state,block,index,previous

    def __call__(self,args,extra):
        state,block = self.state,self.block
        with _lock(block):
            reason = _owner_reason(block,self.previous)
            if reason:
                state.calls['delegated'] += 1
                state.reasons[reason] += 1
                if state.reasons[reason] == 1:
                    LOG.warning('H3 Token LoRA: scope not applied (%s); existing user owner is retained',reason)
                if state.owner_policy == 'require_scope':
                    raise ValueError('Requested scope cannot be established; user owner retained: '+reason)
                return self.previous(args,extra) if self.previous is not None else extra['original_block'](args)
            return self._native(args,extra)

    def _native(self,args,extra):
        state,block = self.state,self.block
        x = args['img']
        if not torch.is_tensor(x) or x.ndim != 2:
            raise ValueError('Scoped H3 block input must have its native two-dimensional packed token axis')
        selected,counts = spans(args.get('layout'),x.shape[0],state.policy)
        prefix = f'diffusion_model.blocks.{self.index}.'
        targets = {key:values for key,values in state.deltas.items() if key.startswith(prefix)}
        by_path = {key[len(prefix):-len('.weight')]:key for key in targets}
        context,handles,pending,seen = object(),[],{},Counter()
        token = _ACTIVE.set(context)

        def fresh_output(module,inputs,output):
            if (not torch.is_tensor(output) or output.ndim != 2 or output.shape[0] != x.shape[0]
                    or not inputs or inputs[0].ndim != 2 or inputs[0].shape[0] != x.shape[0]):
                raise ValueError('Token axis differs from actual PackedLayout')
            if output._base is not None or torch._C._is_alias_of(output,inputs[0]):
                state.calls['alias_copy'] += 1
                return output.clone()
            return output  # known native Linear owns this fresh, unshared result

        def linear_hook(path):
            def hook(module,inputs,output):
                if _ACTIVE.get() is not context:
                    return None  # a concurrent unscoped caller must remain unchanged
                target = by_path.get(path)
                if target is not None:
                    output = fresh_output(module,inputs,output)
                    for a,b in selected:
                        output[a:b].add_(state.delta(target,inputs[0][a:b]))
                    seen[target] += 1
                if path == 'mlp.fc1' and 'mlp.fc2' in by_path:
                    # Observe the actual post-fc1 value even when native fc2 is
                    # fused and bypasses module.forward; do not disable fusion.
                    if output.ndim != 2 or output.shape[0] != x.shape[0]:
                        raise ValueError('MLP fc1 activation has no matching token axis')
                    pending['fc2'] = [(a,b,state.delta(by_path['mlp.fc2'],
                        comfy.ops._eager_input_act(output[a:b],'swiglu'))) for a,b in selected]
                return output
            return hook

        def mlp_hook(module,inputs,output):
            if _ACTIVE.get() is not context:
                return None
            if 'fc2' not in pending:
                raise ValueError('Actual native fc1 call was bypassed; no fc2 scope proof')
            output = fresh_output(module,inputs,output)
            for a,b,value in pending.pop('fc2'):
                output[a:b].add_(value)
            seen[by_path['mlp.fc2']] += 1
            return output

        def install(module,hook):
            handle = module.register_forward_hook(hook)
            handles.append(handle)  # registration is inside the cleanup transaction
            state.handles_active += 1
            state.peak_handles = max(state.peak_handles,state.handles_active)

        try:
            for path in ('attn.qkv_proj','attn.out_proj','mlp.fc1'):
                if path in by_path or (path == 'mlp.fc1' and 'mlp.fc2' in by_path):
                    install(block.get_submodule(path),linear_hook(path))
            if 'mlp.fc2' in by_path:
                install(block.mlp,mlp_hook)
            result = extra['original_block'](args)
            if set(seen) != set(targets) or any(count != 1 for count in seen.values()):
                raise ValueError('Actual block did not execute every requested scoped target exactly once')
            state.targets_seen.update(seen)
            state.row_counts.update(counts)
            state.calls['scoped'] += 1
            return result
        except BaseException as error:
            state.errors.append(type(error).__name__)
            raise
        finally:
            failed = []
            try:
                for handle in reversed(handles):
                    try:
                        handle.remove()
                        state.handles_active -= 1
                    except BaseException as error:
                        failed.append(error)
            finally:
                pending.clear()
                _ACTIVE.reset(token)
            if failed:
                state.errors.append('hook_cleanup_failed')
                raise RuntimeError('Scoped hook cleanup failed; other handles were still reclaimed') from failed[0]


def _ordinary_duplicate(model,deltas):
    ordinary = getattr(model,'patches',{})
    sources = {d.source_sha256 for values in deltas.values() for d in values}
    for source in sources:
        group = {key:d for key,values in deltas.items() for d in values if d.source_sha256 == source}
        matched = True
        for key,d in group.items():
            candidates = []
            for entry in ordinary.get(key,()):
                if not isinstance(entry,(tuple,list)) or len(entry) < 2 or entry[0] == 0:
                    continue
                adapter = entry[1]
                weights = (adapter.weights if type(adapter) is LoRAAdapter else
                    adapter[1] if isinstance(adapter,tuple) and len(adapter) == 2 and adapter[0] == 'lora' else None)
                if weights is not None and len(weights) >= 2:
                    candidates.append(weights)
            if not any(torch.is_tensor(v[0]) and torch.is_tensor(v[1]) and
                       torch.equal(v[0].cpu(),d.up) and torch.equal(v[1].cpu(),d.down) for v in candidates):
                matched = False
                break
        if matched and group:
            return True
    return False


def prepare(model,path,strength=1.,policy='generated_audio',owner_policy='delegate_without_scope'):
    if type(strength) not in (int,float) or not math.isfinite(strength) or not -10 <= strength <= 10:
        raise ValueError('Token LoRA strength must be finite in -10..10')
    if policy not in POLICIES or owner_policy not in {'delegate_without_scope','require_scope'}:
        raise ValueError('Unknown explicit token scope/owner policy')
    if path is None or strength == 0:
        return model,None,{'schema':SCHEMA,'status':'disabled','original_MODEL_returned':True,'file_opened':False}
    diffusion = model.get_model_object('diffusion_model')
    if not isinstance(diffusion,MiniMaxH3Model):
        from .patch_stack_policy import warn_patch_stack
        warn_patch_stack('Token-row scope received another MODEL class; checking actual LoRA targets')
    path = Path(path).resolve(strict=True)
    digest = _sha(path)
    raw,metadata = comfy.utils.load_torch_file(str(path),safe_load=True,return_metadata=True)
    if _sha(path) != digest:
        raise ValueError('LoRA file changed while preparing its content identity')
    gates,raw_adapter = _extract_fastvideo_vsa_gate_weights(raw)
    if gates:
        raise ValueError('Whole VSA gates are not plain token-row residuals; use the original loader')
    converted,conversion = convert_fastvideo_h3_adapter(raw_adapter)
    converted = comfy.lora_convert.convert_lora(converted)
    key_map,_ = build_minimax_h3_lora_key_map(model.model)
    loaded = comfy.lora.load_lora(converted,key_map,log_missing=False)
    mapping = lora_mapping_diagnostics(converted,key_map,loaded,loaded)
    if mapping['converted_unmapped_tensor_count'] or not loaded:
        raise ValueError('Every source tensor must be consumed; unmapped scoped LoRA keys: '+
                         repr(mapping['converted_unmapped_keys'][:12]))
    deltas = {}
    for target,adapter in loaded.items():
        match = TARGET.fullmatch(target) if isinstance(target,str) else None
        if match is None or int(match[1]) >= len(diffusion.blocks):
            raise ValueError('Unsupported non-token/AdaLN/refiner target; file is not partially applied: '+str(target))
        module = diffusion.blocks[int(match[1])].get_submodule(match[2])
        delta = _plain_delta(target,adapter,module,strength)
        deltas[target] = [Delta(delta.target,delta.up,delta.down,delta.scale,digest)]
    prior = model.get_attachment(ATTACHMENT) if hasattr(model,'get_attachment') else None
    replacements = model.model_options.get('transformer_options',{}).get('patches_replace',{}).get('dit',{})
    if prior is not None:
        if type(prior) is not TokenLoRAState or prior.policy != policy or prior.owner_policy != owner_policy:
            raise ValueError('Compose scoped adapters with the same explicit row/owner policy')
        if digest in {source['sha256'] for source in prior.sources}:
            raise ValueError('The same LoRA content is already scoped on this MODEL')
        for key,values in prior.deltas.items():
            deltas[key] = list(values)+deltas.get(key,[])
    # Detect complete duplicate native weight patches, without banning different
    # user LoRAs that happen to target the same layers.
    if _ordinary_duplicate(model,deltas):
        raise ValueError('Same LoRA matrices already applied as ordinary weight patches; choose one application')
    source = {'name':path.name,'sha256':digest,'strength':float(strength),'tensor_count':len(raw),
              'structural_conversion':conversion,'mapping':mapping}
    state = TokenLoRAState(policy,([] if prior is None else list(prior.sources))+[source],deltas,owner_policy)
    patched = model.clone()
    for index,block in enumerate(diffusion.blocks):
        if not any(key.startswith(f'diffusion_model.blocks.{index}.') for key in deltas):
            continue
        previous = replacements.get(('double_block',index))
        if type(previous) is TokenBlock and prior is not None and previous.state is prior:
            previous = previous.previous
        patched.set_model_patch_replace(TokenBlock(state,block,index,previous),'dit','double_block',index)
        state.installed.append(index)
    from comfy.patcher_extension import CallbacksMP
    owner = 't8_h14_token_lora_'+str(id(state))
    patched.add_callback_with_key(CallbacksMP.ON_PRE_RUN,owner,state.pre_run)
    patched.add_callback_with_key(CallbacksMP.ON_CLEANUP,owner,state.cleanup)
    patched.set_attachments(ATTACHMENT,state)
    return patched,state,state.report()


def audit(model,after_sampling):
    state = model.get_attachment(ATTACHMENT)
    if type(state) is not TokenLoRAState:
        raise ValueError('Connect MODEL from the enabled H14 Token LoRA node')
    if not isinstance(after_sampling,dict) or 'samples' not in after_sampling:
        raise ValueError('Connect the actual downstream sampler LATENT to order the audit')
    report = state.report()
    if not report['actual_scoped_block_calls'] and not report['delegated_without_scope']:
        raise ValueError('No actual scoped or delegated block invocation was observed')
    if state.handles_active or state.errors:
        raise ValueError('Token LoRA invocation did not cleanly finish')
    return after_sampling,json.dumps(report,ensure_ascii=False,indent=2,allow_nan=False)
