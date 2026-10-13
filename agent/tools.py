"""The agent's one tool: run model-written Python in a sandboxed session that keeps its variables."""

import json
import select
import subprocess
import sys
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRATCH = ROOT / "scratch"  # one subfolder per run, shared between its steps; the code runs there
SANDBOX_DATA = "/data"  # where the code sees the dataset's files
TIMEOUT_S = 60
OUTPUT_CAP = 2000  # characters the model gets back


@dataclass(frozen=True)
class Dataset:
    """Everything the agent needs to know about one set of tasks (DABstep, the bank test set)."""
    data: Path  # files the code sees read-only at /data
    helpers: Path  # tested helper modules, importable inside the sandbox, seen read-only at /helpers
    preload: str  # run in every new session before the model's first call
    system_prompt: Callable[[], str]

# Runs inside the sandbox. Reads one JSON-encoded code string per line, runs it in a namespace
# that survives between calls (like notebook cells) and answers with one JSON line holding
# everything the code printed. Prints go to a file at the OS level (fd 1 and 2), so even output
# from C libraries can't mix with the replies, which use a private copy of the original stdout.
SERVER = r"""
import json, os, sys, traceback
replies = os.fdopen(os.dup(1), "w")
out = open("/tmp/.cell_output", "w+")
os.dup2(out.fileno(), 1)
os.dup2(out.fileno(), 2)
requests, sys.stdin = sys.stdin, open(os.devnull)
namespace = {"__name__": "__main__"}
exec(sys.argv[1], namespace)
for line in requests:
    try:
        exec(compile(json.loads(line), "<cell>", "exec"), namespace)
    except BaseException:
        traceback.print_exc()
    sys.stdout.flush()
    sys.stderr.flush()
    out.seek(0)
    text = out.read()
    out.seek(0)
    out.truncate()
    replies.write(json.dumps(text) + "\n")
    replies.flush()
"""


def sandbox_command(dataset: Dataset, scratch: Path) -> list[str]:
    """bwrap command that runs the session server with a tiny, mostly read-only filesystem and no network.

    Inside, the code sees only: /usr (system, read-only), /venv (pandas, read-only),
    /data (the dataset's files, read-only), /helpers (our helper modules, read-only),
    /scratch (read-write) and an empty /tmp.
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
        "--ro-bind", str(dataset.data), SANDBOX_DATA,
        "--ro-bind", str(dataset.helpers), "/helpers",
        "--bind", str(scratch), "/scratch",
        "--tmpfs", "/tmp",
        "--proc", "/proc",
        "--dev", "/dev",
        "--chdir", "/scratch",
        "--unshare-all",  # includes the network
        "--die-with-parent",  # killed if the agent dies
        "--new-session",
        "--clearenv",  # no API keys or other variables
        "--setenv", "PATH", "/venv/bin:/usr/bin",
        "--setenv", "HOME", "/scratch",
        "--setenv", "PYTHONPATH", "/helpers",
        "/venv/bin/python", "-c", SERVER, dataset.preload,
    ]


class PythonSession:
    """One sandboxed Python process per task that keeps variables between calls, like a notebook.

    It starts on the first call. If a call times out or the process dies, the next call
    starts a fresh one, and the model is told its variables are gone.
    """

    def __init__(self, dataset: Dataset, scratch: Path = SCRATCH / "default", timeout: float = TIMEOUT_S):
        self.dataset = dataset
        self.scratch = scratch
        self.timeout = timeout
        self.proc = None

    def run(self, code: str) -> str:
        """Run `code` and return what it printed, capped."""
        if self.proc is None:
            self.scratch.mkdir(parents=True, exist_ok=True)
            self.proc = subprocess.Popen(sandbox_command(self.dataset, self.scratch), text=True,
                                         stdin=subprocess.PIPE, stdout=subprocess.PIPE)
        try:
            self.proc.stdin.write(json.dumps(code) + "\n")
            self.proc.stdin.flush()
            if not select.select([self.proc.stdout], [], [], self.timeout)[0]:
                self.close()
                return (f"[killed: still running after {self.timeout:g} s. "
                        "The Python session was restarted: earlier variables are gone]")
            reply = self.proc.stdout.readline()
        except BrokenPipeError:
            reply = ""
        if not reply:  # the process died, e.g. os._exit() or out of memory
            self.close()
            return "[the Python session ended: earlier variables are gone]"
        return cap(json.loads(reply))

    def close(self) -> None:
        if self.proc:
            self.proc.kill()
            self.proc.wait()
            self.proc = None

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()


def run_python(code: str, dataset: Dataset, scratch: Path = SCRATCH / "default", timeout: float = TIMEOUT_S) -> str:
    """Run `code` once in a fresh session and close it (nothing is kept)."""
    with PythonSession(dataset, scratch, timeout) as session:
        return session.run(code)


def cap(output: str, limit: int = OUTPUT_CAP) -> str:
    """Keep the first `limit` characters and say how much was cut."""
    if len(output) <= limit:
        return output
    cut = len(output) - limit
    return output[:limit] + f"\n[output truncated: {cut:,} more chars; print less]"
