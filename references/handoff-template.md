# Partner Handoff Template

Use this packet when Codex sends the implemented state back to the same Claude Code session for polish or final review. Keep it bounded. Do not paste the whole repo unless the repo is tiny.

`bash "$PARTNER_DIR/scripts/make-handoff.sh"` fills the evidence sections (changed files, git status, diff stat, check output) automatically and leaves the judgment sections as TODO markers; `--save` also persists the handoff under `.partner/handoffs/` for recovery. (`$PARTNER_DIR` is the skill's install directory, not the target repo.)

```markdown
# Partner Handoff

## Task
[One sentence: what the user asked for.]

## Claude Plan
[The plan Claude already gave, or a 5-bullet summary.]

## Codex Implementation
- Changed files:
  - ...
- Key decisions:
  - ...
- Known tradeoffs:
  - ...

## Repo Evidence
```bash
git status --short
git diff --stat
[fastest relevant check command and output summary]
```

## What I Need From Claude
Choose exactly one:

1. UI/interaction polish: return prioritized findings only.
2. Architecture/product critique: return blocking risks only.
3. `/codex:review`: review the current diff for bugs, regressions, missing tests, and unsafe behavior.

## Scope Boundary
- Do not commit, push, deploy, publish, or send external messages.
- Do not touch secrets or `.env` files.
- If you need more context, ask for the smallest file or snippet that unblocks the review.

## Partner Session Receipt
Fill this at the end of the loop:

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
```

## Delegation Packet (both directions)

This is the shared implementation/review packet referenced by `SKILL.md`.
Keep facts necessary for a fresh agent; omit empty history, not constraints.
Tool-free planning uses the separate bounded evidence contract in
`references/bounded-planning.md` because that agent cannot read these paths.

```markdown
# Partner Delegation

## Task
[One job and explicit intent: investigate, review, implement, or deliver.]

## Context
[Why this work matters and what it enables.]

## Relevant files and current state
[Live paths, starting revision/dirty baseline, known findings and decisions.]

## What was tried
[Failed approaches and why; omit when none.]

## Acceptance
[Observable behavior and relevant check commands; preserve the original request.]

## Constraints
- Only touch: [paths]. Preserve: [business/compatibility constraints].
- [Existing user authorization and its limits.]
- Pause only for missing user-only information, a real scope change, or an
  action outside authorization; otherwise finish and report evidence.

## Output
[Changed files or investigation findings, checks, unresolved items; concise.]
```

- Analysis/review packets end with the exact no-edits constant from `SKILL.md`
  and use a read-only execution boundary. Do not request fixes inside a review.
- For repair rounds, send only prioritized findings, failed acceptance criteria
  and "Continue end-to-end from here." Reuse the session when healthy.
- Record task ownership separately from the whole-worktree change inventory.
  Handoff evidence includes staged, unstaged and untracked files; it does not
  prove all those changes were created by this job.

## Good Handoff Rules

- Include `git diff --stat`; include full diffs only for small files.
- Include check command, exit status and bounded output, not entire noisy logs.
- Keep one coordinator writing goal state; use the locked goal-sync helper.
- Name the exact phase: `plan`, `polish`, `review`, or `fix`.
- Ask for prioritized findings. Do not ask for a broad rewrite unless the user requested one.
- If Claude Code returns style-only ideas after the app already works, Codex decides whether they are worth applying.
- Include a Partner Session Receipt whenever Claude Code was involved.

## Goal Packet (Plan→Goal→PR→Verification, `references/goal-to-pr.md`)

Use this packet to present a Stage 1 plan for authorization before writing
`.partner/goal.md` and starting Stage 3. It is a decision artifact for the
user, not a delegation packet for Codex.

```markdown
# Partner Goal Packet

## Ask
[One why-forward sentence: what the user asked for and why it matters.]

## Plan
- Goal / non-goals: ...
- Current-state evidence: [file:line citations, not vibes]
- File scope: ...
- Phases: ...
- Risks: ...
- Acceptance criteria: [verifiable per phase]
- Rollback plan: ...

## idea-king Verdict
[ship | needs-attention | no-go, plus surviving attack points and the
changes already folded into the plan above.]

## Open Decisions
[Anything only the user can decide — scope tradeoffs, priorities,
constraints not visible in the repo.]

## What Authorization Unlocks
Confirming this packet authorizes Stage 3 up through merge-ready PR +
preview verified. It does NOT authorize merge, production, tags,
force-push, deletion, destructive migration, or external publish — each of
those needs its own explicit imperative sentence when the time comes.
```

Rules:

- Send this before creating a branch, worktree, or `.partner/goal.md` —
  Stage 1 (Plan) touches no files.
- A reply that only answers a question in this packet is not authorization
  to proceed; wait for an actual imperative.
- Keep it bounded: cite evidence, do not paste the whole repo.
