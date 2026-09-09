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

## Local Biomedical RAG (initial)

The repository now includes a keyless local Chroma index for biomedical evidence. It uses a
deterministic local hashing embedding so development and smoke tests do not require the
Anthropic/OpenAI credentials used by the Agent loop.

```bash
# From the repository root, with Python 3.10+
PYTHONPATH=backend python backend/scripts/build_rag_index.py
PYTHONPATH=backend python backend/scripts/query_rag_index.py "TP53 transcription factor apoptosis cancer"
```

The seed build fetches public records for TP53 from UniProt, Reactome, Open Targets, and
Europe PMC. Normalized records are written to `workspace/rag/normalized/`, the persistent
Chroma database is written to `workspace/rag/index/`, and the build manifest is written to
`workspace/rag/manifest.json`. `workspace/` is gitignored; these are runtime data, not source
files to commit.

This is an initial retrieval smoke-test index, not a complete biomedical knowledge base. The
hashing embedding is useful for deterministic local tests but should later be replaced or
combined with a stronger local biomedical embedding model. Exact entity-ID and metadata
filters remain necessary for gene/protein/species-specific retrieval.

The Agent exposes the same retrieval boundary as the tool
`retrieve_biomedical_evidence`. The intended flow is: normalize a differential-analysis
row with `app.agent.rag.load_candidates`, resolve the exact entity with
`resolve_entity`, then pass the candidate to the Agent tool. The tool returns the local
hits together with source metadata and collection size; the model is responsible for
explaining the evidence and preserving its URLs.

The RAG contract is covered by offline tests for adjusted-p-value/effect-size selection,
species-safe identity resolution, provenance-preserving evidence assembly, source
timeouts, cancellation, and persistent Chroma retrieval:

```bash
PYTHONPATH=backend python -B -m unittest discover -s backend/tests -t backend
```

The checked-in tests use two small fixture documents only. Runtime data remains under the
gitignored `workspace/rag/` directory, so the Chroma files and downloaded public records
are not committed to GitHub. This keeps the branch mergeable while allowing a later bulk
loader to add versioned UniProt/GO/Reactome snapshots and on-demand Open Targets/Europe
PMC evidence.
