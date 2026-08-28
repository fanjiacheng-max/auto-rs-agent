import uuid
import json
from datetime import datetime, timezone
from pathlib import Path
import aiosqlite
from app.config import DB_PATH, WORKSPACE_DIR

DDL = """
CREATE TABLE IF NOT EXISTS projects (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    workspace_path TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS runs (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL,
    trigger_message_id TEXT,
    status TEXT NOT NULL DEFAULT 'pending',
    skill_name TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY (project_id) REFERENCES projects(id)
);

CREATE TABLE IF NOT EXISTS messages (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL,
    run_id TEXT,
    role TEXT NOT NULL,
    content TEXT NOT NULL,
    created_at TEXT NOT NULL,
    FOREIGN KEY (project_id) REFERENCES projects(id),
    FOREIGN KEY (run_id) REFERENCES runs(id)
);

CREATE TABLE IF NOT EXISTS events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id TEXT NOT NULL,
    type TEXT NOT NULL,
    payload TEXT NOT NULL,
    created_at TEXT NOT NULL,
    FOREIGN KEY (run_id) REFERENCES runs(id)
);

CREATE TABLE IF NOT EXISTS artifacts (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL,
    run_id TEXT NOT NULL,
    path TEXT NOT NULL,
    artifact_type TEXT NOT NULL,
    size INTEGER,
    created_at TEXT NOT NULL,
    FOREIGN KEY (project_id) REFERENCES projects(id),
    FOREIGN KEY (run_id) REFERENCES runs(id)
);

CREATE TABLE IF NOT EXISTS run_state (
    run_id TEXT PRIMARY KEY,
    pending_messages TEXT NOT NULL,     -- JSON: LLM message history at pause point
    pending_tool_use_id TEXT NOT NULL,  -- tool_use_id of the ask_user call
    FOREIGN KEY (run_id) REFERENCES runs(id)
);
"""


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


async def init_db() -> None:
    WORKSPACE_DIR.mkdir(parents=True, exist_ok=True)
    async with aiosqlite.connect(DB_PATH) as db:
        await db.executescript(DDL)
        await db.commit()


async def get_db():
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        yield db


# ── Projects ──────────────────────────────────────────────

async def create_project(db, name: str) -> dict:
    pid = str(uuid.uuid4())
    workspace_path = str(WORKSPACE_DIR / pid)
    Path(workspace_path).mkdir(parents=True, exist_ok=True)
    ts = now()
    await db.execute(
        "INSERT INTO projects VALUES (?,?,?,?,?)",
        (pid, name, workspace_path, ts, ts),
    )
    await db.commit()
    # Initialise status.json for the new project
    from app.agent.project_state import ProjectState
    await ProjectState.create(Path(workspace_path), name)
    return {"id": pid, "name": name, "workspace_path": workspace_path,
            "created_at": ts, "updated_at": ts}


async def list_projects(db) -> list[dict]:
    async with db.execute("SELECT * FROM projects ORDER BY created_at DESC") as cur:
        rows = await cur.fetchall()
    return [dict(r) for r in rows]


async def get_project(db, pid: str) -> dict | None:
    async with db.execute("SELECT * FROM projects WHERE id=?", (pid,)) as cur:
        row = await cur.fetchone()
    return dict(row) if row else None


async def delete_project(db, pid: str) -> None:
    await db.execute("DELETE FROM projects WHERE id=?", (pid,))
    await db.commit()


async def rename_project(db, pid: str, name: str) -> None:
    await db.execute("UPDATE projects SET name=?, updated_at=? WHERE id=?",
                     (name, now(), pid))
    await db.commit()


# ── Runs ──────────────────────────────────────────────────

ACTIVE_STATUSES = ("pending", "running", "waiting_for_user")


async def active_run_for_project(db, project_id: str) -> dict | None:
    async with db.execute(
        f"SELECT * FROM runs WHERE project_id=? AND status IN ({','.join('?'*len(ACTIVE_STATUSES))})",
        (project_id, *ACTIVE_STATUSES),
    ) as cur:
        row = await cur.fetchone()
    return dict(row) if row else None


async def create_run(db, project_id: str, trigger_message_id: str) -> dict:
    rid = str(uuid.uuid4())
    ts = now()
    await db.execute(
        "INSERT INTO runs VALUES (?,?,?,?,?,?,?)",
        (rid, project_id, trigger_message_id, "pending", None, ts, ts),
    )
    await db.commit()
    return {"id": rid, "project_id": project_id,
            "trigger_message_id": trigger_message_id,
            "status": "pending", "skill_name": None,
            "created_at": ts, "updated_at": ts}


async def update_run_status(db, run_id: str, status: str, skill_name: str | None = None) -> None:
    if skill_name is not None:
        await db.execute(
            "UPDATE runs SET status=?, skill_name=?, updated_at=? WHERE id=?",
            (status, skill_name, now(), run_id),
        )
    else:
        await db.execute(
            "UPDATE runs SET status=?, updated_at=? WHERE id=?",
            (status, now(), run_id),
        )
    await db.commit()


