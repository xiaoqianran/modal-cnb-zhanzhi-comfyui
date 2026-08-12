from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from env_tokens import parse_dotenv, read_dotenv, token_secret_dict  # noqa: E402


def test_parse_dotenv_skips_comments_and_unrelated_keys():
    parsed = parse_dotenv(
        """
# HF_TOKEN=commented
export GITHUB_TOKEN=ghp_from_export
HF_TOKEN="hf_quoted"
CIVITAI_TOKEN='civitai_quoted'
MODAL_GPU=L40S
MODAL_SECRETS=huggingface,civitai,github
not a line
=nokey
"""
    )
    assert parsed["GITHUB_TOKEN"] == "ghp_from_export"
    assert parsed["HF_TOKEN"] == "hf_quoted"
    assert parsed["CIVITAI_TOKEN"] == "civitai_quoted"
    assert parsed["MODAL_GPU"] == "L40S"
    assert parsed["MODAL_SECRETS"] == "huggingface,civitai,github"
    assert "not a line" not in parsed


def test_read_dotenv_missing_file(tmp_path):
    assert read_dotenv(tmp_path / "nope.env") == {}


def test_token_secret_dict_only_keeps_tokens_and_fills_aliases():
    payload = token_secret_dict(
        {},
        {
            "HF_TOKEN": "hf_abc",
            "CIVITAI_TOKEN": "civ_abc",
            "GITHUB_TOKEN": "ghp_abc",
            "MODAL_GPU": "H100",
            "MODAL_SECRETS": "huggingface,civitai,github",
        },
    )
    assert payload == {
        "HF_TOKEN": "hf_abc",
        "HUGGING_FACE_HUB_TOKEN": "hf_abc",
        "CIVITAI_TOKEN": "civ_abc",
        "CIVITAI_API_TOKEN": "civ_abc",
        "GITHUB_TOKEN": "ghp_abc",
        "GH_TOKEN": "ghp_abc",
    }
    assert "MODAL_GPU" not in payload
    assert "MODAL_SECRETS" not in payload


def test_environ_wins_over_dotenv_and_empty_values_are_ignored():
    payload = token_secret_dict(
        {"HF_TOKEN": "from_env", "GITHUB_TOKEN": "  "},
        {"HF_TOKEN": "from_file", "GITHUB_TOKEN": "from_file", "CIVITAI_API_TOKEN": "civ_only"},
    )
    assert payload["HF_TOKEN"] == "from_env"
    assert payload["HUGGING_FACE_HUB_TOKEN"] == "from_env"
    assert payload["GITHUB_TOKEN"] == "from_file"
    assert payload["GH_TOKEN"] == "from_file"
    assert payload["CIVITAI_API_TOKEN"] == "civ_only"
    assert payload["CIVITAI_TOKEN"] == "civ_only"


def test_no_tokens_yields_empty_secret_dict():
    assert token_secret_dict({"MODAL_GPU": "L40S"}, {"MODAL_SECRETS": "github"}) == {}
