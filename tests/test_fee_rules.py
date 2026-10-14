"""The fee-rule helpers follow the manual, and are preloaded read-only in the agent's sandbox."""

import fee_rules as fr
import pytest

from agent.tools import PythonSession
from datasets.dabstep import DABSTEP, DATA

# The helpers read from /data, where the sandbox mounts the files; outside it they are here.
fr.DATA_DIR = DATA


def matches(field: str, allowed, value) -> bool:
    """Whether a rule allowing `allowed` in `field` matches a transaction whose value is `value`."""
    return fr._field_matches({field: allowed}, field, value)


def test_fee_formula():
    """The manual: fixed_amount + rate * amount / 10000."""
    assert fr.fee({"fixed_amount": 0.1, "rate": 19}, 10) == 0.1 + 19 * 10 / 10000


@pytest.mark.parametrize("allowed", [None, []])
def test_null_and_empty_list_match_anything(allowed):
    assert matches("aci", allowed, "G")
    assert matches("is_credit", allowed, False)


def test_a_list_matches_its_members_only():
    assert matches("account_type", ["R", "D"], "R")
    assert not matches("account_type", ["R", "D"], "H")


@pytest.mark.parametrize(
    "field, allowed, value, expected",
    [
        ("monthly_volume", "100k-1m", 100_000, True),  # both ends of a range included
        ("monthly_volume", "<100k", 100_000, False),
        ("monthly_volume", ">5m", 5_000_001, True),
        ("monthly_fraud_level", "7.2%-7.7%", 7.7, True),
        ("monthly_fraud_level", ">8.3%", 8.3, False),
    ],
)
def test_ranges(field, allowed, value, expected):
    assert matches(field, allowed, value) == expected


@pytest.mark.parametrize(
    "allowed, value, expected",
    [
        ("<3", "2", True),  # merchant days against a range
        ("3-5", "3", True),
        (">5", "7", True),
        (">5", "5", False),
        ("manual", "manual", True),  # 'immediate' and 'manual' only match themselves
        ("<3", "immediate", False),
        ("immediate", "1", False),
    ],
)
def test_capture_delay(allowed, value, expected):
    assert matches("capture_delay", allowed, value) == expected


def test_intracountry_is_stored_as_a_number():
    """Stored as 1.0 / 0.0 / null in fees.json."""
    assert matches("intracountry", 1.0, True)
    assert not matches("intracountry", 0.0, True)


def test_no_facts_returns_every_rule():
    """Facts left out don't filter."""
    assert len(fr.matching_fee_rules()) == len(fr.fee_rules()) == 1000


def test_days_of_year_map_to_calendar_months():
    """Day 31 is January, day 32 February, day 60 March in 2023."""
    assert (fr._month(2023, 31), fr._month(2023, 32), fr._month(2023, 60)) == (1, 2, 3)


def test_helpers_are_preloaded_and_read_only_in_the_sandbox(tmp_path):
    expected = str(len(fr.matching_fee_rules(aci="B")))
    with PythonSession(DABSTEP, tmp_path) as s:
        assert s.run("print(len(matching_fee_rules(aci='B')))").strip() == expected
        writable = s.run("import os; print(os.access('/helpers/fee_rules.py', os.W_OK))")
        assert writable.strip() == "False"
