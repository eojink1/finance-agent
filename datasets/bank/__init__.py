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

When a question asks why spending changed, or what is worth knowing about a period, explain
rather than describe:
1. Compare the period with the one before it: the total first, then each category.
2. For the categories that changed most, find the transactions behind the change and name the
   merchants and amounts.
3. Point out anything unusual: a recurring charge whose price changed, a refund, a large one-off
   purchase, a charge that started or stopped.

# transactions-readme.md
{(DATA / "transactions-readme.md").read_text()}"""


BANK = Dataset(data=DATA, helpers=Path(__file__).resolve().parent / "helpers",
               preload="", system_prompt=system_prompt)
