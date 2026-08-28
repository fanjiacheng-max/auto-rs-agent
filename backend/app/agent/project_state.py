"""
ProjectState — reads and writes workspace/status.json.

This file is the source of truth for:
  - gate confirmations (sample_sheet_review, annotation_review, ...)
  - module execution status and checkpoint paths
  - tried parameter combinations per module
  - free-form notes (written by both agent and user)

Design rules:
  - All writes go through ProjectState methods (never raw json.dump elsewhere)
  - `notes` field: agent appends, never overwrites — user edits are preserved
  - File is always valid JSON; corrupt file raises, never silently ignored
  - Thread-safety: callers hold an asyncio lock per project (see _locks below)
"""
import asyncio
import json
from datetime import datetime, timezone
from pathlib import Path


# Per-project write locks (keyed by workspace path string)
_locks: dict[str, asyncio.Lock] = {}


def _lock_for(workspace: Path) -> asyncio.Lock:
    key = str(workspace)
    if key not in _locks:
        _locks[key] = asyncio.Lock()
    return _locks[key]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


# ── Schema helpers ────────────────────────────────────────────────────────

def _empty_gate() -> dict:
    return {"confirmed": False, "value": None, "confirmed_at": None}


def _empty_module() -> dict:
    return {
        "status": "pending",       # pending | running | completed | failed
        "completed_at": None,
        "checkpoint_path": None,
        "checkpoint_verified": False,
    }


def _initial_state(project_name: str) -> dict:
    ts = _now()
    return {
        "project_name": project_name,
        "created_at": ts,
        "last_updated": ts,
        "inputs": {
            "species": None,
            "data_source": None,
            "sample_sheet_path": None,
        },
        "gates": {
            "sample_sheet_review": _empty_gate(),
            "annotation_review": _empty_gate(),
            "contrast_confirmation": _empty_gate(),
            "pseudotime_config": _empty_gate(),
            "hdwgcna_config": _empty_gate(),
        },
        "modules": {},      # populated on first module run
        "tried_params": {}, # {module_name: [param_attempt, ...]}
        "next_steps": [],
        "notes": "",
    }


# ── ProjectState ──────────────────────────────────────────────────────────

class ProjectState:
    """
    Thin wrapper around status.json.
    All public methods are async and acquire the per-project lock.
    """

    def __init__(self, workspace: Path):
        self.workspace = workspace
        self._path = workspace / "status.json"
        self._lock = _lock_for(workspace)

    # ── I/O ───────────────────────────────────────────────────────────────

    def _read(self) -> dict:
        """Synchronous read — called inside the async lock."""
        if not self._path.exists():
            raise FileNotFoundError(f"status.json not found at {self._path}")
        return json.loads(self._path.read_text())

    def _write(self, state: dict) -> None:
        """Synchronous write with atomic replace."""
        state["last_updated"] = _now()
        tmp = self._path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(state, indent=2, ensure_ascii=False))
        tmp.replace(self._path)

    # ── Init ──────────────────────────────────────────────────────────────

    @classmethod
    async def create(cls, workspace: Path, project_name: str) -> "ProjectState":
        """Create status.json for a new project. Idempotent."""
        ps = cls(workspace)
        async with ps._lock:
            if not ps._path.exists():
                workspace.mkdir(parents=True, exist_ok=True)
                ps._write(_initial_state(project_name))
        return ps

    @classmethod
    def open(cls, workspace: Path) -> "ProjectState":
        """Open existing state (no I/O yet)."""
        return cls(workspace)

    # ── Read ──────────────────────────────────────────────────────────────

    async def read(self) -> dict:
        async with self._lock:
            return self._read()

    async def get_gate(self, gate_name: str) -> dict:
        async with self._lock:
            state = self._read()
            return state["gates"].get(gate_name, _empty_gate())

    async def is_gate_confirmed(self, gate_name: str) -> bool:
        g = await self.get_gate(gate_name)
        return bool(g.get("confirmed"))

    async def get_gate_value(self, gate_name: str):
        g = await self.get_gate(gate_name)
        return g.get("value")

    async def get_module(self, module_name: str) -> dict:
        async with self._lock:
            state = self._read()
            return state["modules"].get(module_name, _empty_module())

    async def is_module_completed(self, module_name: str) -> bool:
        m = await self.get_module(module_name)
        return m.get("status") == "completed"

    async def get_tried_params(self, module_name: str) -> list[dict]:
        async with self._lock:
            state = self._read()
            return state.get("tried_params", {}).get(module_name, [])

    # ── Write: gates ──────────────────────────────────────────────────────

    async def confirm_gate(self, gate_name: str, value) -> None:
        """Mark a gate as confirmed and persist its value."""
        async with self._lock:
            state = self._read()
            state["gates"].setdefault(gate_name, _empty_gate())
            state["gates"][gate_name].update({
                "confirmed": True,
                "value": value,
                "confirmed_at": _now(),
            })
            self._write(state)

    # ── Write: inputs ─────────────────────────────────────────────────────

    async def set_input(self, key: str, value) -> None:
        async with self._lock:
            state = self._read()
            state["inputs"][key] = value
            self._write(state)

    # ── Write: modules ────────────────────────────────────────────────────

    async def set_module_status(
        self,
        module_name: str,
        status: str,                    # pending | running | completed | failed
        checkpoint_path: str | None = None,
        checkpoint_verified: bool = False,
    ) -> None:
        async with self._lock:
            state = self._read()
            state["modules"].setdefault(module_name, _empty_module())
            m = state["modules"][module_name]
            m["status"] = status
            if status == "completed":
                m["completed_at"] = _now()
            if checkpoint_path is not None:
                m["checkpoint_path"] = checkpoint_path
                m["checkpoint_verified"] = checkpoint_verified
            self._write(state)

    # ── Write: tried_params ───────────────────────────────────────────────

    async def record_tried_params(
        self,
        module_name: str,
        params: dict,
        run_id: str,
        selected: bool = False,
    ) -> None:
        """
        Append a parameter attempt. If selected=True, mark all previous
        attempts for this module as selected=False first.
        """
        async with self._lock:
            state = self._read()
            tp = state.setdefault("tried_params", {})
            attempts = tp.setdefault(module_name, [])
            if selected:
                for a in attempts:
                    a["selected"] = False
            attempts.append({**params, "selected": selected,
                             "run_id": run_id, "tried_at": _now()})
            self._write(state)

    async def was_param_tried(self, module_name: str, params: dict) -> bool:
        """Check if this exact param set was already attempted (avoids re-running)."""
        attempts = await self.get_tried_params(module_name)
        check_keys = set(params.keys())
        for a in attempts:
            if all(a.get(k) == v for k, v in params.items()):
                return True
        return False

    # ── Write: next_steps & notes ─────────────────────────────────────────

    async def set_next_steps(self, steps: list[str]) -> None:
        async with self._lock:
            state = self._read()
            state["next_steps"] = steps
            self._write(state)

    async def append_note(self, note: str) -> None:
        """Agent appends; never overwrites existing content."""
        async with self._lock:
            state = self._read()
            existing = state.get("notes", "").strip()
            ts = _now()[:19].replace("T", " ")
            new_entry = f"[{ts}] {note.strip()}"
            state["notes"] = f"{existing}\n{new_entry}".strip()
            self._write(state)
