# Evaluation log: DABstep

Dev set = the 10 DABstep dev tasks, k runs each, official `scorer.py`.
Run: `uv run python -m eval.run_eval --k 3`. Bank results: `EVALUATION-bank.md`.

| Date | Change | Model | Accuracy | pass^3 | No answer (step limit) | Avg steps | Input tok (cached) | Output tok | Cost | Kept |
|---|---|---|---|---|---|---|---|---|---|---|
| 2026-10-09 | Baseline: plain loop, `run_python`, manual in system prompt, 20-step limit | Nemotron 3 Super (free) | 13/30 (43%) | 2/10 | 9/30 | 13.7 | 5.11M (4.50M, 88%) | 265k | $0 | — |
| 2026-10-09 | Baseline repeat (same code + Langfuse tracing) | Nemotron 3 Super (free) | 11/30 (37%) | 2/10 | 11/30 | 12.2 | 4.15M (3.57M, 86%) | 228k | $0 | — |
| 2026-10-10 | Persistent Python session per task (variables survive between steps) | Nemotron 3 Super (free) | 12/30 (40%) | 1/10 | 8/30 | 11.8 | 4.05M (3.54M, 87%) | 472k | $0 | yes |
| 2026-10-11 | Fix B: tested fee-rule helpers preloaded in the Python session | Nemotron 3 Super (free) | 22/30 (73%) | 7/10 | 7/30 | 9.2 | 2.90M (2.50M, 86%) | 129k | $0 | yes |
| 2026-10-12 | Fix B, model comparison (+ `cache_control` marks for Claude) | Claude Haiku 5.5 | 23/30 (77%) | 7/10 | 0/30 | 4.2 | 1.41M (1.33M, 94%) | 52k | $0.050 | — |
| 2026-10-12 | Fix B, model comparison | MiMo-V2.6-Flash | 24/30 (80%) | 8/10 | 2/30 | 7.3 | 2.27M (1.99M, 88%) | 58k | $0.058 | — |
| 2026-10-12 | Fix B, model comparison | Muse Spark 1.3 (contributor) | 21/30 (70%) | 7/10 | 2/30 | 7.9 | 2.32M (1.46M, 63%) | 88k | $0.106 | — |
| 2026-10-13 | LangChain `create_agent` (same prompt, tool and sandbox; sandbox thread fix) | Claude Haiku 5.5 | 22/30 (73%) | 6/10 | 0/30 | 4.1 | 1.38M (1.22M, 89%) | 55k | $0.059 | — |

**Noise: the two baselines differ by 2/30 with no code change (together 24/60, 40%), so a change
must move the score by more than ~3 per 30 to count.**

## 2026-10-09 baseline

Traces: `runs/2026-10-09_154252_…` (29 min), repeat `runs/2026-10-09_214720_…`.

```
task     5  easy  ✓✓✓
task    49  easy  ✗✗✗   'A. NL' every time (expected 'B. BE')
task    70  easy  ✗✗✗   'YES' x2, no answer x1 (expected 'Not Applicable')
task  1273  hard  ✓✓✓
task  1305  hard  ✓✗✗   no answer x1, '0.064000' x1
task  1464  hard  ✗✓✓   no answer x1
task  1681  hard  ✗✗✗   no answer x2; run 1 had the right IDs but scored wrong (below)
task  1753  hard  ✗✓✓   no answer x1
task  1871  hard  ✓✗✓   no answer x1
task  2697  hard  ✗✗✗   no answer x2, 'GlobalCard:0.67' x1 (expected 'E:13.57')
```

- Most losses hit the 20-step limit (9 of 17 wrong runs; 11 of 19 in the repeat).
- Scorer quirk: `286,381,454` (no spaces) is read as one number. 1681 run 1 had the right IDs and
  failed on this; the guidelines' format is `A, B, C`.
- 49 and 70 fail identically every run: wrong analysis, not luck.

## 2026-10-10 error analysis (36 failed runs of 60)

| Cause | Runs | Evidence |
|---|---|---|
| Ran out of steps | 20 | 115 of 534 code runs crashed with `NameError`: each `run_python` was a fresh process, but the model reused variables like in a notebook |
| Ignored the manual's definitions | 10 | 49 ranked by fraud *count* (NL), not *rate* (BE 12.27% vs NL 12.18%); 70 answered YES though the manual defines no "fine" |
| `[]` in a fee rule read as "matches nothing" | 3 | It means "applies to all", like null (1464, 1753) |
| List without spaces read as one number | 1 | 1681 run 1 |
| Other wrong values | 2 | 1305 `0.064000`, 2697 `GlobalCard:0.67` |

