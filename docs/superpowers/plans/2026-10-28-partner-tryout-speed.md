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
- [ ] Add fixture tests for unchanged prompts, concurrent Codex dispatch, native Claude routing, missing configuration, failed/partial submission and bounded waits without restarting jobs.
- [ ] Implement using existing `partner-config.py` resolution and `delegate-codex.sh submit/status/result --json`; keep durable IDs before collection.
- [ ] Add collection tests for nonzero/incomplete execution, unknown model evidence, actual job timings and native-agent results.
- [ ] Run the new suite through RED/GREEN for each behavior; inspect original completed jobs read-only through the collector.

### Task 3: Acceptance, receipts and host instructions
**Files:** Extend the helper/tests; update `references/tryout.md`, relevant adapter/Core instructions, README parity entries, package checks and CI syntax entries.
**Interface:** A finalization command consumes collected evidence and explicit driver reasoning decisions, reuses `make-receipt.py`, and emits scope-correct verification commands without silently writing configuration.
- [ ] Test strict-failure preservation, pending reasoning acceptance, stale verification timestamps, scope-correct write commands and permission-denied write reporting.
- [ ] Replace exploratory tryout directions with the fixed start/Agent/collect/finalize sequence; retain every quality gate.
- [ ] Run `python3 -m unittest discover -s tests`, `bash scripts/check-skill-repo.sh .`, syntax checks and `git diff --check`.

### Task 4: Independent review and live timing
**Files:** Record evidence in a concise validation document, without credentials or private transcript content.
- [ ] Obtain one fresh-context whole-branch review; address material findings with targeted regression coverage.
- [ ] Execute the approved real Claude-driven tryout using unchanged configured identities and original tasks.
- [ ] Record stage timings and verdicts; compare to 546.5 seconds total / 499 seconds outside the execution window.
- [ ] Investigate until an actual improvement is demonstrated without weakening the gates; do not mark the active goal complete from fixture checks alone.
- [ ] Commit the verified result. Shared installation updates and remote-main publication require their own authorization.

## Execution record
- Design approved by the user; native implementation selected to avoid per-task handoff overhead. One independent branch review remains required.
- Existing isolated worktree reused; branch `codex/partner-tryout-speed`, base `7d12a2e`.
- No product changes or live model calls made at plan creation.
- Task 1: complete. Five test methods with literal positive/negative fixtures passed after observing assertion failures; full suite 138 tests passed in 68.338 seconds. Read-only replay of the supplied completed job produced `passed=false`, `format_valid=false`, `content_valid=true`, `keys_sorted=true`, `errors=[markdown_fence]`.
- Task 2 is next. The new module currently contains acceptance functions only; no dispatch/collection CLI or receipt integration exists yet. No live speedup claim is justified.
