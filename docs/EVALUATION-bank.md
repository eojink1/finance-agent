# Evaluation log: bank test set

The phase 2 test set: synthetic transactions (`datasets/bank/make_data.py`) and questions whose
answers are computed from them (`datasets/bank/make_questions.py`), scored with DABstep's
`scorer.py`. DABstep results are in `EVALUATION-dabstep.md`.

Regenerate, then run: `uv run python -m datasets.bank.make_data && uv run python -m datasets.bank.make_questions`,
then `uv run python -m eval.run_eval --split bank --agent langchain --k 1`.

The data changes as it is made messier, so each run names the commit of `datasets/bank/` it used.
Scores are comparable only between runs on the same data.

| Date | Data (commit) | Change | Agent | Model | Accuracy | pass^k | Avg steps | Input tok (cached) | Output tok | Cost | Kept |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 2026-10-13 | `c1a24d4`: clean data, 21 questions | First run | LangChain | Nemotron 3 Super (free) | 20/21 (95%) | 20/21 (k=1) | 4.3 | 156k (23k, 15%) | 55k | $0 | — |

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
- Too easy to steer by: 4.3 steps on average with a free model. Rows are correctly categorized,
  merchant names never vary, the readme defines every term.

Next: messier data, one kind per change; first a credit card autopay that double-counts spending.
