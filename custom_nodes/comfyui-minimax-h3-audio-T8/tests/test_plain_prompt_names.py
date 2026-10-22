"""Filename and reversible migration tests; no Core, models, browser or CUDA."""
from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tools.check_windows_paths import validate_paths  # noqa: E402
from tools.plain_prompt_names import ordinary_target, render_plain_index  # noqa: E402
from tools.rename_plain_prompt_workflows import apply_renames, plan_renames  # noqa: E402


class PlainPromptNamesTests(unittest.TestCase):
    def make_tree(self, root):
        directory = root / "examples/workflows/test"
        directory.mkdir(parents=True)
        source = directory / "2026-09-21_H3_Dual_Model_4plus4_Cold_HIGH_Relay_EXP.json"
        source.write_bytes(b'{"nodes": [{"type": "Source"}]}\r\n')
        ordinary = directory / "Plain_001.json"
        ordinary.write_bytes((json.dumps({"nodes": [], "links": [], "extra": {
            "t8_plain_source": source.relative_to(root).as_posix(), "test": "keep every byte"}},
            ensure_ascii=False) + "\r\n").encode("utf-8"))
        row = {"source": source.relative_to(root).as_posix(), "ordinary": ordinary.relative_to(root).as_posix(),
               "source_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
               "ordinary_sha256": hashlib.sha256(ordinary.read_bytes()).hexdigest(),
               "source_title": source.stem}
        manifest = root / "examples/workflows/plain-prompt-index.json"
        manifest.write_text(json.dumps({"schema": "t8.ordinary-prompt-examples.v1", "source_count": 1, "rows": [row]}), encoding="utf-8")
        (manifest.parent / "filename-map.tsv").write_text("old_path\tnew_path\tsha256\n", encoding="utf-8")
        (manifest.parent / "PLAIN_PROMPTS.md").write_text("old numbered index\n", encoding="utf-8")
        (manifest.parent / "README.md").write_text("examples `Plain_*.json`\n", encoding="utf-8")
        (directory / "README.md").write_text("# Test\n\n普通提示词副本：[本目录原版→普通版对照](../PLAIN_PROMPTS.md#test)。旧说明。\n", encoding="utf-8")
        return source, ordinary, manifest

    def test_readable_feature_recipe_and_resume_name_in_source_category(self):
        source = "examples/workflows/04-long-video/2026-09-21_H3_Dual_Model_4plus4_Cold_HIGH_Relay_EXP.json"
        self.assertEqual(ordinary_target(source).as_posix(),
                         "examples/workflows/04-long-video/Dual_Model_4plus4_Cold_HIGH_EXP_普通提示词.json")

    def test_embedded_date_and_prompt_relay_are_removed_without_losing_audio_branch(self):
        target = ordinary_target("examples/workflows/59-audio-refine-split/S26_2026-08-29_H3_Audio_Refine_Prompt_Relay_Turbo8_Advanced_EXP_resume_audio_Separate_EXP.json")
        self.assertEqual(target.name, "S26_Audio_Refine_Turbo8_EXP_resume_audio_Separate_EXP_普通提示词.json")

    def test_full_save_cold_and_independent_stage_discriminators_remain(self):
        names = [ordinary_target(f"examples/workflows/test/S17_3Stage_combined_{variant}_EXP.json").name
                 for variant in ("stage0_full_save", "stage1_full_save", "all_cold_1", "all_cold_2")]
        self.assertEqual(len(set(names)), 4)
        for variant, name in zip(("stage0_full_save", "stage1_full_save", "all_cold_1", "all_cold_2"), names):
            self.assertIn(variant, name)

    def test_unknown_over_budget_name_is_rejected_not_hashed_or_truncated(self):
        with self.assertRaisesRegex(ValueError, "Workflow filename"):
            ordinary_target("examples/workflows/test/" + "x" * 100 + ".json")

    def test_unsafe_or_featureless_sources_are_rejected(self):
        for name in ("../source.json", "/examples/workflows/test/X.json", "examples/workflows/test/../../X.json",
                     "examples/workflows/test/H3_Prompt_Relay_Advanced.json", "examples/workflows/test/Plain_025.json"):
            with self.subTest(name=name), self.assertRaises(ValueError):
                ordinary_target(name)

    def test_entire_real_manifest_has_unique_descriptive_same_category_names(self):
        manifest = json.loads((ROOT / "examples/workflows/plain-prompt-index.json").read_text(encoding="utf-8"))
        targets = [ordinary_target(row["source"]) for row in manifest["rows"]]
        self.assertEqual(len(targets), len({path.as_posix().casefold() for path in targets}))
        self.assertEqual(validate_paths([path.as_posix() for path in targets]), [])
        for row, target in zip(manifest["rows"], targets):
            self.assertEqual(target.parent.as_posix(), Path(row["source"]).parent.as_posix())

    def test_dry_run_does_not_change_files_or_create_backups(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            self.make_tree(root)
            before = {path: path.read_bytes() for path in root.rglob("*") if path.is_file()}
            plan = plan_renames(root)
            self.assertEqual(len(plan["moves"]), 1)
            self.assertEqual(before, {path: path.read_bytes() for path in root.rglob("*") if path.is_file()})
            self.assertFalse((root / "artifacts").exists())

    def test_move_is_byte_exact_backed_up_and_idempotent(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source, old, _manifest = self.make_tree(root)
            source_bytes, ordinary_bytes = source.read_bytes(), old.read_bytes()
            plan = plan_renames(root)
            backup = root / "artifacts/development/test"
            result = apply_renames(root, plan, backup)
            new = root / plan["moves"][0]["new_path"]
            self.assertEqual(result["renamed"], 1)
            self.assertFalse(old.exists())
            self.assertEqual(new.read_bytes(), ordinary_bytes)
            self.assertEqual(source.read_bytes(), source_bytes)
            with (root / "examples/workflows/filename-map.tsv").open(encoding="utf-8") as stream:
                rows = list(csv.DictReader(stream, delimiter="\t"))
            self.assertEqual(rows[0]["old_path"], plan["moves"][0]["old_path"])
            self.assertEqual(rows[0]["sha256"], hashlib.sha256(ordinary_bytes.replace(b"\r\n", b"\n")).hexdigest())
            self.assertTrue((backup / "preimage/examples/workflows/plain-prompt-index.json").exists())
            self.assertIn("*_普通提示词.json", (new.parent / "README.md").read_text(encoding="utf-8"))
            repeated = plan_renames(root)
            self.assertEqual(repeated["moves"], [])
            self.assertEqual(repeated["updates"], {})

    def test_edited_output_or_existing_destination_stops_before_moving(self):
        for failure in ("edited", "occupied"):
            with self.subTest(failure=failure), tempfile.TemporaryDirectory() as temp:
                root = Path(temp)
                source, old, _manifest = self.make_tree(root)
                if failure == "edited":
                    old.write_bytes(b"user edited content")
                else:
                    new = root / ordinary_target(source.relative_to(root).as_posix())
                    new.write_bytes(b"another workflow")
                with self.assertRaises(ValueError):
                    plan_renames(root)
                self.assertTrue(old.exists())
                self.assertFalse((root / "artifacts").exists())

    def test_reference_changed_after_preflight_is_preserved(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            _source, old, manifest = self.make_tree(root)
            plan = plan_renames(root)
            manifest.write_bytes(b"other agent changed the index")
            with self.assertRaisesRegex(ValueError, "Reference files changed"):
                apply_renames(root, plan, root / "artifacts/development/test")
            self.assertEqual(manifest.read_bytes(), b"other agent changed the index")
            self.assertTrue(old.exists())

    def test_reference_write_failure_rolls_back_file_moves_and_metadata(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            _source, old, manifest = self.make_tree(root)
            plan = plan_renames(root)
            original_write = Path.write_bytes
            did_fail = False

            def write(path, data):
                nonlocal did_fail
                if path.resolve() == manifest.resolve() and not did_fail:
                    did_fail = True
                    raise OSError("simulated write failure")
                return original_write(path, data)

            with patch.object(Path, "write_bytes", write), self.assertRaisesRegex(OSError, "simulated"):
                apply_renames(root, plan, root / "artifacts/development/test")
            self.assertTrue(old.exists())
            self.assertEqual(manifest.read_bytes(), plan["before"][manifest.relative_to(root)])
            self.assertFalse((root / plan["moves"][0]["new_path"]).exists())

    def test_backup_must_be_new_and_scoped_to_private_development(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            _source, old, _manifest = self.make_tree(root)
            plan = plan_renames(root)
            for target in (root, root / "examples", root / "artifacts/development"):
                with self.subTest(target=target), self.assertRaises(ValueError):
                    apply_renames(root, plan, target)
            self.assertTrue(old.exists())

    def test_index_links_use_function_names_and_keep_scope_warning(self):
        source = "examples/workflows/test/VM01_Marked_4plus4.json"
        content = render_plain_index([{"source": source, "ordinary": ordinary_target(source).as_posix()}])
        self.assertIn("VM01_Marked_4plus4_普通提示词.json", content)
        self.assertIn("filename-map.tsv", content)
        self.assertIn("不作为这些新文字副本的画质证明", content)

    def test_ordinary_manifest_cannot_claim_an_original_as_generated_output(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source, _old, manifest = self.make_tree(root)
            index = json.loads(manifest.read_text(encoding="utf-8"))
            index["rows"][0]["ordinary"] = source.relative_to(root).as_posix()
            index["rows"][0]["ordinary_sha256"] = index["rows"][0]["source_sha256"]
            manifest.write_text(json.dumps(index), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "not the manifest-owned ordinary"):
                plan_renames(root)
            self.assertTrue(source.exists())


if __name__ == "__main__":
    unittest.main()
