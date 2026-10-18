"""Create two private H14 canvas drafts; never POST /prompt or replace old graphs."""
import argparse
import json
from pathlib import Path
import urllib.request
import uuid

from api_to_frontend_workflow import convert
from frontend_workflow_compat import normalize_native_widget_inputs
from prepare_h11_spark_workflows import node
from prepare_h11_wuli_workflows import canonical_graph
from prepare_h13_workflows import base


def graph(scoped):
    value = base('wuli_h3_turbo_8step_v1_comfyui_int8_convrot.safetensors')
    common = dict(model=['7', 0], lora_name='minimax_h3_five_view_512_s1500.safetensors')
    value['19'] = (node('MiniMaxH3TokenLoRAApplyEXPT8', **common, strength=.8,
                        row_policy='generated_audio', owner_policy='require_scope') if scoped else
                   node('MiniMaxH3LoRACompatibilityLoaderT8Advanced', **common, strength_model=.8))
    value['8']['inputs']['model'] = ['19', 0]
    # Complete sampler output, not a mid-trajectory preview.
    decoded = ['11', 1]
    if scoped:
        value['20'] = node('MiniMaxH3TokenLoRAAuditEXPT8', model=['19', 0], after_sampling=decoded)
        decoded = ['20', 0]
    for identifier in ('12', '13'):
        value[identifier]['inputs']['samples'] = decoded
    value['16']['inputs']['filename_prefix'] = 'H14/' + ('AudioScope' if scoped else 'Ordinary')
    return canonical_graph(value)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--server', required=True)
    parser.add_argument('--destination', required=True, type=Path)
    args = parser.parse_args()
    if args.destination.exists():
        raise FileExistsError('New draft directory required')
    with urllib.request.urlopen(args.server.rstrip('/')+'/object_info', timeout=30) as response:
        info = json.loads(response.read())
    drafts = []
    for name, scoped in (('Ordinary', False), ('AudioScope', True)):
        api = graph(scoped)
        if {n['class_type'] for n in api.values()} - info.keys():
            raise ValueError('Actual backend lacks required nodes')
        # Fail before writing if an API input/resource is not really declared.
        for entry in api.values():
            schema = info[entry['class_type']]['input']
            declared = {**schema.get('required', {}), **schema.get('optional', {})}
            for key, val in entry['inputs'].items():
                if key not in declared:
                    raise ValueError('Undeclared input '+entry['class_type']+'.'+key)
                typ = declared[key][0]
                if isinstance(typ, list) and not isinstance(val, list) and val not in typ:
                    raise ValueError('Resource/option absent: '+repr(val))
        canvas = convert(api, info, 'H14 '+name+' · DRAFT · 5s')
        normalize_native_widget_inputs(canvas)
        canvas['id'] = str(uuid.uuid5(uuid.NAMESPACE_URL, 't8:h14:'+name+':v1'))
        last = canvas['last_node_id']+1
        canvas['nodes'].append(dict(id=last, type='MarkdownNote', pos=[0, -380], size=[950, 310],
            flags={}, order=last, mode=0, inputs=[], outputs=[], properties={}, widgets_values=[
                '# H14 '+name+' · 实际Run／人审待完成\n\n'
                '同Wuli8／五视角LoRA0.8／seed904512／simple8／Euler／shift12:3。'
                '864×480≈0.4MP，124原生帧→120帧/24fps/5秒，声音明确裁0..5秒。'
                '正常对白：你好，今天天气不错。只有LoRA普通权重patch与generated_audio直接残差作用域不同。'
                '五视角LoRA不是声音LoRA，本测试不承诺音色改变、另一模态最终不变或提速。'
                '保存→关图→重开→API语义核对，再从真实画布Run；不是API-only。'
                'scope Audit应有真实调用、非零残差和0遗留hook；机器通过不等于人审。'
                '旧图和默认不改；EAV／Relay仍外置，本图不为展示硬加二采。'
                '感谢baslack/scripts_nodes PR2、ComfyUI、Wuli-art/sandpies和五视角LoRA原作者。']))
        canvas['last_node_id'] = last
        drafts.append((name, api, canvas))
    args.destination.mkdir(parents=True)
    for name, api, canvas in drafts:
        for suffix, data in (('api', api), ('canvas', canvas)):
            with (args.destination / ('H14_'+name+'_'+suffix+'.json')).open('x', encoding='utf8') as stream:
                json.dump(data, stream, ensure_ascii=False, indent=2)
    print(json.dumps(dict(canvases=2, API_prompt_posted=False, actual_UI_run=False, human_accepted=False)))


if __name__ == '__main__':
    main()
