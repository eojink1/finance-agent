# Finance Agent

Read `PLAN.md` first: goal, phases, every design decision and why, evaluation, costs, first steps.
Architecture diagrams are in `docs/diagrams/` (regenerate with `python3 make.py`).

## How to work in this repo

- Explain a new concept (how it works, why it helps here) before implementing it. If the user
  doesn't follow, re-explain from scratch with one concrete example and no jargon.
- Measure every agent or prompt change on DABstep before keeping it; log results in
  `docs/EVALUATION.md`. Prefer deleting changes that don't help.
- Check model prices before picking a model; iterate on small samples, not full runs.
- Don't commit until the user has reviewed the change.
- Keep the AI side in Python. Keep the MVP small: no database, framework or UI until phase 2.
