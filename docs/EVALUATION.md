# Evaluation log

Every agent or prompt change is measured here before it is kept. Dev set = the 10 DABstep dev
tasks, k runs each, scored with the official `scorer.py`. Run: `uv run python -m eval.run_eval --k 3`.

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

**Baseline over both runs: 24/60 (40%).** The two runs differ by 2 answers out of 30 with no code
change, so a change has to move the score by more than ~3 answers per 30 before it counts as real.

## 2026-10-09 baseline

Traces: `runs/2026-10-09_154252_nvidia_nemotron-3-super-120b-a12b_free/`. 29 min, 0 API errors.

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

First observations (before reading traces):
- **Step limit is the biggest loss:** 9 of 17 wrong runs never answered (hit 20 steps).
- **Scorer quirk:** a list written without spaces, like `286,381,454`, matches the scorer's
  "number with thousands separators" pattern and is compared as one number. Task 1681 run 1 had
  the correct 10 IDs and failed for this reason. The guidelines' example format is `A, B, C`.
- Tasks 49 and 70 fail the same way every run: wrong analysis, not bad luck.

Repeat run (`runs/2026-10-09_214720_…`, also in Langfuse): same pattern. 11 of 19 wrong runs hit
the step limit; 49 and 70 failed identically again; 1464 and 1753 gave wrong ID lists (not a
format issue); 1753/2697 failed all 3 runs this time.

## 2026-10-10 error analysis (both baselines: 36 failed runs of 60)

| Cause | Failed runs | Evidence |
|---|---|---|
| Ran out of steps (20-step limit) | 20 | 115 of 534 code runs in failed runs crashed with `NameError`: the model writes notebook-style code that reuses variables from earlier steps, but each `run_python` is a fresh process. Almost every step reloads the data. |
| Ignored the manual's definitions | 10 | Task 49 ranked countries by fraud *count* (NL) instead of the manual's fraud *rate* (BE 12.27% vs NL 12.18%). Task 70: the manual defines no "fine"; the agent found none and still answered YES (expected Not Applicable). |
| Fee rule matching: `[]` treated as "matches nothing" | 3 | The manual says null means "applies to all"; the data also uses empty lists for that (tasks 1464, 1753). |
| List without spaces read as one number by the scorer | 1 | Task 1681 run 1 had the right IDs. |
| Other wrong values (not yet read) | 2 | 1305 `0.064000`, 2697 `GlobalCard:0.67`. |

First fix to measure: a persistent Python session per task (cause 1).

## 2026-10-10 persistent Python session

Traces: `runs/2026-10-10_001427_…` (also in Langfuse). Accuracy 12/30 (40%), the same as the
baseline (24/60). The mechanism worked: errors in code runs fell from ~73 per eval to 10, and
`NameError` from ~57 to 2. Runs hitting the step limit fell from ~10 to 8. But the saved steps
did not turn into right answers: the remaining failures are the analysis errors from causes 2-3
(task 49 by count, 70 answering yes/no, 1273/1305/1464 fee-rule matching), and 1681/2697/1871
still run out of steps. Output tokens doubled (472k vs ~245k), which would matter on a paid model.

**Kept** (decided 2026-10-10) even though accuracy didn't move: it removes a whole failure mode
(code crashes 73 → 10 per eval), and later fixes need a clean signal that isn't hidden by
step-limit noise.

## 2026-10-10 model probe: Nemotron 3 Ultra (free) on 5 tasks

Not a full eval (free quota was low). Tasks 49, 70, 1464, 1681 (usually fail) and 1273 (usually
passes), 2 runs each, persistent session. Traces: `runs/2026-10-10_012952_…` (also in Langfuse).

| Model | Correct | 49 | 70 | 1273 | 1464 | 1681 | Avg steps | Output tokens per run |
|---|---|---|---|---|---|---|---|---|
| Super (all 3 evals on these tasks) | 14/45 (31%) | 1/9 | 0/9 | 8/9 | 4/9 | 1/9 | — | ~16k |
| Ultra | 5/10 (50%) | 1/2 | 0/2 | 1/2 | 1/2 | 2/2 | 10.6 | ~4.6k |

Ultra solved the step-limit task 1681 both times, and wrote about a third as many output tokens
per run. It still answers yes/no on task 70 and misses the fee-rule cases half the time. 10 runs
is too few to call: +2 answers over Super's rate is within noise.

## 2026-10-10 Fix A (prompt note: null or [] in a fee rule means "all") — not kept

Prompt paragraph explaining that list fields use [] and single-value fields use null for "applies
to all". Tested on 1273, 1305, 1464 (+ task 5 control), 2 runs each, Super, persistent session.
Traces: `runs/2026-10-10_021601_…`.

| Task | Before (Super, 3 evals) | With note |
|---|---|---|
| 1273 | 8/9 | 0/2 |
| 1305 | 3/9 | 1/2 |
| 1464 | 4/9 | 1/2 |
| 5 (control) | 9/9 | 2/2 |

