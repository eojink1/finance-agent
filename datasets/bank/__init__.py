"""The bank test set: synthetic transactions and the system prompt that describes them."""

from pathlib import Path

from agent.tools import ROOT, SANDBOX_DATA, Dataset

DATA = ROOT / "data" / "bank"


def system_prompt() -> str:
    files = "\n".join(f"- {SANDBOX_DATA}/{p.name}" for p in sorted(DATA.iterdir()))
    return f"""You are a data analyst. Answer the question by writing and running Python code \
with the run_python tool, one step at a time: look at the data, compute, check your result.

Data files (use these absolute paths):
{files}

When you are done, reply without a tool call. End the reply with one line:
FINAL ANSWER: <answer>
The answer must follow the question's guidelines exactly.

# transactions-readme.md
{(DATA / "transactions-readme.md").read_text()}"""


BANK = Dataset(data=DATA, helpers=Path(__file__).resolve().parent / "helpers",
               preload="", system_prompt=system_prompt)
