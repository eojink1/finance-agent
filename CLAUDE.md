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
- One idea per change, ideally under ~50 lines of diff, so the user can review each before the
  next starts. Don't stack unreviewed changes.
- Offer to let the user write the code: explain the concept and plan, let them implement it,
  then review their code instead of writing it yourself.
- Keep the AI side in Python. Use LangChain / LangGraph abstractions wherever they exist rather
  than hand-written code; when one hides something that matters (or breaks), explain what it
  does underneath. No database or UI until phase 2.
