"""One shared RAM session; one mutation/admission/serialization authority.

Cheap constructors. One nonblocking threading.Lock grants exclusive ownership of
the emulator/controller to one admitted request. Bookkeeping can renew presence
while that request awaits bounded native work. No other request can access those
objects until the result is committed under the same lock. No detached work,
timer, import, chat launch, or presence expiry starts gameplay.
"""

from collections import deque
from copy import deepcopy
from dataclasses import asdict, dataclass, replace
from math import ceil
from os import environ
from pathlib import Path
from threading import Lock
from time import monotonic
from uuid import uuid4

import anyio

from .controller import Decision, LayaController, LayaError
from .emulator import RedEmulator
from .pokemon_red import (
    ROM_LENGTH,
    Completion,
    Observation,
    PokemonRed,
    RedActionError,
    validate_rom,
)

PRESENCE_SECONDS = 12.0
BATCH_GAP_SECONDS = 2.5
CALL_WORK_SECONDS = 20.0
COMPLETION_SECONDS = 6.0
MAX_ACTIVE_TABS = 128
MAX_TAB_BINDINGS = 4096


@dataclass(frozen=True)
class Operator:
    tenant: str
    subject: str


@dataclass(frozen=True)
class Tab:
    operator: Operator
    expires: float
    displaying: bool


@dataclass
class WatchTotal:
    label: str
    seconds: float = 0.0


@dataclass(frozen=True)
class WorkResult:
    """Private result of one exclusively admitted request, never a transport type."""
    kind: str
    phase: str
    message: str
    elapsed_ms: float = 0.0
    observation: Observation | None = None
    frame: dict | None = None
    decision: Decision | None = None
    completion: Completion | None = None
    milestones: tuple[str, ...] = ()
    stalled: bool = False


