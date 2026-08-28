"""
Tool definitions (Anthropic tool_use schema) and execution logic.
"""
import os
from pathlib import Path
from app.config import SKILLS_DIR, ARTIFACT_TYPES


# ── Schema ────────────────────────────────────────────────

TOOL_SCHEMAS = [
    {
        "name": "read_file",
        "description": (
            "Read the contents of a file. "
            "Paths are resolved relative to the project workspace. "
            "Skill directory files (under skills/) are read-only accessible."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "File path (absolute or relative to workspace)"}
            },
            "required": ["path"],
        },
    },
    {
        "name": "list_dir",
        "description": "List the contents of a directory.",
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Directory path"}
            },
            "required": ["path"],
        },
    },
    {
        "name": "write_file",
        "description": "Write content to a file in the project workspace.",
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "File path relative to workspace"},
                "content": {"type": "string", "description": "File content"},
            },
            "required": ["path", "content"],
        },
    },
    {
        "name": "run_command",
        "description": (
            "Execute a shell command (bash, python, Rscript, etc.) "
            "in the project workspace directory."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "command": {"type": "string", "description": "The command to execute"},
                "timeout": {
                    "type": "number",
                    "description": "Timeout in seconds. Omit for no limit.",
                },
            },
            "required": ["command"],
        },
    },
    {
        "name": "ask_user",
        "description": (
            "Pause and ask the user a question. "
            "Use for decisions that require human judgement "
            "(e.g. confirming sample groupings, choosing analysis parameters). "
            "The run will pause until the user replies."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "question": {"type": "string"},
                "choices": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Optional list of suggested choices",
                },
            },
            "required": ["question"],
        },
    },
]


# ── Execution ─────────────────────────────────────────────

class ToolContext:
    def __init__(self, workspace: Path, emit, executor, cancel_event):
        self.workspace = workspace
        self.emit = emit           # async fn(type, payload)
        self.executor = executor
        self.cancel_event = cancel_event

    def _resolve(self, path: str) -> Path:
        p = Path(path)
        if p.is_absolute():
            return p
        # Try project root first (e.g., skills/... paths)
        from app.config import BASE_DIR
        root_candidate = BASE_DIR / p
        if root_candidate.exists():
            return root_candidate
        return self.workspace / p

    def _check_read(self, p: Path) -> None:
        resolved = p.resolve()
        in_workspace = str(resolved).startswith(str(self.workspace.resolve()))
        in_skills = str(resolved).startswith(str(SKILLS_DIR.resolve()))
        if not (in_workspace or in_skills):
            raise PermissionError(f"Path outside allowed directories: {p}")

    def _check_write(self, p: Path) -> None:
        resolved = p.resolve()
        if not str(resolved).startswith(str(self.workspace.resolve())):
            raise PermissionError(f"Write not allowed outside workspace: {p}")

    # ── tool handlers ──────────────────────────────────────

    async def read_file(self, path: str) -> str:
        p = self._resolve(path)
        self._check_read(p)
        if not p.exists():
            return f"Error: file not found: {p}"
        return p.read_text(errors="replace")

    async def list_dir(self, path: str) -> str:
        p = self._resolve(path)
        self._check_read(p)
        if not p.exists():
            return f"Error: directory not found: {p}"
        entries = sorted(p.iterdir(), key=lambda e: (not e.is_dir(), e.name))
        lines = []
        for e in entries:
            prefix = "/" if e.is_dir() else " "
            size = f" ({e.stat().st_size}B)" if e.is_file() else ""
            lines.append(f"{prefix} {e.name}{size}")
        return "\n".join(lines) if lines else "(empty)"

    async def write_file(self, path: str, content: str) -> str:
        p = self._resolve(path)
        self._check_write(p)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content)
        # Register artifact immediately
        rel = p.relative_to(self.workspace)
        ext = p.suffix.lower()
        atype = ARTIFACT_TYPES.get(ext, "file")
        await self.emit("artifact_created", {
            "path": str(rel),
            "artifact_type": atype,
            "size": p.stat().st_size,
        })
        return f"Written {p.stat().st_size} bytes to {rel}"

    async def run_command(self, command: str, timeout: float | None = None) -> dict:
        # Snapshot watched dirs before execution
        before = self._snapshot_workspace()

        async def on_stdout(chunk: str):
            await self.emit("stdout_chunk", {"chunk": chunk})

        result = await self.executor.run(
            command=command,
            cwd=str(self.workspace),
            timeout=timeout,
            stdout_callback=on_stdout,
            cancel_event=self.cancel_event,
        )

        # Discover new/modified artifacts
        after = self._snapshot_workspace()
        new_paths = [p for p in after if p not in before or after[p] != before[p]]
        for rel_str, size in [(p, after[p]) for p in new_paths]:
            ext = Path(rel_str).suffix.lower()
            atype = ARTIFACT_TYPES.get(ext, "file")
            await self.emit("artifact_created", {
                "path": rel_str,
                "artifact_type": atype,
                "size": size,
            })

        return {
            "exit_code": result.exit_code,
            "stdout": result.stdout[-8000:] if len(result.stdout) > 8000 else result.stdout,
            "stderr": result.stderr[-4000:] if len(result.stderr) > 4000 else result.stderr,
            "timed_out": result.timed_out,
        }

    def _snapshot_workspace(self) -> dict[str, int]:
        """Return {relative_path: size} for monitored directories."""
        from app.config import ARTIFACT_WATCH_DIRS, ARTIFACT_IGNORE_DIRS
        snapshot: dict[str, int] = {}
        for watch in ARTIFACT_WATCH_DIRS:
            d = self.workspace / watch
            if not d.exists():
                continue
            for p in d.rglob("*"):
                if p.is_file():
                    parts = set(p.parts)
                    if not parts & ARTIFACT_IGNORE_DIRS:
                        try:
                            snapshot[str(p.relative_to(self.workspace))] = p.stat().st_size
                        except Exception:
                            pass
        return snapshot

    # ── dispatch ───────────────────────────────────────────

    async def execute(self, tool_name: str, tool_input: dict):
        if tool_name == "read_file":
            return await self.read_file(**tool_input)
        elif tool_name == "list_dir":
            return await self.list_dir(**tool_input)
        elif tool_name == "write_file":
            return await self.write_file(**tool_input)
        elif tool_name == "run_command":
            return await self.run_command(**tool_input)
        elif tool_name == "ask_user":
            return "ASK_USER"  # Handled specially in the loop
        else:
            return f"Error: unknown tool '{tool_name}'"
