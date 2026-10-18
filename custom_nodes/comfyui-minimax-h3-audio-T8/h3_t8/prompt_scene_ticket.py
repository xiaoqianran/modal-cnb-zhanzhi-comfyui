"""Thin scene/revision/request-ticket binding around the unchanged H09 provider."""
from dataclasses import dataclass
import re
from . import prompt_provider as provider


@dataclass(frozen=True)
class SceneTicket:
    request: object
    scene_id: str
    scene_revision: int
    request_id: str
    sha256: str

    def verify(self):
        if type(self.request) is not provider.PromptRequest:
            raise ValueError("Scene ticket requires actual verified request")
        self.request.verify()
        value = {"schema": "t8.h11.scene-ticket.v1", "scene_id": self.scene_id,
                 "scene_revision": self.scene_revision, "request_id": self.request_id,
                 "request_sha256": self.request.sha256}
        if provider.content_sha(value) != self.sha256:
            raise ValueError("Scene ticket contents changed")
        return value


def bind(request, scene_id, scene_revision, request_id):
    if type(request) is not provider.PromptRequest:
        raise ValueError("Use actual verified H09 request")
    if (not isinstance(scene_id, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,63}", scene_id)
            or type(scene_revision) is not int or not 0 <= scene_revision <= 2**31-1
            or not isinstance(request_id, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,127}", request_id)):
        raise ValueError("Explicit short scene ID, revision and fresh request ID required")
    value = {"schema": "t8.h11.scene-ticket.v1", "scene_id": scene_id, "scene_revision": scene_revision,
             "request_id": request_id, "request_sha256": request.sha256}
    ticket = SceneTicket(request, scene_id, scene_revision, request_id, provider.content_sha(value))
    ticket.verify()
    return ticket


@dataclass(frozen=True)
class SceneProposal:
    ticket: SceneTicket
    proposal: object

    def verify(self):
        if type(self.ticket) is not SceneTicket or type(self.proposal) is not provider.PromptProposal:
            raise ValueError("Actual scene-bound proposal required")
        self.ticket.verify()
        return self.proposal.verify(self.ticket.request)


def rewrite(ticket, runtime_config, *, interrupt=None):
    if type(ticket) is not SceneTicket:
        raise ValueError("Actual scene ticket required before dispatch")
    ticket.verify()  # bind before dispatch, not attach a guessed scene after return
    proposal, report = provider.rewrite(ticket.request, runtime_config, interrupt=interrupt)
    ticket.verify()
    wrapped = SceneProposal(ticket, proposal)
    wrapped.verify()
    return wrapped, {**report, "scene_ticket": ticket.verify(), "ticket_sha256": ticket.sha256,
                     "automatic_accept": False}


def choose(current_ticket, candidate, confirmed=False):
    if type(current_ticket) is not SceneTicket or type(candidate) is not SceneProposal or type(confirmed) is not bool:
        raise ValueError("Actual scene ticket/proposal and explicit adoption boolean required")
    current = current_ticket.verify()
    previous = candidate.ticket.verify()
    value = candidate.verify()  # stale history remains readable for its original scene
    stale = current_ticket.sha256 != candidate.ticket.sha256
    report = {"current_scene_ticket": current, "candidate_original_scene_ticket": previous,
              "stale": stale, "history_readable": True, "candidate_text": value["text"],
              "automatic_accept": False, "original_retained": True, "adopted": False}
    if not confirmed:
        return current_ticket.request.verify()["text"], report
    if stale:
        raise ValueError("Late/expired scene proposal cannot be adopted into current scene/revision/request")
    text, adoption = provider.choose(current_ticket.request, candidate.proposal, True)
    return text, {**report, **adoption}
