"""Pinned local Python Laya, compact run memory, and measured typed decisions.

Receives immutable observations/actions. Never receives an emulator, writes
memory, handles operators, or imports MCP. There is no substitute policy.
"""

from collections import OrderedDict, deque
from dataclasses import dataclass
from importlib.metadata import distribution, version
from inspect import signature
from json import loads
from math import isfinite
from pathlib import Path
from time import monotonic
from typing import TYPE_CHECKING, Any

from .pokemon_red import LegalAction, Observation

if TYPE_CHECKING:
    from laya.agent import Agent

SDK_REVISION = "42626c348753fbb17572a813127df2278a1ec527"
MODEL_REVISION = "1c5edc17a7acd8701df6fc341c0d179f1c62c982"


@dataclass(frozen=True)
class Decision:
    action_id: str
    action: str
    objective: str
    inference_ms: float
    input_tokens: int
    state_tokens: int
    omitted_tokens: int
    confidence: float | None
    model_calls: int
    source: str
    stalled: bool


class LayaController:
    def __init__(self) -> None:
        self._path: Path | None = None
        self._library: Any = None
        self._agent: Agent | None = None
        self._config: dict = {}
        self._objective = ""
        self._objective_at = 0
        self._steps = 0
        self._same = 0
        self._recent: deque[tuple] = deque(maxlen=12)
        self._dialogue: deque[str] = deque(maxlen=3)
        self._visits: OrderedDict[tuple[int, int, int], int] = OrderedDict()
        self._transitions: deque[str] = deque(maxlen=24)
        self._milestones: list[str] = []
        self._last_action = ""
        self._last_effect = ""
        self._last_map: int | None = None

    @property
    def milestones(self) -> tuple[str, ...]:
        return tuple(self._milestones)

    @property
    def stalled(self) -> bool:
        return self._same >= 8 or (len(self._recent) == 12 and len(set(self._recent)) <= 3)

    def configure(self, directory: str) -> None:
        """Check the provisioned root snapshot without importing a model library.

        Use the Hub's canonical read-only snapshots/<pinned-revision> directory.
        Provenance is an operator provisioning responsibility; neither its path
        nor an arbitrary locally authored manifest is treated as cryptographic
        proof. No request downloads or executes code from the model directory.
        """
        path = Path(directory).expanduser().absolute()
        if path.name != MODEL_REVISION or path.parent.name != "snapshots":
            raise ValueError("LAYA_MODEL_PATH must be the local Hub snapshots/" + MODEL_REVISION + " root English checkpoint.")
        required = ("rl_agent_config.json", "encoder/config.json", "model.safetensors",
                    "tokenizer/tokenizer.json", "tokenizer/tokenizer_config.json")
        if any(not (path / name).is_file() for name in required):
            raise ValueError("The pinned Laya snapshot is incomplete: needs config, encoder, tokenizer and model.safetensors.")
        config_path = path / "rl_agent_config.json"
        encoder_path = path / "encoder/config.json"
        if config_path.stat().st_size > 65536 or encoder_path.stat().st_size > 65536:
            raise ValueError("Laya configuration files exceed their expected bounds.")
        cfg = loads(config_path.read_text(encoding="utf-8"))
        encoder = loads(encoder_path.read_text(encoding="utf-8"))
        if cfg.get("max_len") != 512 or not isinstance(cfg.get("head_max_len"), int) or not 64 <= cfg["head_max_len"] < 512:
            raise ValueError("Use the pinned general English Laya checkpoint with its 512-token context.")
        if encoder.get("model_type") != "modernbert" or "auto_map" in encoder:
            raise ValueError("Expected the local ModernBERT encoder configuration without remote code.")
        size = (path / "model.safetensors").stat().st_size
        if not 750_000_000 <= size <= 1_900_000_000:
            raise ValueError("The root English Laya safetensors file has an unexpected size or is an LFS pointer.")
        self._path, self._config = path, cfg

    def import_library(self) -> None:
        """A separate admitted initialization phase, never a detached task."""
        if self._path is None:
            raise RuntimeError("Configure local Laya assets first.")
        if version("laya") != "0.3.4":
            raise RuntimeError("Install the pinned Laya 0.3.4 SDK.")
        provenance = distribution("laya").read_text("direct_url.json")
        if not provenance or loads(provenance).get("vcs_info", {}).get("commit_id") != SDK_REVISION:
            raise RuntimeError("Laya must be installed from the exact configured SDK source revision.")
        import laya
        # Bind the public API; no alternative SDK, remote model, or dependency
        # compatibility shim is tried.
        signature(laya.load).bind(str(self._path), device="cpu")
        self._library = laya

    def load_model(self) -> None:
        if self._agent is not None:
            raise RuntimeError("Laya is already loaded; run rollover must only reset memory.")
        if self._library is None or self._path is None:
            raise RuntimeError("Import the pinned SDK first.")
        # The pinned SDK treats an existing directory as local. All encoder,
        # tokenizer and weight files were checked. No model repository ID, token,
        # remote code or network download is used.
        agent = self._library.load(str(self._path), device="cpu")
        signature(agent.predict).bind("", {"next_action": {
            "type": "choice", "instructions": "Choose.", "criteria": {"wait": "Wait"}}})
        if not isinstance(agent.cfg, dict):
            raise TypeError("Loaded Laya configuration is not a dictionary.")
        if agent.cfg.get("max_len") != 512 or agent.cfg.get("head_max_len") != self._config["head_max_len"]:
            raise RuntimeError("Loaded Laya configuration differs from the pinned input contract.")
        if not callable(agent.tok) or not callable(agent.tok.decode):
            raise TypeError("Loaded Laya does not expose its inspected tokenizer API.")
        self._agent = agent

    def reset_run(self) -> None:
        """Discard only decision memory; retain the already loaded model."""
        self._objective, self._objective_at = "", 0
        self._steps = self._same = 0
        self._recent.clear()
        self._dialogue.clear()
        self._visits.clear()
        self._transitions.clear()
        self._milestones.clear()
        self._last_action = self._last_effect = ""
        self._last_map = None

    def _state(self, o: Observation) -> str:
        # Salient information first; optional memory at the end can be omitted to
        # fit the actual SDK sequence budget. No hidden enemy details are passed.
        lines = [f"Pokemon Red. {o.mode}. Goal:{self._objective or 'choose an objective'}.",
                 f"{o.location} x{o.x} y{o.y} facing{o.facing}; badges{o.badges.bit_count()}/8."]
        if o.battle:
            lines.append(f"{o.battle} battle; foe {o.enemy or 'not yet visible'}.")
        if o.party:
            lines.append("Party:" + ";".join(f"{i}:{p.name}/{p.species} L{p.level} HP{p.hp}/{p.max_hp} {p.status}"
                                           for i, p in enumerate(o.party)))
            active = o.party[o.active_slot]
            lines.append(f"Active {o.active_slot} moves:" + ";".join(
                f"{m.name}/{m.kind}/power{m.power}/PP{m.pp}" for m in active.moves))
        else:
            lines.append("No Pokemon acquired yet.")
        if o.text:
            lines.append("Visible text:" + " / ".join(o.text)[-300:])
        if o.menu:
            lines.append(f"Cursor:{o.cursor}. Choices describe visible menu entries.")
        lines.append(f"Last:{self._last_action} -> {self._last_effect}.")
        if self.stalled:
            lines.append("STALLED: repeated observations. Reconsider goal/direction; do not repeat blindly.")
        if o.mode == "overworld":
            visits = []
            for direction, dx, dy in (("up", 0, -1), ("down", 0, 1), ("left", -1, 0), ("right", 1, 0)):
                visits.append(f"{direction}:{self._visits.get((o.map_id, o.x + dx, o.y + dy), 0)}")
            lines.append("Neighbor visits " + ",".join(visits) + "; " + ",".join(o.objects))
        if o.bag:
            lines.append("Bag:" + ",".join(f"{name}x{count}" for _, name, count in o.bag))
        lines.append(f"Money:{o.money}; seen progress:" + ",".join(self._milestones[-6:]))
        if self._dialogue:
            lines.append("Recent dialogue:" + " / ".join(self._dialogue)[-180:])
        if self._transitions:
            lines.append("Recent travel:" + " / ".join(tuple(self._transitions)[-3:]))
        return "\n".join(lines)

    def _predict(self, state: str, options: dict[str, str], deadline: float) -> tuple:
        if self._agent is None:
            raise RuntimeError("The real Laya model is not loaded.")
        if monotonic() >= deadline:
            raise TimeoutError("No inference budget remains.")
        question = {"type": "choice", "instructions": "Choose the next action toward the current objective.",
                    "criteria": options}
        # Measure our exact text with the loaded tokenizer; reserve headroom for
        # SDK delimiters. This is explicitly TEXT-token accounting, not a claim
        # about private renderer overhead, padding or an uninspected SDK helper.
        head_limit = self._config["head_max_len"]
        option_text = question["instructions"] + "\n" + "\n".join(f"{key}: {value}" for key, value in options.items())
        option_tokens = len(self._agent.tok.encode(option_text, add_special_tokens=False))
        if option_tokens > head_limit - 48:
            raise RuntimeError("Legal action descriptions exceed Laya's option-token budget.")
        original = self._agent.tok.encode(state, add_special_tokens=False)
        budget = max(0, 512 - head_limit - 8)
        kept = min(budget, len(original))
        compact = self._agent.tok.decode(original[:kept], skip_special_tokens=True)
        state_tokens = len(self._agent.tok.encode(compact, add_special_tokens=False))
        if state_tokens > budget:
            raise RuntimeError("Laya tokenizer round-trip exceeded the state-token budget.")
        started = monotonic()
        result = self._agent.predict(compact, {"next_action": question})
        elapsed = (monotonic() - started) * 1000
        if monotonic() >= deadline:
            raise TimeoutError("Laya inference exceeded the per-request CPU budget.")
        if not isinstance(result, dict):
            raise TypeError("Laya returned a non-object result.")
        answer = result.get("answers", {}).get("next_action")
        if not isinstance(answer, dict) or answer.get("choice") not in options:
            raise RuntimeError("Laya returned an action outside the supplied legal choices.")
        confidence = answer.get("confidence")
        if not isinstance(confidence, (int, float)) or not isfinite(confidence) or not 0 <= confidence <= 1:
            raise RuntimeError("Laya returned invalid option concentration metadata.")
        return answer["choice"], float(confidence), elapsed, state_tokens + option_tokens, state_tokens, len(original) - kept

    def decide(self, o: Observation, legal: tuple[LegalAction, ...], deadline: float) -> Decision:
        if not legal or len({a.identifier for a in legal}) != len(legal):
            raise RuntimeError("The legal-action set is empty or ambiguous.")
        # Deterministic animation waits are not advertised as model decisions.
        if len(legal) == 1 and legal[0].identifier == "wait":
            return Decision("wait", legal[0].description, "Animation wait",
                            0, 0, 0, 0, None, 0, "animation", self.stalled)
        measurements = []
        if not self._objective or (o.mode == "overworld" and
                (self._steps - self._objective_at >= 12 or self._last_map != o.map_id or self.stalled)):
            goals = {
                "explore": "Explore unvisited nearby routes/rooms",
                "interact": "Talk/read/interact to learn story tasks",
                "story": "Follow observed story task; gain badges",
                "recover": "Heal party, restore PP, recover after blackout",
                "train": "Train/catch/select party for upcoming battles",
            }
            goal = self._predict(self._state(o), goals, deadline)
            self._objective = goals[goal[0]]
            self._objective_at = self._steps
            measurements.append(goal)
        options = {a.identifier: a.description for a in legal}
        choice = self._predict(self._state(o), options, deadline)
        measurements.append(choice)
        action = next(a for a in legal if a.identifier == choice[0])
        return Decision(action.identifier, action.description, self._objective,
                        sum(m[2] for m in measurements), sum(m[3] for m in measurements),
                        sum(m[4] for m in measurements), sum(m[5] for m in measurements),
                        choice[1], len(measurements), "laya", self.stalled)

    def record_transition(self, before: Observation, after: Observation, decision: Decision) -> None:
        """Remember observed effects, never claim an objective was achieved by intent."""
        self._steps += 1
        key = after.progress_key()
        self._same = self._same + 1 if before.progress_key() == key else 0
        self._recent.append(key)
        self._last_action = decision.action
        self._last_effect = "no observed change" if before.progress_key() == key else after.summary()
        if after.mode == "overworld":
            position = (after.map_id, after.x, after.y)
            self._visits[position] = self._visits.get(position, 0) + 1
            self._visits.move_to_end(position)
            if len(self._visits) > 4096:
                self._visits.popitem(last=False)
        if before.map_id != after.map_id:
            self._transitions.append(f"{before.location}->{after.location}")
        self._last_map = after.map_id
        if after.text and after.mode in ("dialogue", "battle_text"):
            text = " ".join(after.text)[-220:]
            if not self._dialogue or text != self._dialogue[-1]:
                self._dialogue.append(text)
        observed = []
        if after.party:
            observed.append("first Pokemon acquired")
        if any("PARCEL" in name.upper() for _, name, _ in after.bag):
            observed.append("Oak's parcel in bag")
        if any("POKéDEX" in entry.label or "POKDEX" in entry.label for entry in after.menu):
            observed.append("Pokedex menu observed")
        if after.badges & 1:
            observed.append("Boulder badge acquired")
        if after.map_id in (3, 58, 59, 60):
            observed.append("Mt. Moon/Cerulean region reached")
        if "BLACKED OUT" in " ".join(after.text).upper():
            observed.append("blackout observed")
        for milestone in observed:
            if milestone not in self._milestones:
                self._milestones.append(milestone)
