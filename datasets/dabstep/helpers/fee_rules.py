"""Fee-rule helpers, preloaded into the agent's Python session. They implement the manual's rules
so the model doesn't rewrite (and get wrong) the matching logic in every task.

A fact left out (or None) is treated as unknown: the rules are not filtered on that field.
"""

import json
import os
from datetime import date, timedelta
from functools import cache
from pathlib import Path

import pandas as pd

__all__ = ["fee", "fee_rules", "matching_fee_rules", "merchant_info", "monthly_stats",
           "transaction_rules", "applicable_fee_ids"]

DATA_DIR = Path(os.environ.get("DABSTEP_DATA", "/data"))


@cache
def fee_rules() -> list[dict]:
    return json.loads((DATA_DIR / "fees.json").read_text())


@cache
def _merchants() -> dict:
    return {m["merchant"]: m for m in json.loads((DATA_DIR / "merchant_data.json").read_text())}


@cache
def _payments() -> pd.DataFrame:
    p = pd.read_csv(DATA_DIR / "payments.csv")
    p["month"] = pd.to_datetime(p.year * 1000 + p.day_of_year, format="%Y%j").dt.month
    return p


def fee(rule: dict, amount: float) -> float:
    """Fee in euros for one transaction of `amount` euros: fixed_amount + rate * amount / 10000."""
    return rule["fixed_amount"] + rule["rate"] * amount / 10000


def matching_fee_rules(card_scheme=None, account_type=None, merchant_category_code=None,
                       is_credit=None, aci=None, intracountry=None, capture_delay=None,
                       monthly_volume=None, monthly_fraud_level=None) -> list[dict]:
    """Fee rules that apply to the given facts. A rule field that is null or [] matches anything.

    account_type: 'R', 'D', 'H', 'F' or 'S'          merchant_category_code: int, e.g. 5812
    is_credit: bool                                  aci: 'A' to 'G'
    intracountry: bool (issuing country == acquirer's country)
    capture_delay: the merchant's value, e.g. '1', '7', 'immediate', 'manual'
    monthly_volume: euros in that calendar month      monthly_fraud_level: percent, e.g. 8.1
    """
    facts = {k: v for k, v in locals().items() if v is not None}
    return [rule for rule in fee_rules() if all(_field_matches(rule, k, v) for k, v in facts.items())]


def _field_matches(rule: dict, field: str, value) -> bool:
    allowed = rule[field]
    if allowed is None or allowed == []:
        return True
    if isinstance(allowed, list):
        return value in allowed
    if field == "intracountry":
        return bool(allowed) == bool(value)
    if field == "capture_delay":
        return _capture_delay_matches(allowed, value)
    if field == "monthly_volume":
        return _in_range(allowed, value, scale={"k": 1e3, "m": 1e6})
    if field == "monthly_fraud_level":
        return _in_range(allowed.replace("%", ""), value)
    return allowed == value


def _capture_delay_matches(allowed: str, value: str) -> bool:
    if not str(value).isdigit() or allowed in ("immediate", "manual"):
        return allowed == value
    return _in_range(allowed, int(value))  # '<3', '3-5', '>5' against a number of days


def _in_range(spec: str, value: float, scale: dict | None = None) -> bool:
    """'<100k', '100k-1m', '>5m', '7.2-7.7' -> whether value falls in it (range ends included)."""
    def num(s):
        s = s.strip()
        if scale and s[-1] in scale:
            return float(s[:-1]) * scale[s[-1]]
        return float(s)
    if spec.startswith("<"):
        return value < num(spec[1:])
    if spec.startswith(">"):
        return value > num(spec[1:])
    lo, hi = spec.split("-")
    return num(lo) <= value <= num(hi)


def merchant_info(merchant: str) -> dict:
    """The merchant's record from merchant_data.json (account_type, capture_delay, MCC, acquirers)."""
    return _merchants()[merchant]


def monthly_stats(merchant: str, year: int, month: int) -> dict:
    """{'volume': euros, 'fraud_level': percent} for the merchant in that calendar month."""
    p = _payments()
    rows = p[(p.merchant == merchant) & (p.year == year) & (p.month == month)]
    volume = rows.eur_amount.sum()
    fraud = rows.loc[rows.has_fraudulent_dispute, "eur_amount"].sum()
    return {"volume": volume, "fraud_level": 100 * fraud / volume if volume else 0.0}


def transaction_rules(row, merchant: dict | None = None, stats: dict | None = None) -> list[dict]:
    """Fee rules that apply to one payments.csv row, using its merchant and that month's stats."""
    merchant = merchant or merchant_info(row["merchant"])
    stats = stats or monthly_stats(row["merchant"], row["year"], _month(row["year"], row["day_of_year"]))
    return matching_fee_rules(
        card_scheme=row["card_scheme"], account_type=merchant["account_type"],
        merchant_category_code=merchant["merchant_category_code"], is_credit=bool(row["is_credit"]),
        aci=row["aci"], intracountry=row["issuing_country"] == row["acquirer_country"],
        capture_delay=merchant["capture_delay"], monthly_volume=stats["volume"],
        monthly_fraud_level=stats["fraud_level"],
    )


def applicable_fee_ids(merchant: str, year: int, month: int | None = None,
                       day_of_year: int | None = None) -> list[int]:
    """IDs of all fee rules that apply to at least one of the merchant's payments in that
    month or on that day, sorted."""
    p = _payments()
    rows = p[(p.merchant == merchant) & (p.year == year)]
    if day_of_year is not None:
        rows = rows[rows.day_of_year == day_of_year]
    if month is not None:
        rows = rows[rows.month == month]
    info = merchant_info(merchant)
    stats = {m: monthly_stats(merchant, year, m) for m in rows.month.unique()}
    ids = set()
    for _, row in rows.iterrows():
        ids.update(r["ID"] for r in transaction_rules(row, info, stats[row["month"]]))
    return sorted(ids)


def _month(year: int, day_of_year: int) -> int:
    """Calendar month (1-12) of a day of the year."""
    return (date(int(year), 1, 1) + timedelta(days=int(day_of_year) - 1)).month
