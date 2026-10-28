# Partner workflow hardening implementation plan

**Goal:** Apply the approved engineering audit while preserving the installed main branch.
**Architecture:** Extend existing Bash/Python helpers; keep schema v2 and existing CLI commands compatible. No workflow service, new dependency, model substitution, or paid benchmark.
**Spec:** The engineering audit accepted by the user on 2026-10-28; concrete decisions below.

## Tasks and checks
- [x] Lock goal read/compare/write using the existing lock; concurrent stale writers must not overwrite each other.
- [x] Include staged, unstaged and untracked files in handoffs; retain check exit codes and distinguish the worktree inventory from task ownership.
- [x] Preserve explicit sandbox and identity metadata across resumes. Add process timestamps, acceptance status and observed-model evidence to result JSON without changing legacy DONE semantics.
- [x] Add an opt-in wall limit to delegated jobs using a process-group runner, independent of caller wait timeout. Record failures without automatic retries.
- [x] Preserve current clean Claude child environment by default; offer explicit route inheritance and an explicit expected returned model for intentional mappings. Never log credentials or infer billing from CLI.
- [x] Do not promote Codex dry-run smoke to verified; support one-role smoke and document the narrower verified meaning.
- [x] Make workflow depth risk-based; unify handoff intent, read-only incident behavior, review, recovery, single-writer ownership and receipt guidance across both adapters.
- [x] Run offline unit suite, static repository checks and sandbox matrix; inspect the branch diff before publication.

## Review focus
- Existing jobs/configs remain readable; new metadata can be unknown.
- No route or permission escalation is inferred from a role name.
- Read-only investigation must not become implementation or replay production requests.
- Successful CLI exit is not task acceptance or proof of model identity.
- Concurrent writers, resumed writable jobs, staged/new files and timed-out child processes get regression coverage.

## Validation limits
Offline fixtures can prove orchestration and contracts, not real provider behavior or subscription savings. Real Java/HIS work and paid model comparisons remain user-run validation after review.

## Verification record
- Full offline suite: 129 tests passed.
- Final cancellation/resume race regression added; delegated-job suite rerun separately.
- Static repository checks: fail=0; existing risky-text warning remains.
- Dual-host sandbox matrix: 4 passed. README parity and 36 static behavior cases passed.
