"""The agent loop: ask the model, run the code it asks for, repeat until it answers."""

import json
import os
import shutil
import time
from pathlib import Path

from langfuse import get_client
from langfuse.openai import OpenAI  # same client as openai's, but each call is traced in Langfuse

from agent.tools import DATA, ROOT, SANDBOX_DATA, SCRATCH, run_python

MAX_STEPS = 20

TOOLS = [{
    "type": "function",
    "function": {
        "name": "run_python",
        "description": (
            "Run Python code in a fresh process and return what it printed (stdout and "
            "stderr, cut to 2,000 characters). Variables do not survive between calls; "
            "save anything worth keeping to a file in the current folder. pandas is installed."
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


def system_prompt() -> str:
    files = "\n".join(f"- {SANDBOX_DATA}/{p.name}" for p in sorted(DATA.iterdir()))
    return f"""You are a data analyst. Answer the question by writing and running Python code \
with the run_python tool, one step at a time: look at the data, compute, check your result.

Data files (use these absolute paths):
{files}

When you are done, reply without a tool call. End the reply with one line:
FINAL ANSWER: <answer>
The answer must follow the question's guidelines exactly.

# payments-readme.md
{(DATA / "payments-readme.md").read_text()}

# manual.md
{(DATA / "manual.md").read_text()}"""


def run_agent(question: str, guidelines: str, model: str, trace_path: Path | None = None,
              scratch: Path = SCRATCH / "default") -> dict:
    """Run one task in an empty `scratch` folder. Returns the answer plus step, token, cost and time counts."""
    # The SDK retries rate limits (429) and server errors itself, waiting longer each time.
    client = OpenAI(base_url="https://openrouter.ai/api/v1", api_key=os.environ["OPENROUTER_API_KEY"],
                    max_retries=5)
    messages = [
        {"role": "system", "content": system_prompt()},
        {"role": "user", "content": f"{question}\n\nGuidelines: {guidelines}"},
    ]
    shutil.rmtree(scratch, ignore_errors=True)  # no files left over from an earlier run
    scratch.mkdir(parents=True)
    usage = {"input_tokens": 0, "cached_tokens": 0, "output_tokens": 0, "cost": 0.0}
    start = time.time()

    langfuse = get_client()
    with (open(trace_path or os.devnull, "w") as trace,
          langfuse.start_as_current_observation(name="agent", as_type="agent",
                                                input={"question": question, "guidelines": guidelines}) as span):
        def log(**event):
            trace.write(json.dumps(event) + "\n")
            trace.flush()

        answer = None
        try:
            for step in range(1, MAX_STEPS + 1):
                response = client.chat.completions.create(
                    model=model, messages=messages, tools=TOOLS,
                    extra_body={"usage": {"include": True}},  # OpenRouter adds the cost in USD
                )
                add_usage(usage, response.usage)
                reply = response.choices[0].message
                messages.append(reply.model_dump(exclude_none=True))
                log(step=step, role="assistant", content=reply.content,
                    tool_calls=[c.function.arguments for c in reply.tool_calls or []])

                if not reply.tool_calls:  # no tool call: the model is done
                    answer = extract_answer(reply.content or "")
                    break

                for call in reply.tool_calls:
                    with langfuse.start_as_current_observation(name="run_python", as_type="tool") as tool:
                        try:
                            code = json.loads(call.function.arguments)["code"]
                            output = run_python(code, scratch)
                        except (json.JSONDecodeError, KeyError) as e:
                            code = call.function.arguments
                            output = f"[bad tool call: {e}; send JSON with a 'code' field]"
                        tool.update(input=code, output=output)
                    messages.append({"role": "tool", "tool_call_id": call.id, "content": output})
                    log(step=step, role="tool", content=output)
        except Exception as e:  # still out of retries: keep the trace, let the caller decide
            log(error=repr(e), **usage)
            raise

        result = {"answer": answer, "steps": step, "seconds": round(time.time() - start, 1), **usage}
        log(**result)
        span.update(output=result)
        result["trace_id"] = langfuse.get_current_trace_id()  # lets the eval attach a score
    return result


def add_usage(total: dict, usage) -> None:
    """Add one response's token counts and cost (when the provider reports them) to `total`."""
    if not usage:
        return
    total["input_tokens"] += usage.prompt_tokens
    total["output_tokens"] += usage.completion_tokens
    details = usage.prompt_tokens_details
    total["cached_tokens"] += (details and details.cached_tokens) or 0
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
    # Run one dev task by hand: uv run python -m agent.loop <task_id>
    import sys

    load_env()
    task_id = sys.argv[1] if len(sys.argv) > 1 else "5"
    tasks = [json.loads(l) for l in open(ROOT / "data" / "tasks" / "dev.jsonl")]
    task = next(t for t in tasks if str(t["task_id"]) == task_id)
    (ROOT / "runs").mkdir(exist_ok=True)
    trace_path = ROOT / "runs" / f"task_{task_id}.jsonl"
    result = run_agent(task["question"], task["guidelines"], os.environ["MODEL"], trace_path)
    print(json.dumps(result, indent=2))
    print("expected:", task["answer"])
    print("trace:", trace_path)
    get_client().flush()  # send the Langfuse trace before exiting
