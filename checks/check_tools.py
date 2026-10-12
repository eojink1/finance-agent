"""Fails loudly if run_python's safety limits break. Run: uv run python checks/check_tools.py"""

import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from agent.tools import DATA, OUTPUT_CAP, ROOT, SCRATCH, PythonSession, run_python

# 1. Normal code: output comes back.
assert run_python("print(1 + 1)").strip() == "2"

# 2. Errors come back too, so the model can fix its code.
out = run_python("1 / 0")
assert "ZeroDivisionError" in out, out

# 3. Endless loop is killed by the timeout.
start = time.time()
out = run_python("while True: pass", timeout=2)
assert time.time() - start < 5, "timeout did not stop the loop"
assert "[killed" in out, out

# 4. A huge print is cut and the model is told.
out = run_python("print('x' * 1_000_000)")
assert len(out) < OUTPUT_CAP + 100, len(out)
assert "[output truncated" in out, out[-200:]

# 5. API keys don't reach the subprocess.
os.environ["OPENROUTER_API_KEY"] = "secret-test-value"
out = run_python("import os; print(os.environ.get('OPENROUTER_API_KEY'))")
assert out.strip() == "None", out

# 6. Separate sessions share nothing in memory, but files in scratch/ persist.
run_python("x = 5; open('note.txt', 'w').write('kept')")
assert "NameError" in run_python("print(x)")
assert run_python("print(open('note.txt').read())").strip() == "kept"
(SCRATCH / "default" / "note.txt").unlink()

# 7. pandas and the data are available.
assert run_python("import pandas; print('ok')").strip() == "ok"
assert "(138236, 21)" in run_python("import pandas as pd; print(pd.read_csv('/data/payments.csv').shape)")

# 8. Sandbox: the home folder and the project (including .env) are invisible.
for path in [Path.home(), Path.home() / ".ssh", ROOT / ".env"]:
    out = run_python(f"import os; print(os.path.exists({str(path)!r}))")
    assert out.strip() == "False", f"{path} is visible: {out}"

# 9. Sandbox: the data and the system are read-only; only scratch is writable.
for path in ["/data/payments.csv", "/data/new.txt", "/usr/evil.txt", "/venv/evil.txt"]:
    out = run_python(f"open({path!r}, 'a').write('x')")
    assert "Read-only file system" in out or "Permission denied" in out, f"{path} writable: {out}"
assert (DATA / "payments.csv").stat().st_size > 20_000_000  # still intact

# 10. Sandbox: no network.
out = run_python("import socket; socket.create_connection(('1.1.1.1', 443), timeout=5)")
assert "OSError" in out or "unreachable" in out, out

# 11. A session keeps variables and imports between calls, like notebook cells.
with PythonSession(timeout=2) as s:
    s.run("import pandas as pd; x = 5")
    assert s.run("print(x + 1, pd.__name__)").strip() == "6 pandas"
    # An error doesn't lose the variables.
    assert "ZeroDivisionError" in s.run("1 / 0")
    assert s.run("print(x)").strip() == "5"
    # Output printed below Python (C level, straight to the file descriptor) is captured too.
    assert s.run("import os; os.write(1, b'raw\\n')").strip() == "raw"
    # A timeout restarts the session and says so.
    out = s.run("while True: pass")
    assert "[killed" in out and "variables are gone" in out, out
    assert "NameError" in s.run("print(x)")
    # Killing the process also restarts it on the next call.
    assert "session ended" in s.run("import os; os._exit(1)")
    assert s.run("print('back')").strip() == "back"

print("all run_python checks passed")
