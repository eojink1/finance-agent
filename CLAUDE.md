# Finance Agent

Read `PLAN.md` first: goal, phases, every design decision and why, evaluation, costs, first steps.
Architecture diagrams are in `docs/diagrams/` (regenerate with `python3 make.py`).

## Commands

- Run a DABstep sample: `uv run python -m eval.run_eval --k 1 --tasks 5 1273`
- Run the bank set: `uv run python -m eval.run_eval --split bank --k 1`
- Tests: `uv run pytest` (one file: `uv run pytest tests/test_tools.py`)

## How to work in this repo

- Explain a new concept (how it works, why it helps here) before implementing it. If the user
  doesn't follow, re-explain from scratch with one concrete example and no jargon.
- Measure every agent or prompt change on DABstep before keeping it; log results in
  `docs/EVALUATION-dabstep.md` (bank: `docs/EVALUATION-bank.md`). Prefer deleting changes that don't help.
- Check model prices before picking a model; iterate on small samples, not full runs.
- Don't commit until the user has reviewed the change.
- Run `uv run pytest` before every commit; don't commit with failing tests.
- One idea per change, ideally under ~50 lines of diff, so the user can review each before the
  next starts. This limits scope, not density. Never compress code to fit under it.
  Don't stack unreviewed changes.
- Offer to let the user write the code: explain the concept and plan, let them implement it,
  then review their code instead of writing it yourself.
- Keep the AI side in Python. Use LangChain / LangGraph abstractions wherever they exist rather
  than hand-written code; when one hides something that matters (or breaks), explain what it
  does underneath. No database or UI until phase 2.

## Code style

- Optimize for readability, not line count. Don't pitch or judge a change by how few lines it has.
- Write code that reads top to bottom: name values before passing them (no dicts or messages built
  inside a call), one job per function, compound conditions as a named boolean, comments above the
  code rather than inside call arguments, lines under ~100 characters. Accept more lines to get this.
- Use the common, industry-standard idiom over the shorter or cleverer one: list comprehensions
  over `map`/`filter`/`lambda`, plain loops over long one-line `"".join(...)` expressions,
  `argparse` over `sys.argv[i]`. When writing something less common, or when the user asks,
  say what the standard way is and why.
