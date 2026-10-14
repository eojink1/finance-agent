"""Write the open-ended bank tasks: data/tasks/bank-why.jsonl, scored by eval/judge.py.

uv run python -m datasets.bank.make_reports

Each task has a checklist instead of an answer: the points a good reply must make. The numbers
are computed from transactions.csv the same way make_questions.py computes its answers.
"""

import json

import pandas as pd

from agent.tools import ROOT
from datasets.bank.make_questions import NOT_SPENDING, in_month, spending

# The agent returns only the text after FINAL ANSWER:, so the explanation has to go there.
EXPLAIN = (
    "Answer in a few sentences, with the amounts that explain it. Put the whole explanation"
    " after 'FINAL ANSWER:'."
)


def checklists(df: pd.DataFrame) -> list[tuple[str, list[str]]]:
    """(question, checklist) for each task."""
    feb, mar, apr = in_month(df, 2), in_month(df, 3), in_month(df, 4)

    feb_by_category = -feb.groupby("category").amount.sum()
    mar_by_category = -mar.groupby("category").amount.sum()
    change = mar_by_category.sub(feb_by_category, fill_value=0)
    change = change.drop(NOT_SPENDING, errors="ignore")
    best_buy = mar[mar.description.str.startswith("BEST BUY")].iloc[0]

    netflix = df[df.description == "NETFLIX.COM"]
    netflix_march = -in_month(netflix, 3).amount.iloc[0]
    netflix_april = -in_month(netflix, 4).amount.iloc[0]
    refund = apr[apr.description.str.endswith("REFUND")].iloc[0]

    march_why = [
        f"Spending rose by about ${spending(mar) - spending(feb):.2f} from February to March",
        f"A ${-best_buy.amount:.2f} purchase at Best Buy in March",
        f"Dining rose by about ${change['Dining']:.2f}",
        f"Gas (Transportation) rose by about ${change['Transportation']:.2f}",
    ]
    april_news = [
        f"Netflix went up from ${netflix_march:.2f} to ${netflix_april:.2f}",
        f"The ${refund.amount:.2f} Amazon order was refunded",
        f"Spending was about ${spending(mar) - spending(apr):.2f} lower than in March",
    ]
    return [
        ("Why did I spend more in March 2026 than in February 2026?", march_why),
        ("Anything I should know about my spending in April 2026?", april_news),
    ]


def main():
    df = pd.read_csv(ROOT / "data" / "bank" / "transactions.csv", parse_dates=["date"])
    out = ROOT / "data" / "tasks" / "bank-why.jsonl"
    with open(out, "w") as f:
        for i, (question, checklist) in enumerate(checklists(df), 1):
            task = {
                "task_id": f"bank-why-{i}",
                "question": question,
                "guidelines": EXPLAIN,
                "level": "hard",
                "answer": "",  # no exact answer: eval/run_eval.py scores the checklist instead
                "checklist": checklist,
            }
            f.write(json.dumps(task) + "\n")
            print(f"{task['task_id']}  {question}")
            for item in checklist:
                print(f"    - {item}")


if __name__ == "__main__":
    main()
