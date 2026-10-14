"""Fails loudly if the fee-rule helpers stop following the manual.

Run: uv run python checks/check_fee_rules.py
"""

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
os.environ["DABSTEP_DATA"] = str(ROOT / "data" / "context")
sys.path.insert(0, str(ROOT / "datasets" / "dabstep" / "helpers"))
sys.path.insert(0, str(ROOT))
import fee_rules as fr
from agent.tools import PythonSession
from datasets.dabstep import DABSTEP

# 1. The manual's fee formula: fixed_amount + rate * amount / 10000.
assert fr.fee({"fixed_amount": 0.1, "rate": 19}, 10) == 0.1 + 19 * 10 / 10000

# 2. null and [] match anything; a list matches its members only.
rule = {"aci": [], "is_credit": None, "account_type": ["R", "D"]}
assert fr._field_matches(rule, "aci", "G")
assert fr._field_matches(rule, "is_credit", False)
assert fr._field_matches(rule, "account_type", "R")
assert not fr._field_matches(rule, "account_type", "H")

# 3. Ranges: volumes with k/m, fraud levels in percent, both ends of a range included.
assert fr._field_matches({"monthly_volume": "100k-1m"}, "monthly_volume", 100_000)
assert not fr._field_matches({"monthly_volume": "<100k"}, "monthly_volume", 100_000)
assert fr._field_matches({"monthly_volume": ">5m"}, "monthly_volume", 5_000_001)
assert fr._field_matches({"monthly_fraud_level": "7.2%-7.7%"}, "monthly_fraud_level", 7.7)
assert not fr._field_matches({"monthly_fraud_level": ">8.3%"}, "monthly_fraud_level", 8.3)

# 4. Capture delay: merchant days against '<3', '3-5', '>5'; 'immediate' and 'manual' only match
# themselves.


def cd(allowed: str, value: str) -> bool:
    return fr._field_matches({"capture_delay": allowed}, "capture_delay", value)


assert cd("<3", "2") and cd("3-5", "3") and cd(">5", "7") and not cd(">5", "5")
assert cd("manual", "manual") and not cd("<3", "immediate") and not cd("immediate", "1")

# 5. Intracountry is stored as 1.0 / 0.0 / null.
assert fr._field_matches({"intracountry": 1.0}, "intracountry", True)
assert not fr._field_matches({"intracountry": 0.0}, "intracountry", True)

# 6. Facts left out don't filter: no facts at all returns every rule.
assert len(fr.matching_fee_rules()) == len(fr.fee_rules()) == 1000

# 7. Months are calendar months: day 31 is January, day 32 February, day 60 March in 2023.
assert (fr._month(2023, 31), fr._month(2023, 32), fr._month(2023, 60)) == (1, 2, 3)

# 8. Inside the agent's sandbox the helpers are preloaded, read-only and use /data.
with PythonSession(DABSTEP) as s:
    expected = str(len(fr.matching_fee_rules(aci="B")))
    assert s.run("print(len(matching_fee_rules(aci='B')))").strip() == expected
    assert s.run("import os; print(os.access('/helpers/fee_rules.py', os.W_OK))").strip() == "False"

print("all fee-rule checks passed")