No gain (fee tasks 2/6 vs 15/27). Traces: in 1464 run 2 the model wrote the correct wildcard
match at step 2, then second-guessed it for 9 steps and switched to dropping the [] rules; in
1273 run 1 it filtered `is_credit == True` again, ignoring the note. Written rules are followed
inconsistently by this model. Reverted.

## 2026-10-11 Fix B (tested fee-rule helpers preloaded in the Python session)

`agent/sandbox/fee_rules.py` (checked by `checks/check_fee_rules.py`) is imported into every
session; the prompt lists the helpers and says to use them instead of writing rule matching.
Same tasks as Fix A, 2 runs each, Super, persistent session. Traces: `runs/2026-10-11_214640_…`
(also in Langfuse).

| Task | Before (Super, 3 evals) | Fix A | Fix B |
|---|---|---|---|
| 1273 | 8/9 | 0/2 | 1/2 |
| 1305 | 3/9 | 1/2 | 2/2 |
| 1464 | 4/9 | 1/2 | 2/2 |
| 5 (control) | 9/9 | 2/2 | 2/2 |

Fee tasks 5/6 (83%) vs 15/27 (56%) before. Average 7.75 steps; 28k output tokens for 8 runs
(~3.6k per run vs ~16k before). The one miss, 1273 run 2, used the helpers but misread the
question: 1273 is about rules in general, yet the model picked one real payment and passed that
merchant's facts (capture delay, volume, fraud level) to `matching_fee_rules`, getting 0 rules.
At step 12 it made the right call (scheme + credit only) but kept adding filters, then wrote its
own matcher (also 0) and hit the step limit.
Run 1 called `matching_fee_rules(card_scheme='GlobalCard', is_credit=True)` and finished in 5.
6 runs is a small sample; the full 10-task eval will confirm.

### Full eval

Traces: `runs/2026-10-11_223202_…` (also in Langfuse). 16.6 min, 0 API errors.

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

22/30 (73%) vs the 24/60 (40%) baseline: +10 answers per 30, well above the ~3 noise threshold.
pass^3 went from 1-2/10 to 7/10, average steps from ~12 to 9.2, and output tokens from 472k to
129k. All 8 misses are on three tasks (70, 1871, 2697), and 7 of them hit the 20-step limit.
(`runs/2026-10-11_220519_…` is an aborted earlier attempt with no summary; ignore it.)

**Kept** (decided 2026-10-12).

## 2026-10-12 cheap-model comparison for the leaderboard run

Goal: pick a model for the full 450-task run and submission with a budget of ~$2-3. Same code
as Fix B on all models. Candidates were chosen from OpenRouter on price (estimated full run
under $2) and published agent / tool-use scores; Muse Spark 1.3 and Haiku 5.5 first, MiMo added
when Muse Spark was blocked by account settings (it needs an 18+ confirmation and allowing
paid-model training: the "contributor" tier trains on prompts; fine for public DABstep data,
switch it off again before phase 2).

Haiku needed one code change: Anthropic only caches up to a `cache_control` mark, so
`with_cache_marks` in `agent/loop.py` marks the system prompt and the newest message for
`anthropic/` models (other models get unchanged requests). Checked on task 1305: 72% of input
cached on 1 run, 94% over the 30-run eval.

