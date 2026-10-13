"""DABstep: the payments files, the tested fee-rule helpers and the system prompt that describes them."""

from pathlib import Path

from agent.tools import ROOT, SANDBOX_DATA, Dataset

DATA = ROOT / "data" / "context"


def system_prompt() -> str:
    files = "\n".join(f"- {SANDBOX_DATA}/{p.name}" for p in sorted(DATA.iterdir()))
    return f"""You are a data analyst. Answer the question by writing and running Python code \
with the run_python tool, one step at a time: look at the data, compute, check your result.

Data files (use these absolute paths):
{files}

Tested fee-rule helpers are already loaded in the Python session; use them instead of writing \
your own rule matching. They follow the manual (a null or empty-list field in a rule matches \
anything; ranges, capture delay, intracountry and monthly stats are handled):
- matching_fee_rules(card_scheme=, account_type=, merchant_category_code=, is_credit=, aci=, \
intracountry=, capture_delay=, monthly_volume=, monthly_fraud_level=) -> list of rule dicts. \
Pass only the facts the question gives; the rest are not filtered on.
- fee(rule, amount) -> fee in euros for one transaction
- merchant_info(merchant) -> the merchant's record (account_type, capture_delay, MCC, acquirers)
- monthly_stats(merchant, year, month) -> {{"volume": euros, "fraud_level": percent}}
- transaction_rules(row) -> rules that apply to one payments.csv row
- applicable_fee_ids(merchant, year, month=None, day_of_year=None) -> sorted rule IDs that \
apply to any of the merchant's payments in that period
Call help(name) for details.

When you are done, reply without a tool call. End the reply with one line:
FINAL ANSWER: <answer>
The answer must follow the question's guidelines exactly.

# payments-readme.md
{(DATA / "payments-readme.md").read_text()}

# manual.md
{(DATA / "manual.md").read_text()}"""


DABSTEP = Dataset(data=DATA, helpers=Path(__file__).resolve().parent / "helpers",
                  preload="from fee_rules import *", system_prompt=system_prompt)
