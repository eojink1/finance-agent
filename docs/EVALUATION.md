# Evaluation log

Every agent or prompt change is measured here before it is kept. Dev set = the 10 DABstep dev
tasks, k runs each, scored with the official `scorer.py`. Run: `uv run python -m eval.run_eval --k 3`.

| Date | Change | Model | Accuracy | pass^3 | No answer (step limit) | Avg steps | Input tok (cached) | Output tok | Cost | Kept |
|---|---|---|---|---|---|---|---|---|---|---|
| 2026-10-09 | Baseline: plain loop, `run_python`, manual in system prompt, 20-step limit | Nemotron 3 Super (free) | 13/30 (43%) | 2/10 | 9/30 | 13.7 | 5.11M (4.50M, 88%) | 265k | $0 | — |
| 2026-10-09 | Baseline repeat (same code + Langfuse tracing) | Nemotron 3 Super (free) | 11/30 (37%) | 2/10 | 11/30 | 12.2 | 4.15M (3.57M, 86%) | 228k | $0 | — |
| 2026-10-10 | Persistent Python session per task (variables survive between steps) | Nemotron 3 Super (free) | 12/30 (40%) | 1/10 | 8/30 | 11.8 | 4.05M (3.54M, 87%) | 472k | $0 | yes |

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

