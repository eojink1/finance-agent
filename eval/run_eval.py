"""Run the agent on DABstep or bank tasks k times each and score with DABstep's official scorer.

uv run python -m eval.run_eval --k 3            # 10 dev tasks
uv run python -m eval.run_eval --k 1 --tasks 5 1273
uv run python -m eval.run_eval --k 1 --split all  # all 450 tasks; writes submission.jsonl
uv run python -m eval.run_eval --k 1 --split bank  # 21 bank questions
uv run python -m eval.run_eval --k 3 --split bank-why  # open-ended bank tasks, LLM-judged
"""

import argparse
import importlib.util
import json
import os
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime

from langfuse import get_client, propagate_attributes

from agent.langchain_agent import load_env, run_agent
from agent.tools import ROOT, SCRATCH, Dataset
from datasets import DATASETS, load_tasks
from eval.judge import judge

MARKS = {True: "✓", False: "✗", None: "?"}  # ? = no public answer to score against

# scorer.py is the leaderboard's own file, downloaded into data/ (not part of this repo).
_spec = importlib.util.spec_from_file_location("scorer", ROOT / "data" / "scorer.py")
scorer = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(scorer)


def run_one(task: dict, run: int, model: str, dataset: Dataset, out_dir) -> dict:
    """One attempt at one task. API failures count as wrong, so the eval keeps going."""
    name = f"task_{task['task_id']}_run{run}"
    expected = task["answer"]  # empty for the 440 test tasks: those are scored only by submission
    checklist = task.get("checklist")  # open-ended bank tasks: eval/judge.py scores these
    row = {"task_id": task["task_id"], "level": task["level"], "run": run, "expected": expected}

    # In Langfuse: one session per eval, one trace per run, tagged and scored.
    metadata = {"task_id": str(task["task_id"]), "run": str(run), "model": model}
    trace_path = out_dir / f"{name}.jsonl"
    scratch = SCRATCH / out_dir.name / name
    try:
        with propagate_attributes(
            session_id=out_dir.name, trace_name=name, tags=[task["level"]], metadata=metadata
        ):
            result = run_agent(
                task["question"], task["guidelines"], model, dataset, trace_path, scratch
            )
        row |= result
        if expected:
            answered = result["answer"] is not None
            row["correct"] = answered and scorer.question_scorer(result["answer"], expected)
            get_client().create_score(
                name="correct",
                value=int(row["correct"]),
                data_type="BOOLEAN",
                trace_id=result["trace_id"],
                comment=f"expected {expected!r}",
            )
        elif checklist:
            answer = result["answer"] or ""
            verdict = judge(task["question"], answer, checklist)
            row["score"] = verdict.score
            row["verdicts"] = [item.model_dump() for item in verdict.items]
            # A run counts as correct only if it makes every point on the checklist.
            row["correct"] = verdict.score == 1
        else:
            row["correct"] = None
    except Exception as e:
        has_key = bool(expected or checklist)
        row |= {"answer": None, "correct": False if has_key else None, "error": repr(e)}

    line = f"  {name}: {MARKS[row['correct']]} {row['answer']!r} (expected {expected!r})"
    if "score" in row:
        line = f"  {name}: {MARKS[row['correct']]} score {row['score']:.2f}"
        for item in row["verdicts"]:
            line += f"\n      {MARKS[item['met']]} {item['item']}: {item['reason']}"
    if "error" in row:
        line += f" ERROR {row['error']}"
    print(line, flush=True)
    return row


def summarize(rows: list[dict], tasks: list[dict], k: int) -> dict:
    scored = [r for r in rows if r["correct"] is not None]
    ok = [r for r in rows if "error" not in r]
    runs_by_task = {}
    for t in tasks:
        if t["answer"] or t.get("checklist"):
            runs_by_task[t["task_id"]] = [r for r in rows if r["task_id"] == t["task_id"]]
    all_runs_correct = [all(r["correct"] for r in runs) for runs in runs_by_task.values()]

    judged = [r["score"] for r in rows if "score" in r]

    def total(key: str) -> float:
        return sum(r.get(key, 0) for r in rows)

    return {
        "accuracy": sum(r["correct"] for r in scored) / len(scored) if scored else None,
        "judge_score": sum(judged) / len(judged) if judged else None,
        "scored_runs": len(scored),
        f"pass^{k}": sum(all_runs_correct),
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
    parser.add_argument(
        "--workers", type=int, default=2, help="runs in parallel (free models are rate-limited)"
    )
    parser.add_argument("--model", help="default: MODEL from .env")
    parser.add_argument(
        "--split",
        choices=list(DATASETS),
        default="dev",
        help="10 DABstep dev tasks, all 450, the 21 bank questions, or the open-ended bank tasks",
    )
    args = parser.parse_args()

    load_env()
    model = args.model or os.environ["MODEL"]
    dataset = DATASETS[args.split]
    tasks = load_tasks(args.split)
    if args.tasks:
        tasks = [t for t in tasks if str(t["task_id"]) in args.tasks]

    timestamp = f"{datetime.now():%Y-%m-%d_%H%M%S}"
    model_name = model.replace("/", "_").replace(":", "_")
    out_dir = ROOT / "runs" / f"{timestamp}_{args.split}_langchain_{model_name}"
    out_dir.mkdir(parents=True)
    print(f"{len(tasks)} tasks x {args.k} runs on {model} -> {out_dir}")

    def run_job(job: tuple[dict, int]) -> dict:
        task, run = job
        return run_one(task, run, model, dataset, out_dir)

    start = time.time()
    jobs = [(t, run) for run in range(1, args.k + 1) for t in tasks]
    with ThreadPoolExecutor(args.workers) as pool:
        rows = list(pool.map(run_job, jobs))
    minutes = round((time.time() - start) / 60, 1)

    summary = {"model": model, "k": args.k, "minutes": minutes}
    summary |= summarize(rows, tasks, args.k)
    get_client().flush()
    (out_dir / "summary.json").write_text(json.dumps({"summary": summary, "rows": rows}, indent=2))
    if args.k == 1:  # the leaderboard's format: one line per task; no answer counts as wrong
        with open(out_dir / "submission.jsonl", "w") as f:
            for r in rows:
                line = {"task_id": str(r["task_id"]), "agent_answer": r["answer"] or ""}
                f.write(json.dumps(line) + "\n")

    print()
    for t in tasks:
        marks = "".join(MARKS[r["correct"]] for r in rows if r["task_id"] == t["task_id"])
        print(f"task {t['task_id']:>5}  {t['level']:<4}  {marks}")
    print()
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
