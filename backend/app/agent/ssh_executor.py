"""
SSH + rjob executor.

All commands are submitted as rjob jobs on the remote server.
Implements the same interface as the local Executor so the agent loop
does not need to change.

Flow:
  run_command(cmd)
    → rjob submit ... -- bash -c 'source conda && <cmd> | tee <logfile>'
    → ssh tail -f <logfile>  (real-time, no delay)
    → rjob status poll runs concurrently; kills tail when job is terminal
    → rsync pull new PNG/CSV artifacts back to local workspace
    → return CommandResult

  rjob logs (65s-delayed) is kept as fallback only when tail fails.
"""
import asyncio
import json
import re
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path

from app.config import (
    ARTIFACT_TYPES,
    ARTIFACT_WATCH_DIRS,
    REMOTE_BASE,
    REMOTE_CONDA_INIT,
    REMOTE_LOG_SUBDIR,
    RJOB_CHARGED_GROUP,
    RJOB_IMAGE,
    RJOB_MOUNTS,
    RJOB_RESOURCES,
    SFTP_PULL_EXTENSIONS,
    SSH_HOST,
)
from app.agent.executor import CommandResult


# ── SSH helpers ───────────────────────────────────────────────────────────

async def _ssh(cmd: str, timeout: float | None = 30) -> tuple[str, str, int]:
    """Run a command on the remote host via ssh. Returns (stdout, stderr, rc)."""
    proc = await asyncio.create_subprocess_exec(
        "ssh", SSH_HOST, cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
    except asyncio.TimeoutError:
        proc.terminate()
        await proc.wait()
        return "", "ssh command timed out", 1
    return stdout.decode(errors="replace"), stderr.decode(errors="replace"), proc.returncode or 0


async def _rsync_pull(remote_paths: list[str], local_dir: Path) -> list[Path]:
    """
    Pull a list of remote files to local_dir via rsync over SSH.
    Returns list of successfully pulled local paths.
    """
    if not remote_paths:
        return []
    local_dir.mkdir(parents=True, exist_ok=True)
    # rsync accepts multiple sources
    args = ["rsync", "-az", "--no-relative", "-e", "ssh"] + \
           [f"{SSH_HOST}:{p}" for p in remote_paths] + \
           [str(local_dir) + "/"]
    proc = await asyncio.create_subprocess_exec(
        *args,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    _, _ = await proc.communicate()
    return [local_dir / Path(p).name for p in remote_paths
            if (local_dir / Path(p).name).exists()]


# ── rjob helpers ──────────────────────────────────────────────────────────

def _build_rjob_submit(
    job_name: str,
    command: str,
    remote_cwd: str,
    resources: dict,
    log_file: str,
) -> str:
    mount_flags = " ".join(f"--mount={m}" for m in RJOB_MOUNTS)
    cpu = resources.get("cpu", 8)
    mem = resources.get("memory", 32768)

    # Wrap command: set cwd, activate conda, run with tee to log file
    inner = (
        f"set -euo pipefail; "
        f"mkdir -p {remote_cwd}/{REMOTE_LOG_SUBDIR}; "
        f"cd {remote_cwd}; "
        f"{REMOTE_CONDA_INIT}; "
        f"( {command} ) 2>&1 | tee {log_file}; "
        f"echo __AGENT_EXIT_${{PIPESTATUS[0]}}__ >> {log_file}"
    )
    inner_escaped = inner.replace("'", "'\\''")

    return (
        f"source /etc/profile.d/ssh-init.sh 2>/dev/null; "
        f"rjob submit "
        f"--name={job_name} "
        f"--priority=1 "
        f"--cpu={cpu} --gpu=0 --memory={mem} "
        f"--charged-group={RJOB_CHARGED_GROUP} "
        f"--private-machine=group "
        f"{mount_flags} "
        f"--image={RJOB_IMAGE} "
        f"--host-network=false "
        f"-e PYTHONUNBUFFERED=1 "
        f"-- bash -c '{inner_escaped}'"
    )


async def _submit_job(submit_cmd: str) -> tuple[str, str]:
    """
    Submit a rjob and return (actual_job_name, error).
    rjob appends a timestamp suffix, so we parse it from stdout:
      'created rjob_name: agent-xxx-64895796'
    """
    out, err, rc = await _ssh(submit_cmd, timeout=30)
    if rc != 0:
        return "", f"rjob submit failed (rc={rc}):\n{err}\n{out}"
    m = re.search(r"created rjob_name:\s*(\S+)", out)
    if not m:
        return "", f"Could not parse job name from submit output:\n{out}"
    return m.group(1), ""


async def _get_job_status(job_name: str) -> str:
    """
    Returns normalised status: Succeeded | Failed | Running | Pending | Starting | Unknown.
    Terminal states: Succeeded, Failed, Stopped.
    """
    out, _, rc = await _ssh(
        f"source /etc/profile.d/ssh-init.sh 2>/dev/null; "
        f"rjob get {job_name} 2>/dev/null",
        timeout=15,
    )
    if rc != 0 or not out.strip():
        return "Unknown"
    line = out.lower()
    for s in ("succeeded", "failed", "stopped", "running", "starting", "pending"):
        if s in line:
            return s.capitalize()
    return "Unknown"


TERMINAL_STATUSES = {"Succeeded", "Failed", "Stopped"}


async def _stream_via_tail(
    log_file: str,
    job_name: str,
    stdout_callback,
    cancel_event: asyncio.Event | None,
) -> tuple[str, int | None]:
    """
    Primary log streaming: `ssh tail -f <log_file>` for real-time output.

    The reader is authoritative: it stops only when it sees the sentinel
    __AGENT_EXIT_<code>__ written by the shell after the command finishes.
    The poller is a safety net: if the job is terminal for >60s with no
    sentinel (e.g. container OOM-killed), it forces completion.

    Returns (full_log_text, exit_code_from_sentinel | None).
    """
    exit_code_sentinel = re.compile(r"__AGENT_EXIT_(\d+)__")
    reader_done = asyncio.Event()
    full_log: list[str] = []
    parsed_exit: list[int] = []

    # Wait for log file to appear on GPFS (job startup takes a few seconds)
    for _ in range(30):
        out, _, _ = await _ssh(f"test -f {log_file} && echo yes", timeout=5)
        if out.strip() == "yes":
            break
        if cancel_event and cancel_event.is_set():
            return "", None
        await asyncio.sleep(2)

    tail_proc = await asyncio.create_subprocess_exec(
        "ssh", SSH_HOST, f"tail -f {log_file}",
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.DEVNULL,
    )

    async def read_tail():
        assert tail_proc.stdout
        while True:
            line = await tail_proc.stdout.readline()
            if not line:
                break
            text = line.decode(errors="replace")
            m = exit_code_sentinel.search(text)
            if m:
                parsed_exit.append(int(m.group(1)))
                reader_done.set()   # reader is the authority: done when sentinel seen
                break
            full_log.append(text)
            if stdout_callback:
                await stdout_callback(text)

    async def poll_safety_net():
        """Only force-done if job is terminal for >60s without a sentinel."""
        terminal_since: float | None = None
        while not reader_done.is_set():
            if cancel_event and cancel_event.is_set():
                reader_done.set()
                break
            status = await _get_job_status(job_name)
            if status in TERMINAL_STATUSES:
                if terminal_since is None:
                    terminal_since = asyncio.get_event_loop().time()
                elif asyncio.get_event_loop().time() - terminal_since > 60:
                    reader_done.set()   # safety net: give up waiting for sentinel
                    break
            await asyncio.sleep(3)

    reader = asyncio.create_task(read_tail())
    poller = asyncio.create_task(poll_safety_net())

    await reader_done.wait()

    try:
        tail_proc.terminate()
    except ProcessLookupError:
        pass
    reader.cancel()
    poller.cancel()
    await asyncio.gather(reader, poller, return_exceptions=True)

    return "".join(full_log), parsed_exit[0] if parsed_exit else None


async def _stream_logs_fallback(
    job_name: str,
    stdout_callback,
    cancel_event: asyncio.Event | None,
    poll_interval: float = 3.0,
) -> str:
    """
    Fallback: poll rjob logs (has ~65s delay). Used when tail -f fails
    (e.g. log file never appeared because the job failed during startup).
    """
    log_prefix = re.compile(r"^\[.*?\]\s+\S+\s+>>\s?")
    rjob_json = re.compile(r'^\s*\{"@caller"')
    seen_lines = 0
    full_log: list[str] = []
    terminal_since: float | None = None
    LOG_WAIT_TIMEOUT = 90.0

    while True:
        if cancel_event and cancel_event.is_set():
            break

        out, _, rc = await _ssh(
            f"source /etc/profile.d/ssh-init.sh 2>/dev/null; "
            f"rjob logs job {job_name} 2>/dev/null",
            timeout=20,
        )
        user_lines: list[str] | None = None
        if rc == 0:
            user_lines = []
            for l in out.splitlines(keepends=True):
                if ">>" not in l:
                    continue
                cleaned = log_prefix.sub("", l)
                if rjob_json.match(cleaned):
                    continue
                user_lines.append(cleaned)

        if user_lines is not None:
            new = user_lines[seen_lines:]
            if new:
                chunk = "".join(new)
                full_log.extend(new)
                seen_lines = len(user_lines)
                if stdout_callback:
                    await stdout_callback(chunk)

        status = await _get_job_status(job_name)
        if status in TERMINAL_STATUSES:
            if terminal_since is None:
                terminal_since = asyncio.get_event_loop().time()
            if user_lines is not None:
                break
            if asyncio.get_event_loop().time() - terminal_since > LOG_WAIT_TIMEOUT:
                break

        await asyncio.sleep(poll_interval)

    return "".join(full_log)


# ── Remote file snapshot ──────────────────────────────────────────────────

async def _remote_snapshot(remote_cwd: str) -> dict[str, int]:
    """
    Return {relative_path: size} for watched dirs on the remote server.
    Uses %p (full relative path) so keys include the subdir prefix, e.g. 'results/foo.csv'.
    """
    watch = " ".join(ARTIFACT_WATCH_DIRS)
    script = (
        f"cd {remote_cwd} 2>/dev/null || exit 0; "
        f"for d in {watch}; do "
        f"  [ -d \"$d\" ] && find \"$d\" -type f -printf '%s %p\\n'; "
        f"done"
    )
    out, _, _ = await _ssh(script, timeout=15)
    result: dict[str, int] = {}
    for line in out.splitlines():
        parts = line.strip().split(" ", 1)
        if len(parts) == 2:
            try:
                result[parts[1]] = int(parts[0])
            except ValueError:
                pass
    return result


# ── Main executor ─────────────────────────────────────────────────────────

class SSHRjobExecutor:
    """
    Drop-in replacement for Executor that runs commands on a remote
    server via rjob. Same interface as Executor.run().
    """

    def _infer_resources(self, command: str) -> dict:
        cmd_lower = command.lower()
        if any(k in cmd_lower for k in ("cellchat", "hdwgcna", "hdwgcna")):
            return RJOB_RESOURCES["heavy"]
        if any(k in cmd_lower for k in ("rscript", "run_pipeline")):
            return RJOB_RESOURCES["normal"]
        return RJOB_RESOURCES["light"]

    async def run(
        self,
        command: str,
        cwd: str,
        timeout: float | None,
        stdout_callback=None,
        cancel_event: asyncio.Event | None = None,
        resources: dict | None = None,
    ) -> CommandResult:
        local_path = Path(cwd)
        project_id = local_path.name
        remote_cwd = f"{REMOTE_BASE}/{project_id}"

        job_name = f"agent-{project_id[:8]}-{uuid.uuid4().hex[:6]}"
        res = resources or self._infer_resources(command)
        log_file = f"{remote_cwd}/{REMOTE_LOG_SUBDIR}/{job_name}.log"

        # Snapshot before
        before = await _remote_snapshot(remote_cwd)

        # Submit (command output is tee'd to log_file inside the container)
        submit_cmd = _build_rjob_submit(job_name, command, remote_cwd, res, log_file)
        actual_job_name, submit_err = await _submit_job(submit_cmd)
        if submit_err:
            return CommandResult(stdout="", stderr=submit_err, exit_code=1)

        # Wait for job to start
        for _ in range(40):
            if cancel_event and cancel_event.is_set():
                await _ssh(
                    f"source /etc/profile.d/ssh-init.sh 2>/dev/null; rjob stop {actual_job_name} 2>/dev/null",
                    timeout=10,
                )
                return CommandResult(stdout="", stderr="Cancelled by user", exit_code=130)
            status = await _get_job_status(actual_job_name)
            if status in ("Running", *TERMINAL_STATUSES):
                break
            await asyncio.sleep(3)

        # Stream logs via tail -f (real-time); fallback to rjob logs on failure
        timed_out = False
        log_text = ""
        exit_code_from_sentinel: int | None = None
        try:
            log_text, exit_code_from_sentinel = await asyncio.wait_for(
                _stream_via_tail(log_file, actual_job_name, stdout_callback, cancel_event),
                timeout=timeout,
            )
        except asyncio.TimeoutError:
            timed_out = True
            await _ssh(
                f"source /etc/profile.d/ssh-init.sh 2>/dev/null; rjob stop {actual_job_name} 2>/dev/null",
                timeout=10,
            )
        except Exception:
            # tail failed (e.g. log file never appeared) — fall back to rjob logs
            log_text = await _stream_logs_fallback(actual_job_name, stdout_callback, cancel_event)

        # Determine exit code: sentinel > rjob status
        if exit_code_from_sentinel is not None:
            exit_code = exit_code_from_sentinel
        else:
            final_status = await _get_job_status(actual_job_name)
            exit_code = 0 if final_status == "Succeeded" else 1

        # Pull back new/modified artifacts
        after = await _remote_snapshot(remote_cwd)
        for rel, size in after.items():
            if rel not in before or before[rel] != size:
                if Path(rel).suffix.lower() in SFTP_PULL_EXTENSIONS:
                    local_target = local_path / Path(rel).parent
                    await _rsync_pull([f"{remote_cwd}/{rel}"], local_target)

        return CommandResult(
            stdout=log_text,
            stderr="",
            exit_code=exit_code,
            timed_out=timed_out,
        )
