import asyncio
import json
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
import aiosqlite

import app.db as db
from app.db import get_db
from app.schemas import CreateProjectRequest, RenameProjectRequest, SendMessageRequest
from app.agent.loop import run_agent

router = APIRouter(prefix="/api")


# ── Projects ──────────────────────────────────────────────

@router.post("/projects", status_code=201)
async def create_project(body: CreateProjectRequest, conn=Depends(get_db)):
    return await db.create_project(conn, body.name)


@router.get("/projects")
async def list_projects(conn=Depends(get_db)):
    return await db.list_projects(conn)


@router.get("/projects/{project_id}")
async def get_project(project_id: str, conn=Depends(get_db)):
    project = await db.get_project(conn, project_id)
    if not project:
        raise HTTPException(404, "Project not found")
    return project


@router.delete("/projects/{project_id}", status_code=204)
async def delete_project(project_id: str, conn=Depends(get_db)):
    project = await db.get_project(conn, project_id)
    if not project:
        raise HTTPException(404, "Project not found")
    await db.delete_project(conn, project_id)


@router.patch("/projects/{project_id}")
async def rename_project(project_id: str, body: RenameProjectRequest, conn=Depends(get_db)):
    project = await db.get_project(conn, project_id)
    if not project:
        raise HTTPException(404, "Project not found")
    await db.rename_project(conn, project_id, body.name)
    return await db.get_project(conn, project_id)


# ── Messages / Runs ───────────────────────────────────────

@router.get("/projects/{project_id}/messages")
async def list_messages(project_id: str, conn=Depends(get_db)):
    return await db.list_messages(conn, project_id, limit=100)


@router.post("/projects/{project_id}/messages", status_code=201)
async def send_message(
    project_id: str, body: SendMessageRequest, conn=Depends(get_db)
):
    project = await db.get_project(conn, project_id)
    if not project:
        raise HTTPException(404, "Project not found")

    # Enforce single active run per project
    active = await db.active_run_for_project(conn, project_id)
    if active:
        raise HTTPException(
            409,
            f"Project already has an active run ({active['id']}). "
            "Stop it before starting a new one.",
        )

    # Persist user message
    user_msg = await db.create_message(conn, project_id, "user", body.content)

    # Create run linked to this message
    run = await db.create_run(conn, project_id, user_msg["id"])

    # Launch agent in background — independent of this request
    asyncio.create_task(run_agent(run["id"], project, body.content))

    return {"message": user_msg, "run": run}


@router.get("/projects/{project_id}/runs")
async def list_runs(project_id: str, conn=Depends(get_db)):
    return await db.list_runs(conn, project_id)


@router.get("/projects/{project_id}/artifacts")
async def list_artifacts(project_id: str, conn=Depends(get_db)):
    return await db.list_artifacts(conn, project_id)


# ── Run operations ────────────────────────────────────────

@router.get("/runs/{run_id}/events-json")
async def get_run_events_json(run_id: str, conn=Depends(get_db)):
    """Return all events for a run as a JSON array (for historical view)."""
    run = await db.get_run(conn, run_id)
    if not run:
        raise HTTPException(404, "Run not found")
    import json as _json
    events = await db.get_events_after(conn, run_id, 0)
    return [
        {"id": e["id"], "type": e["type"], "payload": _json.loads(e["payload"])}
        for e in events
    ]


@router.get("/runs/{run_id}")
async def get_run(run_id: str, conn=Depends(get_db)):
    run = await db.get_run(conn, run_id)
    if not run:
        raise HTTPException(404, "Run not found")
    return run


@router.post("/runs/{run_id}/stop", status_code=204)
async def stop_run(run_id: str, conn=Depends(get_db)):
    from app.agent.loop import cancel_run
    run = await db.get_run(conn, run_id)
    if not run:
        raise HTTPException(404, "Run not found")
    cancel_run(run_id)


@router.post("/runs/{run_id}/reply")
async def reply_to_run(run_id: str, body: SendMessageRequest, conn=Depends(get_db)):
    run = await db.get_run(conn, run_id)
    if not run:
        raise HTTPException(404, "Run not found")
    if run["status"] != "waiting_for_user":
        raise HTTPException(409, "Run is not waiting for user input")

    project = await db.get_project(conn, run["project_id"])
    if not project:
        raise HTTPException(404, "Project not found")

    # Persist user reply as a message
    await db.create_message(conn, run["project_id"], "user", body.content, run_id)

    # Resume agent in background
    from app.agent.loop import resume_agent
    asyncio.create_task(resume_agent(run_id, project, body.content))

    return {"status": "resumed"}


# ── SSE event stream ──────────────────────────────────────

TERMINAL_STATUSES = {"completed", "failed", "interrupted"}


@router.get("/runs/{run_id}/events")
async def stream_events(run_id: str, cursor: int = 0):
    """
    SSE stream of run events.
    Client sends ?cursor=<last_event_id> to resume after disconnect.
    """
    async def generate():
        nonlocal cursor
        poll_interval = 0.4  # seconds

        async with aiosqlite.connect(db.DB_PATH) as conn:
            conn.row_factory = aiosqlite.Row
            idle_count = 0

            while True:
                events = await db.get_events_after(conn, run_id, cursor)

                for ev in events:
                    cursor = ev["id"]
                    data = json.dumps({
                        "id": ev["id"],
                        "type": ev["type"],
                        "payload": json.loads(ev["payload"]),
                    })
                    yield f"id: {ev['id']}\ndata: {data}\n\n"

                    if ev["type"] in ("run_completed", "run_failed", "run_interrupted"):
                        return

                if not events:
                    # Check if run is terminal even without events
                    run = await db.get_run(conn, run_id)
                    if run and run["status"] in TERMINAL_STATUSES:
                        idle_count += 1
                        if idle_count >= 3:
                            return
                    await asyncio.sleep(poll_interval)
                else:
                    idle_count = 0

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


# ── File serving for artifact preview ─────────────────────

@router.get("/projects/{project_id}/files/{file_path:path}")
async def serve_file(project_id: str, file_path: str, conn=Depends(get_db)):
    from pathlib import Path
    import mimetypes

    project = await db.get_project(conn, project_id)
    if not project:
        raise HTTPException(404, "Project not found")

    workspace = Path(project["workspace_path"])
    full_path = (workspace / file_path).resolve()

    if not str(full_path).startswith(str(workspace.resolve())):
        raise HTTPException(403, "Access denied")
    if not full_path.exists() or not full_path.is_file():
        raise HTTPException(404, "File not found")

    mime, _ = mimetypes.guess_type(str(full_path))
    mime = mime or "application/octet-stream"
    return StreamingResponse(
        iter([full_path.read_bytes()]),
        media_type=mime,
    )


# ── Skills ────────────────────────────────────────────────

@router.get("/projects/{project_id}/state")
async def get_project_state(project_id: str, conn=Depends(get_db)):
    """Return status.json content for a project."""
    project = await db.get_project(conn, project_id)
    if not project:
        raise HTTPException(404, "Project not found")
    from pathlib import Path
    import json
    state_path = Path(project["workspace_path"]) / "status.json"
    if not state_path.exists():
        raise HTTPException(404, "status.json not found")
    return json.loads(state_path.read_text())


@router.get("/skills")
async def list_skills():
    from app.agent.skill import load_skills
    skills = load_skills()
    return [{"name": s.name, "description": s.description} for s in skills]
