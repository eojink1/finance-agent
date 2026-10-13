"""The agent, built with LangChain: create_agent runs the ask-model / run-tool / repeat cycle.

Same inputs and result as agent.loop.run_agent, so the eval can run either and compare them.
"""

import json
import os
import shutil
import time
from pathlib import Path

from langchain.agents import create_agent
from langchain.agents.middleware import ModelCallLimitMiddleware
from langchain_core.tools import tool
from langchain_openai import ChatOpenAI
from langfuse import get_client
from langfuse.langchain import CallbackHandler

from agent.loop import MAX_STEPS, extract_answer, load_env
from agent.tools import ROOT, SCRATCH, Dataset, PythonSession


def chat_model(model: str) -> ChatOpenAI:
    """An OpenRouter model. For Claude, a request-level cache_control makes OpenRouter cache the
    whole conversation so far on every call (other providers cache repeated prefixes by themselves)."""
    extra = {"usage": {"include": True}}  # OpenRouter adds the cost in USD
    if model.startswith("anthropic/"):
        extra["cache_control"] = {"type": "ephemeral"}
    return ChatOpenAI(model=model, base_url="https://openrouter.ai/api/v1",
                      api_key=os.environ["OPENROUTER_API_KEY"], extra_body=extra,
                      timeout=120, max_retries=5)  # no timeout by default: a stalled call would hang forever


def run_agent(question: str, guidelines: str, model: str, dataset: Dataset, trace_path: Path | None = None,
              scratch: Path = SCRATCH / "default") -> dict:
    """Run one task in an empty `scratch` folder. Returns the answer plus step, token, cost and time counts."""
    shutil.rmtree(scratch, ignore_errors=True)  # no files left over from an earlier run
    scratch.mkdir(parents=True)
    start = time.time()

    with (PythonSession(dataset, scratch) as python,
          get_client().start_as_current_observation(name="agent", as_type="agent",
                                                    input={"question": question, "guidelines": guidelines}) as span):
        @tool
        def run_python(code: str) -> str:
            """Run Python code and return what it printed (stdout and stderr, cut to 2,000 characters).
            Like a notebook: variables, imports and loaded data stay available in later calls, so load
            each file once and reuse it. pandas is installed."""
            return python.run(code)

        agent = create_agent(chat_model(model), [run_python], system_prompt=dataset.system_prompt(),
                             middleware=[ModelCallLimitMiddleware(run_limit=MAX_STEPS, exit_behavior="end")])
        state = agent.invoke({"messages": [{"role": "user", "content": f"{question}\n\nGuidelines: {guidelines}"}]},
                             config={"callbacks": [CallbackHandler()], "recursion_limit": 10 * MAX_STEPS})  # LangGraph counts ~4 graph steps per model call; the
        # call limit above is what should stop a run, so this backstop sits well above it

        # Only the model's own replies carry token usage; the call limit adds an AI message without it.
        replies = [m for m in state["messages"] if m.type == "ai" and m.usage_metadata]
        last = state["messages"][-1]
        result = {
            "answer": extract_answer(last.text) if last in replies and not last.tool_calls else None,
            "steps": len(replies),
            "seconds": round(time.time() - start, 1),
            "input_tokens": sum(m.usage_metadata["input_tokens"] for m in replies),
            "cached_tokens": sum(m.usage_metadata["input_token_details"].get("cache_read", 0) for m in replies),
            "output_tokens": sum(m.usage_metadata["output_tokens"] for m in replies),
            "cost": sum(m.response_metadata.get("token_usage", {}).get("cost") or 0 for m in replies),
        }
        span.update(output=result)
        result["trace_id"] = get_client().get_current_trace_id()  # lets the eval attach a score

    if trace_path:
        with open(trace_path, "w") as trace:
            for m in state["messages"]:
                trace.write(json.dumps({"role": m.type, "content": m.text,
                                        "tool_calls": [c["args"] for c in getattr(m, "tool_calls", [])]}) + "\n")
            trace.write(json.dumps(result) + "\n")
    return result


if __name__ == "__main__":
    # Run one dev task by hand and print each step: uv run python -m agent.langchain_agent <task_id> [model]
    import sys

    from datasets.dabstep import DABSTEP

    load_env()
    task_id = sys.argv[1] if len(sys.argv) > 1 else "5"
    model = sys.argv[2] if len(sys.argv) > 2 else os.environ["MODEL"]
    task = next(t for t in map(json.loads, open(ROOT / "data" / "tasks" / "dev.jsonl")) if t["task_id"] == task_id)
    (ROOT / "runs").mkdir(exist_ok=True)
    trace_path = ROOT / "runs" / f"task_{task_id}_langchain.jsonl"
    result = run_agent(task["question"], task["guidelines"], model, DABSTEP, trace_path)
    for step in map(json.loads, open(trace_path)):
        if "role" in step:
            print(f"--- {step['role']}\n{step['content'][:500]}" + "".join(f"\n[run_python]\n{c['code']}" for c in step["tool_calls"]))
    print(json.dumps(result, indent=2))
    print("expected:", task["answer"])
    print("trace:", trace_path)
    get_client().flush()  # send the Langfuse trace before exiting