## 2026-10-10 persistent Python session — kept

Traces: `runs/2026-10-10_001427_…`. 12/30, same as baseline. Code errors fell 73 → 10 per eval
(`NameError` 57 → 2) and step-limit runs ~10 → 8, but the remaining failures are analysis errors.
Output tokens doubled (472k vs ~245k). Kept anyway: it removes a failure mode, so later fixes are
measured without step-limit noise.

## 2026-10-10 model probe: Nemotron 3 Ultra (free), 5 tasks

Traces: `runs/2026-10-10_012952_…`. 2 runs each on 49, 70, 1464, 1681 (usually fail) and 1273.

| Model | Correct | 49 | 70 | 1273 | 1464 | 1681 | Output tok/run |
|---|---|---|---|---|---|---|---|
| Super (3 evals) | 14/45 (31%) | 1/9 | 0/9 | 8/9 | 4/9 | 1/9 | ~16k |
| Ultra | 5/10 (50%) | 1/2 | 0/2 | 1/2 | 1/2 | 2/2 | ~4.6k |

Within noise on 10 runs. Ultra writes a third of the output tokens and solved 1681 twice.

## 2026-10-10 Fix A (prompt note: null or [] means "all") — not kept

Traces: `runs/2026-10-10_021601_…`. Fee tasks 2/6 vs 15/27 before (1273 0/2, 1305 1/2,
1464 1/2; control task 5 2/2). The model followed the note inconsistently: in 1464 it matched
correctly at step 2, then second-guessed itself for 9 steps. Reverted.

## 2026-10-11 Fix B (tested fee-rule helpers preloaded) — kept

`fee_rules.py` (tested by `tests/test_fee_rules.py`) is imported into every session; the
prompt lists the helpers. Small test (`runs/2026-10-11_214640_…`): fee tasks 5/6 vs 15/27, ~3.6k
output tokens per run vs ~16k. The miss (1273) passed one payment's facts to `matching_fee_rules`
for a question about rules in general.

Full eval (`runs/2026-10-11_223202_…`, 16.6 min; `…220519_…` is an aborted attempt):

```
task     5  easy  ✓✓✓
task    49  easy  ✓✓✓
task    70  easy  ✗✗✗   no answer x3 (expected 'Not Applicable')
task  1273  hard  ✓✓✓
task  1305  hard  ✓✓✓
task  1464  hard  ✓✓✓
task  1681  hard  ✓✓✓
task  1753  hard  ✓✓✓
task  1871  hard  ✗✓✗   no answer x2
task  2697  hard  ✗✗✗   no answer x2, 'TransactPlus:61.05' x1 (expected 'E:13.57')
```

22/30 vs 12/30: +10, well above noise. pass^3 1-2 → 7/10, output tokens 472k → 129k. All 8 misses
are on 70, 1871, 2697; 7 hit the step limit.

## 2026-10-12 cheap-model comparison for the leaderboard run

Goal: a model for the 450-task run under ~$2-3. Same code as Fix B. Haiku needed `cache_control`
marks (`with_cache_marks` in `agent/loop.py`, for `anthropic/` models only): 94% cached.
Muse Spark needs OpenRouter's "contributor" tier (trains on prompts): switch it off before phase 2.
Traces: `runs/2026-10-12_013614_anthropic_…`, `…013614_xiaomi_…`, `…014146_meta_…`.

| Model | Correct | pass^3 | Avg steps | Minutes | Cost (30 runs) | Full run (× 15) |
|---|---|---|---|---|---|---|
| Nemotron 3 Super (free) | 22/30 (73%) | 7/10 | 9.2 | 16.6 | $0 | $0, ~5 days of free quota |
| Claude Haiku 5.5 | 23/30 (77%) | 7/10 | 4.2 | 2.1 | $0.050 | ~$0.75 |
| MiMo-V2.6-Flash | 24/30 (80%) | 8/10 | 7.3 | 9.1 | $0.058 | ~$0.87 |
| Muse Spark 1.3 (contributor) | 21/30 (70%) | 7/10 | 7.9 | 6.5 | $0.106 | ~$1.60 |

