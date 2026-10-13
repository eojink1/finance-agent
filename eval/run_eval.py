"""Run the agent on DABstep tasks k times each and score with the official scorer.

uv run python -m eval.run_eval --k 3            # 10 dev tasks
uv run python -m eval.run_eval --k 1 --tasks 5 1273
uv run python -m eval.run_eval --k 1 --split all  # all 450 tasks; writes submission.jsonl
"""

import argparse
import importlib.util
import json
import os
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime

from langfuse import get_client, propagate_attributes

from agent.loop import load_env, run_agent
from agent.tools import ROOT, SCRATCH
from datasets.dabstep import DABSTEP

# scorer.py is the leaderboard's own file, downloaded into data/ (not part of this repo).
_spec = importlib.util.spec_from_file_location("scorer", ROOT / "data" / "scorer.py")
scorer = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(scorer)


def run_one(task: dict, run: int, model: str, out_dir) -> dict:
    """One attempt at one task. API failures count as wrong, so the eval keeps going."""
    name = f"task_{task['task_id']}_run{run}"
    row = {"task_id": task["task_id"], "level": task["level"], "run": run, "expected": task["answer"]}
    try:
        # In Langfuse: one session per eval, one trace per run, tagged and scored.
        with propagate_attributes(session_id=out_dir.name, trace_name=name, tags=[task["level"]],
                                  metadata={"task_id": str(task["task_id"]), "run": str(run), "model": model}):
            result = run_agent(task["question"], task["guidelines"], model, DABSTEP,
                               trace_path=out_dir / f"{name}.jsonl", scratch=SCRATCH / out_dir.name / name)
        row |= result
        if task["answer"]:  # hidden for the 440 test tasks: those are scored only by submission
            row["correct"] = result["answer"] is not None and scorer.question_scorer(result["answer"], task["answer"])
            get_client().create_score(name="correct", value=int(row["correct"]), data_type="BOOLEAN",
                                      trace_id=result["trace_id"], comment=f"expected {task['answer']!r}")
        else:
            row["correct"] = None
    except Exception as e:
        row |= {"answer": None, "correct": False if task["answer"] else None, "error": repr(e)}
    print(f"  {name}: {MARKS[row['correct']]} {row['answer']!r} (expected {task['answer']!r})"
          + (f" ERROR {row['error']}" if "error" in row else ""), flush=True)
    return row


MARKS = {True: "✓", False: "✗", None: "?"}  # ? = no public answer to score against


def summarize(rows: list[dict], tasks: list[dict], k: int) -> dict:
    by_task = {t["task_id"]: [r for r in rows if r["task_id"] == t["task_id"]] for t in tasks if t["answer"]}
    scored = [r for r in rows if r["correct"] is not None]
    total = lambda key: sum(r.get(key, 0) for r in rows)
    ok = [r for r in rows if "error" not in r]
    return {
        "accuracy": sum(r["correct"] for r in scored) / len(scored) if scored else None,
        "scored_runs": len(scored),
        f"pass^{k}": sum(all(r["correct"] for r in rs) for rs in by_task.values()),
        "tasks": len(tasks),
        "runs": len(rows),
        "errors": len(rows) - len(ok),
        "avg_steps": sum(r["steps"] for r in ok) / max(len(ok), 1),
        "input_tokens": total("input_tokens"),
        "cached_tokens": total("cached_tokens"),
        "output_tokens": total("output_tokens"),
        "cost": round(total("cost"), 4),
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--k", type=int, default=3, help="runs per task")
    parser.add_argument("--tasks", nargs="*", help="task ids (default: all dev tasks)")
    parser.add_argument("--workers", type=int, default=2, help="runs in parallel (free models are rate-limited)")
    parser.add_argument("--model", help="default: MODEL from .env")
    parser.add_argument("--split", choices=["dev", "all"], default="dev", help="10 dev tasks or all 450")
    args = parser.parse_args()

    load_env()
    model = args.model or os.environ["MODEL"]
    tasks = [json.loads(l) for l in open(ROOT / "data" / "tasks" / f"{args.split}.jsonl")]
    if args.tasks:
        tasks = [t for t in tasks if str(t["task_id"]) in args.tasks]

    out_dir = ROOT / "runs" / f"{datetime.now():%Y-%m-%d_%H%M%S}_{model.replace('/', '_').replace(':', '_')}"
    out_dir.mkdir(parents=True)
    print(f"{len(tasks)} tasks x {args.k} runs on {model} -> {out_dir}")

    start = time.time()
    jobs = [(t, run) for run in range(1, args.k + 1) for t in tasks]
    with ThreadPoolExecutor(args.workers) as pool:
        rows = list(pool.map(lambda job: run_one(*job, model, out_dir), jobs))

    summary = {"model": model, "k": args.k, "minutes": round((time.time() - start) / 60, 1),
               **summarize(rows, tasks, args.k)}
    get_client().flush()
    (out_dir / "summary.json").write_text(json.dumps({"summary": summary, "rows": rows}, indent=2))
    if args.k == 1:  # the leaderboard's format: one line per task; no answer counts as wrong
        with open(out_dir / "submission.jsonl", "w") as f:
            for r in rows:
                f.write(json.dumps({"task_id": str(r["task_id"]), "agent_answer": r["answer"] or ""}) + "\n")

    print()
    for t in tasks:
        marks = "".join(MARKS[r["correct"]] for r in rows if r["task_id"] == t["task_id"])
        print(f"task {t['task_id']:>5}  {t['level']:<4}  {marks}")
    print()
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
