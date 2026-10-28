# Partner Tryout Speed Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. The user approved direct implementation and autonomous verification.

**Goal:** Shorten orchestration while preserving the approved workflow and quality gates.
**Architecture:** Add a thin Python CLI over existing configuration, delegated-job and receipt helpers. Keep Claude roles in host-native subagents; the driver retains reasoning acceptance and permission decisions.
**Tech Stack:** Python standard library, existing Bash helpers and unittest.
**Spec:** `docs/superpowers/specs/2026-10-28-partner-latency-design.md`

## Global Constraints
- Preserve the three original tasks, blind prompts, configured backend/model/effort and strict raw-JSON acceptance.
- No dependencies, workflow service, model fallback or permission bypass.
- Keep existing configuration/receipt schemas and CLI commands compatible.
- Actual model and effort observations remain unknown when no evidence exists.
- Real timing, not fixture speed, determines whether the objective is achieved.

## Review Focus
- Duplicate JSON keys and bool-versus-number equality must not produce false acceptance (Task 1).
- A failed or still-running process with plausible output must not pass (Task 2).
- Partial submission must retain job identifiers rather than cause duplicate dispatch (Task 2).
- Mixed backends and configuration scope must preserve the actual routing and write destination (Tasks 2/3).
- Missing native-agent evidence and denied configuration writes must stay visible in receipts (Task 3).

### Task 1: Deterministic output acceptance
**Files:** Create `scripts/partner-tryout.py`, `tests/test_partner_tryout.py`.
**Interface:** `validate_fast_worker(text: str) -> dict` returns `passed`, `format_valid`, `content_valid`, `keys_sorted`, `errors`.
- [x] Write cases for raw correct JSON, fences, wrong nested order, wrong values/types, changed arrays, duplicate keys, non-finite numbers and extra text.
- [x] Run `python3 -m unittest discover -s tests -p test_partner_tryout.py -v`; observe RED, then implement and obtain GREEN.
- [x] Replay the supplied fast-worker output read-only; preserve strict failure while confirming diagnostic content/order correctness.

### Task 2: Fixed dispatch and collection
**Files:** Extend `scripts/partner-tryout.py`, `tests/test_partner_tryout.py`.
**Interfaces:** `start --host HOST --repo REPO [--role ROLE]` produces a durable run manifest and native-agent packets; `collect RUN --wait-seconds N [--agent-result ROLE=PATH]` reads actual result evidence and preserves incomplete jobs.
- [x] Add fixture tests for unchanged prompts, concurrent Codex dispatch, native Claude routing, missing configuration, failed/partial submission and bounded waits without restarting jobs.
- [x] Implement using existing `partner-config.py` resolution and `delegate-codex.sh submit/status/result --json`; keep durable IDs before collection.
- [x] Add collection tests for nonzero/incomplete execution, unknown model evidence, actual job timings and native-agent results.
- [x] Run the new suite through RED/GREEN for each behavior; inspect original completed jobs read-only through the collector.

### Task 3: Acceptance, receipts and host instructions
**Files:** Extend the helper/tests; update `references/tryout.md`, relevant adapter/Core instructions, README parity entries, package checks and CI syntax entries.
**Interface:** A finalization command consumes collected evidence and explicit driver reasoning decisions, reuses `make-receipt.py`, and emits scope-correct verification commands without silently writing configuration.
- [x] Test strict-failure preservation, pending reasoning acceptance, stale verification timestamps, scope-correct write commands and permission-denied write reporting.
- [x] Replace exploratory tryout directions with the fixed start/Agent/collect/finalize sequence; retain every quality gate.
- [x] Run `python3 -m unittest discover -s tests`, `bash scripts/check-skill-repo.sh .`, syntax checks and `git diff --check`.

### Task 4: Independent review and live timing
**Files:** Record evidence in a concise validation document, without credentials or private transcript content.
- [x] Obtain one fresh-context whole-branch review; address material findings with targeted regression coverage.
- [x] Execute the approved real Claude-driven tryout using unchanged configured identities and original tasks.
- [x] Record stage timings and verdicts; compare to 546.5 seconds total / 499 seconds outside the execution window.
- [x] Investigate until an actual improvement is demonstrated without weakening the gates; do not mark the active goal complete from fixture checks alone.
- [x] Commit the verified result. Shared installation updates and remote-main publication require their own authorization.

## Execution record
- Design approved by the user; native implementation selected to avoid per-task handoff overhead. Independent branch review and supplemental transcript review completed.
- Existing isolated worktree reused; branch `codex/partner-tryout-speed`, base `7d12a2e`.
- No product changes or live model calls made at plan creation.
- Task 1: complete. Five test methods with literal positive/negative fixtures passed after observing assertion failures; full suite 138 tests passed in 68.338 seconds. Read-only replay of the supplied completed job produced `passed=false`, `format_valid=false`, `content_valid=true`, `keys_sorted=true`, `errors=[markdown_fence]`.
- Tasks 2/3 implementation: fixed start/collect/finalize entry point, per-role scope and explicit verification commands, existing receipt generator and updated host/package instructions. Read-only replay preserves the supplied fast-worker fence failure and the arbiter's pending judgment.
- Ruling: reuse sequential submissions to the existing asynchronous delegate rather than introduce another concurrency layer; the actual jobs overlap. The native Agent remains the host's responsibility. A partial start is collectable and never automatically resubmits.
- First full suite after Tasks 2/3: 146 tests passed in 67.775 seconds. Package checks fail=0, warn=1 (pre-existing risky-text warning); README parity and 36 static prompt checks passed. Python syntax checked with a cache file inside .partner because the system cache directory is outside the sandbox.
- Fresh independent review found two material defects: invalid receipt phase and undispatched roles missing state after interruption. Both were reproduced by failing tests, then fixed; all 16 tryout tests passed. Final full suite: 149 tests passed in 61.317 seconds. An earlier run hit an intermittent sandbox permission error in an unchanged process-cleanup test; its 29-test module and the final full suite both passed on rerun.
- Real Claude-driven trial launched with normal auto permissions, unchanged default driver routing and configured identities. First-trial timing and output outcomes are recorded in the validation document.

- First live trial completed in 530.431 seconds versus 546.461 seconds baseline (only 2.9% lower). Preparation improved, but the driver still manually grepped native transcript models, rewrote evidence and rediscovered finalize flags. This is limited improvement, not evidence of the intended large reduction.
- Ruling: accept native transcript paths directly in the existing collector, because the live trace showed evidence extraction remained a deterministic task delegated to the model. Keep explicit native JSON as the fallback for hosts without confirmed SubagentHandback; no guessed completion or model identity. The added parser is deliberately limited to the observed Claude transcript contract.
- Native transcript checks cover exact task matching, observed-versus-requested models, confirmed completion, missing timing, partial/failed results, and rejecting source conflicts or Codex replacement. Supplemental independent review found stale success carried into a subsequent handback; a regression failed before resetting completion/timing per handback and passed afterward. All 21 targeted tests passed.
- Second live trial runs with the same driver route, role configuration, task prompts and normal permissions; it uses transcript collection directly. Final regression: 154 tests passed in 64.001 seconds; static checks and README parity passed. Final end-to-end time 232.620s versus 546.461s baseline (57.4% lower); outside-execution time 184.908s. See `2026-10-28-partner-tryout-speed-validation.md`.
