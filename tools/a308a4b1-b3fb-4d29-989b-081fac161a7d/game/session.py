"""Single authority for a shared, ephemeral viewer session.

This first vertical slice serves real setup status through the final view
contract. Heavy game integration is added behind the same request interface.
"""

from copy import deepcopy
from dataclasses import dataclass
from os import environ
from threading import Lock
from time import monotonic
from uuid import uuid4


@dataclass(frozen=True)
class Operator:
    tenant: str
    subject: str


class GameSession:
    def __init__(self) -> None:
        self._lock = Lock()
        self.runtime_id = str(uuid4())
        self._view = {
            "schema": 1, "runtime_id": self.runtime_id, "run_id": None,
            "run_number": 0, "revision": 0, "status": "setup_required",
            "message": "Provision approved local ROM and pinned model assets.",
            "requirements": [], "frame": None, "game": None,
            "timing": {"active_seconds": 0, "retry_after_ms": 15000,
                       "batch_ms": None, "init_ms": None, "steps": 0},
            "presence": {"operators": 0, "tabs": 0, "expiry_seconds": 12},
            "decisions": [], "fastest_runs": [], "watch_leaders": [],
            "you": {"label": None, "watch_seconds": 0}, "completion": None,
        }
        self._created = monotonic()

    def status(self) -> dict:
        return {"status": self._view["status"], "runtime_id": self.runtime_id,
                "run_number": self._view["run_number"],
                "message": self._view["message"],
                "ephemeral": True}

    def request(self, operator: Operator, tab_id: str, visible: bool,
                runtime_id: str | None, run_id: str | None,
                revision: int | None, playback: bool) -> dict:
        if not self._lock.acquire(blocking=False):
            return deepcopy(self._view)
        try:
            missing = [name for name in (
                "POKEMON_RED_ROM_PATH", "POKEMON_RED_ROM_SHA256", "LAYA_MODEL_PATH"
            ) if not environ.get(name)]
            view = deepcopy(self._view)
            view["requirements"] = [
                f"Configure {name} using approved deployment assets." for name in missing
            ]
            if not missing:
                view["requirements"] = [
                    "Game integration validation is not complete; gameplay is disabled."
                ]
            self._view = view
            return deepcopy(view)
        finally:
            self._lock.release()
