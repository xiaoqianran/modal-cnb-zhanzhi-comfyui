"""Two lightweight export/acceptance contracts, no replay of inference tests."""
import copy
import hashlib
import json
from pathlib import Path
import re
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'tools'))
from save_h14_reviewed_workflows import CASES, MEDIA, REVIEW_ID, exact_projection, validate_feedback  # noqa: E402


def read(path):
    return json.loads((ROOT/path).read_text(encoding='utf8'))


def sha(path):
    return hashlib.sha256((ROOT/path).read_bytes()).hexdigest()


class ReviewedH14Export(unittest.TestCase):
    def test_accepted_graphs_exact_to_actual_execution_and_runtime(self):
        ledger = read('tests/fixtures/h14_reviewed_export.json')
        self.assertEqual(ledger['review_id'], REVIEW_ID)
        self.assertEqual(ledger['revision'], 2)
        self.assertFalse(ledger['automatic_accept'])
        self.assertFalse(ledger['published'])
        self.assertEqual({r['case'] for r in ledger['records']}, set(CASES.values()))
        self.assertEqual(len(ledger['records']), 2)
        for record in ledger['records']:
            self.assertEqual(sha(record['relative_path']), record['template_sha256'])
            graph = read(record['relative_path'])
            bound = graph['extra']['h14_reviewed_source']
            self.assertEqual(bound['review_id'], REVIEW_ID)
            self.assertEqual(bound['original_saved_sha256'], record['source_sha256'])
            self.assertEqual(bound['execution_history_sha256'], record['history_sha256'])
            self.assertEqual(bound['accepted_media_sha256'], [MEDIA[record['case']]])
            self.assertEqual(bound['resource_adaptations'], {})
            self.assertFalse(bound['resampled_during_export'])
            self.assertFalse(bound['automatic_adoption'])
            self.assertIsNone(re.search(r'[A-Za-z]:[\\/]|127\.0\.0\.1|localhost', json.dumps(graph)))
            self.assertEqual(hashlib.sha256(json.dumps(graph['links'], sort_keys=True).encode()).hexdigest(),
                             record['links_sha256'])
            self.assertEqual(len(exact_projection(graph, record['execution_api'])), record['execution_nodes'])
            changed = copy.deepcopy(graph)
            scheduler = next(n for n in changed['nodes'] if n['type'] == 'BasicScheduler')
            scheduler['widgets_values'][list(scheduler['widgets_values_named']).index('steps')] = 7
            scheduler['widgets_values_named']['steps'] = 7
            with self.assertRaises(ValueError):
                exact_projection(changed, record['execution_api'])
        for path, digest in ledger['runtime_source_sha256'].items():
            self.assertEqual(sha(path), digest, path)
        info = read('meta.json')['h14_token_scope_local']
        self.assertEqual(info, read('features.json')['h14_token_scope_local'])
        self.assertTrue(info['human_quality_accepted'])
        if info['published']:
            self.assertEqual(info['github_release_version'], '1.101.0')
            self.assertGreaterEqual(tuple(map(int, read('meta.json')['version'].split('.'))), (1, 101, 0))
        self.assertFalse(info['generated_video_GPU_quality_qualified'])
        self.assertFalse(info['fc2_large_model_GPU_asset_qualified'])
        self.assertFalse(info['fair_speedup_qualified'])
        self.assertEqual(info['human_feedback_sha256'], ledger['feedback_sha256'])
        self.assertEqual(set(info['saved_workflows']), {r['relative_path'] for r in ledger['records']})
        self.assertEqual((ledger['new_GPU_runs_during_export'], ledger['old_workflow_changes']), (0, 0))

    def test_feedback_gate_rejects_QA_automatic_unsaved_or_other_media(self):
        value = {'schema': 't8.v188.human-review.v1', 'review_id': REVIEW_ID, 'revision': 2,
            'qa': False, 'automatic_accept': False, 'unsaved_case_ids': [],
            'answers': {k: {'status': 'pass'} for k in MEDIA},
            'media': {k: [{'sha256': v}] for k, v in MEDIA.items()}}
        validate_feedback(value)
        for key, bad in (('qa', True), ('automatic_accept', True), ('review_id', 'other'),
                         ('unsaved_case_ids', ['A2'])):
            changed = {**value, key: bad}
            with self.assertRaises(ValueError):
                validate_feedback(changed)
        changed = copy.deepcopy(value)
        changed['media']['A2'][0]['sha256'] = '0'*64
        with self.assertRaises(ValueError):
            validate_feedback(changed)


if __name__ == '__main__':
    unittest.main()
