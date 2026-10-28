# Partner Scenario Profiles

Apply the workflow depth from `SKILL.md` first. These profiles refine task
intent and acceptance; they do not force another agent or a separate polish pass.

## Review-Only

- Review the complete relevant diff against the original requirements.
- Use a read-only reviewer and return findings. Apply fixes only when the user
  asked for fixes as well; do not reinterpret "review" as authorization to edit.
- Skip planning and `/goal` unless an unresolved decision requires them.
- Receipt: `phase: review`; distinguish findings from fixes actually applied.

## Debugging / Incident

- For investigation, gather bounded evidence and test ranked hypotheses using
  read-only sources. Return the supported conclusion, alternatives and unknowns.
- A production investigation never authorizes request replay, resends, data edits
  or deployment. Keep HIS success, local commit, downstream notification and final
  business outcome distinct; timestamps alone do not establish causality.
- For an authorized fix, reproduce the failure where possible, implement it and
  run the relevant regression check. Investigation can finish with a supported
  diagnosis even when the user has not authorized a repair.

## Non-UI Task (Backend, Scripts, Data)

- Include API compatibility, error behavior and relevant edge cases in the same
  acceptance review. Do not create a separate polish phase merely to fill a slot.
- Before a Java job, resolve the project's JDK and build command, network needs
  and dependency-cache write permissions. A blocked build is an environment issue,
  not evidence that implementation passed or failed.
- Report local checks, external/HIS integration, SQL execution/plan, deployment
  and observed production effects separately. An unrun layer stays unverified.

## Non-Git Directory

`git status` is the default grounding step, but some targets are plain folders.

- Replace git evidence with a bounded file inventory (see `NOT_GIT_REPO` in `references/monitoring.md`); `"$PARTNER_DIR/scripts/make-handoff.sh"` does this automatically.
- Verification relies on checks and file diffs by timestamp/content, so state before/after inventories explicitly.
- Receipt: note `non-git target` under `checks` or `anomalies` so the evidence level is transparent.

## Monorepo

Repo-wide diffs drown the handoff in unrelated noise.

- Scope every git command to the package: `git status --short -- <path>`, `git diff --stat -- <path>`.
- Name the package path in the handoff Task line; Claude should not reason about sibling packages.
- Run the package-local check (workspace script) rather than the repo-wide suite when iterating; run a wider suite when affected dependencies or the repo's checks require it.

## Large Or Multi-Day Task

One session will not survive the whole task, so persist state instead of hoping.

- Write the accepted plan to `.partner/plan.md` as soon as Claude produces it.
- Save every handoff with `bash "$PARTNER_DIR/scripts/make-handoff.sh" --save`; save the final receipt with `make-receipt.py --save`.
- When the session is lost, cold-start the replacement with `plan.md` + the newest handoff only — this is the bounded payload, already written.
- Receipt: count each replacement session honestly (`claude_session_reused: no` for the first pass after a loss) and say why in `anomalies`.
