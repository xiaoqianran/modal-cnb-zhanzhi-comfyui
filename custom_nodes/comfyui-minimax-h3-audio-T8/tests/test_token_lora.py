"""Actual native tiny H3 blocks; no diffusion/model file/GPU sampling."""
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from types import SimpleNamespace

import comfy.ops
import comfy.supported_models
from comfy.ldm.minimax.model import DiTBlock, PackedLayout
from comfy.weight_adapter import LoRAAdapter
import pytest
import torch

from h3_audio_t8_pkg import token_lora as scope
from test_prompt_relay_core_compat import model_fixture


def model():
    value = model_fixture()
    value.model.model_config = comfy.supported_models.MiniMaxH3({})
    value.model.diffusion_model.blocks = torch.nn.ModuleList([DiTBlock(24,3,8,32,24,1e-6,1e-6,
        dtype=torch.float32,device='cpu',operations=comfy.ops.disable_weight_init)])
    generator = torch.Generator().manual_seed(417)
    with torch.no_grad():
        for parameter in value.model.parameters():
            parameter.copy_(torch.randn(parameter.shape,generator=generator)*.1)
        block = value.model.diffusion_model.blocks[0]
        block.attn.q_norm.weight.fill_(1.)
        block.attn.k_norm.weight.fill_(1.)
    return value


def fixture_args():
    # Includes all reference/condition kinds, not just generated rows.
    layout = PackedLayout(3,1,2,2,3,
        keyframes=[{'resolved_frame_index':0,'latent':torch.zeros(1,24,1,2,2),
                    'audio_latent':torch.zeros(1,32,2,1)}],
        refs=[{'kind':'image','latent_h':2,'latent_w':2},
              {'kind':'audio','ref_audio_t':1}])
    generator = torch.Generator().manual_seed(418)
    return {'img':torch.randn(layout.seq_len,24,generator=generator),
            'layout':layout,'t_emb':torch.randn(3,24,generator=generator),
            'mod_segments':[(0,layout.seq_len,0)],'rope_freqs':None,'transformer_options':{}}


def native(block,args):
    return {'img':block(args['img'],args['t_emb'],args['mod_segments'],args['rope_freqs'],
                         transformer_options=args['transformer_options'])}


def deltas(block,paths=('attn.qkv_proj','attn.out_proj','mlp.fc1','mlp.fc2')):
    generator = torch.Generator().manual_seed(419)
    result = {}
    for path in paths:
        module = block.get_submodule(path)
        target = 'diffusion_model.blocks.0.'+path+'.weight'
        result[target] = [scope.Delta(target,torch.randn(module.out_features,2,generator=generator)*.02,
                                      torch.randn(2,module.in_features,generator=generator)*.02,.7)]
    return result


def state(block,policy='generated_audio',paths=('attn.qkv_proj','attn.out_proj','mlp.fc1','mlp.fc2')):
    return scope.TokenLoRAState(policy,[{'sha256':'fixture'}],deltas(block,paths))


def assert_clean(block,s):
    assert s.handles_active == 0
    assert scope._ACTIVE.get() is None
    assert all(not item._forward_hooks for item in block.modules())


def test_all_rows_matches_native_plain_weight_math_and_fc2_fused_boundary(monkeypatch):
    value = model()
    block = value.model.diffusion_model.blocks[0]
    original = deepcopy(block)
    s = state(block,'all_eligible_rows')
    merged = deepcopy(block)
    with torch.no_grad():
        for target,values in s.deltas.items():
            path = target.split('blocks.0.')[1].removesuffix('.weight')
            for d in values:
                merged.get_submodule(path).weight.add_((d.up@d.down)*d.scale)
    # Reproduce Core's native fused branch: no fc2.module.forward invocation.
    fused_calls = []
    def fused(linear,x,activation,*args,**kwargs):
        fused_calls.append(linear)
        return torch.nn.functional.linear(comfy.ops._eager_input_act(x,activation),linear.weight,linear.bias)
    monkeypatch.setattr(comfy.ops,'linear_input_act',fused)
    block.mlp.fc2.forward = lambda *_: (_ for _ in ()).throw(AssertionError('fc2.forward must stay bypassed'))
    args = fixture_args()
    with torch.inference_mode():
        actual = scope.TokenBlock(s,block,0)(deepcopy(args),{'original_block':lambda a:native(block,a)})['img']
        expected = native(merged,deepcopy(args))['img']
    torch.testing.assert_close(actual,expected,atol=2e-6,rtol=2e-6)
    assert len(fused_calls) == 2 and s.report()['scope_effective']
    assert len(s.targets_seen) == 4
    assert all(torch.equal(p,q) for p,q in zip(block.parameters(),original.parameters()))
    assert_clean(block,s)


