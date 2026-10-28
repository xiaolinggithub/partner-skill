---
name: partner-skill
version: 2.0.1
description: |
  搭子.skill / Partner — two-direction engineering workflow between Claude Code and Codex. The active host chooses workflow depth by task risk, delegates only useful units, and verifies results against the user's intent. Complex plans may use idea-king; contentious decisions may use blind arbitration. Use on "搭子" / "双向搭子" / "搭子，恢复" (resume from .partner/), "搭子，配置" (first-run setup wizard), "搭子，试跑" (identity tryout report), 分工给 codex / 让 codex 做 / codex 后台跑 / Claude 计划 Codex 实现 / 让 Claude skip 做完, or any request to split coding work between Claude Code and Codex to save quota. Not for ordinary code review without Claude Code; do not trigger on the bare English word "partner" in unrelated contexts.
---

# 搭子.skill (Partner)

> 我的 Claude Code 和 Codex 天下第一好。

## Overview

The active host owns the result. Use the configured roles for planning,
implementation and review when their contribution outweighs handoff, context,
review and rework overhead. Neither client name determines model quality,
provider, authentication, or billing. CC Switch can intentionally route Claude
Code to a GPT or other model; both clients can share the same quota pool.

## Workflow Depth

Choose from repo evidence and the user's request without asking them to select
an operating mode:

| Task | Default flow |
|---|---|
| Small, reversible, clear change | Driver implements and runs the relevant check; no mandatory delegation, goal file or extra review session. |
| Bounded module task | One delegation, then one full acceptance review; combine polish and review. |
| Cross-module or uncertain work | Compact plan, justified split, integrated acceptance; use idea-king when the split or premise needs challenge. |
| High-risk change or contentious decision | Independent review; use blind arbitration for disputed decisions, not every task. |

Keep implementation and investigation distinct. A read-only request never
becomes a fix, production replay, resend, or deployment. Full acceptance means
checking the original requirements and evidence, not running every phase.
Use helpers for routing, waiting, timestamps and reports; use models for
judgment. Only one writer owns a working directory; isolate independent write
jobs in worktrees. Read-only jobs can run concurrently.

## Host Detection

Partner is one Core (this file) plus one host adapter. Decide the host once at the start and say which direction you are in:

- **The host is the runtime that actually loaded this SKILL.md.** Self-identification wins: a prompt that merely mentions the other agent ("让 codex 做", "ask Claude") never switches your identity.
- The `host=codex|claude|generic` marker in `.install-meta` (written by install.sh) is a tiebreaker only, for copies whose load path is ambiguous. It never overrides self-identification.
- An unknown runtime runs Core-only until capabilities are established. A shared `~/.agents` directory or symlink does not override a known Claude Code/Codex runtime.
- Probing the peer CLI (`codex --version`, `check-claude-cli.sh`) only tells you what the other side can do; it never decides which adapter you load.

Then load the matching adapter:

- **Direction A — Codex-driven**: this file is loaded by Codex; Codex orchestrates and Claude Code is the high-value planning/polish/review agent. Read `references/codex-driven.md` and follow its Default Flow, Session Strategy, and Permission Policy.
- **Direction B — Claude-driven**: this file is loaded inside Claude Code and the user asks to delegate work to Codex ("双向搭子", "分工给 codex", "让 codex 做", "codex 后台跑"). Claude plans and splits the work, delegates to Codex via `bash "$PARTNER_DIR/scripts/delegate-codex.sh"` background jobs, monitors with a loop, and full-reviews the result before accepting. Read `references/claude-driven.md` and follow its five phases; the shared prompting rules live in `references/fable5-principles.md` and the wrap-up memory rules in `references/memory-protocol.md`.

Both directions end with the same Partner Session Receipt; `direction` records which flow ran.

## Configuration

On "搭子，配置", or when a Partner flow needs an identity with no
configuration yet, run the local setup UI in `references/setup.md` with
`python3 "$PARTNER_DIR/scripts/partner-setup-ui.py" --host <host> --repo <repo>`.
Do not collect the matrix through repeated chat questions when a browser is
available. The single page shows every backend, concrete model, and effort,
then delegates every preview/write to `partner-setup.py` (preview → atomic
apply → automatic smoke test). It uses beginner-safe project defaults instead
of asking scope/Git/routing questions in chat; the terminal engine remains
available for explicit advanced overrides. Three identities — deep_reasoner, fast_worker, and
arbiter (the blind second solver for contentious calls) — each carry their
own backend (which CLI executes: claude or codex), model, and effort,
freely mixed across vendors. Their values live only in
`.partner/config.toml` (project) or `~/.config/partner/config.toml`
(global) — schema in `docs/config-schema.md`; never duplicate them into
prompts or docs. On "搭子，试跑", run the identity tryout in
`references/tryout.md`: each identity executes one micro-task and the
report distinguishes requested and observed models, actual elapsed time, and output validity. A dry-run configuration check is not a live verification.

