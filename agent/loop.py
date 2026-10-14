"""The agent loop: ask the model, run the code it asks for, repeat until it answers."""

import json
import os
import shutil
import time
from pathlib import Path

from langfuse import get_client

from agent.tools import ROOT, SCRATCH, Dataset, PythonSession

MAX_STEPS = 20

TOOLS = [{
    "type": "function",
    "function": {
        "name": "run_python",
        "description": (
            "Run Python code and return what it printed (stdout and stderr, cut to 2,000 "
            "characters). Like a notebook: variables, imports and loaded data stay available "
            "in later calls, so load each file once and reuse it. pandas is installed."
        ),
        "parameters": {
            "type": "object",
            "properties": {"code": {"type": "string", "description": "Python code to run"}},
            "required": ["code"],
        },
    },
}]


def load_env(path: Path = ROOT / ".env") -> None:
    """Read KEY=value lines from .env into os.environ (no extra dependency)."""
    for line in path.read_text().splitlines():
        if "=" in line and not line.startswith("#"):
            key, value = line.split("=", 1)
            os.environ.setdefault(key.strip(), value.strip())


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
    # Langfuse's OpenAI client traces each call, but importing it patches the openai package for the
    # whole program, so it is imported here: the LangChain agent (which also uses openai underneath)
    # would otherwise log every model call twice.
    from langfuse.openai import OpenAI

    # The SDK retries rate limits (429) and server errors itself, waiting longer each time.
    client = OpenAI(
        base_url="https://openrouter.ai/api/v1",
        api_key=os.environ["OPENROUTER_API_KEY"],
        max_retries=5,
    )
    messages = [
        {"role": "system", "content": dataset.system_prompt()},
        {"role": "user", "content": f"{question}\n\nGuidelines: {guidelines}"},
    ]
    shutil.rmtree(scratch, ignore_errors=True)  # no files left over from an earlier run
    scratch.mkdir(parents=True)
    usage = {"input_tokens": 0, "cached_tokens": 0, "output_tokens": 0, "cost": 0.0}
    start = time.time()

    langfuse = get_client()
    span_input = {"question": question, "guidelines": guidelines}
    with (
        open(trace_path or os.devnull, "w") as trace,
        PythonSession(dataset, scratch) as python,
        langfuse.start_as_current_observation(
            name="agent", as_type="agent", input=span_input
        ) as span,
    ):
        def log(**event):
            trace.write(json.dumps(event) + "\n")
            trace.flush()

        answer = None
        try:
            for step in range(1, MAX_STEPS + 1):
                response = client.chat.completions.create(
                    model=model,
                    messages=with_cache_marks(messages, model),
                    tools=TOOLS,
                    extra_body={"usage": {"include": True}},  # OpenRouter adds the cost in USD
                )
                add_usage(usage, response.usage)
                reply = response.choices[0].message
                messages.append(reply.model_dump(exclude_none=True))
                tool_calls = [c.function.arguments for c in reply.tool_calls or []]
                log(step=step, role="assistant", content=reply.content, tool_calls=tool_calls)

                if not reply.tool_calls:  # no tool call: the model is done
                    answer = extract_answer(reply.content or "")
                    break

                for call in reply.tool_calls:
                    with langfuse.start_as_current_observation(
                        name="run_python", as_type="tool"
                    ) as tool:
                        try:
                            code = json.loads(call.function.arguments)["code"]
                            output = python.run(code)
                        except (json.JSONDecodeError, KeyError) as e:
                            code = call.function.arguments
                            output = f"[bad tool call: {e}; send JSON with a 'code' field]"
                        tool.update(input=code, output=output)
                    messages.append({"role": "tool", "tool_call_id": call.id, "content": output})
                    log(step=step, role="tool", content=output)
        except Exception as e:  # still out of retries: keep the trace, let the caller decide
            log(error=repr(e), **usage)
            raise

        seconds = round(time.time() - start, 1)
        result = {"answer": answer, "steps": step, "seconds": seconds, **usage}
        log(**result)
        span.update(output=result)
        result["trace_id"] = langfuse.get_current_trace_id()  # lets the eval attach a score
    return result


def with_cache_marks(messages: list[dict], model: str) -> list[dict]:
    """Mark the system prompt and the newest message as cacheable, for Claude models only.

    Other providers cache repeated prompt prefixes by themselves; Anthropic caches only up to
    a `cache_control` mark. Marking the newest message each step caches the whole conversation
    so far, so the next step pays the cached price for all of it. Returns a marked copy.
    """
    if not model.startswith("anthropic/"):
        return messages
    marked = list(messages)
    for i in {0, len(marked) - 1}:  # the system prompt, and the newest message
        message = dict(marked[i])
        if isinstance(message.get("content"), str) and message["content"]:
            text = message["content"]
            message["content"] = [
                {"type": "text", "text": text, "cache_control": {"type": "ephemeral"}}
            ]
            marked[i] = message
    return marked


def add_usage(total: dict, usage) -> None:
    """Add one response's token counts and cost (when the provider reports them) to `total`."""
    if not usage:
        return
    total["input_tokens"] += usage.prompt_tokens
    total["output_tokens"] += usage.completion_tokens
    details = usage.prompt_tokens_details
    if details and details.cached_tokens:
        total["cached_tokens"] += details.cached_tokens
    total["cost"] += getattr(usage, "cost", None) or 0.0  # OpenRouter's extra field


def extract_answer(text: str) -> str:
    """Take what follows the last 'FINAL ANSWER:'; fall back to the whole reply.

    Markdown around the answer is dropped: '**FINAL ANSWER:** 0.12' gives '0.12'.
    """
    marker = "FINAL ANSWER:"
    if marker in text:
        text = text.rsplit(marker, 1)[1]
    return text.strip().strip("*`").strip()


if __name__ == "__main__":
    # Run one dev task by hand: uv run python -m agent.loop [task_id] [--model M]
    import argparse

    from datasets.dabstep import DABSTEP

    load_env()  # first, so the --model default can read MODEL from .env
    parser = argparse.ArgumentParser(description="Run one DABstep dev task with the plain loop.")
    parser.add_argument("task_id", nargs="?", default="5", help="dev task id (default: 5)")
    parser.add_argument("--model", default=os.environ["MODEL"], help="default: MODEL from .env")
    args = parser.parse_args()

    with open(ROOT / "data" / "tasks" / "dev.jsonl") as f:
        tasks = [json.loads(line) for line in f]
    task = next(t for t in tasks if t["task_id"] == args.task_id)
    (ROOT / "runs").mkdir(exist_ok=True)
    trace_path = ROOT / "runs" / f"task_{args.task_id}.jsonl"
    result = run_agent(task["question"], task["guidelines"], args.model, DABSTEP, trace_path)
    print(json.dumps(result, indent=2))
    print("expected:", task["answer"])
    print("trace:", trace_path)
    get_client().flush()  # send the Langfuse trace before exiting
