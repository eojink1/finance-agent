# Evaluation log: bank test set

The phase 2 test set: synthetic transactions (`datasets/bank/make_data.py`) and questions whose
answers are computed from them (`datasets/bank/make_questions.py`), scored with DABstep's
`scorer.py`. DABstep results are in `EVALUATION-dabstep.md`.

Regenerate, then run: `uv run python -m datasets.bank.make_data && uv run python -m datasets.bank.make_questions`,
then `uv run python -m eval.run_eval --split bank --k 1`.

The data changes as it is made messier, so each run names the commit of `datasets/bank/` it used.
Scores are comparable only between runs on the same data.

| Date | Data (commit) | Change | Agent | Model | Accuracy | pass^k | Avg steps | Input tok (cached) | Output tok | Cost | Kept |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 2026-10-13 | `c1a24d4`: clean data, 21 questions | First run | LangChain | Nemotron 3 Super (free) | 20/21 (95%) | 20/21 (k=1) | 4.3 | 156k (23k, 15%) | 55k | $0 | — |
| 2026-10-14 | autopay trap (this commit) | Card autopay on both accounts | LangChain | Nemotron 3 Super (free) | 20/21 (95%) | 20/21 (k=1) | 5.0 | 227k (64k, 28%) | 68k | $0 | yes |

## 2026-10-13 first run (clean data)

Traces: `runs/2026-10-13_175846_bank_langchain_nvidia_nemotron-3-super-120b-a12b_free`. 5.9
minutes, 0 errors.

| Task | Level | Expected | Answer | Steps |
|---|---|---|---|---|
| bank-18 | easy | Not Applicable | 192.77 | 4 |

All other tasks were correct (2 to 7 steps; the 'Not Applicable' ones 2, 6, 7).

Findings:

- 20/21 (k=1). The miss, bank-18, is a question flaw: the agent read "travel" as Transportation
  (gas). Reword the question or say in the readme there is no travel category.
  2026-10-14: reworded to "flights and hotels"; bank-18 alone now answers Not Applicable
  (`runs/2026-10-14_112511_bank_...`, k=1, 4 steps).
- Too easy to steer by: 4.3 steps on average with a free model. Rows are correctly categorized,
  merchant names never vary, the readme defines every term.

Next: messier data, one kind per change; first a credit card autopay that double-counts spending.

## 2026-10-14 card autopay trap

Each month checking pays last month's card bill (`CHASE CARD AUTOPAY`), and the card shows the
payment coming in (`AUTOPAY PAYMENT - THANK YOU`), both in a new Credit Card Payment category the
readme says is not spending. Answer key unchanged. Traces:
`runs/2026-10-14_133237_bank_langchain_nvidia_nemotron-3-super-120b-a12b_free`. 8.1 minutes,
0 errors.

| Task | Level | Expected | Answer | Steps |
|---|---|---|---|---|
| bank-18 | easy | Not Applicable | 0.00 | 9 |

Findings:

- The trap didn't bite: every spending question was right. The agent follows the readme's
  definition, so a mess the readme names explicitly costs it nothing; steps rose only 4.3 -> 5.0.
- bank-18 missed again, a different way: it found no flights or hotels and answered 0.00. It
  passed when run alone this morning, so this is run-to-run noise on a question where 0.00 is
  arguably fair.

Next: a mess the readme does not spell out, merchant name variants (AMZN Mktp, Amazon.com*).

## 2026-10-14 open-ended baseline (bank-why, LLM-judged)

Two "explain my spending" tasks in `data/tasks/bank-why.jsonl` (`datasets/bank/make_reports.py`),
each scored by `eval/judge.py` (Claude Haiku 5.5) against a checklist of the causes planted in the
data. Agent unchanged. Traces:
`runs/2026-10-14_151653_bank-why_langchain_nvidia_nemotron-3-super-120b-a12b_free`. k=3,
3.2 minutes, 0 errors, 6.5 steps on average.

| Task | Question | Runs | Avg score |
|---|---|---|---|
| bank-why-1 | Why did I spend more in March than in February? (4 items) | ✗✗✓ | 0.83 |
| bank-why-2 | Anything I should know about my spending in April? (3 items) | ✗✗✗ | 0.11 |

judge_score 0.47, all items met in 1/6 runs, pass^3 0/2.

Findings:

- The judge is right: all 18 verdicts agree with reading the answers myself. It accepts
  "Transportation" for gas because the checklist item names both.
- When the question names the comparison (March vs February), the agent finds it: total, Dining
  and Transportation in every run. It stops at the category, though: only 1/3 runs named the
  Best Buy purchase behind Shopping +$549.99.
- "Anything I should know?" gets a description, not a finding: every run listed April's
  categories and income, none compared with March, none noticed Netflix rose to $17.99. The
  refund was mentioned 2/3 times, with Amazon named once.

Next: teach the agent what "explain" means (compare with the previous month, drill into the
merchants behind a category change), measured on this split.

## 2026-10-14 "explain rather than describe" prompt

A general section in the bank system prompt (`datasets/bank/__init__.py`): for why / what's worth
knowing questions, compare with the previous period (total, then categories), name the merchants
behind the biggest changes, point out unusual items (price changes, refunds, one-offs, charges
that start or stop). Nothing specific to this data.

bank-why, k=3 (`runs/2026-10-14_153807_bank-why_...`), 3.5 minutes, 0 errors, 6.7 steps:

| Task | Before | After |
|---|---|---|
| bank-why-1 (March vs February) | ✗✗✓ 0.83 | ✓✓✓ 1.00 |
| bank-why-2 (April) | ✗✗✗ 0.11 | ✗✗✗ 0.67 |

judge_score 0.47 -> 0.83, all items met 1/6 -> 3/6 runs.

bank, k=1 (`runs/2026-10-14_154147_bank_...`): 20/21, unchanged; the miss is bank-18 again
(0.00 instead of Not Applicable). 4.2 steps on average.

Findings:

- Keep. Every run now compares with the previous month and names the merchants: Best Buy in
  3/3 March runs, the $488.15 drop and the Amazon refund in 3/3 April runs.
- Netflix ($15.49 -> $17.99) is still missed in every April run. The agent sees
  "Subscriptions +$2.50" but doesn't look inside a category that small. Not fixed by naming
  subscriptions in the prompt: that would teach to this checklist.

Next: 1-2 held-out why tasks (e.g. June, when a subscription stops) that the prompt wasn't
written against, to check this generalizes.
