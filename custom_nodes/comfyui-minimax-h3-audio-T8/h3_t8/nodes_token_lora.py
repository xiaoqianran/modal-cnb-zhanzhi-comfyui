"""Append-only MODEL helpers; existing loaders, samplers and effects stay external."""
import json

import folder_paths
from comfy_api.latest import io

from . import token_lora

CATEGORY = 'T8/MiniMax H3/LoRA Token Scope Experimental'


class MiniMaxH3TokenLoRAApplyEXPT8(io.ComfyNode):
    @classmethod
    def define_schema(cls):
        return io.Schema(node_id=cls.__name__,display_name='H3 LoRA · 生成音频/视频行作用域',
            category=CATEGORY,is_experimental=True,
            description='MODEL独立外置。仅支持完整plain LoRA的实际token层；generated模式不直接修改text/条件/参考行，'
                        '但共享attention仍可能影响另一模态。fc2保留原生融合并在MLP输出补残差。'
                        '不支持目标明确报错，不静默加载半份；未知owner保留并报告未生效。旧loader不改。',
            inputs=[io.Model.Input('model'),
                    io.Combo.Input('lora_name',options=['disabled',*[v for v in folder_paths.get_filename_list('loras') if v != 'disabled']]),
                    io.Float.Input('strength',default=1.,min=-10.,max=10.,step=.01),
                    io.Combo.Input('row_policy',options=list(token_lora.POLICIES),default='generated_audio'),
                    io.Combo.Input('owner_policy',options=['delegate_without_scope','require_scope'],
                                   default='delegate_without_scope')],
            outputs=[io.Model.Output('model'),io.String.Output('report_json')])

    @classmethod
    def execute(cls,model,lora_name,strength=1.,row_policy='generated_audio',owner_policy='delegate_without_scope'):
        path = None if lora_name == 'disabled' or strength == 0 else folder_paths.get_full_path_or_raise('loras',lora_name)
        patched,_,report = token_lora.prepare(model,path,strength,row_policy,owner_policy)
        return io.NodeOutput(patched,json.dumps(report,ensure_ascii=False,indent=2,allow_nan=False))

    @classmethod
    def fingerprint_inputs(cls,lora_name='disabled',strength=1.,**kwargs):
        if lora_name == 'disabled' or strength == 0:
            return ('disabled',)
        return token_lora._sha(folder_paths.get_full_path_or_raise('loras',lora_name))


class MiniMaxH3TokenLoRAAuditEXPT8(io.ComfyNode):
    @classmethod
    def define_schema(cls):
        return io.Schema(node_id=cls.__name__,display_name='H3 LoRA · 实际行作用域审计（采样后）',
            category=CATEGORY,is_experimental=True,is_output_node=True,
            description='MODEL接上游作用域节点，after_sampling接实际采样LATENT保证顺序。'
                        '报告实际层调用、委托和清理，原样返回LATENT；不是全轨迹完成证明或画质/声纹认证。',
            inputs=[io.Model.Input('model'),io.Latent.Input('after_sampling')],
            outputs=[io.Latent.Output('samples'),io.String.Output('report_json')])

    @classmethod
    def execute(cls,model,after_sampling):
        samples,report = token_lora.audit(model,after_sampling)
        return io.NodeOutput(samples,report,ui={'text':[report]})

    @classmethod
    def fingerprint_inputs(cls,**kwargs):
        return float('nan')


NODES = [MiniMaxH3TokenLoRAApplyEXPT8,MiniMaxH3TokenLoRAAuditEXPT8]