def test_generated_rows_leave_reference_rows_directly_unchanged_and_layout_errors():
    block = model().model.diffusion_model.blocks[0]
    s = state(block,paths=('mlp.fc2',))
    args = fixture_args()
    before = args['img'].clone()
    with torch.inference_mode():
        baseline = native(block,deepcopy(args))['img']
        actual = scope.TokenBlock(s,block,0)(deepcopy(args),{'original_block':lambda a:native(block,a)})['img']
    selected,counts = scope.spans(args['layout'],before.shape[0],'generated_audio')
    a,b = selected[0]
    assert torch.equal(actual[:a],baseline[:a]) and torch.equal(actual[b:],baseline[b:])
    assert not torch.equal(actual[a:b],baseline[a:b])
    assert counts['ref_audio'] and counts['cond_audio'] and counts['ref_img'] and counts['cond']
    assert torch.equal(args['img'],before)
    bad = deepcopy(args['layout'])
    bad.segments[0] = (0,2,'alien')
    with pytest.raises(ValueError,match='Unknown'):
        scope.spans(bad,bad.seq_len,'generated_audio')
    with pytest.raises(ValueError,match='matching'):
        scope.spans(args['layout'],before.shape[0]+1,'generated_audio')
    assert_clean(block,s)


def test_partial_registration_failure_execution_failure_and_same_module_second_task(monkeypatch):
    block = model().model.diffusion_model.blocks[0]
    s = state(block)
    args = fixture_args()
    with torch.inference_mode():
        expected = native(block,deepcopy(args))['img']
    with monkeypatch.context() as patch:
        patch.setattr(block.mlp,'register_forward_hook',lambda *_: (_ for _ in ()).throw(RuntimeError('register4')))
        with pytest.raises(RuntimeError,match='register4'):
            scope.TokenBlock(s,block,0)(deepcopy(args),{'original_block':lambda a:native(block,a)})
    assert_clean(block,s)
    s.pre_run()
    with pytest.raises(RuntimeError,match='interrupted'):
        scope.TokenBlock(s,block,0)(deepcopy(args),{'original_block':lambda _: (_ for _ in ()).throw(RuntimeError('interrupted'))})
    assert_clean(block,s)
    s.pre_run()
    with torch.inference_mode():
        second = native(block,deepcopy(args))['img']
    assert torch.equal(second,expected)
    assert s.run == 2 and not s.errors
    s.cleanup()


def test_concurrent_unscoped_call_is_not_contaminated_and_owner_delegates():
    block = model().model.diffusion_model.blocks[0]
    s = state(block)
    args = fixture_args()
    with torch.inference_mode():
        expected = native(block,deepcopy(args))['img']
    def call(a):
        # The same module has hooks installed, but a separate thread has no
        # invocation ContextVar and therefore receives no scoped residuals.
        def unrelated():
            with torch.inference_mode():
                return native(block,deepcopy(args))['img']
        with ThreadPoolExecutor(1) as executor:
            observed = executor.submit(unrelated).result(timeout=10)
        assert torch.equal(observed,expected)
        return native(block,a)
    with torch.inference_mode():
        scope.TokenBlock(s,block,0)(deepcopy(args),{'original_block':call})
    assert_clean(block,s)
    called = []
    def previous(a,e):
        called.append('owner')
        return e['original_block'](a)
    delegate = state(block)
    with torch.inference_mode():
        result = scope.TokenBlock(delegate,block,0,previous)(deepcopy(args),{'original_block':lambda a:native(block,a)})
    assert called == ['owner'] and torch.equal(result['img'],expected)
    assert not delegate.report()['scope_effective'] and delegate.report()['delegated_without_scope'] == 1
    delegate.owner_policy = 'require_scope'
    with pytest.raises(ValueError,match='retained'):
        scope.TokenBlock(delegate,block,0,previous)(deepcopy(args),{'original_block':lambda a:native(block,a)})


def save_adapter(path,block,*,bad=False):
    values = {}
    for target,entries in deltas(block).items():
        d = entries[0]
        stem = target.removesuffix('.weight')
        values[stem+'.lora_up.weight'] = d.up
        values[stem+'.lora_down.weight'] = d.down
    if bad:
        values['diffusion_model.blocks.0.adaln_proj.linear.lora_up.weight'] = torch.zeros(432,2)
        values['diffusion_model.blocks.0.adaln_proj.linear.lora_down.weight'] = torch.zeros(2,24)
    comfy.utils.save_torch_file(values,str(path))


