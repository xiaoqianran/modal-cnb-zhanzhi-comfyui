"""Two scene-ticket contracts; no extra Qwen provider or H3 GPU execution."""
from dataclasses import replace
import pytest
from h3_audio_t8_pkg import prompt_scene_ticket as tickets
from h3_audio_t8_pkg import prompt_provider as old
from h3_audio_t8_pkg.reference_package import canonical


def candidate(ticket):
    value = {"schema": "t8.h09.prompt-proposal.v1", "request_sha256": ticket.request.sha256,
             "text": "integrated_multimodal_description: " + ticket.request.verify()["text"] + " "*110}
    return tickets.SceneProposal(ticket, old.PromptProposal(canonical(value), old.content_sha(value)))


def test_same_text_different_scene_revision_or_request_cannot_adopt_late_history():
    request = old.make_request("A woman says exactly once: <d>[Chinese]你好，今天天气不错。</d>", 5., [], ["你好，今天天气不错。"])
    first = tickets.bind(request, "scene_1", 0, "r1")
    value = candidate(first)
    for current in (tickets.bind(request, "scene_2", 0, "r1"), tickets.bind(request, "scene_1", 1, "r1"),
                    tickets.bind(request, "scene_1", 0, "r2")):
        text, report = tickets.choose(current, value)
        assert text == request.verify()["text"] and report["stale"] and report["history_readable"]
        assert report["candidate_original_scene_ticket"]["scene_id"] == "scene_1"
        with pytest.raises(ValueError, match="Late/expired"):
            tickets.choose(current, value, True)
    assert tickets.choose(first, value, True)[1]["adopted"]
    assert old.choose(request, value.proposal)[0] == request.verify()["text"]


def test_ticket_bound_before_dispatch_and_actual_tampering_not_accepted(monkeypatch):
    request = old.make_request("A steady shot of a cup on a table.", 5., [], [])
    first = tickets.bind(request, "scene_1", 0, "r1")
    value = candidate(first)
    calls = []
    def provider(request_arg, config, **kwargs):
        calls.append((request_arg, config, kwargs))
        assert request_arg is first.request
        return value.proposal, {"automatic_accept": False}
    monkeypatch.setattr(old, "rewrite", provider)
    wrapped, report = tickets.rewrite(first, "unchanged config")
    assert wrapped.ticket is first and len(calls) == 1 and report["ticket_sha256"] == first.sha256
    with pytest.raises(ValueError, match="changed"):
        replace(first, scene_revision=1).verify()
