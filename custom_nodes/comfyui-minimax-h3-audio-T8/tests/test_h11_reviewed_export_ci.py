"""One stdlib-only release check; no replay of CPU/GPU qualification tests."""
import hashlib
import json
from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[1]


def read(path):
    return json.loads((ROOT/path).read_text(encoding='utf8'))


def sha(path):
    return hashlib.sha256((ROOT/path).read_bytes()).hexdigest()


class ReviewedH11Export(unittest.TestCase):
    def test_reviewed_sources_export_and_previous_defaults_remain_bound(self):
        ledger = read('tests/fixtures/h11_reviewed_export_1_99.json')
        self.assertEqual(ledger['revision'], 7)
        self.assertFalse(ledger['automatic_accept'])
        self.assertEqual(len(ledger['records']), 8)
        self.assertEqual({r['case'] for r in ledger['records']}, {'A1','A2','A3','A4','B1','B2','B3'})
        for record in ledger['records']:
            self.assertEqual(sha(record['relative_path']), record['template_sha256'])
            graph = read(record['relative_path'])
            self.assertEqual(hashlib.sha256(json.dumps(graph['links'], sort_keys=True).encode()).hexdigest(),
                             record['links_sha256'])
            self.assertEqual(sum(n['type'] not in ('Note','MarkdownNote') for n in graph['nodes']),
                             record['execution_nodes'])
            provenance = graph['extra']['h11_reviewed_source']
            self.assertEqual(provenance['review_id'], ledger['review_id'])
            self.assertEqual(provenance['original_saved_sha256'], record['source_sha256'])
            self.assertEqual(provenance['accepted_media_sha256'], record['accepted_media_sha256'])
            self.assertFalse(provenance['resource_adaptations_reexecuted'])
            self.assertFalse(provenance['automatic_adoption'])
            self.assertIsNone(re.search(r'[A-Za-z]:[\\/]|127\.0\.0\.1|localhost', json.dumps(graph)))
        h13 = read('tests/fixtures/h13_reviewed_export.json')
        prior = h13['prior_H11_runtime_sha256_for_explicit_changes']
        self.assertEqual(set(prior), {'__init__.py', 'h3_t8/wuli_native.py'})
        h14 = read('tests/fixtures/h14_registration_append.json')
        self.assertEqual(set(h14['prior_runtime_source_sha256']), {'__init__.py', 'pyproject.toml'})
        for path, digest in ledger['runtime_source_sha256'].items():
            if path in prior:
                self.assertEqual(prior[path], digest, path)
                digest = h13['runtime_source_sha256'][path]
            if path in h14['prior_runtime_source_sha256']:
                self.assertEqual(h14['prior_runtime_source_sha256'][path], digest, path)
                digest = h14['runtime_source_sha256'][path]
            self.assertEqual(sha(path), digest, path)
        for name in ('meta.json','features.json'):
            info = read(name)['h11_native_extensions_local']
            self.assertEqual(info['human_feedback_revision'], 7)
            self.assertTrue(info['human_quality_accepted'])
            self.assertEqual(len(info['new_nodes']), 13)
            self.assertEqual(len(info['saved_workflows']), 8)
            self.assertFalse(info['fair_speedup_qualified'])
        self.assertEqual(read('meta.json')['h11_native_extensions_local'],
                         read('features.json')['h11_native_extensions_local'])
        nodes = read('features.json')['nodes']
        self.assertEqual(len(nodes), len(set(nodes)))
        self.assertEqual(nodes[720:733], read('meta.json')['h11_native_extensions_local']['new_nodes'])
        self.assertEqual(nodes[733:735], read('meta.json')['h13_audio_first_hybrid_local']['new_nodes'])
        self.assertEqual(nodes[735:], h14['new_nodes'])
        historical = read('tests/fixtures/h09_reviewed_sampling_1_98.json')
        self.assertIn('prior_runtime_file_sha256_before_H11_observation', historical)
        self.assertEqual(len(historical['runtime_file_sha256']),
                         len(historical['prior_runtime_file_sha256_before_H11_observation']))
        self.assertTrue(historical['old_sites_and_reviewed_layout_tripwire_retained'])
        self.assertEqual((ledger['new_GPU_runs_during_export'],ledger['old_workflow_changes']), (0,0))


if __name__ == '__main__':
    unittest.main()
