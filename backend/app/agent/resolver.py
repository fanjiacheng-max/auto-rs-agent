"""
Dependency Resolver.

Reads module_registry.yaml + status.json to produce an ExecutionPlan:
  - which modules need to run (computational dependencies, auto-filled)
  - which gates are unconfirmed (must ask_user before running)
  - which required inputs are missing (must ask_user)

The agent loop calls resolve() before starting execution.
The LLM never decides the dependency graph — this module does.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from app.agent.project_state import ProjectState

_REGISTRY_PATH = Path(__file__).parent / "module_registry.yaml"


def _load_registry() -> dict:
    return yaml.safe_load(_REGISTRY_PATH.read_text())


# ── Result types ──────────────────────────────────────────────────────────

@dataclass
class ExecutionPlan:
    """
    What the agent needs to do before running the target module.

    modules_to_run: ordered list of module names to enable (includes deps).
                    Empty means all required deps are already cached.
    blocking_gates: gates that must be confirmed by the user before execution.
                    Agent must call ask_user for each.
    missing_inputs: required config inputs not yet recorded in status.json.
                    Agent must call ask_user for each.
    target_module:  the module the user actually asked for.
    already_done:   modules already completed (cache verified), skipped.
    """
    target_module: str
    modules_to_run: list[str] = field(default_factory=list)
    blocking_gates: list[str] = field(default_factory=list)
    missing_inputs: list[str] = field(default_factory=list)
    already_done: list[str] = field(default_factory=list)

    @property
    def can_run(self) -> bool:
        return not self.blocking_gates and not self.missing_inputs

    def summary(self) -> str:
        lines = [f"Target: {self.target_module}"]
        if self.already_done:
            lines.append(f"Cached (skip): {', '.join(self.already_done)}")
        if self.modules_to_run:
            lines.append(f"Will run: {', '.join(self.modules_to_run)}")
        if self.blocking_gates:
            lines.append(f"Blocking gates: {', '.join(self.blocking_gates)}")
        if self.missing_inputs:
            lines.append(f"Missing inputs: {', '.join(self.missing_inputs)}")
        return "\n".join(lines)


# ── Resolver ──────────────────────────────────────────────────────────────

class DependencyResolver:
    def __init__(self, registry: dict | None = None):
        self._reg = registry or _load_registry()

    # ── Public ────────────────────────────────────────────────────────────

    async def resolve(
        self,
        target_module: str,
        ps: ProjectState,
        remote_cwd: str | None = None,
    ) -> ExecutionPlan:
        """
        Build an ExecutionPlan for the requested target_module.

        remote_cwd: if provided, verify checkpoint existence on remote
                    (SSH ls). If None, trust status.json module records only.
        """
        modules = self._reg["modules"]
        gates_reg = self._reg["gates"]

        if target_module not in modules:
            raise ValueError(f"Unknown module: '{target_module}'. "
                             f"Known: {list(modules.keys())}")

        # 1. Topological sort: target + all transitive deps
        ordered = self._topo_sort(target_module, modules)

        # 2. For each module, check if already done
        state = await ps.read()
        already_done: list[str] = []
        to_run: list[str] = []

        for mod in ordered:
            if await self._is_cached(mod, state, modules, remote_cwd):
                already_done.append(mod)
            else:
                to_run.append(mod)

        # 3. Collect blocking gates (from ALL modules in to_run, deduplicated)
        seen_gates: set[str] = set()
        blocking_gates: list[str] = []
        for mod in to_run:
            for gate in modules[mod].get("gates", []):
                if gate in seen_gates:
                    continue
                seen_gates.add(gate)
                gate_state = state["gates"].get(gate, {})
                if not gate_state.get("confirmed", False):
                    blocking_gates.append(gate)

        # 4. Collect missing required inputs (from target module only)
        missing_inputs: list[str] = []
        for inp in modules[target_module].get("required_inputs", []):
            # Check status.json inputs section or gates values
            val = state.get("inputs", {}).get(inp)
            if val is None:
                # Also check gates that might satisfy this input
                if not any(
                    state["gates"].get(g, {}).get("confirmed") and
                    state["gates"].get(g, {}).get("value")
                    for g in gates_reg
                    if g == inp or g.startswith(inp)
                ):
                    missing_inputs.append(inp)

        return ExecutionPlan(
            target_module=target_module,
            modules_to_run=to_run,
            blocking_gates=blocking_gates,
            missing_inputs=missing_inputs,
            already_done=already_done,
        )

    def gate_question(self, gate_name: str) -> tuple[str, list[str] | None]:
        """Return (question_text, choices | None) for a gate."""
        gate = self._reg["gates"].get(gate_name, {})
        return gate.get("question", f"Please confirm: {gate_name}"), None

    def module_config_key(self, module_name: str) -> str | None:
        return self._reg["modules"].get(module_name, {}).get("config_key")

    def modules_to_enable(self, plan: ExecutionPlan) -> list[str]:
        """Return config keys to set enabled=TRUE for this plan."""
        keys = []
        for mod in plan.modules_to_run:
            key = self.module_config_key(mod)
            if key:
                keys.append(key)
        return keys

    # ── Private ───────────────────────────────────────────────────────────

    def _topo_sort(self, target: str, modules: dict) -> list[str]:
        """
        Return modules in execution order (deps before target).
        Uses iterative DFS, raises on cycles.
        """
        order: list[str] = []
        visited: set[str] = set()
        in_stack: set[str] = set()

        def visit(name: str) -> None:
            if name in visited:
                return
            if name in in_stack:
                raise ValueError(f"Cycle detected in module dependencies at '{name}'")
            if name not in modules:
                raise ValueError(f"Unknown dependency module: '{name}'")
            in_stack.add(name)
            for dep in modules[name].get("requires_modules", []):
                visit(dep)
            in_stack.discard(name)
            visited.add(name)
            order.append(name)

        visit(target)
        return order

    async def _is_cached(
        self,
        module_name: str,
        state: dict,
        modules: dict,
        remote_cwd: str | None,
    ) -> bool:
        """
        True if this module's output is already available.
        Primary: check status.json modules[module_name].status == "completed".
        Secondary (if remote_cwd provided): verify checkpoint dir exists on remote.
        """
        mod_state = state.get("modules", {}).get(module_name, {})
        if mod_state.get("status") != "completed":
            return False

        # If we have remote access, verify the checkpoint actually exists
        if remote_cwd and mod_state.get("checkpoint_path"):
            checkpoint = f"{remote_cwd}/{mod_state['checkpoint_path']}"
            exists = await self._remote_path_exists(checkpoint)
            if not exists:
                return False

        return True

    @staticmethod
    async def _remote_path_exists(remote_path: str) -> bool:
        """Check if a path exists on the remote server via SSH."""
        import asyncio
        from app.config import SSH_HOST
        try:
            proc = await asyncio.create_subprocess_exec(
                "ssh", SSH_HOST, f"test -e {remote_path} && echo yes",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.DEVNULL,
            )
            stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=10)
            return stdout.decode().strip() == "yes"
        except Exception:
            return False  # on SSH failure, assume not cached (safe default)
