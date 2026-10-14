"""run_python's sandbox: safety limits, and a session that keeps variables like a notebook."""

import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from agent.tools import OUTPUT_CAP, ROOT, TIMEOUT_S, PythonSession
from datasets.dabstep import DABSTEP, DATA


@pytest.fixture
def session(tmp_path):
    """A DABstep session with a short timeout, in an empty scratch folder of its own."""
    with PythonSession(DABSTEP, tmp_path, timeout=2) as s:
        yield s


def run_once(code: str, scratch: Path, timeout: float = TIMEOUT_S) -> str:
    """Run `code` in a fresh session and close it, so nothing is kept between calls."""
    with PythonSession(DABSTEP, scratch, timeout) as s:
        return s.run(code)


# Basics


def test_output_comes_back(session):
    assert session.run("print(1 + 1)").strip() == "2"


def test_errors_come_back(session):
    """The model sees the traceback, so it can fix its code."""
    assert "ZeroDivisionError" in session.run("1 / 0")


def test_endless_loop_is_killed(session):
    start = time.time()
    out = session.run("while True: pass")
    assert time.time() - start < 5, "timeout did not stop the loop"
    assert "[killed" in out


def test_huge_print_is_cut(session):
    out = session.run("print('x' * 1_000_000)")
    assert len(out) < OUTPUT_CAP + 100
    assert "[output truncated" in out


def test_pandas_and_data_are_available(session):
    out = session.run("import pandas as pd; print(pd.read_csv('/data/payments.csv').shape)")
    assert "(138236, 21)" in out


# Sandbox


def test_api_keys_dont_reach_the_sandbox(session, monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "secret-test-value")
    out = session.run("import os; print(os.environ.get('OPENROUTER_API_KEY'))")
    assert out.strip() == "None"


@pytest.mark.parametrize("path", [Path.home(), Path.home() / ".ssh", ROOT / ".env"])
def test_home_and_project_are_invisible(session, path):
    out = session.run(f"import os; print(os.path.exists({str(path)!r}))")
    assert out.strip() == "False", f"{path} is visible"


@pytest.mark.parametrize(
    "path", ["/data/payments.csv", "/data/new.txt", "/usr/evil.txt", "/venv/evil.txt"]
)
def test_data_and_system_are_read_only(session, path):
    out = session.run(f"open({path!r}, 'a').write('x')")
    assert "Read-only file system" in out or "Permission denied" in out, f"{path} writable"
    assert (DATA / "payments.csv").stat().st_size > 20_000_000  # still intact


def test_no_network(session):
    out = session.run("import socket; socket.create_connection(('1.1.1.1', 443), timeout=5)")
    assert "OSError" in out or "unreachable" in out


def test_separate_sessions_share_files_not_memory(tmp_path):
    run_once("x = 5; open('note.txt', 'w').write('kept')", tmp_path)
    assert "NameError" in run_once("print(x)", tmp_path)
    assert run_once("print(open('note.txt').read())", tmp_path).strip() == "kept"


# A session is like a notebook


def test_variables_and_imports_persist(session):
    session.run("import pandas as pd; x = 5")
    assert session.run("print(x + 1, pd.__name__)").strip() == "6 pandas"


def test_an_error_keeps_the_variables(session):
    session.run("x = 5")
    session.run("1 / 0")
    assert session.run("print(x)").strip() == "5"


def test_c_level_output_is_captured(session):
    """Output written below Python, straight to the file descriptor, comes back too."""
    assert session.run("import os; os.write(1, b'raw\\n')").strip() == "raw"


def test_a_timeout_restarts_the_session_and_says_so(session):
    session.run("x = 5")
    out = session.run("while True: pass")
    assert "[killed" in out and "variables are gone" in out
    assert "NameError" in session.run("print(x)")


def test_a_dead_process_restarts_on_the_next_call(session):
    assert "session ended" in session.run("import os; os._exit(1)")
    assert session.run("print('back')").strip() == "back"


# Threads (LangGraph runs tool calls in threads)


def test_parallel_calls_each_get_their_own_reply(tmp_path):
    """LangGraph runs a reply's tool calls at the same time, in parallel threads."""
    codes = ["import time; time.sleep(1); print('slow')", "print('fast')"]
    with PythonSession(DABSTEP, tmp_path, timeout=10) as s, ThreadPoolExecutor(2) as pool:
        slow, fast = pool.map(s.run, codes)
    assert (slow.strip(), fast.strip()) == ("slow", "fast")


def test_session_survives_the_thread_that_started_it(tmp_path):
    """LangGraph runs each tool call in a new, short-lived thread."""
    calls = [("x = 7; print('set')", "set"), ("import time; time.sleep(1); print(x)", "7")]
    with PythonSession(DABSTEP, tmp_path, timeout=10) as s:
        for code, expected in calls:
            with ThreadPoolExecutor(1) as pool:
                out = pool.submit(s.run, code).result()
            assert out.strip() == expected
