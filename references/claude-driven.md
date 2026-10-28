# Claude-Driven Partner Flow (Direction B)

Use this flow when the skill is loaded inside Claude Code and the user asks
Claude to split work with Codex ("双向搭子", "分工给 codex", "让 codex 做",
"codex 后台跑"). Claude Code is the driver; its routed model may be Claude,
GPT or another provider. Apply Workflow Depth in `SKILL.md` before starting
these phases. Delegate only when the task benefits from separation, and verify
all results. CLI selection alone says nothing about billing or savings.

All helper scripts live in `$PARTNER_DIR` (see Tool Location in `SKILL.md`).
Job state lives under `<repo>/.partner/jobs/`.

## Phase 0 — Preflight

- Confirm the Codex CLI: `codex --version`. If missing, stop and tell the
  user this flow needs the Codex CLI installed and authenticated.
- Read the project's instructions and preserve the user's requested intent.
  Keep output concise in the delegation packet; do not ask to modify AGENTS.md
  just to enable Partner.
- Check required runtime, build command and writable cache roots (for example
  the project's JDK and Maven cache) before starting implementation.
- Run `git status --short` and note pre-existing dirt so Codex's diff can be
  isolated later.

## Phase 1 — Plan and Split (goal file)

- For a small or single bounded task, keep the brief in the prompt/job; a goal
  file is optional. For multi-job or resumable work, write
  `<repo>/.partner/goal.md` (template: `references/goal-template.md`): the
  overall goal as one why-forward sentence, a task table, and the checkpoint
  rule from `references/fable5-principles.md`. One coordinator owns state. Use
  `scripts/goal-sync.py read`/`write --expect-sha256 <hash>` instead of
  editing the file directly — the helper locks read/compare/write and rejects a
  stale baseline instead of silently clobbering another update.
- Split tasks by making one judgment per row — which capability does this
  work need (see the identity definitions in `references/goal-template.md`):
  - `fast_worker` for mechanical, spec-complete work (refactors, test
    writing, wide read-only scans, doc generation, boilerplate, batch
    migrations) — the bulk of delegable work.
  - `deep_reasoner` for ambiguous, wrong-premise-is-expensive work (a hard
    diagnosis, a config change whose wrong variant silently breaks things).
  - identity `-` for what the driver keeps inline: architecture, the split
    decision itself, cross-task integration, security/correctness-critical
    paths, final acceptance. Never route these to a cheaper identity to
    save money. Keep tiny mechanical work inline when delegation costs more.
  The configured `backend` selects a CLI, not a provider or quota pool.
  Two escape hatches remain for edge cases: a one-shot Codex subagent
  (e.g. a rescue agent) for a stuck step needing a second diagnosis with
  no durable state, and a raw Task-tool subagent when no Partner identity
  fits — billing notes for both in `references/fable5-principles.md`.
- For uncertain, cross-module or high-risk plans, run the idea-king adversarial review (the `idea-king`
  skill, or `references/../idea-king/SKILL.md` content inline) against the
  split. It must answer three questions: does each delegated task really
  not need the expensive tier, does the integration cost of the split
  boundary eat the savings, and does each row's identity match the work's
  actual stakes (with a reason it is not a more expensive one). Fix the
  split before delegating; its `分工 (Assignment)` section is the
  corrected task→identity mapping you act on.

## Sub Agent Routing

This lookup applies **only to identities whose configured `backend` is
`claude`** — an identity with `backend = codex` never enters it: that work
goes through `delegate-codex.sh` (Phase 2), and spawning a Task subagent
for it would silently swap execution channels. For a
claude-backend identity, resolve *which* agent definition to spawn with
this three-level lookup, in order:

1. **`partner-*` namespaced agent** — if `搭子，配置` has generated
   `partner-deep-reasoner` / `partner-fast-worker` / `partner-arbiter`
   (project or global scope; check
   `python3 "$PARTNER_DIR/scripts/partner-config.py" --host claude_code resolve`
   for the configured identity, or just try spawning the namespaced agent),
   use it explicitly. Its model came from setup; generated effort text is
   advisory, not proof of an enforced API parameter.
2. **The user's own similarly-named agent** — if no `partner-*` agent exists
   but the user has their own `deep-reasoner.md` / `fast-worker.md` (or an
   agent whose description clearly matches the identity), use it as-is.
   Never rename or edit it. Confirm its routing matches the intended identity;
   a similar name alone is not verification.
3. **Generic host subagent** — use it only if the intended model can be selected
   explicitly. A role name in the prompt does not select a model. If this cannot
   be established, report the routing limitation rather than claim the identity
   ran. Configure missing identities before delegating through them.

## Arbiter Protocol — 盲解仲裁

For contentious or high-stakes calls — the driver judges the answer
disputable, or the user says 仲裁 / 有争议 / second opinion — do not settle
for one solver's answer:

1. Send the **same problem, verbatim** to both `deep_reasoner` and
   `arbiter`, each through its own configured backend (subagent spawn or
   `delegate-codex.sh --host claude_code --role arbiter`).
2. **Contamination rule**: neither packet may contain the other solver's
   answer, conclusion, or any leaning hint ("X thinks A, verify it" is
   already contaminated). Blind means blind — a contaminated run silently
   produces fake agreement and must be rerun, not patched.
3. Compare the two answers against evidence. Agreement is corroboration, not
   proof; record both independent runs.
   Disagreement → the driver rules, and records the point of divergence
   plus the ruling's reasoning in the receipt (both solvers appear in
   `roles_used`; the divergence goes in the report/Notes).
