# Codex-Driven Partner Flow (Direction A)

Use this flow when the skill is loaded by Codex: Codex is the outer
orchestrator and main implementer, and Claude Code is the high-value
planning and review client. Apply Workflow Depth in `SKILL.md`; small work may
remain entirely with the driver and ordinary polish/review share one pass.
Host detection, shared routing rules, the validation gate, monitoring
signals, and the Partner Session Receipt contract live in `SKILL.md`;
this file holds only the Codex-driven flow itself.

All helper scripts live in `$PARTNER_DIR` (see Tool Location in `SKILL.md`).

## Default Flow

1. Ground in the target repo.
   - Enter the concrete project directory, not the `agent-workbench` root.
   - Run `git status --short` before starting Claude Code. For a non-git target, record a bounded file inventory instead (see `references/monitoring.md`).
   - Run `bash "$PARTNER_DIR/scripts/check-claude-cli.sh"` once to learn the available monitoring level; report it in the final receipt.
   - Run `bash "$PARTNER_DIR/scripts/session-snapshot.sh" start --repo <repo>` so the receipt's new-session count is computed, not guessed.
   - Identify whether the task is greenfield, feature-heavy, UI-heavy, review-only, or debugging. When the task does not fit the default profile (review-only, debugging, non-UI, non-git, monorepo, multi-day), apply the matching profile in `references/scenarios.md`.

2. Start a planning session only when planning needs another perspective.
   - For repository-heavy planning through a Claude-backed `deep_reasoner`,
     especially at `xhigh`, follow `references/bounded-planning.md`: Codex
     prepares the contract packet and invokes
     `python3 "$PARTNER_DIR/scripts/run-claude-plan.py"`. The runner preserves a
     resumable session id while disabling tools and subagents.
   - For small interactive planning, or when the user explicitly asks for
     Claude Code `/goal`, start Claude Code in a PTY with
     `claude --permission-mode plan --name <task-name>` and send
     `/goal <clear completion condition>`.
   - Ask Claude Code for a concrete implementation plan, acceptance criteria, and UI/interaction guidance.
   - Reuse the bounded runner's session id or the interactive session for later
     polish and review when it remains healthy.
   - Reuse context for normal repair/review. For a high-risk independent review,
     use a fresh session with the original requirements and bounded evidence.

3. Implement primarily with Codex.
   - Convert Claude Code's plan into a short checklist.
   - Make the code changes directly in Codex, using existing repo patterns.
   - Run the fastest relevant check after risky edits.
   - Keep Claude Code out of mechanical bulk edits, repeated lint fixes, and long command loops unless the user asks.

4. Run one acceptance review, combining polish when relevant.
   - Use `references/handoff-template.md`: original acceptance criteria, changed
     files, staged/unstaged/untracked evidence, checks and known risks.
     `bash "$PARTNER_DIR/scripts/make-handoff.sh"` collects the evidence half;
     compare it with the starting baseline before attributing files to this task.
   - Include UI/interaction/accessibility findings for frontend work, or behavior
     and compatibility for backend work. Ask for prioritized findings, not rewrites.
   - `/codex:review`, when available and appropriate, can perform this review;
     do not automatically add it after a review that already covers the criteria.
   - Codex applies authorized fixes and reruns affected checks. Review-only tasks
     return findings without modifying files.
   - Save a Partner Session Receipt for a non-trivial collaboration and summarize
     its outcome and limitations in the user-facing reply.

## Session Strategy

- Small task: keep it inline. Bounded collaboration: reuse a healthy session
  for implementation feedback and combined review.
- Start a fresh session when context is stale, recovery fails, independent
  high-risk review is needed, or the user asks. Account for its context cost;
  session reuse alone is not evidence of lower quota usage.
- If the same Claude session gets stuck in a prompt, permission wait, or idle state, first try to continue or resume the same session with a bounded message. Do not cold-start a replacement review unless the value clearly beats the context cost.
- Large task or huge diff: split sessions only after Codex produces a compact handoff containing the plan, changed files, key decisions, known risks, and check results.
- For large or multi-day tasks, persist the loop state under `.partner/` in the target repo (plan, handoffs via `make-handoff.sh --save`, receipts) so a lost session restarts from the newest handoff, not from zero. See `references/failure-playbook.md`.
- When the user says `搭子，恢复` or asks to resume the last Partner task, load `.partner/plan.md` plus the newest file in `.partner/handoffs/` as the cold-start payload instead of rebuilding context.
- If the same Claude session gets slow, confused, or context-heavy, close it and restart with a bounded handoff only after reporting the token tradeoff.
- Include UI quality in the acceptance review when the task has a visual surface;
  a separate polish phase is needed only for distinct design work.
- If review appears stuck, inspect commands and permission state before stopping
  it. Preserve evidence, classify the blocker, then use bounded recovery or
  Codex-side verification and report any independent-review gap.
- If Claude Code produces no actionable polish, do not keep prompting it blindly. Capture the empty/low-signal result, run Codex verification, and report the limitation.
- Raw `claude -p` is not the default Partner path. The bounded runner is the
  only default print-mode exception: it supplies limits, artifacts, config-only
  model resolution, and a resumable session id. Use raw print mode only for a
  cheap one-off where losing prior context is acceptable.

## Permission Policy

- Default to `--permission-mode plan` for planning and normal permissions for implementation review.
- Use skip/bypass only when the user explicitly asks for `skip`, `最高权限`, `全部允许`, `bypass`, or when the work is inside an intentionally isolated worktree.
- Treat `skip` as a permission escalation only when it clearly refers to Claude Code's permission mode (for example `让 Claude skip 做完`). When `skip` could mean skipping a workflow step (for example `skip the polish`, `跳过这一步`), ask one clarifying question instead of launching bypassPermissions.
- For skip mode, start Claude Code with `claude --permission-mode bypassPermissions --name <task-name>` or `claude --dangerously-skip-permissions --name <task-name>`.
- Before any skip session, state the repo path, current git status, intended scope, and stop condition.
- Never let skip mode commit, push, deploy, send messages, publish, or touch secrets unless the user gives a separate explicit instruction.
- Never treat `skip` as permission to ignore repo evidence. `skip` changes Claude Code permissions, not Partner's verification duty.
- Keep repository visibility changes, release tags, registry publication, and external announcements behind a separate explicit publish instruction.
