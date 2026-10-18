"""Promote only the two actually accepted H14 sources; no sampling or rewiring."""
import argparse
import copy
import hashlib
import json
from pathlib import Path
import shutil
import uuid

from save_h11_reviewed_workflows import PRIVATE, read, set_widget, strings, write_new
from save_h13_reviewed_workflows import exact_projection, sha

REVIEW_ID = '9721e9121a0786a7aeabf698e93b2fa5cc5a363c6d95eff676b188bc5510a203'
CASES = {'Ordinary': 'A1', 'AudioScope': 'A2'}
MEDIA = {'A1': 'a1743ddce6535caa180bc9c243702f135cef5712c949c418aa81513ad4bfe619',
         'A2': 'a76472674b90934bc0a3ef9529a071417bcb45cb0cc49c522852724763dfa84c'}


def validate_feedback(feedback):
    if (feedback.get('schema') != 't8.v188.human-review.v1'
            or feedback.get('review_id') != REVIEW_ID or feedback.get('revision') != 2
            or feedback.get('qa') is not False or feedback.get('automatic_accept') is not False
            or feedback.get('unsaved_case_ids') != []
            or set(feedback.get('answers', {})) != set(CASES.values())
            or set(feedback.get('media', {})) != set(CASES.values())
            or any(row.get('status') != 'pass' for row in feedback['answers'].values())):
        raise ValueError('Require the actual complete H14 human feedback, not QA or automatic acceptance')
    for case, digest in MEDIA.items():
        if (len(feedback['media'][case]) != 1
                or feedback['media'][case][0].get('sha256') != digest):
            raise ValueError('Accepted media identity changed')