4. Record the observed model/provider for each solver, or `unknown`. Different
   CLIs do not guarantee different models; routed clients may share a provider.
   Note `same-vendor` when known rather than infer diversity from backend names.

This is distinct from the idea-king gate: 点子王 attacks a *plan* you
already have; the arbiter independently *solves the same problem* with no
knowledge of the first answer.

## Phase 2 — Delegate

- Build each Codex prompt from the "Claude → Codex Delegation Packet" in
  `references/handoff-template.md`: why-forward context, one-sentence task,
  verifiable acceptance criteria, scope constraints, and the fixed output
  rules (no optional commentary; lessons learned at the end).
- Submit as a background job, passing the row's identity so backend, model,
  and effort resolve from `搭子，配置`'s config. `--host claude_code` reads
  the driver's own routing table (explicit `--model`/`--effort` still wins
  per field if a specific task genuinely needs an override):

```bash
prompt=$(mktemp)
# ... write the delegation packet into "$prompt" ...
bash "$PARTNER_DIR/scripts/delegate-codex.sh" submit \
  --repo "$REPO" --prompt-file "$prompt" --label <task-id> \
  --host claude_code --role <identity> --writable
```

**`--writable` is not optional for implementation tasks.** With no sandbox
flag the job inherits `codex exec`'s own default, which is **read-only**
unless the user happens to have set `sandbox_mode` in `~/.codex/config.toml`.
A read-only implementation job does not fail — Codex reads everything, works
out the patch, gets `apply_patch` rejected, and finishes `DONE` having
changed nothing. Check the box before delegating: no `~/.codex/config.toml`
(or no `sandbox_mode` in it) means every write-bearing job needs
`--writable`. On a Maven/Gradle/npm task whose build writes outside the
repo, note that `workspace-write` covers the repo and `/tmp` only; a job that
must populate `~/.m2` or a similar cache needs that root granted too.

The tool fail-closes on both misconfigurations: no Partner config yet →
clear error (run `搭子，配置` first, or fall back to an explicit `--effort`
for this one job and note it in `Notes`); identity configured with
`backend = claude` → refusal with a pointer to spawn the `partner-<identity>`
subagent instead — this is the guard against silently running a
claude-backend identity through the wrong CLI.

- Use `--read-only` for scan/review jobs that must not modify the repo.
- Record the returned jobId in the task brief or goal file. Keep one writer per
  working directory. Parallelize read-only tasks; isolate independent write tasks
  in worktrees and make the driver responsible for integration.

## Phase 3 — Monitor (loop)

- Short single job (expected under ~5 minutes): block on it —
  `bash "$PARTNER_DIR/scripts/delegate-codex.sh" status <jobId> --repo "$REPO" --wait --timeout 300`.
- Long or multiple jobs: set up the built-in `/loop` skill at a 5-minute
  interval with a prompt like: read `.partner/goal.md`, run
  `delegate-codex.sh status` for every running jobId (tail the job's
  `log.jsonl` for the last event), update task statuses in the goal file,
  and when no job is left running, stop the loop and continue with Phase 4.
