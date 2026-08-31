# Developer Guide

Quick reference for getting the project running, understanding the codebase, and extending it.

---

## Requirements

| Tool | Version |
|------|---------|
| Python | 3.10+ |
| Node.js | 18+ |
| SSH access | `ailab` alias configured in `~/.ssh/config` |
| Anthropic API | `ANTHROPIC_AUTH_TOKEN` or `ANTHROPIC_API_KEY` |

---

## Environment Setup

### 1. Backend

```bash
cd backend
pip install -r requirements.txt
```

**Required environment variables:**

```bash
# Option A — Anthropic relay platform (recommended)
export ANTHROPIC_AUTH_TOKEN=sk-...
export ANTHROPIC_BASE_URL=https://your-relay-endpoint

# Option B — Direct Anthropic API
export ANTHROPIC_API_KEY=sk-ant-...

# Optional overrides
export CLAUDE_MODEL=claude-opus-4-6        # default
export AGENT_EXECUTOR=ssh                  # or "local" (default)
export REMOTE_BASE=/mnt/gpfs/your/workdir  # remote workspace root
export RJOB_CHARGED_GROUP=your_group
```

Put these in `~/.bashrc` and run `source ~/.bashrc`.

### 2. SSH config (`~/.ssh/config`)

```
Host ailab
    HostName h.pjlab.org.cn
    User your-username
    Port 22
    IdentityFile ~/.ssh/id_ed25519
    IdentitiesOnly yes
```

### 3. Frontend

```bash
cd frontend
npm install
```

---

## Running Locally

```bash
# Terminal 1 — Backend
source ~/.bashrc
PYTHONPATH=backend uvicorn app.main:app --port 8000 --reload

# Terminal 2 — Frontend
cd frontend && npm run dev
```

Open **http://localhost:5173**

The Vite dev server proxies `/api/*` → `http://localhost:8000` automatically.

---

## Running with Remote HPC

```bash
# Same as above, just add AGENT_EXECUTOR=ssh
source ~/.bashrc
AGENT_EXECUTOR=ssh PYTHONPATH=backend uvicorn app.main:app --port 8000 --reload
```

All `run_command` calls will be submitted as rjob jobs on the remote cluster. Results (PNG, CSV) are rsync'd back to local `workspace/` after each job completes.

---

## REST API Reference

All endpoints are prefixed with `/api`.

### Projects

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/projects` | List all projects |
| `POST` | `/projects` | Create project `{ name }` |
| `GET` | `/projects/{id}` | Get project |
| `PATCH` | `/projects/{id}` | Rename `{ name }` |
| `DELETE` | `/projects/{id}` | Delete project |
| `GET` | `/projects/{id}/messages` | Conversation history |
| `POST` | `/projects/{id}/messages` | Send message → starts Run `{ content }` |
| `GET` | `/projects/{id}/runs` | List runs |
| `GET` | `/projects/{id}/artifacts` | List artifacts |
| `GET` | `/projects/{id}/files/{path}` | Serve artifact file |
| `GET` | `/projects/{id}/state` | Get status.json |

### Runs

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/runs/{id}` | Get run |
| `GET` | `/runs/{id}/events` | SSE stream `?cursor=<last_event_id>` |
| `GET` | `/runs/{id}/events-json` | All events as JSON array |
| `POST` | `/runs/{id}/stop` | Cancel run |
| `POST` | `/runs/{id}/reply` | Reply to ask_user `{ content }` |

### Other

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/skills` | List available skills |

---

## SSE Event Types

The frontend consumes these from `GET /runs/{id}/events`:

```typescript
type RunEventType =
  | 'run_started'        // { run_id }
  | 'skill_selected'     // { skill, description }
  | 'plan_resolved'      // { target, to_run[], cached[], blocking_gates[] }
  | 'tool_call'          // { tool, args, tool_use_id }
  | 'tool_result'        // { tool, tool_use_id, result }
  | 'stdout_chunk'       // { chunk }
  | 'agent_message'      // { text }
  | 'artifact_created'   // { path, artifact_type, size }
  | 'run_question'       // { question, choices? }
  | 'run_completed'      // { skill }
  | 'run_failed'         // { error }
  | 'run_interrupted'    // {}