def export(evidence_root, feedback_path, destination, evidence):
    root = Path(__file__).resolve().parents[1]
    feedback = read(feedback_path)
    validate_feedback(feedback)
    delivery = read(evidence_root/'human-review-v1/delivery.json')
    seal = read(evidence_root/'source-freeze-v2.json')
    if delivery['review_id'] != REVIEW_ID:
        raise ValueError('Different review delivery')
    groups = {g['id']: g for g in delivery['groups']}
    if set(groups) != set(CASES.values()):
        raise ValueError('Unexpected review cases')
    for case, group in groups.items():
        clip, = group['clips']
        if (feedback['media'][case] != [{'label': clip['label'], 'sha256': MEDIA[case]}]
                or clip['sha256'] != MEDIA[case]
                or sha(evidence_root/'human-review-v1/public'/clip['url']) != MEDIA[case]):
            raise ValueError('Actual reviewed clip or label changed')
    if (evidence.exists() or (destination.exists() and
            (not destination.is_dir() or {p.name for p in destination.iterdir()} != {'README.md'}))):
        raise FileExistsError('Fresh targets only; never overwrite saved source files')
    for path, digest in seal['source_sha256'].items():
        if sha(root/path) != digest:
            raise ValueError('Frozen pre-acceptance source changed: '+path)
    planned = []
    for name, case in CASES.items():
        saved = evidence_root/(name.lower()+'-saved-ui-v1')
        source = saved/'canvas.json'
        receipt = read(saved/'receipt.json')
        actual = evidence_root/(name.lower()+'-actual-v1')
        history_path, audit_path = actual/'history.json', actual/'audit.json'
        history, audit = read(history_path), read(audit_path)
        if (sha(source) != receipt['source_sha256'] or not receipt['semantic_projection_exact']
                or not history['status']['completed'] or history['status']['status_str'] != 'success'
                or audit['media']['sha256'] != MEDIA[case] or sha(Path(audit['media']['path'])) != MEDIA[case]
                or not audit['actual_UI_graph_exact']):
            raise ValueError('Source graph, completed history or actual media changed')
        graph = read(source)
        api = exact_projection(graph, history['prompt'][2])
        child = copy.deepcopy(graph)
        notes = [n for n in child['nodes'] if n['type'] in ('Note', 'MarkdownNote')]
        if len(notes) != 1 or set(notes[0].get('widgets_values_named', {})) != {'text'}:
            raise ValueError('Unexpected source NOTE contract')
        note = ('# H14 · '+name+' · 人工审核通过的来源工作流\n\n'
            '2026-10-15实际人审r2通过；普通权重LoRA／generated_audio直接残差两臂，同Wuli8与既有五视角LoRA0.8。'
            '864×480，原生124帧明确裁120帧/24fps/5秒；对白：你好，今天天气不错。'
            '原seed904512、8步Euler/simple、shift12:3、提示词、所有资源、裁片和每条接线保持，未重采。'
            '五视角LoRA不是声音LoRA；只认证这两段指定音画，不承诺音色改变、另一模态完全不变或提速。'
            'generated_video和大型fc2权重不继承本次成片质量资格；不支持目标整文件明确报错，旧loader保留。'
            'LOW/HIGH、EAV、Prompt Relay仍外置，本图不强加二采，不迁移旧图。'
            '仅本说明及展示来源标记改变。详见本目录README和docs/H14_TOKEN_SCOPE.md。'
            '感谢baslack/Scriptorium、ComfyUI、Wuli-art/sandpies及权重原作者；模型不随仓库分发。')
        set_widget(notes[0], 'text', note)
        child['id'] = str(uuid.uuid5(uuid.NAMESPACE_URL, 't8:h14:'+name+':reviewed:r2'))
        child['revision'] = 0
        child.setdefault('extra', {})['workflow_title'] = 'H14 '+name+' · reviewed source'
        child['extra']['h14_reviewed_source'] = {
            'review_id': REVIEW_ID, 'revision': 2, 'case': case,
            'original_saved_sha256': sha(source), 'execution_history_sha256': sha(history_path),
            'accepted_media_sha256': [MEDIA[case]], 'resource_adaptations': {},
            'resampled_during_export': False, 'automatic_adoption': False,
            'scope': 'specified_two_5second_clips_NOT_universal_modality_isolation_or_speedup'}
        if any(PRIVATE.search(v) or v.startswith('\\\\') for v in strings(child)):
            raise ValueError('Private path in portable graph; no broad redaction')
        if exact_projection(child, api) != api or child['links'] != graph['links']:
            raise ValueError('Execution parameters or wiring must not change')
        planned.append((name, case, source, history_path, child, api))
    destination.mkdir(parents=True, exist_ok=True)
    evidence.mkdir(parents=True)
    shutil.copy2(feedback_path, evidence/'actual-human-feedback.json')
    records = []
    for name, case, source, history_path, graph, api in planned:
        target = destination/('H14_'+name+'.json')
        write_new(target, graph)
        shutil.copy2(source, evidence/(name+'_Original.json'))
        records.append({'relative_path': target.relative_to(root).as_posix(), 'case': case,
            'source_sha256': sha(source), 'history_sha256': sha(history_path),
            'template_sha256': sha(target), 'accepted_media_sha256': [MEDIA[case]],
            'links_sha256': hashlib.sha256(json.dumps(graph['links'], sort_keys=True).encode()).hexdigest(),
            'execution_nodes': len(api), 'execution_api': api,
            'all_execution_parameters_and_edges_exact': True})
    runtime = ['__init__.py', 'h3_t8/token_lora.py', 'h3_t8/nodes_token_lora.py',
        'tests/test_token_lora.py', 'tools/prepare_h14_workflows.py', 'pyproject.toml']
    result = {'schema': 't8.h14.reviewed-export.v1', 'review_id': REVIEW_ID, 'revision': 2,
        'feedback_sha256': sha(feedback_path), 'automatic_accept': False, 'records': records,
        'saved_templates': 2, 'human_passes': 2, 'new_GPU_runs_during_export': 0,
        'old_workflow_changes': 0, 'runtime_source_sha256': {p: sha(root/p) for p in runtime},
        'published': False}
    write_new(evidence/'audit.json', result)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for flag in ('evidence-root', 'feedback', 'destination', 'evidence'):
        parser.add_argument('--'+flag, type=Path, required=True)
    args = parser.parse_args()
    receipt = export(args.evidence_root, args.feedback, args.destination.resolve(), args.evidence)
    print(json.dumps({key: receipt[key] for key in ('human_passes', 'saved_templates', 'new_GPU_runs_during_export', 'published')}))


if __name__ == '__main__':
    main()
