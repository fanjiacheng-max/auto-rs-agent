# Research Agent

A full-stack agent platform for biomedical single-cell RNA-seq analysis. Users describe a scientific task in natural language; the agent selects the appropriate Skill, resolves dependencies, handles human review gates, and executes the analysis pipeline on a remote HPC cluster via rjob.

---

## Architecture

```
┌──────────────┬────────────────────────────┬──────────────────┐
│ Projects     │ Agent                      │ Files / State    │
│              │                            │                  │
│ Project A    │ User: 分析 GSE123456       │ Figures          │
│ ▸ History    │                            │ Tables           │
│   ✓ scrna-qc │ Agent: 正在执行 QC...      │ Reports          │
│              │ ✓ io  ✓ qc  ● integration │                  │
│              │                            │ Gates / Modules  │
└──────────────┴────────────────────────────┴──────────────────┘
```

**Stack:**
- Backend: FastAPI + SQLite + aiosqlite
- Agent: Claude API (tool_use loop) + LLMProvider abstraction
- Execution: SSH + rjob (Kubernetes job scheduler on HPC)
- Frontend: React + TypeScript + Vite

---

## Features

- **Dependency-aware execution** — A declarative module registry (`module_registry.yaml`) defines the full dependency graph. The resolver auto-fills missing upstream modules and surfaces blocking scientific gates before any code runs.
- **Scientific gates** — Human review checkpoints (sample sheet, annotation review, contrast confirmation) are asked once and persisted per project.
- **Real-time log streaming** — Commands run as rjob jobs; stdout is streamed via `ssh tail -f` with zero ingestion delay.
- **QC parameter sweep** — Automatically tries 9 parameter combinations and selects the highest cell retention rate.
- **ask_user / resume** — Agent can pause mid-run, persist full LLM message state, and resume after user input.
- **Project state** — Each project maintains a `status.json` with gate confirmations, module completion, tried parameters, and notes.
- **Run history** — Browse and replay any past run's event stream.
- **14 scRNA-seq Skills** — `geo-scrna-workflow` (full pipeline) + 13 modular sub-skills (inspect, configure, QC, integration, annotation, differential, enrichment, pseudotime, CellChat, hdWGCNA, …).

---

## Project Structure

```
auto_rs_agent/
├── skills/                      # Skill definitions (read-only)
│   ├── geo-scrna-workflow/      # Full scRNA pipeline + R modules
│   ├── scrna-inspect/           # Data inspection
│   ├── scrna-qc/                # QC with parameter sweep
│   ├── scrna-integration/       # Normalization + clustering
│   ├── scrna-annotation/        # Cell type annotation
│   ├── scrna-differential/      # Pseudobulk DE
│   ├── scrna-enrichment/        # Pathway enrichment
│   └── ...                      # + 7 more
│
├── backend/
│   └── app/
│       ├── agent/
│       │   ├── loop.py          # Agent loop (run_agent / resume_agent)
│       │   ├── tools.py         # 5 tools: read_file, list_dir, write_file, run_command, ask_user
│       │   ├── executor.py      # Local subprocess executor
│       │   ├── ssh_executor.py  # SSH + rjob remote executor
│       │   ├── resolver.py      # Dependency resolver
│       │   ├── project_state.py # status.json read/write
│       │   ├── module_registry.yaml
│       │   └── providers/       # LLMProvider abstraction (AnthropicProvider)
│       ├── db.py                # SQLite: projects / runs / messages / events / artifacts
│       ├── routes/              # REST API + SSE stream
│       └── config.py
│
├── frontend/
│   └── src/
│       ├── App.tsx
│       ├── components/
│       │   ├── ChatPanel.tsx    # Live + historical run view
│       │   ├── ProjectPanel.tsx # Project list + run history
│       │   ├── ArtifactPanel.tsx
│       │   ├── StatePanel.tsx   # status.json visualizer
│       │   └── ErrorBoundary.tsx
│       └── hooks/useRunEvents.ts  # SSE consumer with cursor reconnect
│
├── workspace/                   # Runtime data (gitignored)
├── SPEC.md                      # Architecture decisions (ADR-001 ~ ADR-012)
└── ARCHITECTURE_NOTES.md        # Developer cheat sheet
```

---

## Quick Start

### Backend

```bash
# Install dependencies
cd backend && pip install -r requirements.txt

# Set API key (supports Anthropic relay platforms)
export ANTHROPIC_AUTH_TOKEN=sk-...
export ANTHROPIC_BASE_URL=https://your-relay-endpoint  # optional

# Run locally (subprocess executor)
PYTHONPATH=backend uvicorn app.main:app --port 8000 --reload

# Run with remote HPC execution
AGENT_EXECUTOR=ssh PYTHONPATH=backend uvicorn app.main:app --port 8000 --reload
```

### Frontend

```bash
cd frontend && npm install && npm run dev
# → http://localhost:5173
```

### SSH / rjob configuration (HPC execution)

The SSH executor uses an `ailab` alias from `~/.ssh/config`. Configure:

```
Host ailab
    HostName your-hpc-host
    User your-username
    IdentityFile ~/.ssh/id_ed25519
```

Remote paths and rjob resource defaults are in `backend/app/config.py`.

---

## Key Design Decisions

See [`SPEC.md`](SPEC.md) for full ADR log. Highlights:

| Decision | Choice |
|----------|--------|
| Agent loop | Claude API tool_use, thin LLMProvider abstraction |
| Realtime comms | SSE + REST (no WebSocket); cursor-based reconnect |
| Execution | SSH + rjob; `tail -f` log streaming (no ingestion delay) |
| State persistence | SQLite for runs/events; `status.json` for project state |
| Dependency resolution | Declarative YAML registry; resolver, not LLM, decides execution order |
| Frontend | React + TypeScript + Vite; useState/useEffect only |
