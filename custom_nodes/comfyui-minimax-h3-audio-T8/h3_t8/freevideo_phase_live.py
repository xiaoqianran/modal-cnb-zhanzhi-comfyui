"""Bounded, transient phase display. Never advances NFE or serializes graph state."""
import json
import math
from pathlib import Path
import time

PHASES = {"preparation", "startup", "source_preflight", "imports_conditioning", "tables_policy_lora",
          "engine_load", "sampling", "latent_validation_transport", "release", "receipt_integrity",
          "complete", "legacy_receipt", "phase_unavailable"}
EVENT = "t8.h11.freevideo_phase"


class ObservedProgress:
    def __init__(self, update, total, emit=None, *, clock=time.monotonic):
        self.update, self.total, self.emit, self.clock = update, total, emit, clock
        self.completed, self.phase = 0, "preparation"
        self.start = self.clock()
        self.last_sent, self.last_identity = float("-inf"), None
        self.publish()

    def __call__(self, completed, total):
        # Preserve the original callback and its exception. Phase records are
        # never used to update this original Core ProgressBar.
        result = self.update(completed, total)
        if type(completed) is int and type(total) is int and total == self.total and 0 <= completed <= total:
            self.completed = completed
            self.publish()
        return result

    def publish(self):
        if self.emit is None:
            return
        now = self.clock()
        identity = (self.phase, self.completed)
        if identity == self.last_identity and now-self.last_sent < 1.:
            return
        self.emit({"schema": "t8.h11.freevideo-live-phase.v1", "phase": self.phase,
            "completed_NFE": self.completed, "total_NFE": self.total,
            "observed_host_seconds": max(0., now-self.start),
            "phase_is_NFE": False, "scope": "host observation NOT CUDA timing or quality",
            "automatic_restart": False})
        self.last_identity, self.last_sent = identity, now

    def poll(self, run):
        # Only this owned process's fixed phase.json. Ignore malformed observer
        # records as unavailable; original worker/result/hash failures still
        # propagate through the unchanged production paths.
        try:
            with (Path(run)/"phase.json").open("rb") as stream:
                raw = stream.read(65537)
            if len(raw) > 65536:
                raise ValueError("Observer byte budget")
            value = json.loads(raw)
            phase = value.get("current_phase")
            if value.get("schema") != "t8.h11.freevideo-phases.v1" or phase not in PHASES:
                raise ValueError("Unknown observer phase")
            self.phase = phase
        except FileNotFoundError:
            pass  # preparation may precede the worker's first atomic record
        except (OSError, ValueError, TypeError, AttributeError):
            self.phase = "phase_unavailable"
        self.publish()


def observe_phase(progress, run):
    if type(progress) is ObservedProgress:
        progress.poll(run)
    # External callable callbacks retain their old behavior, no extra hooks.


def current_sender():
    from comfy_execution.utils import get_executing_context
    from server import PromptServer
    context, server = get_executing_context(), getattr(PromptServer, "instance", None)
    if context is None or server is None:
        return None
    identity = {"prompt_id": str(context.prompt_id), "node_id": str(context.node_id)}
    if any(not 1 <= len(v) <= 128 for v in identity.values()):
        return None
    sid = server.client_id
    def send(value):
        # Never include worker paths, prompt contents, compiler key names or
        # arbitrary JSON. The scalar phase whitelist is the entire transport.
        if (value["phase"] not in PHASES or type(value["completed_NFE"]) is not int
                or type(value["total_NFE"]) is not int
                or not 0 <= value["completed_NFE"] <= value["total_NFE"] <= 2048
                or not math.isfinite(value["observed_host_seconds"])):
            raise ValueError("Invalid owned phase observation")
        server.send_sync(EVENT, {**value, **identity}, sid)
    return send


def core_progress(bar, total):
    return ObservedProgress(lambda n, count: bar.update_absolute(n, count), total, current_sender())


def completed_card_notice(receipt):
    send = current_sender()
    if send is not None:
        count = receipt["completed_nfe"]
        send({"schema": "t8.h11.freevideo-live-phase.v1", "phase": "legacy_receipt",
            "completed_NFE": count, "total_NFE": count, "observed_host_seconds": 0.,
            "phase_is_NFE": False, "scope": "actual completed Stage metadata, NO new sampling",
            "automatic_restart": False})
