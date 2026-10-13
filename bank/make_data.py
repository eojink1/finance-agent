"""Make a synthetic bank export for the phase 2 test set: data/bank/transactions.csv.

uv run python -m bank.make_data

Same seed, same file. The patterns the questions probe are planted on purpose: a one-off
purchase in March, a Netflix price rise in April, Hulu cancelled after February, a refunded
Amazon order, monthly transfers to savings, and no travel at all.
"""

import csv
import random
import shutil
from datetime import date, timedelta

from agent.tools import ROOT

OUT = ROOT / "data" / "bank"
START, END = date(2026, 1, 1), date(2026, 6, 30)

GROCERS = ["TRADER JOE'S #552", "SAFEWAY #1234", "COSTCO WHSE #0412"]
RESTAURANTS = ["CHIPOTLE 2291", "SQ *BLUE BOTTLE COFFEE", "SWEETGREEN SOMA", "DOORDASH*THAI BASIL",
               "IN-N-OUT BURGER #88", "SQ *TARTINE BAKERY"]


def transactions(rng: random.Random) -> list[tuple]:
    rows = []  # (date, description, amount, category, account)
    add = lambda d, desc, amount, cat, acct="credit card": rows.append((d, desc, round(amount, 2), cat, acct))

    day = START
    while day <= END:
        m = day.month
        if day.weekday() == 4 and (day - date(2026, 1, 9)).days % 14 == 0:  # every other Friday
            add(day, "ACME CORP PAYROLL", 2450.00, "Income", "checking")
        if day.day == 1:
            add(day, "OAKWOOD APTS RENT", -1650.00, "Housing", "checking")
        if day.day == 12:
            add(day, "CITY POWER & LIGHT", -rng.uniform(70, 110), "Utilities", "checking")
        if day.day == 20:
            add(day, "T-MOBILE", -65.00, "Utilities", "checking")
        if day.day == 15:
            add(day, "TRANSFER TO SAVINGS", -500.00, "Transfer", "checking")
        if day.day == 3:
            add(day, "PLANET FITNESS", -24.99, "Subscriptions")
        if day.day == 5:
            add(day, "NETFLIX.COM", -15.49 if m <= 3 else -17.99, "Subscriptions")
        if day.day == 14:
            add(day, "SPOTIFY USA", -11.99, "Subscriptions")
        if day.day == 22 and m <= 2:
            add(day, "HULU", -9.99, "Subscriptions")
        if day.weekday() == 5:  # weekly grocery run on Saturday
            add(day, rng.choice(GROCERS), -rng.uniform(45, 140), "Groceries")
        if rng.random() < 0.2:
            add(day, rng.choice(RESTAURANTS), -rng.uniform(12, 65), "Dining")
        if rng.random() < 0.07:
            add(day, "SHELL OIL 5744", -rng.uniform(35, 60), "Transportation")
        day += timedelta(days=1)

    add(date(2026, 3, 14), "BEST BUY 00123", -549.99, "Shopping")
    add(date(2026, 4, 8), "AMAZON.COM*RT4KX", -89.99, "Shopping")
    add(date(2026, 4, 15), "AMAZON.COM*RT4KX REFUND", 89.99, "Shopping")
    return sorted(rows)


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    with open(OUT / "transactions.csv", "w", newline="") as f:
        out = csv.writer(f)
        out.writerow(["date", "description", "amount", "category", "account"])
        for d, desc, amount, cat, acct in transactions(random.Random(2026)):
            out.writerow([d.isoformat(), desc, f"{amount:.2f}", cat, acct])
    shutil.copy(ROOT / "bank" / "transactions-readme.md", OUT)
    print(f"wrote {OUT / 'transactions.csv'}")


if __name__ == "__main__":
    main()
