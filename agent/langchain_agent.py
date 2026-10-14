"""The agent, built with LangChain: create_agent runs the ask-model / run-tool / repeat cycle.

Same inputs and result as agent.loop.run_agent, so the eval can run either and compare them.
"""

import functools
import json
import os
import shutil
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from langchain.agents import create_agent
from langchain.agents.middleware import ModelCallLimitMiddleware
from langchain.tools import ToolRuntime, tool
from langchain_core.runnables import RunnableConfig
from langchain_openai import ChatOpenAI
from langfuse import get_client
from langfuse.langchain import CallbackHandler
from pydantic import SecretStr

from agent.loop import MAX_STEPS, extract_answer, load_env
from agent.tools import ROOT, SCRATCH, Dataset, PythonSession

OPENROUTER_URL = "https://openrouter.ai/api/v1"


def chat_model(model: str) -> ChatOpenAI:
    """An OpenRouter model.

    For Claude, a request-level cache_control makes OpenRouter cache the whole conversation so far
    on every call (other providers cache repeated prefixes by themselves).
    """
    extra_body: dict[str, Any] = {"usage": {"include": True}}  # OpenRouter adds the cost in USD
    if model.startswith("anthropic/"):
        extra_body["cache_control"] = {"type": "ephemeral"}
    return ChatOpenAI(
        model=model,
        base_url=OPENROUTER_URL,
        api_key=SecretStr(os.environ["OPENROUTER_API_KEY"]),
        extra_body=extra_body,
        timeout=120,  # no timeout by default: a stalled call would hang forever
        max_retries=5,
    )


@dataclass
class Context:
    """What each task passes to agent.invoke(context=...); tools read it from runtime.context."""

    python: PythonSession  # this task's sandbox


# LangChain fills in `runtime` on each call and hides it from the model, which sees only `code`.
@tool
def run_python(code: str, runtime: ToolRuntime[Context]) -> str:
    """Run Python code and return what it printed (stdout and stderr, cut to 2,000 characters).
    Like a notebook: variables, imports and loaded data stay available in later calls, so load
    each file once and reuse it. pandas is installed."""
    return runtime.context.python.run(code)


@functools.cache
def build_agent(model: str, dataset: Dataset):
    """One agent per model and dataset, reused by every task.

    Each task's sandbox comes in as context when the agent is invoked.
    """
    # [Any, Context]: every middleware must declare the agent's context type, or type checkers
    # reject the create_agent call (it runs either way).
    step_limit = ModelCallLimitMiddleware[Any, Context](run_limit=MAX_STEPS, exit_behavior="end")
    return create_agent(
        chat_model(model),
        [run_python],
        system_prompt=dataset.system_prompt(),
        middleware=[step_limit],
        context_schema=Context,
    )


def run_agent(
    question: str,
    guidelines: str,
    model: str,
    dataset: Dataset,
    trace_path: Path | None = None,
    scratch: Path = SCRATCH / "default",
) -> dict:
    """Run one task in an empty `scratch` folder.

    Returns the answer plus step, token, cost and time counts.
    """
    shutil.rmtree(scratch, ignore_errors=True)  # no files left over from an earlier run
    scratch.mkdir(parents=True)
    start = time.time()

    message = {"role": "user", "content": f"{question}\n\nGuidelines: {guidelines}"}
    # LangGraph counts ~4 graph steps per model call. The model-call limit is what should stop a
    # run, so this backstop sits well above it.
    config: RunnableConfig = {"callbacks": [CallbackHandler()], "recursion_limit": 10 * MAX_STEPS}
    langfuse = get_client()
    span_input = {"question": question, "guidelines": guidelines}

    with (
        PythonSession(dataset, scratch) as python,
        langfuse.start_as_current_observation(
            name="agent", as_type="agent", input=span_input
        ) as span,
    ):
        agent = build_agent(model, dataset)
        state = agent.invoke({"messages": [message]}, config, context=Context(python=python))
        result = summarize(state["messages"])
        result["seconds"] = round(time.time() - start, 1)
        span.update(output=result)
        result["trace_id"] = langfuse.get_current_trace_id()  # lets the eval attach a score

    if trace_path:
        write_trace(trace_path, state["messages"], result)
    return result


def summarize(messages: list) -> dict:
    """The answer, if the model finished on its own, plus step, token and cost counts."""
    # Only the model's own replies carry token usage; the call limit adds an AI message without it.
    replies = [m for m in messages if m.type == "ai" and m.usage_metadata]
    last = messages[-1]
    finished = last in replies and not last.tool_calls
    usage = [m.usage_metadata for m in replies]
    return {
        "answer": extract_answer(last.text) if finished else None,
        "steps": len(replies),
        "input_tokens": sum(u["input_tokens"] for u in usage),
        "cached_tokens": sum(u["input_token_details"].get("cache_read", 0) for u in usage),
        "output_tokens": sum(u["output_tokens"] for u in usage),
        "cost": sum(cost(m) for m in replies),
    }


def cost(reply) -> float:
    """USD cost OpenRouter reported for one model call (0 if it didn't)."""
    return reply.response_metadata.get("token_usage", {}).get("cost") or 0


def write_trace(path: Path, messages: list, result: dict) -> None:
    """One JSON line per message, then the result, for reading a run without Langfuse."""
    with open(path, "w") as trace:
        for m in messages:
            tool_calls = [c["args"] for c in getattr(m, "tool_calls", [])]
            line = {"role": m.type, "content": m.text, "tool_calls": tool_calls}
            trace.write(json.dumps(line) + "\n")
        trace.write(json.dumps(result) + "\n")


if __name__ == "__main__":
    # Run one dev task by hand and print each step:
    #   uv run python -m agent.langchain_agent [task_id] [--model M]
    import argparse

    from datasets.dabstep import DABSTEP

    load_env()  # first, so the --model default can read MODEL from .env
    parser = argparse.ArgumentParser(description="Run one DABstep dev task and print each step.")
    parser.add_argument("task_id", nargs="?", default="5", help="dev task id (default: 5)")
    parser.add_argument("--model", default=os.environ["MODEL"], help="default: MODEL from .env")
    args = parser.parse_args()

    with open(ROOT / "data" / "tasks" / "dev.jsonl") as f:
        tasks = [json.loads(line) for line in f]
    task = next(t for t in tasks if t["task_id"] == args.task_id)
    (ROOT / "runs").mkdir(exist_ok=True)
    trace_path = ROOT / "runs" / f"task_{args.task_id}_langchain.jsonl"
    result = run_agent(task["question"], task["guidelines"], args.model, DABSTEP, trace_path)

    with open(trace_path) as f:
        steps = [json.loads(line) for line in f]
    for step in steps:
        if "role" not in step:  # the last line is the result, printed below
            continue
        print(f"--- {step['role']}")
        print(step["content"][:500])
        for call in step["tool_calls"]:
            print(f"[run_python]\n{call['code']}")
    print(json.dumps(result, indent=2))
    print("expected:", task["answer"])
    print("trace:", trace_path)
    get_client().flush()  # send the Langfuse trace before exiting