## Tool Location

The helper scripts referenced below live in this skill's install directory (the directory containing this SKILL.md), not in the target repo. Resolve it once as `$PARTNER_DIR` — you know it from wherever this file was loaded; otherwise probe `~/.codex/skills/partner-skill`, `~/.claude/skills/partner-skill`, `~/.agents/skills/partner-skill`, or the local clone. All scripts accept running from any cwd; repo-dependent ones take `--repo`.

## LOCAL NOTE — 本机安装拓扑与来源（非上游内容）

This installation may be shared through symlinks. Inspect `ls -ld`, `readlink`,
and `git remote -v` before updating it; an installation lock's source URL does
not prove that `.git` exists or that local edits are safe from an updater.
Do not run `install.sh --target all` from a directory that is also an install
target: moving the target away can invalidate the source. Use an isolated
checkout for development, retain a backup, and preserve existing symlinks.
`idea-king/SKILL.md` and `idea-king/codex-prompt.md` are separate instruction
files; update both when changing their shared rules.

## Routing Rules

- Choose capability (`deep_reasoner`, `fast_worker`, `arbiter`) before execution
  channel. Keep integration and final acceptance with the driver.
- Resolve backend/model/effort from config. Record requested and observed models
  separately; label unobserved values and billing sources `unknown`.
- Intentional route mappings are allowed; do not silently substitute a model
  to make a task pass. Different clients alone do not prove independent models.
- Reuse a healthy session for repair rounds; use a bounded fresh session when
  context has become stale or independent high-risk review is needed.
- Keep Kimi Work/Kimi Code Goal separate from Claude Code `/goal`.

## Delegation Contract

Every handoff to another agent — a Codex background job, a Claude subagent,
an arbiter call — obeys these four rules. They are cheap, and each one fails
silently when skipped, which is why they are written down instead of assumed.

**1. Use the delegation packet in `references/handoff-template.md`.** It is the
single template for task, purpose, relevant files/current state, prior attempts,
acceptance and constraints. Omit empty history rather than filling it with
boilerplate. Implementation packets point at live files; tool-free planning
packets must contain the bounded evidence the planner cannot fetch itself.

**2. Preserve task semantics verbatim.** Investigate-only → "DO NOT edit
files." Fix → "implement the fix." Refactor → "refactor, not rewrite."
Review → "report findings, do not apply them." The delegated task is the
user's task, not your paraphrase of it; the packet carries the original
intent including its limits. Semantic drift at the boundary is the most
common way a correct plan produces a wrong diff.

**3. Analysis-only jobs end with the no-edits constant.** Any job that must
not touch the repo — the idea-king gate, an arbiter call, a review pass, a
second opinion — ends its prompt with this exact string, copied, not
reworded:

```
This is analysis only. Do NOT edit, create, or delete any files. Do NOT write code.
```

A fixed constant is greppable and can be checked before send; an ad-hoc
sentence cannot. Belt and braces: pair it with the sandbox flag
(`delegate-codex.sh --read-only`) so the constraint still holds when the
model ignores prose.

**4. Monitor evidence without interrupting useful work.** Prefer completion
signals or bounded waits. A caller wait timeout does not stop the job. No new
JSONL events alone is not proof of a hang: inspect the running command, process,
permission state and task deadline before cancelling. `DONE` means process exit,
not acceptance; inspect results, changes against the starting baseline and checks.
An empty diff is expected for analysis and can be valid when work was already done.

## Bounded Claude Planning

For repository-heavy planning through a Claude-backed `deep_reasoner`,
especially at `xhigh`, use `references/bounded-planning.md` and
`scripts/run-claude-plan.py`. The outer host prepares the required
24,000-character-max evidence packet; Claude runs in safe mode with no tools or
subagents, explicit wall/valid-event idle limits, bounded stream/output/log
sizes, process-group termination, and a Claude-CLI-enforced API budget.
Model and effort come only from `.partner/config.toml`. Failure preserves a
checkpoint, sanitized events, cost metadata, and a same-session recovery
command; Partner never substitutes another model silently.

