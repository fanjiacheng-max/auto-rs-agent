import asyncio
import os
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class CommandResult:
    stdout: str
    stderr: str
    exit_code: int
    timed_out: bool = False


class Executor:
    """Subprocess-based command executor. Swap implementation for Docker later."""

    async def run(
        self,
        command: str,
        cwd: str,
        timeout: float | None,
        stdout_callback=None,  # async callable(chunk: str)
        cancel_event: asyncio.Event | None = None,
    ) -> CommandResult:
        env = {**os.environ}
        proc = await asyncio.create_subprocess_shell(
            command,
            cwd=cwd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=env,
        )

        stdout_chunks: list[str] = []
        stderr_data: bytes = b""
        timed_out = False

        async def read_stdout():
            assert proc.stdout
            while True:
                chunk = await proc.stdout.read(4096)
                if not chunk:
                    break
                text = chunk.decode(errors="replace")
                stdout_chunks.append(text)
                if stdout_callback:
                    await stdout_callback(text)

        async def read_stderr():
            nonlocal stderr_data
            assert proc.stderr
            stderr_data = await proc.stderr.read()

        async def wait_proc():
            await proc.wait()

        async def watch_cancel():
            if cancel_event:
                await cancel_event.wait()
                try:
                    proc.terminate()
                except ProcessLookupError:
                    pass

        tasks = [
            asyncio.create_task(read_stdout()),
            asyncio.create_task(read_stderr()),
            asyncio.create_task(wait_proc()),
        ]
        if cancel_event:
            tasks.append(asyncio.create_task(watch_cancel()))

        try:
            await asyncio.wait_for(
                asyncio.gather(*tasks, return_exceptions=True),
                timeout=timeout,
            )
        except asyncio.TimeoutError:
            timed_out = True
            try:
                proc.terminate()
            except ProcessLookupError:
                pass
            await proc.wait()
            # drain remaining output
            if proc.stdout:
                try:
                    rest = await asyncio.wait_for(proc.stdout.read(), timeout=2)
                    if rest:
                        text = rest.decode(errors="replace")
                        stdout_chunks.append(text)
                        if stdout_callback:
                            await stdout_callback(text)
                except Exception:
                    pass
        finally:
            for t in tasks:
                t.cancel()

        return CommandResult(
            stdout="".join(stdout_chunks),
            stderr=stderr_data.decode(errors="replace"),
            exit_code=proc.returncode or 0,
            timed_out=timed_out,
        )