```

Reconnect after disconnect: `GET /runs/{id}/events?cursor=<last_id>` replays missed events.

---

## SQLite Schema

Database lives at `workspace/.agent.db`.

```sql
projects   (id, name, workspace_path, created_at, updated_at)
runs       (id, project_id, trigger_message_id, status, skill_name, created_at, updated_at)
messages   (id, project_id, run_id, role, content, created_at)
events     (id INTEGER AUTOINCREMENT, run_id, type, payload JSON, created_at)
artifacts  (id, project_id, run_id, path, artifact_type, size, created_at)
run_state  (run_id, pending_messages JSON, pending_tool_use_id)
```

`events.id` is the SSE cursor. `run_state` holds paused agent state for ask_user resume.

---

## Adding a New Skill

1. Create `skills/<skill-name>/SKILL.md` with YAML frontmatter:

```markdown
---
name: my-skill
description: One sentence describing when to use this skill.
---

# My Skill

## Steps
...
```

2. The skill is auto-discovered on next backend restart — no code changes needed.

3. If the skill maps to a pipeline module, add it to `backend/app/agent/module_registry.yaml`:

```yaml
modules:
  my_module:
    label: "My module"
    config_key: "my_module.enabled"
    cache_checkpoint: "07_my_module"
    requires_modules: [annotation]
    required_inputs: []
    gates: [annotation_review]
    produces:
      - "results/tables/my_output.csv"
```

The skill name `scrna-my-module` maps to module `my_module` automatically (`-` → `_`).

---

## Project State (`status.json`)

Each project workspace contains `status.json` — the source of truth for:
- Gate confirmations (sample sheet, annotation review, contrast, etc.)
- Module completion status + checkpoint paths
- Tried parameter combinations
- Notes (agent appends, user edits freely)

**You can edit it manually.** For example, to manually mark annotation as reviewed:

```json
"gates": {
  "annotation_review": {
    "confirmed": true,
    "value": "inputs/my_annotation.csv",
    "confirmed_at": "2026-08-28T10:00:00Z"
  }
}
```

All reads/writes in code go through `ProjectState` class (`backend/app/agent/project_state.py`) which uses per-project asyncio locks and atomic file writes.

---

## Switching Executor

| Mode | How to activate | When to use |
|------|-----------------|-------------|
| Local subprocess | `AGENT_EXECUTOR=local` (default) | Development, testing |
| SSH + rjob | `AGENT_EXECUTOR=ssh` | Production, real analysis |

Both implement the same `Executor.run()` interface. The agent loop doesn't know which one is active.

---

## Common Debugging

**Backend won't start:**
```bash
# Check port is free
lsof -i :8000
# Check imports
PYTHONPATH=backend python3 -c "from app.main import app"
```

**SSH executor job fails immediately:**
```bash
# Test SSH connection
ssh ailab echo ok
# Test rjob availability
ssh ailab "source /etc/profile.d/ssh-init.sh && rjob list"
```

**Run stuck in `running` after server restart:**
The run is marked `interrupted` on next startup automatically. Runs in `running`/`waiting_for_user`/`pending` at startup are NOT auto-resumed (by design — see ADR-004).

**Ask_user not resuming:**
Check `run_state` table has an entry for the run:
```bash
sqlite3 workspace/.agent.db "SELECT * FROM run_state WHERE run_id='...';"
```

**Frontend not reflecting backend changes:**
The Vite proxy only rewrites `/api/*`. If you add new routes without the `/api` prefix, add them to `frontend/vite.config.ts`.

---

## File Artifacts

After each `run_command`, the executor diffs `results/`, `figures/`, `tables/`, `objects/`, `reports/` directories. New/changed files with these extensions are automatically pulled back and registered:

```
.png .jpg .jpeg .svg   → image
.csv .tsv              → table
.html                  → html
.pdf                   → pdf
.json                  → json
.txt .md               → text
```

`.rds`, `.h5ad`, `.loom` and other large files stay on the remote server — only the path and size are recorded in SQLite.