- For an explicit task runtime limit, pass `--wall-timeout <seconds>` on submit.
  The runner records timing/failure in `execution.json` and cleans up its process
  group on expiry. Explicit `--writable` jobs hold a workspace write lock; a busy
  writer returns `writer_busy` without starting another model call.
- A wait timeout only ends the caller's wait. Check the process and configured
  task deadline before taking action; do not launch a duplicate job.
- No new JSONL events across two ticks is a reason to inspect, not cancel.
  Long builds/tests can be quiet. Check the running command, permissions and
  stderr; use that command's timeout where available. Authentication, missing
  dependencies, transport errors and failed acceptance require different fixes.
- Retry a transient failure at most once after preserving evidence; fix a
  deterministic blocker before retrying. Save the checkpoint before terminating
  a job that exceeds its task deadline. Never retry a production replay or resend
  merely because a response was missing.
- **`DONE` means process completion, not task acceptance.** Collect result JSON,
  inspect the full task diff (staged, unstaged and untracked) against the starting
  baseline, and run the agreed checks. For analysis, inspect evidence instead of
  expecting a diff. An implementation with no changes may already be satisfied;
  verify that or identify a permission failure before requesting a fix round.

## Phase 4 — Full Review Gate

- Collect each finished job:
  `bash "$PARTNER_DIR/scripts/delegate-codex.sh" result <jobId> --repo "$REPO"`.
- The driver performs one complete acceptance review, combining any relevant
  polish with correctness review. Include staged, unstaged and untracked changes,
  scoped against the starting baseline, plus the relevant check. After a fix,
  review the changed area and affected acceptance criteria rather than repeat an
  unchanged full pass.
- Review against the acceptance criteria in the task brief or `.partner/goal.md`, not against
  the diff alone. A reviewer given only the diff confidently redefines the
  spec as "internally consistent with what changed" and misses tasks that
  were never done — in Superpowers 6, diff-only reviewers caught 0 of 5
  missing task briefs. Re-read each task's brief, then ask "does this diff
  satisfy that brief," not just "is this diff self-consistent."
- Findings? Send one bounded fix round back to the same Codex session:

```bash
bash "$PARTNER_DIR/scripts/delegate-codex.sh" resume <jobId> \
  --repo "$REPO" --prompt-file <fix-notes>
```

- Maximum two fix rounds per task. Then diagnose the remaining blocker and
  either finish within the driver's capabilities or report required user input.
  Record the takeback. A fresh independent final review is justified for high-risk
  changes; do not add another review just because a command exists.

## Phase 4.5 — Delivery (opt-in, `references/goal-to-pr.md`)

Only runs when the user asked for the full "完整协议 / PR 交付 / 目标模式"
protocol (see Trigger Grading in `references/goal-to-pr.md`) and has
authorized it via a Goal Packet (`references/handoff-template.md`). Skip
this phase entirely on the default lightweight flow above.

- Follow Stage 3 (PR) and Stage 4 (Verify Ladder) in
  `references/goal-to-pr.md`: branch/worktree, implement, verify, push,
  open/update PR, wait for and fix CI, verify preview.
- Stop at merge-ready + preview verified. Merge, production, tags,
  force-push, deletion, destructive migration, and external publish are
  each an independent hard stop — each needs its own fresh imperative
  sentence, recorded in the goal file's `Delivery.authorization` field.
- Update `.partner/goal.md`'s `## Delivery` section as each field becomes
  known (branch/worktree, pr, ci, preview, live).

## Phase 5 — Wrap Up

- Mark tasks done only after acceptance; update `.partner/goal.md` if one exists
  and stop any remaining `/loop`. Save the full receipt; show the user a concise
  outcome, checks and remaining limitations.
- Emit the Partner Session Receipt with `direction: claude-driven` and
  `codex_jobs: <count>`; in this direction `claude_session` refers to the
  current session and `new_claude_p_sessions` is normally `0`. Set `host`,
  `scope`, and `config_source` from `partner-config.py resolve` (or
  `partner-setup.py --status`), and build `roles_used` from the roles this
  run actually invoked: each `delegate-codex.sh` job's `meta` file has
  `role`/`model`/`effort`/`model_source`/`effort_source`, and
  `partner-config.py resolve` has each role's `verified`/`verified_at`. List
  a role even when `verified` is `false` — never guess it true.
- Run the memory protocol in `references/memory-protocol.md`: what got
  delegated, how Codex performed per task type, rework rounds, and effort
  fit — so the next split decision starts smarter.