## Validation Gate

Use the Darwin-style ratchet in `references/darwin-ratchet.md` when improving this workflow or applying it to a substantial task:

- Change one workflow dimension at a time: planning, implementation, UI polish, review, monitoring, permissions, or reporting.
- Run test prompts or a real miniloop before calling an improvement better.
- Do not let the same agent be the only maker and only judge for high-risk changes.
- Keep the change only when repo evidence improves. If it regresses, use a reviewable revert, not `git reset --hard`.
- Stop when another prompt loop produces low signal or <1 point expected improvement.

## Monitoring

For active Claude Code sessions, read `references/monitoring.md`. Prefer five signals instead of trusting chat text alone:

1. PTY output from the running Claude Code session.
2. `claude agents --json --cwd <repo>` session status.
3. Claude JSONL transcript structure, without dumping full message bodies by default.
4. Optional task files under `~/.claude/tasks/<sessionId>/`.
5. Repo evidence: `git status --short`, `git diff --stat`, and relevant test/build checks.

Signals 2-4 depend on Claude Code CLI internals that can drift between versions. Probe them with `bash "$PARTNER_DIR/scripts/check-claude-cli.sh"` and report the resulting `monitoring_level` (`full`, `degraded`, or `none`) in the receipt. Never claim a signal the probe says is unavailable. When an anomaly occurs, follow the fixed recovery path in `references/failure-playbook.md`.

## Output Contract

Report the outcome, checks and remaining limitations briefly; save the complete
receipt with `--save` and link it instead of dumping every internal field.
The saved report includes:

- Current phase: planning, Codex implementation, Claude polish, review, or final fix.
- Claude Code session id when one exists.
- Files changed and checks run.
- Review findings fixed or still open.
- Whether the work is ready to commit; do not commit by default.
- Any monitoring anomaly such as idle session, permission wait, empty review output, no diff, or failed check.
- A Partner Session Receipt for non-trivial Claude Code workflows:

```text
[Partner session receipt]
phase: <planning | codex implementation | claude polish | review | final fix>
claude_session: <sessionId or none>
claude_session_reused: <yes | no | n/a>
new_claude_p_sessions: <0 | count | unknown>
codex_passes: <number of implementation/fix passes>
checks: <commands run or not run>
anomalies: <none | permission wait | idle | empty review | failed check | other>
monitoring_level: <full | degraded | none | unknown>
direction: <codex-driven | claude-driven>
codex_jobs: <0 | count>
host: <claude_code | codex | generic>
scope: <project | global | n/a>
config_source: <session | project | global | default | n/a>
roles_used: <none | JSON array of {role, host, model, effort, verified}>
receipt_schema_version: 2
```

Generate the receipt with `python3 "$PARTNER_DIR/scripts/make-receipt.py"` — it auto-fills `monitoring_level` from the probe and refuses to emit an invalid receipt. Get `new_claude_p_sessions` from `bash "$PARTNER_DIR/scripts/session-snapshot.sh" diff` so the count is computed from transcript evidence. In Direction B, set `direction: claude-driven` and `codex_jobs` to the number of `delegate-codex.sh` jobs (including fix rounds); in Direction A they are `codex-driven` and `0` unless background jobs were used. A written receipt can be re-checked any time with `validate-receipt.py` against `docs/receipt-schema.json`.

`host` is the runtime that loaded this file (see Host Detection above); `scope`
and `config_source` come straight from `partner-setup.py --status` or a
`partner-config.py resolve` call (`n/a` when the run touched no configured
role). `roles_used` lists every role actually invoked this run, each entry's
`verified` taken from the config's `verified` field, not guessed — an
unconfigured or unverified role still gets an entry with `verified: false`,
it is never omitted to make the receipt look cleaner. `receipt_schema_version`
is always `2`; a receipt missing the four fields above is a schema v1
receipt from before this contract and will fail `validate-receipt.py`, which
is the intended signal to regenerate it with the current `make-receipt.py`.

Do not infer subscription quota percentages from token counts or client names. Do not fabricate token savings. When exact token telemetry is unavailable, report verifiable behavior instead: same Claude Code session reused, no fresh `claude -p` session, bounded handoff used, checks passed.
