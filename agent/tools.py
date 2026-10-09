"""The agent's one tool: run model-written Python in a fresh, sandboxed subprocess."""

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRATCH = ROOT / "scratch"  # one subfolder per run, shared between its steps; the code runs there
DATA = ROOT / "data" / "context"
SANDBOX_DATA = "/data"  # where the code sees DATA
TIMEOUT_S = 60
OUTPUT_CAP = 2000  # characters the model gets back


def sandbox_command(scratch: Path) -> list[str]:
    """bwrap command that runs Python with a tiny, mostly read-only filesystem and no network.

    Inside, the code sees only: /usr (system, read-only), /venv (pandas, read-only),
    /data (DABstep files, read-only), /scratch (read-write) and an empty /tmp.
    No home folder, no .env, no network, no other processes.
    """
    venv = Path(sys.prefix)
    return [
        "bwrap",
        "--ro-bind", "/usr", "/usr",
        "--symlink", "usr/bin", "/bin",
        "--symlink", "usr/lib", "/lib",
        "--symlink", "usr/lib64", "/lib64",
        "--ro-bind", str(venv), "/venv",
        "--ro-bind", str(DATA), SANDBOX_DATA,
        "--bind", str(scratch), "/scratch",
        "--tmpfs", "/tmp",
        "--proc", "/proc",
        "--dev", "/dev",
        "--chdir", "/scratch",
        "--unshare-all",  # includes the network
        "--die-with-parent",  # killed if the timeout kills bwrap
        "--new-session",
        "--clearenv",  # no API keys or other variables
        "--setenv", "PATH", "/venv/bin:/usr/bin",
        "--setenv", "HOME", "/scratch",
        "/venv/bin/python", "-",  # "-" = read the program from stdin
    ]


def run_python(code: str, scratch: Path = SCRATCH / "default", timeout: float = TIMEOUT_S) -> str:
    """Run `code` with a fresh, sandboxed Python in `scratch` and return what it printed, capped."""
    scratch.mkdir(parents=True, exist_ok=True)
    try:
        result = subprocess.run(
            sandbox_command(scratch),
            input=code,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        output = result.stdout + result.stderr
        if result.returncode != 0:
            output += f"\n[exit code {result.returncode}]"
    except subprocess.TimeoutExpired as e:
        output = _text(e.stdout) + _text(e.stderr)
        output += f"\n[killed: still running after {timeout:g} s]"
    return cap(output)


def cap(output: str, limit: int = OUTPUT_CAP) -> str:
    """Keep the first `limit` characters and say how much was cut."""
    if len(output) <= limit:
        return output
    cut = len(output) - limit
    return output[:limit] + f"\n[output truncated: {cut:,} more chars; print less]"


def _text(b: bytes | str | None) -> str:
    # On timeout, the partial output may come back as bytes.
    if isinstance(b, bytes):
        return b.decode(errors="replace")
    return b or ""
