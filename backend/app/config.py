import os
from pathlib import Path

BASE_DIR = Path(__file__).parent.parent.parent  # auto_rs_agent/
SKILLS_DIR = BASE_DIR / "skills"
WORKSPACE_DIR = BASE_DIR / "workspace"
DB_PATH = WORKSPACE_DIR / ".agent.db"

# LLM provider — support both official key and relay platform auth token
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
ANTHROPIC_AUTH_TOKEN = os.environ.get("ANTHROPIC_AUTH_TOKEN", "")
ANTHROPIC_BASE_URL = os.environ.get("ANTHROPIC_BASE_URL", "")  # relay base URL
CLAUDE_MODEL = os.environ.get("CLAUDE_MODEL", "claude-opus-4-6")

# ── Remote execution (SSH + rjob) ─────────────────────────────────────────
SSH_HOST = os.environ.get("SSH_HOST", "ailab")           # ssh config alias
REMOTE_BASE = os.environ.get(
    "REMOTE_BASE",
    "/mnt/shared-storage-gpfs2/gpfs-aging/huaxi_omics/auto_agent_workspace",
)
REMOTE_CONDA_INIT = (
    "source /mnt/shared-storage-user/medeval-share/fanjiacheng/miniconda3"
    "/etc/profile.d/conda.sh && conda activate r_seurat"
)
RJOB_IMAGE = os.environ.get(
    "RJOB_IMAGE",
    "registry.h.pjlab.org.cn/ailab-medeval-medeval_gpu/omicgpu:jcfan-v-cu128torhc27",
)
RJOB_CHARGED_GROUP = os.environ.get("RJOB_CHARGED_GROUP", "evalmed_gpu")
RJOB_MOUNTS = [
    "gpfs://gpfs2/gpfs-aging:/mnt/shared-storage-gpfs2/gpfs-aging",
    "gpfs://gpfs1/medeval-share:/mnt/shared-storage-user/medeval-share",
]
REMOTE_LOG_SUBDIR = ".agent_logs"  # relative to remote project cwd; holds per-job tee logs

# Default resources per task type (can be overridden in run_command)
RJOB_RESOURCES: dict[str, dict] = {
    "light":  {"cpu": 4,  "memory": 16384},   # Python helper scripts
    "normal": {"cpu": 16, "memory": 131072},   # R pipeline: QC/integration/annotation/DE
    "heavy":  {"cpu": 16, "memory": 262144},   # CellChat / hdWGCNA
}

# Artifact types to SFTP back from remote (others stay on server)
SFTP_PULL_EXTENSIONS = {".png", ".jpg", ".jpeg", ".svg", ".csv", ".tsv", ".html", ".pdf", ".json", ".txt", ".md"}

# Directories to monitor for artifact discovery after run_command
ARTIFACT_WATCH_DIRS = ["results", "figures", "tables", "objects", "reports"]
ARTIFACT_IGNORE_DIRS = {"inputs", ".cache", "tmp", "logs", ".runs"}

# Artifact type mapping by extension
ARTIFACT_TYPES: dict[str, str] = {
    ".png": "image", ".jpg": "image", ".jpeg": "image", ".svg": "image",
    ".csv": "table", ".tsv": "table",
    ".txt": "text", ".md": "text", ".log": "text",
    ".html": "html",
    ".json": "json",
    ".rds": "rds", ".rda": "rds",
    ".h5": "h5", ".h5ad": "h5ad", ".loom": "loom",
    ".pdf": "pdf",
}


# Directories to monitor for artifact discovery after run_command
ARTIFACT_WATCH_DIRS = ["results", "figures", "tables", "objects", "reports"]
ARTIFACT_IGNORE_DIRS = {"inputs", ".cache", "tmp", "logs", ".runs"}

# Artifact type mapping by extension
ARTIFACT_TYPES: dict[str, str] = {
    ".png": "image", ".jpg": "image", ".jpeg": "image", ".svg": "image",
    ".csv": "table", ".tsv": "table",
    ".txt": "text", ".md": "text", ".log": "text",
    ".html": "html",
    ".json": "json",
    ".rds": "rds", ".rda": "rds",
    ".h5": "h5", ".h5ad": "h5ad", ".loom": "loom",
    ".pdf": "pdf",
}