def test_real_parser_full_coverage_disabled_duplicate_and_composition(tmp_path):
    value = model()
    block = value.model.diffusion_model.blocks[0]
    path = tmp_path/'plain.safetensors'
    save_adapter(path,block)
    same,s,report = scope.prepare(value,tmp_path/'not-opened',0.)
    assert same is value and s is None and not report['file_opened']
    patched,s,report = scope.prepare(value,path,.8)
    assert patched is not value and len(s.deltas) == 4 and not value.model_options['transformer_options'].get('patches_replace')
    assert report['sources'][0]['mapping']['converted_unmapped_tensor_count'] == 0
    with pytest.raises(ValueError,match='already scoped'):
        scope.prepare(patched,path,.8)
    other = tmp_path/'unsupported.safetensors'
    save_adapter(other,block,bad=True)
    with pytest.raises(ValueError,match='not partially'):
        scope.prepare(value,other,.8)
    # Another file with different actual matrices composes, not nested hooks.
    raw = comfy.utils.load_torch_file(str(path),safe_load=True)
    raw[next(iter(raw))] = raw[next(iter(raw))]+.01
    second = tmp_path/'second.safetensors'
    comfy.utils.save_torch_file(raw,str(second))
    composed,s2,_ = scope.prepare(patched,second,.3)
    assert len(s2.sources) == 2 and all(len(v) == 2 for v in s2.deltas.values())
    node = composed.model_options['transformer_options']['patches_replace']['dit'][('double_block',0)]
    assert node.previous is None
    args = fixture_args()
    with torch.inference_mode():
        result = node(deepcopy(args),{'original_block':lambda a:native(block,a)})
    assert s2.report()['scope_effective'] and not s.report()['scope_effective']
    observed,text = scope.audit(composed,{'samples':result['img']})
    assert observed['samples'] is result['img'] and 'scope_effective' in text
    before = s2.signatures.copy()
    s2.deltas[next(iter(s2.deltas))][0].up[0,0] += .01
    with pytest.raises(ValueError,match='content changed'):
        s2.pre_run()
    assert s2.signatures == before
    assert_clean(block,s2)


def test_nonplain_nonfinite_and_mutated_layout_are_rejected():
    block = model().model.diffusion_model.blocks[0]
    target = 'diffusion_model.blocks.0.mlp.fc2.weight'
    module = block.mlp.fc2
    up,down = torch.zeros(24,2),torch.zeros(2,32)
    with pytest.raises(ValueError,match='plain'):
        scope._plain_delta(target,SimpleNamespace(weights=(up,down,None,None,None,None)),module,1.)
    with pytest.raises(ValueError,match='DoRA'):
        scope._plain_delta(target,LoRAAdapter(set(),(up,down,None,None,torch.ones(24),None)),module,1.)
    up[0,0] = float('nan')
    with pytest.raises(ValueError,match='finite'):
        scope._plain_delta(target,LoRAAdapter(set(),(up,down,None,None,None,None)),module,1.)
    layout = fixture_args()['layout']
    layout.segments[1] = (1,2,'cond')
    with pytest.raises(ValueError,match='overlapping'):
        scope.spans(layout,layout.seq_len,'generated_audio')
    assert not torch.cuda.is_initialized()


def test_new_node_content_fingerprint_and_later_duplicate_are_not_timestamp_caches(tmp_path,monkeypatch):
    from h3_audio_t8_pkg.nodes_token_lora import MiniMaxH3TokenLoRAApplyEXPT8 as Node
    value = model()
    block = value.model.diffusion_model.blocks[0]
    path = tmp_path/'same-path.safetensors'
    save_adapter(path,block)
    import folder_paths
    monkeypatch.setattr(folder_paths,'get_full_path_or_raise',lambda *_:str(path))
    first = Node.fingerprint_inputs(lora_name='same-path.safetensors')
    stamp = path.stat()
    raw = comfy.utils.load_torch_file(str(path),safe_load=True)
    raw[next(iter(raw))] = raw[next(iter(raw))]+.01
    comfy.utils.save_torch_file(raw,str(path))
    import os
    os.utime(path,ns=(stamp.st_atime_ns,stamp.st_mtime_ns))
    assert path.stat().st_size == stamp.st_size
    assert Node.fingerprint_inputs(lora_name='same-path.safetensors') != first
    assert Node.fingerprint_inputs(lora_name='disabled') == ('disabled',)
    patched,s,_ = scope.prepare(value,path,.8)
    original_raw = comfy.utils.load_torch_file(str(path),safe_load=True)
    key_map,_ = scope.build_minimax_h3_lora_key_map(value.model)
    native_patches = comfy.lora.load_lora(original_raw,key_map,log_missing=False)
    later = patched.clone()
    later.add_patches(native_patches,.8)
    with pytest.raises(ValueError,match='later ordinary'):
        s.pre_run(later)
    ordinary = value.clone()
    ordinary.add_patches(native_patches,.8)
    with pytest.raises(ValueError,match='already applied'):
        scope.prepare(ordinary,path,.8)


def test_scoped_model_opaque_identity_cannot_mint_a_portable_cross_task_cache(tmp_path):
    from h3_audio_t8_pkg.long_video_dual_identity import stage_model_identity
    value = model()
    path = tmp_path/'identity.safetensors'
    save_adapter(path,value.model.diffusion_model.blocks[0])
    patched,_,_ = scope.prepare(value,path,.8)
    identity = stage_model_identity(patched)
    assert identity.get('portable_cache_reuse') is False
