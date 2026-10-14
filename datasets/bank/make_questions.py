"""Write the phase 2 test set: data/tasks/bank.jsonl, in the same format as DABstep's tasks.

uv run python -m datasets.bank.make_data && uv run python -m datasets.bank.make_questions

Every answer is computed from transactions.csv with the definitions in transactions-readme.md,
never typed by hand, so the key matches the data even if the generator changes. Questions whose
premise the data can't support (no travel, no 2025 data) expect 'Not Applicable'.
"""

import json

import pandas as pd

from agent.tools import ROOT

NA = "Not Applicable"
APPLICABLE = (
    " If a question does not have a relevant or applicable answer for the task,"
    " please respond with 'Not Applicable'"
)
MONEY = "Answer must be just a number rounded to 2 decimals, without a currency sign."
MONTH = "Answer must be just the month's full English name."
MERCHANT = "Answer must be just the merchant text exactly as in the description column."


def spending(df: pd.DataFrame) -> float:
    """The readme's definition: money out minus refunds, outside Income and Transfer, positive."""
    return -df[~df.category.isin(["Income", "Transfer"])].amount.sum()


def in_month(df: pd.DataFrame, month: int) -> pd.DataFrame:
    return df[df.date.dt.month == month]


def by_month(df: pd.DataFrame) -> pd.Series:
    return df.groupby(df.date.dt.month).apply(spending)


def month_name(m: int) -> str:
    return pd.Timestamp(2026, m, 1).month_name()


def answers(df: pd.DataFrame) -> list[tuple[str, str, str, str]]:
    """(level, question, guidelines, answer) for each task."""
    spend = df[~df.category.isin(["Income", "Transfer"])]
    feb, mar, apr, may = in_month(df, 2), in_month(df, 3), in_month(df, 4), in_month(df, 5)

    subs = df[df.category == "Subscriptions"]
    june_subs = in_month(subs, 6)
    prices = subs.groupby("description").amount.agg(["first", "last"])
    # Amounts are negative, so a bigger charge is a smaller number.
    rose = prices[prices["last"] < prices["first"]]
    cancelled = sorted(set(subs.description) - set(june_subs.description))

    pays = df[df.category == "Income"].groupby(df.date.dt.month).size()
    feb_by_category = -feb.groupby("category").amount.sum()
    mar_by_category = -mar.groupby("category").amount.sum()
    change = mar_by_category.sub(feb_by_category, fill_value=0)
    change = change.drop(["Income", "Transfer"], errors="ignore")
    largest = spend[spend.category != "Housing"].sort_values("amount").iloc[0]
    groceries = -df[df.category == "Groceries"].groupby("description").amount.sum()
    q1_groceries = df[(df.category == "Groceries") & (df.date.dt.month <= 3)]
    amazon_april = apr[apr.description.str.startswith("AMAZON")]
    housing_share = -spend[spend.category == "Housing"].amount.sum() / spending(df) * 100

    return [
        ("easy", "How much did I spend in total in March 2026?", MONEY, f"{spending(mar):.2f}"),
        ("easy", "Which month in 2026 had my highest spending?", MONTH,
         month_name(by_month(df).idxmax())),
        ("hard", "How much more did I spend in March 2026 than in February 2026?", MONEY,
         f"{spending(mar) - spending(feb):.2f}"),
        ("hard",
         "Which category accounts for the largest part of the increase in my spending"
         " from February to March 2026?",
         "Answer must be just the category name as it appears in the data.",
         change.idxmax()),
        ("easy", "What was my largest single purchase, not counting rent?", MERCHANT,
         largest.description),
        ("easy", "How much did I spend on groceries from January through March 2026?", MONEY,
         f"{-q1_groceries.amount.sum():.2f}"),
        ("hard", "Which subscription went up in price, and what does it cost now?",
         "Answer must be in the form 'description, price' where description is exactly as in"
         " the description column and price is a number rounded to 2 decimals.",
         f"{rose.index[0]}, {-rose['last'].iloc[0]:.2f}"),
        ("easy", "Which subscription did I cancel during the period?", MERCHANT, cancelled[0]),
        ("hard", "What is the total monthly cost of my active subscriptions in June 2026?", MONEY,
         f"{-june_subs.amount.sum():.2f}"),
        ("easy", "What was my total income from January through June 2026?", MONEY,
         f"{df[df.category == 'Income'].amount.sum():.2f}"),
        ("easy", "In which month of 2026 did I get paid three times?", MONTH,
         month_name(pays[pays == 3].index[0])),
        ("hard", "How much money did I move into savings in total?", MONEY,
         f"{-df[df.category == 'Transfer'].amount.sum():.2f}"),
        ("easy", "How many times did I eat out in May 2026?", "Answer must be just a whole number.",
         str(len(may[may.category == "Dining"]))),
        ("hard", "What was my net spending at Amazon in April 2026, after refunds?", MONEY,
         f"{-amazon_april.amount.sum() + 0:.2f}"),  # + 0 turns -0.0 into 0.0
        ("hard",
         "What percentage of my total spending from January through June 2026 went to Housing?",
         "Answer must be just a number rounded to 2 decimals, without a % sign.",
         f"{housing_share:.2f}"),
        ("easy", "At which grocery store did I spend the most overall?", MERCHANT,
         groceries.idxmax()),
        ("hard",
         "Leaving out my single largest purchase other than rent, which month in 2026 had my"
         " highest spending?",
         MONTH,
         month_name(by_month(df.drop(largest.name)).idxmax())),
        ("easy", "How much did I spend on travel in May 2026?", MONEY, NA),
        ("easy", "What was my total spending in December 2025?", MONEY, NA),
        ("hard", "What interest rate does my credit card charge?",
         "Answer must be just a percentage rounded to 2 decimals, without a % sign.", NA),
        ("hard", "Why did my Hulu bill go up in May 2026? Name the new price.", MONEY, NA),
    ]


def main():
    df = pd.read_csv(ROOT / "data" / "bank" / "transactions.csv", parse_dates=["date"])
    out = ROOT / "data" / "tasks" / "bank.jsonl"
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w") as f:
        for i, (level, question, guidelines, answer) in enumerate(answers(df), 1):
            task = {
                "task_id": f"bank-{i}",
                "question": question,
                "guidelines": guidelines + APPLICABLE,
                "level": level,
                "answer": answer,
            }
            f.write(json.dumps(task) + "\n")
            print(f"{task['task_id']:>8}  {level:<4}  {answer:<22}  {question}")


if __name__ == "__main__":
    main()