class GameSession:
    def __init__(self) -> None:
        self._lock = Lock()
        self._limiter: anyio.CapacityLimiter | None = None
        self.runtime_id = str(uuid4())
        self._run_id: str | None = None
        self._run_number = self._revision = self._steps = 0
        self._status = "setup_required"
        self._message = "Provision approved local ROM and pinned model assets."
        self._requirements: list[str] = []
        self._phase = "assets"
        self._busy = False
        self._asset_signature: tuple[str, ...] | None = None
        self._asset_error: str | None = None
        self._rom: bytes | None = None
        self._red: PokemonRed | None = None
        self._emulator = RedEmulator()
        self._controller = LayaController()
        self._observation: Observation | None = None
        self._game: dict | None = None
        self._frame: dict | None = None
        self._tabs: dict[str, Tab] = {}
        # Bounded binding tombstones, not presence/history. Active records expire;
        # an old tab UUID can never be claimed by another operator in this runtime.
        self._owners: dict[str, Operator] = {}
        self._watch: dict[Operator, WatchTotal] = {}
        self._active_seconds = 0.0
        self._accounted_at = monotonic()
        self._due = self._accounted_at
        self._batch_active = False
        self._batch_ms: float | None = None
        self._batch_times: deque[float] = deque(maxlen=16)
        self._init_times: dict[str, float] = {}
        self._decisions: deque[dict] = deque(maxlen=8)
        self._best: list[dict] = []
        self._completion: dict | None = None
        self._completion_until = 0.0
        self._finalized_run: str | None = None
        # Published dictionaries are NEVER subsequently mutated. Own totals and
        # bindings are published atomically with the shared view for busy readers.
        self._published: tuple[dict, dict, dict] = ({}, {}, {})
        self._publish(self._accounted_at)

    def status(self) -> dict:
        """Small read-only launch status; no presence, clocks or I/O are mutated."""
        view = self._published[0]
        status = view["status"]
        message = view["message"]
        if status == "running" and not view["busy"] and monotonic() >= view["presence"]["fresh_until"]:
            status = "paused"
            message = "No fresh visible viewers. The exact emulator state remains paused in RAM."
        return {"status": status, "runtime_id": self.runtime_id,
                "run_number": view["run_number"], "message": message,
                "ephemeral": True,
                "note": "Open the App for live state. One replica required; no chat-driven gameplay."}

    def _account(self, now: float) -> None:
        """Integrate unions of known server intervals up to now, then expire tabs.

        Between request boundaries all intervals start before accounted_at. Thus
        max(expiry) for a person's visible/displaying tabs is exactly their union
        endpoint. A missing close can add no more than the 12-second lease.
        """
        visible_until = self._accounted_at
        watching_until: dict[Operator, float] = {}
        for tab in self._tabs.values():
            visible_until = max(visible_until, tab.expires)
            if tab.displaying:
                watching_until[tab.operator] = max(watching_until.get(tab.operator, self._accounted_at), tab.expires)
        for operator, end in watching_until.items():
            self._watch[operator].seconds += max(0.0, min(now, end) - self._accounted_at)
        if self._status == "running":
            active_end = now if self._batch_active else min(now, visible_until)
            self._active_seconds += max(0.0, active_end - self._accounted_at)
        self._accounted_at = now
        self._tabs = {key: tab for key, tab in self._tabs.items() if tab.expires > now}

    def _touch(self, operator: Operator, tab_id: str, visible: bool,
               displaying: bool, now: float) -> bool:
        bound = self._owners.get(tab_id)
        if bound is not None and bound != operator:
            raise ValueError("This browser session belongs to another authenticated operator.")
        if bound is None:
            if len(self._owners) >= MAX_TAB_BINDINGS:
                raise ValueError("This ephemeral runtime reached its 4096 browser-session limit.")
            self._owners[tab_id] = operator
        if operator not in self._watch:
            self._watch[operator] = WatchTotal(f"Viewer {len(self._watch) + 1:03}")
        existing = self._tabs.get(tab_id)
        fresh = existing is not None and existing.expires > now
        if visible:
            if not fresh and len(self._tabs) >= MAX_ACTIVE_TABS:
                raise ValueError("This shared demo has reached its 128 visible-tab limit.")
            was_empty = not self._tabs
            self._tabs[tab_id] = Tab(operator, now + PRESENCE_SECONDS,
                                     bool(displaying and self._frame is not None))
            if was_empty:
                # Do not simulate missed due slots. A resume gets only one slot.
                self._due = max(now, self._due)
        else:
            self._tabs.pop(tab_id, None)
        return fresh

    def _setup_requirements(self) -> None:
        """Cheap presence/view path: configuration only, never files/model load."""
        names = ("POKEMON_RED_ROM_PATH", "POKEMON_RED_ROM_SHA256", "LAYA_MODEL_PATH")
        signature = tuple(environ.get(name, "") for name in names)
        if signature != self._asset_signature:
            self._asset_signature, self._asset_error = signature, None
        if self._asset_error is not None:
            self._status = "setup_required"
            self._message = "Static asset validation failed; gameplay has not started."
            self._requirements = [self._asset_error,
                                  "Correct the deployment assets/configuration, then reload or republish to recheck the same paths."]
            return
        self._requirements = [f"Configure {name} using approved deployment assets."
                              for name in names if not environ.get(name)]
        if self._requirements:
            self._status = "setup_required"
            self._message = "Setup required. No game or model has been started."
        elif self._phase == "assets":
            self._status = "initializing"
            self._message = "Asset paths configured. Initialization proceeds only on visible playback requests."

    def _snapshot(self, operator: Operator, tab_id: str, admission: str) -> dict:
        shared, own, owners = self._published
        if owners.get(tab_id, operator) != operator:
            raise ValueError("This browser session belongs to another authenticated operator.")
        view = deepcopy(shared)
        view["you"] = deepcopy(own.get(operator, {"label": None, "watch_seconds": 0.0}))
        view["admission"] = admission
        if admission == "busy":
            view["timing"]["retry_after_ms"] = 2500
        return view

    def _publish(self, now: float) -> None:
        """Only called by the lock owner (or once by the cheap constructor)."""
        fresh_until = max((tab.expires for tab in self._tabs.values()), default=now)
        status = self._status
        message = self._message
        if status == "running" and not self._tabs and not self._busy:
            status, message = "paused", "No fresh visible viewers. The exact emulator state remains paused in RAM."
        retry = 15000 if status == "setup_required" or (status == "failed" and self._frame is None) else 2500
        if status == "completed":
            retry = max(1500, min(4000, ceil((self._completion_until - now) * 1000)))
        elif status in ("running", "initializing"):
            retry = max(1500, ceil((self._due - now) * 1000))
        totals = {key: {"label": value.label, "watch_seconds": round(value.seconds, 3)}
                  for key, value in self._watch.items()}
        ranked = sorted((value for value in self._watch.values() if value.seconds > 0),
                        key=lambda value: (-value.seconds, value.label))[:10]
        leaders = [{"label": value.label, "watch_seconds": round(value.seconds, 3)}
                   for value in ranked]
        view = {
            "schema": 1, "runtime_id": self.runtime_id, "run_id": self._run_id,
            "run_number": self._run_number, "revision": self._revision,
            "status": status, "message": message, "requirements": list(self._requirements),
            "frame": deepcopy(self._frame), "game": deepcopy(self._game), "busy": self._busy,
            "timing": {"active_seconds": round(self._active_seconds, 3),
                       "retry_after_ms": retry, "batch_ms": self._batch_ms,
                       "mean_batch_ms": (sum(self._batch_times) / len(self._batch_times)) if self._batch_times else None,
                       "init_ms": sum(self._init_times.values()) if self._init_times else None,
                       "init_phases_ms": dict(self._init_times), "stage": self._phase,
                       "steps": self._steps, "minimum_batch_gap_ms": 2500,
                       "work_budget_ms": 20000},
            "presence": {"operators": len({tab.operator for tab in self._tabs.values()}),
                         "tabs": len(self._tabs), "expiry_seconds": 12,
                         "fresh_until": fresh_until},
            "decisions": deepcopy(list(self._decisions)),
            "fastest_runs": deepcopy(self._best), "watch_leaders": deepcopy(leaders),
            "you": {"label": None, "watch_seconds": 0.0},
            "completion": deepcopy(self._completion),
        }
        self._published = (view, totals, dict(self._owners))

    async def request(self, operator: Operator, tab_id: str, visible: bool,
                      displaying: bool, runtime_id: str | None,
                      run_id: str | None, revision: int | None, playback: bool) -> dict:
        if not self._lock.acquire(blocking=False):
            return self._snapshot(operator, tab_id, "busy")
        admission = "view"
        work_phase: str | None = None
        deadline = 0.0
        try:
            now = monotonic()
            self._account(now)
            matching_runtime = runtime_id == self.runtime_id
            fresh = self._touch(operator, tab_id, visible and (matching_runtime or runtime_id is None),
                                displaying and matching_runtime, now)
            if self._phase == "assets" and self._status != "failed" and not self._busy:
                self._setup_requirements()
            eligible = (playback and visible and fresh and matching_runtime
                        and run_id == self._run_id and revision == self._revision)
            if self._busy:
                admission = "busy"
            elif not eligible:
                admission = "stale" if playback else "view"
            elif now < self._due or (self._status == "completed" and now < self._completion_until):
                admission = "not_due"
            elif self._status in ("failed", "setup_required"):
                admission = "paused"
            else:
                # Grant the only gameplay lease BEFORE offloading. No second
                # request gets queued behind it, even if a thread pool is busy.
                self._busy = True
                self._batch_active = self._status == "running"
                self._revision += 1
                work_phase = "new_run" if self._status == "completed" else self._phase
                deadline = now + CALL_WORK_SECONDS
                admission = "admitted"
                if self._limiter is None:
                    self._limiter = anyio.CapacityLimiter(1)
            self._publish(monotonic())
            if work_phase is None:
                return self._snapshot(operator, tab_id, admission)
        finally:
            self._lock.release()

        # The exclusively owned lower objects can be mutated only by this work.
        # Concurrent viewers may update presence but read only detached views.
        # Shield both the awaited work and its commit: cancellation never leaves
        # a native action detached from a settled request.
        with anyio.CancelScope(shield=True):
            try:
                result = await anyio.to_thread.run_sync(self._run_admitted, work_phase, deadline,
                                                        abandon_on_cancel=False, limiter=self._limiter)
            except Exception as error:  # noqa: BLE001 -- also fail closed if thread dispatch itself fails
                result = WorkResult("failed", work_phase,
                                    f"Request dispatch failed ({type(error).__name__}); the run is paused.",
                                    elapsed_ms=round((monotonic() - deadline + CALL_WORK_SECONDS) * 1000, 2))
            with self._lock:
                now = monotonic()
                self._account(now)
                self._commit(result, work_phase)
                self._batch_active = self._busy = False
                self._due = now + BATCH_GAP_SECONDS
                self._revision += 1
                self._publish(now)
        return self._snapshot(operator, tab_id, admission)

    def _initialize_phase(self, phase: str) -> WorkResult:
        if phase == "assets":
            rom_path = Path(environ["POKEMON_RED_ROM_PATH"]).expanduser()
            if not rom_path.is_absolute() or not rom_path.is_file():
                raise ValueError("POKEMON_RED_ROM_PATH must be a readable absolute deployment-local file.")
            if rom_path.stat().st_size != ROM_LENGTH:
                raise ValueError("Expected the supported 1 MiB English Red ROM.")
            with rom_path.open("rb") as stream:
                rom = stream.read(ROM_LENGTH + 1)
            validate_rom(rom, environ["POKEMON_RED_ROM_SHA256"])
            red = PokemonRed(rom)
            self._controller.configure(environ["LAYA_MODEL_PATH"])
            self._rom, self._red = rom, red
            return WorkResult("phase", "libraries", "ROM fingerprint and local snapshot layout checked. SDK import is next.")
        elif phase == "libraries":
            self._controller.import_library()
            return WorkResult("phase", "model", "Pinned SDK imported. The next visible request loads the CPU model once.")
        elif phase == "model":
            self._controller.load_model()
            return WorkResult("phase", "emulator", "Local Laya loaded. The next visible request powers on a fresh RAM-only cartridge.")
        elif phase in ("emulator", "new_run"):
            return self._new_run()
        else:
            raise RuntimeError("Unexpected initialization phase.")

    def _new_run(self) -> WorkResult:
        if self._rom is None:
            raise RuntimeError("A verified ROM is required before power-on.")
        self._emulator.close()
        self._controller.reset_run()
        self._red = PokemonRed(self._rom)
        self._emulator.open(self._rom)
        observation = self._red.observe(self._emulator.read, self._emulator.frame_count)
        # Establish the initial zero-counter/blank cartridge witness.
        if self._red.completion(self._emulator.read, observation) is not None:
            raise RuntimeError("A fresh RAM cartridge unexpectedly contained a completion.")
        return WorkResult("new_run", "ready", "Laya controls the game. Viewers only spectate.",
                          observation=observation, frame=self._emulator.capture())

    def _play_batch(self, deadline: float) -> WorkResult:
        red = self._red
        if red is None:
            raise RuntimeError("Game observation is not initialized.")
        before = red.observe(self._emulator.read, self._emulator.frame_count)
        legal = red.legal_actions(before)
        decision = self._controller.decide(before, legal, deadline - 1)
        action = next((a for a in legal if a.identifier == decision.action_id), None)
        if action is None:
            raise RuntimeError("Controller action is not a member of the legal-action set.")
        if sum(held + released for _, held, released in action.pulses) > 120:
            raise RuntimeError("Game macro exceeds the 120-frame batch limit.")
        red.note_action(action, before)
        current = before
        for index, (button, held, released) in enumerate(action.pulses):
            if index == len(action.pulses) - 1:
                red.verify_target(action, current)
            self._emulator.execute(button, held, released, deadline)
            current = red.observe(self._emulator.read, self._emulator.frame_count)
        self._controller.record_transition(before, current, decision)
        frame = self._emulator.capture()
        completion = red.completion(self._emulator.read, current)
        message = ("Laya is stalled: repeated observations, not verified progress."
                   if self._controller.stalled else "Laya controls the game. Viewers only spectate.")
        return WorkResult("batch", "ready", message, observation=current, frame=frame,
                          decision=decision, completion=completion,
                          milestones=self._controller.milestones, stalled=self._controller.stalled)

    def _commit(self, result: WorkResult, work_phase: str) -> None:
        """The lock owner alone updates clocks, displays and scores, once per lease."""
        self._batch_ms = result.elapsed_ms
        self._message = result.message
        if work_phase == "ready":
            self._batch_times.append(result.elapsed_ms)
        elif work_phase != "new_run":
            self._init_times[work_phase] = result.elapsed_ms
        if result.kind == "setup_error":
            self._asset_error = result.message
            self._setup_requirements()
            return
        if result.kind == "failed":
            self._status = "failed"
            self._requirements = [
                "No substitute model or scripted policy was used.",
                "A failed action may have partially advanced the emulator; the last successful frame is retained.",
                "Repair/republication deliberately discards this server session.",
            ]
            return
        self._requirements = []
        self._phase = result.phase
        if result.kind == "phase":
            self._status = "initializing"
            return
        if result.kind == "new_run":
            self._run_id = str(uuid4())
            self._run_number += 1
            self._active_seconds = 0.0
            self._steps = 0
            self._decisions.clear()
            self._completion = None
        elif result.decision is not None:
            self._steps += 1
            self._decisions.append(asdict(result.decision))
        self._status = "running"
        self._observation = result.observation
        if result.frame is not None:
            self._frame = dict(result.frame, id=f"{self._run_id}:{result.frame['emulator_frame']}")
        if result.observation is not None:
            o = result.observation
            self._game = {"summary": o.summary(), "mode": o.mode, "map": o.location,
                          "position": [o.x, o.y], "badges": o.badges.bit_count(),
                          "milestones": list(result.milestones), "stalled": result.stalled}
        if result.completion is not None:
            self._finish(result.completion)

    def _finish(self, completion: Completion) -> None:
        if self._run_id is None or self._finalized_run == self._run_id:
            return
        self._finalized_run = self._run_id
        result = {"run_id": self._run_id, "run_number": self._run_number,
                  "active_seconds": round(self._active_seconds, 3),
                  "steps": self._steps, "team": list(completion.team),
                  "record_sha256": completion.record_sha256,
                  "evidence": completion.evidence, "observed_frame": completion.observed_frame}
        self._best = sorted(self._best + [result],
                            key=lambda value: (value["active_seconds"], value["run_number"]))[:10]
        self._completion = result
        self._status = "completed"
        self._completion_until = monotonic() + COMPLETION_SECONDS
        self._message = "Verified first Hall-of-Fame team recording. Score recorded; a fresh run follows on eligible viewer requests."

    def _run_admitted(self, phase: str, deadline: float) -> WorkResult:
        """One request-owned lease, not a worker loop. Never updates presence/scores."""
        try:
            if monotonic() >= deadline:
                raise TimeoutError("No work budget remains after offload admission.")
            result = self._play_batch(deadline) if phase == "ready" else self._initialize_phase(phase)
            if monotonic() >= deadline:
                raise TimeoutError("The admitted work exceeded its CPU time budget.")
        except Exception as error:  # noqa: BLE001 -- fail-closed request boundary; no automatic retry
            if phase == "assets" and isinstance(error, (ValueError, OSError, KeyError)):
                message = (str(error) if isinstance(error, ValueError) else
                           "The configured static assets are missing or unreadable by the Python process.")
                result = WorkResult("setup_error", phase, message)
            else:
                detail = str(error) if isinstance(error, (LayaError, RedActionError)) else (
                    "Check pinned assets, CPU memory/budget and decoder compatibility.")
                result = WorkResult("failed", phase,
                                    f"{phase} failed ({type(error).__name__}). The run is paused, not reset. "
                                    + detail)
        return replace(result, elapsed_ms=round((monotonic() - deadline + CALL_WORK_SECONDS) * 1000, 2))
