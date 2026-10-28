# Partner orchestration latency validation — 2026-10-29

The final live tryout took **232.6 seconds**, versus **546.5 seconds** in the supplied baseline: **57.4% less elapsed time**. The execution window remained about 48 seconds; the reduction was in dispatch and completion work. This is one observed comparison, not a stable latency guarantee or quota-saving estimate.

## Timing evidence

All times below are seconds, measured from actual timestamps. Baseline begins at the user's tryout request and ends at the final assistant report. New runs include Claude CLI startup through process exit, including the final report. The helper's internal start-to-finalize time is deliberately not used as end-to-end time.

| Stage | Supplied baseline | First implementation | Final implementation |
| --- | ---: | ---: | ---: |
| Preparation: request/launch to first job | 205.1 | 109.8 | 30.6 |
| Execution window: first start to last completion | 47.5 | 89.7 | 47.7 |
| After execution: collection, judgment and final report | 293.9 | 330.9 | 154.4 |
| End-to-end total | 546.5 | 530.4 | 232.6 |
| Outside execution window | 499.0 | 440.7 | 184.9 |

Outside-execution time fell **62.9%**. The aspirational under-60-second orchestration target was not reached. The driver still spends time assessing reasoning, recording judgments, looking up session counts, and producing its report; these are included in the numbers.

- Baseline: supplied `dazi2.txt` and its original Claude session `2aa44b37-5da6-4a9e-b959-37e32d468acb`; request `14:55:46.750Z`, first job `14:59:11.819113Z`, native completion `14:59:59.297Z`, final report `15:04:53.211Z` on 2026-10-28 UTC.
- First trial: `.partner/latency-live/launch.json`, `driver.jsonl`, and `.partner/receipts/tryout-py114352/run.json`. CLI `15:58:42.621894Z`–`16:07:33.062110Z`; only 2.9% lower total time. The trace exposed manual model extraction and evidence rewriting after tasks had finished.
- Final trial: `.partner/latency-live2/launch.json`, `driver.jsonl`, and `.partner/receipts/tryout-ukfhlsph/run.json`. CLI `16:12:06.910502Z`–`16:15:59.530663Z`; tasks occupied `16:12:37.467272Z`–`16:13:25.179Z`.
- Final helper start-to-finalize: 162.893 seconds. That narrower number excludes startup and final report time and is not the reported speedup.

Raw local evidence remains ignored under `.partner/`; no credentials or transcript bodies are included in this document. The final driver also invoked its existing work-state plugin twice; this incidental bookkeeping and its latency are included in the measurement, and are not required by the new helper.

## Preserved contract and actual outcomes

Configuration, driver routing, role models/efforts and the original three prompts stayed unchanged. Codex jobs used the existing read-only delegate; the Claude role used the native Agent. The arbiter received the identical reasoning task without the other answer. No failed role was retried or replaced, no permission bypass was used, and no routing configuration was changed.

| Role | Requested model / effort | Observed model | Actual task time | Acceptance |
| --- | --- | --- | ---: | --- |
| fast_worker | gpt-6.1-terra / medium | unknown | 35.047s | FAIL: Markdown fence; JSON contents/order correct |
| deep_reasoner | opus / high | glm-5.3-flash | 13.782s | PASS: clear position and move/rename consequence |
| arbiter | gpt-6.1-sol / high | unknown | 33.593s | PASS: independent position, agrees on A |

Acceptance does not establish model routing. There is no declared opus-to-GLM mapping and no observed Codex model evidence; all three `verified_this_run` values remain false. No eligible verification-write command was emitted, no configuration write was performed, and no permission denial occurred. Requested effort remains distinct from enforced effort evidence.

The transcript collector checks the exact task, reads model fields only from assistant messages, and requires the matching successful SubagentHandback result. Unknown timing remains null. Hosts without this transcript contract retain explicit Agent-result JSON. Strict raw-JSON validation still rejects fences, duplicate keys, altered values/types/arrays and extra text.

## Verification and delivery

- Full existing suite: **154 tests passed in 64.001 seconds**, including **21 tryout tests**.
- Package/static checks: fail=0; existing risky-command-text warning remains. README parity and 36 static prompt cases passed; `git diff --check` passed.
- Independent branch review identified receipt-phase and interrupted-dispatch defects; both were reproduced and fixed. Supplemental review of transcript collection found new handbacks inheriting an old answer's success. The regression failed before the reset and passed after it; completion/timing now belong to the current handback.
- An earlier suite run encountered an intermittent permission error in an unchanged process-cleanup test. Its module and subsequent full suites passed. No test remains skipped or failing.
- Branch: `codex/partner-tryout-speed`, based on `7d12a2e`. The shared installation remains on `main` at `7d12a2e`; these new changes have not been merged, installed or pushed.

This validates the tryout path and shared collection conventions. It does not measure a real engineering task, downstream production behavior, subscription consumption, or repeat-run latency distribution. Further driver/provider latency remains outside these script changes.