Traces: `runs/2026-10-12_013614_anthropic_…`, `runs/2026-10-12_013614_xiaomi_…`,
`runs/2026-10-12_014146_meta_…` (also in Langfuse). `runs/2026-10-12_013542_meta_…` and
`…013640_meta_…` are the blocked attempts (all 403, $0); `…013557_anthropic_…` is the 1-task
caching check.

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
task    70  easy  ✗✗✗     ✗✗✗    ✗✗✗   ✗✗✗  all models answer yes/no (expected 'Not Applicable')
task  1273  hard  ✓✓✓     ✓✓✓    ✓✓✓   ✓✓✓
task  1305  hard  ✓✓✓     ✓✓✓    ✓✓✓   ✓✓✓
task  1464  hard  ✓✓✓     ✓✗✓    ✓✓✓   ✓✓✓  Haiku run 2 missed 3 IDs
task  1681  hard  ✓✓✓     ✓✓✓    ✓✓✓   ✓✓✓
task  1753  hard  ✓✓✓     ✓✓✓    ✓✓✓   ✓✓✓
task  1871  hard  ✗✓✗     ✓✓✓    ✓✓✓   ✓✓✓
task  2697  hard  ✗✗✗     ✗✗✗    ✗✗✗   ✗✗✗  no model gets 'E:13.57'
```

All four are within the ~3-answer noise of each other: accuracy doesn't separate them on 30 runs.
Every model fails 70 and 2697, so those are agent or task problems, not model problems. Haiku
is the fastest and cheapest (fewest steps, never hit the step limit); the estimates from Fix B's
token use (~$1.94) were too high for Haiku and MiMo because they take fewer steps than Nemotron.
Muse Spark costs the most of the paid three: only 63% of its input was cached.

## 2026-10-12 full run: all 450 tasks, Claude Haiku 5.5 (Fix B + caching)

Picked Haiku from the comparison above: same accuracy as the others within noise, fastest,
cheapest, never hit the step limit. `eval/run_eval.py` gained `--split all` (loads
`data/tasks/all.jsonl`, skips scoring where the answer is hidden) and writes `submission.jsonl`
(`task_id`, `agent_answer`) when `--k 1`. Traces: `runs/2026-10-12_141316_anthropic_…`
(also in Langfuse); submission file in the same folder.

| Tasks | Minutes (8 workers) | Errors | Hit step limit | Avg steps | Input tok (cached) | Output tok | Cost |
|---|---|---|---|---|---|---|---|
| 450 | 40.9 | 0 | 0 | 5.4 | 29.4M (27.7M, 94%) | 1.06M | $1.02 |

Every task got an answer (2 are empty strings, which the guidelines allow for empty lists).
Only 2 of 450 answers are "Not Applicable", although every model failed dev task 70 by answering
yes/no where "Not Applicable" was expected: likely a systematic loss on the hidden set.
**Leaderboard (submitted 2026-10-12 as `Independent / finance-agent-v1`, unvalidated):
310/450 (68.9%): easy 60/72 (83.3%), hard 250/378 (66.1%).** Per-task scores:
`data/task_scores/v1__Independent-finance-agent-v1__12-10-2026.jsonl` in the `adyen/DABstep`
dataset. Dev was 77% on Haiku, so the hidden set is ~8 points harder for this agent, mostly on
hard tasks. For scale: the best hard-split baseline in the DABstep paper (Q1 2025) was 14.6%.

## 2026-10-12 refactor: DABstep parts moved out of the agent (no behavior change intended)

The system prompt and `fee_rules.py` moved to `datasets/dabstep/`; `run_agent` and the sandbox
now take a `Dataset` (data folder, helpers folder, preload line, system prompt) so the bank test
set can plug in the same way. The system prompt is byte-identical (same SHA-256) and both checks
pass. Haiku 5.5, task 5: 1/1. Task 1305: 2/4 after vs 2/3 on the old code in the same hour;
every miss is the same `0.127795`, from passing `account_type=['H']` (a list) to
`matching_fee_rules`, which then skips the rules that list H. Model noise on both versions, not
the refactor; 1305 was 3/3 on 2026-10-12 morning. The list-vs-string slip is a candidate helper
fix (accept a one-item list), to be measured separately.

## 2026-10-13 the agent rebuilt on LangChain

`agent/langchain_agent.py`: `create_agent` with `ChatOpenAI` pointed at OpenRouter, `run_python`
as a `@tool` over the same sandbox, the same DABstep system prompt, and
`ModelCallLimitMiddleware(run_limit=20)` for the step limit. 78 lines vs 160 for `agent/loop.py`.
Claude caching is one request-level `cache_control` that OpenRouter applies to the whole
conversation (replaces `with_cache_marks`); 95% of input cached. Run with `--agent langchain`.
Traces: `runs/2026-10-13_091305_langchain_…` (also in Langfuse); `runs/2026-10-13_014858_langchain_…` is the run
before the sandbox thread fix.

| Agent (Haiku 5.5) | Correct | pass^3 | Avg steps | Minutes | Cost (30 runs) |
|---|---|---|---|---|---|
| Plain loop (2026-10-12) | 23/30 (77%) | 7/10 | 4.2 | 2.1 | $0.050 |
| LangChain, before the sandbox thread fix | 22/30 (73%) | 6/10 | 6.7 | 2.0 | $0.073 |
| LangChain | 22/30 (73%) | 6/10 | 4.1 | 1.8 | $0.059 |

Same accuracy within the ~3-answer noise, same steps per task, cost within ~20%; same failures
(70: answers 'Yes', not 'Not Applicable'; 2697, now answered every run with a wrong ACI instead of
running out of steps). Before the sandbox thread fix (below) it took 6.7 steps and cost ~45% more.

Three things the abstraction hid, found on the way:
- **No request timeout.** `ChatOpenAI` waits forever by default (the plain OpenAI client gives up
  after 600 s); set `timeout=120`.
- **`recursion_limit` counts graph steps, not model calls.** Each model call is ~4 LangGraph steps
  (limit check, model, tools, routing), so a limit of 80 crashed runs at ~20 calls with
  `GraphRecursionError` before the call limit could stop them. When the call limit does stop a
  run, it adds an AI message ("Model call limits exceeded") that must not be read as the answer.
- **Parallel tool calls run in parallel threads.** LangGraph's tool node runs a reply's tool calls
  at the same time; two threads sharing one sandbox process could take each other's reply and
  wait forever (two runs hung per eval). `PythonSession.run` now takes a lock; checked by
  `checks/check_tools.py` #12.
- **Each tool call runs in a new thread, and the sandbox died with it.** bwrap's
  `--die-with-parent` kills the sandbox when the *thread* that started it exits (Linux ties
  `PR_SET_PDEATHSIG` to the thread, not the process). Every second call to a session failed with
  "session ended", so the model reloaded data, gave up on the helpers and wrote its own matcher
  (seen in 2697: 10 of 20 calls failed). Sandboxes now start from one long-lived launcher thread;
  checked by `checks/check_tools.py` #13. After the fix: 0 failed calls, 6.7 → 4.1 steps.