```
task            Nemotron  Haiku  MiMo  Muse
task     5  easy  ✓✓✓     ✓✓✓    ✓✓✓   ✓✓✓
task    49  easy  ✓✓✓     ✓✓✓    ✓✓✓   ✗✗✗  'A. NL' x3
task    70  easy  ✗✗✗     ✗✗✗    ✗✗✗   ✗✗✗  all answer yes/no (expected 'Not Applicable')
task  1273  hard  ✓✓✓     ✓✓✓    ✓✓✓   ✓✓✓
task  1305  hard  ✓✓✓     ✓✓✓    ✓✓✓   ✓✓✓
task  1464  hard  ✓✓✓     ✓✗✓    ✓✓✓   ✓✓✓  Haiku run 2 missed 3 IDs
task  1681  hard  ✓✓✓     ✓✓✓    ✓✓✓   ✓✓✓
task  1753  hard  ✓✓✓     ✓✓✓    ✓✓✓   ✓✓✓
task  1871  hard  ✗✓✗     ✓✓✓    ✓✓✓   ✓✓✓
task  2697  hard  ✗✗✗     ✗✗✗    ✗✗✗   ✗✗✗  no model gets 'E:13.57'
```

All within noise. Every model fails 70 and 2697: agent or task problems, not model problems.
Haiku is fastest and cheapest and never hit the step limit.

## 2026-10-12 full run: all 450 tasks, Haiku 5.5

`--split all` with `--k 1` writes `submission.jsonl`. Traces and submission:
`runs/2026-10-12_141316_anthropic_…`.

| Tasks | Minutes (8 workers) | Errors | Hit step limit | Avg steps | Input tok (cached) | Output tok | Cost |
|---|---|---|---|---|---|---|---|
| 450 | 40.9 | 0 | 0 | 5.4 | 29.4M (27.7M, 94%) | 1.06M | $1.02 |

**Leaderboard (2026-10-12, `Independent / finance-agent-v1`, unvalidated): 310/450 (68.9%);
easy 60/72 (83.3%), hard 250/378 (66.1%).** Per-task scores:
`data/task_scores/v1__Independent-finance-agent-v1__12-10-2026.jsonl` in `adyen/DABstep`.
~8 points below dev (77%). Only 2 of 450 answers are "Not Applicable", so dev task 70's yes/no
habit is likely a systematic loss. For scale: the paper's best hard-split baseline was 14.6%.

## 2026-10-12 refactor: DABstep parts moved into `datasets/dabstep/`

`run_agent` and the sandbox take a `Dataset`. System prompt byte-identical; checks pass. Haiku:
task 5 1/1, task 1305 2/4 vs 2/3 on the old code. Every 1305 miss passes `account_type=['H']` (a
list) to `matching_fee_rules`: model noise, not the refactor. Candidate helper fix: accept a
one-item list.

## 2026-10-13 the agent rebuilt on LangChain

`agent/langchain_agent.py` (78 lines vs 160 for `agent/loop.py`): `create_agent`, `ChatOpenAI` on
OpenRouter, `run_python` as a `@tool`, `ModelCallLimitMiddleware(run_limit=20)`, one
request-level `cache_control` (95% cached). Traces: `runs/2026-10-13_091305_langchain_…`;
`…014858_langchain_…` is before the sandbox thread fix.

| Agent (Haiku 5.5) | Correct | pass^3 | Avg steps | Minutes | Cost (30 runs) |
|---|---|---|---|---|---|
| Plain loop (2026-10-12) | 23/30 (77%) | 7/10 | 4.2 | 2.1 | $0.050 |
| LangChain, before the sandbox thread fix | 22/30 (73%) | 6/10 | 6.7 | 2.0 | $0.073 |
| LangChain | 22/30 (73%) | 6/10 | 4.1 | 1.8 | $0.059 |

Same accuracy within noise, same failures (70 answers 'Yes'; 2697 now a wrong ACI instead of the
step limit).

What the abstraction hid:
- **No request timeout:** `ChatOpenAI` waits forever by default; set `timeout=120`.
- **`recursion_limit` counts graph steps (~4 per model call), not model calls:** a limit of 80
  crashed at ~20 calls. When the call limit stops a run, its "Model call limits exceeded" message
  must not be read as the answer.
- **A reply's tool calls run in parallel threads:** two threads on one sandbox could swap replies
  and hang. `PythonSession.run` now takes a lock (`test_parallel_calls_each_get_their_own_reply`).
- **The sandbox died with the thread that started it** (bwrap's `--die-with-parent` is per
  thread), so every second call failed. Sandboxes now start from one long-lived thread
  (`test_session_survives_the_thread_that_started_it`): 0 failed calls, 6.7 → 4.1 steps.
