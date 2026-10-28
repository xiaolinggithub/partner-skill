# Partner Failure Playbook

Fixed recovery paths for every anomaly a Partner run can hit. Each entry has
three parts: how to detect it, what to do, and how to record it in the
Partner Session Receipt. Detection signals come from the five monitoring
layers in `references/monitoring.md`; run
`bash "$PARTNER_DIR/scripts/check-claude-cli.sh"` first to learn which layers
are available (`$PARTNER_DIR` = the skill's install directory).

## Permission Wait

- Detect: PTY output shows a permission prompt; session status is not progressing; transcript stops at a tool call.
- Recover: answer or cancel inside the same PTY when the action is safe and in scope. If the requested action is out of scope (commit, push, secrets), deny it and continue.
- Receipt: `anomalies: permission wait`.

## Idle Session, No Diff

- Detect: session status `idle`, `git status --short` unchanged, transcript not growing.
- Recover: first compare the requested intent with the result. Analysis needs no
  diff, and implementation may already be satisfied. If work is incomplete,
  identify a permission/dependency blocker before sending one bounded follow-up.
- Receipt: `anomalies: idle`.

## Idle Session, Meaningful Diff

- Detect: session status `idle` but the repo has new changes.
- Recover: process completion is not acceptance. Inspect changes against the
  starting baseline and original requirements, then run the relevant check.
- Receipt: `anomalies: none` (idle after finishing is not an anomaly).

## Empty Or Low-Signal Review

- Detect: `/codex:review` or a polish pass returns nothing actionable.
- Recover: a completed review with no findings can be healthy. Confirm it covered
  the requirements and evidence; empty or incomplete output is a limitation. Do
  not prompt repeatedly just to obtain a finding.
- Receipt: `anomalies: empty review` only when coverage/output is missing.

## Review Or Polish Hangs

- Detect: no transcript/diff growth across several polls; PTY shows no prompt.
- Recover: inspect the active command, permission state and task deadline first.
  Quiet builds or reasoning are not automatically hung. Preserve the checkpoint
  before terminating a job that exceeds its deadline; record any verification gap.
- Receipt: `anomalies: other (review hang, codex-side verification used)`.

## Bounded Planner Idle Or Timeout

- Detect: `scripts/run-claude-plan.py` exits non-zero and its
  `.partner/runs/<run-id>/metadata.json` reports `idle_timeout`,
  `wall_timeout`, or `upstream_idle`.
- Recover: inspect the sanitized `events.jsonl` and `checkpoint.md`, then use
  the exact same-session command in `recovery.md`. Do not restart repository
  discovery and do not substitute another role/model automatically. If resume
  fails, ask for explicit approval before selecting another configured role.
- Receipt: `anomalies: other (bounded planner <failure_kind>; checkpoint
  preserved)` and list the run id under checks.

Authentication is a separate failure class. `metadata.json` reports
`authentication` only when the child CLI produces authentication evidence;
an idle or API timeout after successful model events must not be relabeled as a
login error.

## Delegated Job Failure or Wait Timeout

- A caller wait timeout is not a task termination; inspect the existing job before
  retrying. Never submit a duplicate merely because `status --wait` timed out.
- Authentication or permission failures need the actual blocker resolved. Missing
  JDK/dependencies/cache access need environment repair. Do not retry unchanged.
- A transient transport failure may receive one bounded retry after evidence is
  preserved. A failed acceptance check receives a same-session fix packet.
- Production replay/resend is a separate user action; transport uncertainty does
  not authorize it. Use task-specific deadlines for known long commands.

## Session Crash Or Unrecoverable Exit

- Detect: process gone, `claude agents --json` no longer lists the session.
- Recover: try `claude --resume <name-or-id>` first. If resume fails, start a fresh session only with a bounded handoff (`bash "$PARTNER_DIR/scripts/make-handoff.sh"`) and state the token tradeoff.
- Receipt: `claude_session_reused: no` plus `anomalies: other (session lost, resumed via bounded handoff)`.

## Context-Heavy Or Confused Session

- Detect: responses degrade, Claude re-asks answered questions, latency grows.
- Recover: close the session and restart with a bounded handoff after reporting the tradeoff. Persist state first (see below).
- Receipt: `claude_session_reused: no` with the reason in `anomalies`.

## Failed Check

- Detect: any verification command exits non-zero.
- Recover: the failure becomes a Codex implementation task unless it needs credentials or user-only context. Fix, rerun, then continue the loop.
- Receipt: list the command under `checks`; `anomalies: failed check` only if it remains failing at report time.

## Degraded Monitoring

- Detect: `scripts/check-claude-cli.sh` prints `MONITORING_LEVEL=degraded` or `none`.
- Recover: rely on PTY output and repo evidence; do not claim signals you cannot read. With `none`, run the task Codex-only and say so.
- Receipt: `monitoring_level: degraded` or `none` — never report `full` when probes failed.

## State Persistence: `.partner/`

For large or multi-day tasks, persist the loop state inside the target repo so
a lost session never means rebuilding context from zero. `.partner/` is
git-ignored by this skill's convention.

```text
.partner/
  plan.md                  The accepted Claude plan for the current task
  handoffs/                Bounded handoffs, one file per pass
                           (written by make-handoff.sh --save)
  plans/                   Successful bounded Claude plans
  runs/                    Sanitized bounded-plan events/checkpoints/metadata
  receipts/                Final receipts (written by make-receipt.py --save)
  session-baseline.txt     Transcript snapshot (written by session-snapshot.sh)
```

Recovery rule: when a session is lost, the newest file in `.partner/handoffs/`
plus `plan.md` is the complete cold-start payload. Send only that — not the
repository — to the replacement session. The user can trigger this directly
with `搭子，恢复` (resume the last Partner task).