async def get_run(db, run_id: str) -> dict | None:
    async with db.execute("SELECT * FROM runs WHERE id=?", (run_id,)) as cur:
        row = await cur.fetchone()
    return dict(row) if row else None


async def list_runs(db, project_id: str) -> list[dict]:
    async with db.execute(
        "SELECT * FROM runs WHERE project_id=? ORDER BY created_at DESC", (project_id,)
    ) as cur:
        rows = await cur.fetchall()
    return [dict(r) for r in rows]


# ── Messages ──────────────────────────────────────────────

async def create_message(db, project_id: str, role: str, content: str,
                         run_id: str | None = None) -> dict:
    mid = str(uuid.uuid4())
    ts = now()
    await db.execute(
        "INSERT INTO messages VALUES (?,?,?,?,?,?)",
        (mid, project_id, run_id, role, content, ts),
    )
    await db.commit()
    return {"id": mid, "project_id": project_id, "run_id": run_id,
            "role": role, "content": content, "created_at": ts}


async def list_messages(db, project_id: str, limit: int = 20) -> list[dict]:
    async with db.execute(
        "SELECT * FROM messages WHERE project_id=? ORDER BY created_at DESC LIMIT ?",
        (project_id, limit),
    ) as cur:
        rows = await cur.fetchall()
    return list(reversed([dict(r) for r in rows]))


# ── Events ────────────────────────────────────────────────

async def append_event(db, run_id: str, event_type: str, payload: dict) -> int:
    ts = now()
    cur = await db.execute(
        "INSERT INTO events (run_id, type, payload, created_at) VALUES (?,?,?,?)",
        (run_id, event_type, json.dumps(payload), ts),
    )
    await db.commit()
    return cur.lastrowid  # type: ignore[return-value]


async def get_events_after(db, run_id: str, cursor: int) -> list[dict]:
    async with db.execute(
        "SELECT * FROM events WHERE run_id=? AND id>? ORDER BY id ASC",
        (run_id, cursor),
    ) as cur:
        rows = await cur.fetchall()
    return [dict(r) for r in rows]


# ── Artifacts ─────────────────────────────────────────────

async def upsert_artifact(db, project_id: str, run_id: str,
                          rel_path: str, artifact_type: str, size: int) -> dict:
    # Check if artifact for this path already exists (update run association)
    async with db.execute(
        "SELECT id FROM artifacts WHERE project_id=? AND path=?", (project_id, rel_path)
    ) as cur:
        existing = await cur.fetchone()

    ts = now()
    if existing:
        aid = existing["id"]
        await db.execute(
            "UPDATE artifacts SET run_id=?, artifact_type=?, size=?, created_at=? WHERE id=?",
            (run_id, artifact_type, size, ts, aid),
        )
    else:
        aid = str(uuid.uuid4())
        await db.execute(
            "INSERT INTO artifacts VALUES (?,?,?,?,?,?,?)",
            (aid, project_id, run_id, rel_path, artifact_type, size, ts),
        )
    await db.commit()
    return {"id": aid, "project_id": project_id, "run_id": run_id,
            "path": rel_path, "artifact_type": artifact_type, "size": size, "created_at": ts}


async def list_artifacts(db, project_id: str) -> list[dict]:
    async with db.execute(
        "SELECT * FROM artifacts WHERE project_id=? ORDER BY created_at DESC", (project_id,)
    ) as cur:
        rows = await cur.fetchall()
    return [dict(r) for r in rows]


async def set_run_pending_question(db, run_id: str, question: str,
                                   choices: list[str] | None) -> None:
    payload = json.dumps({"question": question, "choices": choices})
    await db.execute(
        "UPDATE runs SET status='waiting_for_user', updated_at=? WHERE id=?",
        (now(), run_id),
    )
    await db.execute(
        "INSERT INTO events (run_id, type, payload, created_at) VALUES (?,?,?,?)",
        (run_id, "run_question", payload, now()),
    )
    await db.commit()


async def save_pending_state(db, run_id: str,
                             messages: list[dict],
                             tool_use_id: str) -> None:
    """Persist LLM message history and pending tool_use_id before pausing."""
    await db.execute(
        "INSERT OR REPLACE INTO run_state (run_id, pending_messages, pending_tool_use_id) "
        "VALUES (?,?,?)",
        (run_id, json.dumps(messages), tool_use_id),
    )
    await db.commit()


async def load_pending_state(db, run_id: str) -> tuple[list[dict], str] | None:
    """Load persisted state for resuming a paused run. Returns None if not found."""
    async with db.execute(
        "SELECT pending_messages, pending_tool_use_id FROM run_state WHERE run_id=?",
        (run_id,),
    ) as cur:
        row = await cur.fetchone()
    if not row:
        return None
    return json.loads(row["pending_messages"]), row["pending_tool_use_id"]


async def delete_pending_state(db, run_id: str) -> None:
    await db.execute("DELETE FROM run_state WHERE run_id=?", (run_id,))
    await db.commit()
