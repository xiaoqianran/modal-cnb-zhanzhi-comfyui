"""One stdlib export contract, without repeating sampling/CPU qualification."""
import copy
import hashlib
import json
from pathlib import Path
import re
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
from save_h13_reviewed_workflows import CASES, MEDIA, REVIEW_ID, exact_projection  # noqa: E402


def read(path):
    return json.loads((ROOT / path).read_text(encoding='utf8'))


def sha(path):
    return hashlib.sha256((ROOT / path).read_bytes()).hexdigest()


class ReviewedH13Export(unittest.TestCase):
    def test_exact_accepted_sources_and_execution_contract(self):
        ledger = read('tests/fixtures/h13_reviewed_export.json')
        self.assertEqual(ledger['review_id'], REVIEW_ID)
        self.assertEqual(ledger['revision'], 2)
        self.assertFalse(ledger['automatic_accept'])
        self.assertFalse(ledger['published'])
        self.assertEqual(len(ledger['records']), 2)
        self.assertEqual({r['case'] for r in ledger['records']}, set(CASES.values()))
        for record in ledger['records']:
            self.assertEqual(sha(record['relative_path']), record['template_sha256'])
            graph = read(record['relative_path'])
            provenance = graph['extra']['h13_reviewed_source']
            self.assertEqual(provenance['review_id'], REVIEW_ID)
            self.assertEqual(provenance['revision'], 2)
            self.assertEqual(provenance['original_saved_sha256'], record['source_sha256'])
            self.assertEqual(provenance['execution_history_sha256'], record['history_sha256'])
            self.assertEqual(provenance['accepted_media_sha256'], [MEDIA[record['case']]])
            self.assertFalse(provenance['resampled_during_export'])
            self.assertFalse(provenance['automatic_adoption'])
            self.assertEqual(provenance['resource_adaptations'], {})
            self.assertIsNone(re.search(r'[A-Za-z]:[\\/]|127\.0\.0\.1|localhost', json.dumps(graph)))
            links_sha = hashlib.sha256(json.dumps(graph['links'], sort_keys=True).encode()).hexdigest()
            self.assertEqual(links_sha, record['links_sha256'])
            api = record['execution_api']
            self.assertEqual(len(exact_projection(graph, api)), record['execution_nodes'])
            # The known display alias is narrow, not arbitrary widget coercion.
            corrupted = copy.deepcopy(graph)
            scheduler = next(n for n in corrupted['nodes'] if n['type'] == 'BasicScheduler')
            values = scheduler['widgets_values_named']
            scheduler['widgets_values'][list(values).index('steps')] = 7
            values['steps'] = 7
            with self.assertRaises(ValueError):
                exact_projection(corrupted, api)
        h14 = read('tests/fixtures/h14_registration_append.json')
        self.assertEqual(set(h14['prior_runtime_source_sha256']), {'__init__.py', 'pyproject.toml'})
        self.assertEqual(h14['preserved_registered_prefix'], 735)
        for path, digest in ledger['runtime_source_sha256'].items():
            if path in h14['prior_runtime_source_sha256']:
                self.assertEqual(h14['prior_runtime_source_sha256'][path], digest, path)
                digest = h14['runtime_source_sha256'][path]
            self.assertEqual(sha(path), digest, path)
        self.assertEqual(read('features.json')['nodes'][735:], h14['new_nodes'])
        self.assertEqual(read('meta.json')['h13_audio_first_hybrid_local'],
                         read('features.json')['h13_audio_first_hybrid_local'])
        info = read('meta.json')['h13_audio_first_hybrid_local']
        self.assertTrue(info['human_quality_accepted'])
        if info['published']:
            self.assertEqual(info['github_release_version'], '1.100.0')
            self.assertGreaterEqual(tuple(map(int, read('meta.json')['version'].split('.'))), (1, 100, 0))
        self.assertFalse(info['single_first_frame_full_video_quality_qualified'])
        self.assertEqual(info['human_feedback_revision'], 2)
        self.assertEqual(set(info['saved_workflows']), {r['relative_path'] for r in ledger['records']})
        self.assertEqual((ledger['new_GPU_runs_during_export'], ledger['old_workflow_changes']), (0, 0))


if __name__ == '__main__':
    unittest.main()
