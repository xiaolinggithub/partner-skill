# Frontier-Model Prompting Principles (Fable 5 Masterclass distillation)

Shared rules for every agent-to-agent prompt in Partner, both directions.
Distilled from Anthropic's Fable 5 (Mythos) Prompting Masterclass; the
principles transfer to any frontier agentic model, including the Codex side.

## Why-Forward Context

Frontier models perform on *why*, not just *what*. Open every handoff with:

> I'm working on [the larger task] for [who it's for]. They need
> [what the output enables]. With that in mind: [the actual request].

Never send a bare instruction ("refactor this file") without the purpose.

## Brevity Over Exhaustiveness

Short prompts with a clear goal beat long constraint lists. Over-specifying
degrades output — you are constraining a model that would have found the
right approach itself. Specify only genuine blockers as constraints. Do not
port prompt templates written for older, weaker models.

## Explicit Checkpoints

Autonomous agents define their own checkpoints unless you set them:

> Pause only when the work genuinely requires input: a destructive or
> irreversible action, a real scope change, or something only I can
> provide. Otherwise keep going and report back when done.

Put this rule in the goal file and in every delegation packet.

## Effort as a Handoff Parameter

Effort level is the intelligence/latency/cost dial. Prefer `delegate-codex.sh
--host <driver> --role <identity>` so backend, effort, and model resolve
from `搭子，配置`'s config instead of being picked ad hoc per call; pass an
explicit `--effort` only when a specific task genuinely needs to override
its identity's default. Without a `--role` or explicit `--effort`, the tool
falls back to `high` — reserve `xhigh` for the hardest, quality-critical
jobs. Select effort using task outcomes and total rework cost; do not assume
medium is suitable only for trivial work or high is always more economical.
Distinguish CLI-enforced parameters from advisory prompt text.

## Resume Instead of Restart

Frontier models occasionally stop early. Recovery is one line, sent to the
same session:

> Continue end-to-end from [last checkpoint]. Reference: [goal file / job
> log]. Report back when complete.

Use `delegate-codex.sh resume` when the session remains usable. If context is
stale or recovery fails, use a bounded fresh handoff instead of rediscovery.

## Memory Instruction

When an agent has a place to write lessons (rollout memory, memory dir,
mem0), include:

> Store one lesson per note with a one-line summary. Record corrections and
> confirmed approaches alike, including why they mattered. Don't save what
> the repo or chat history already records. Update an existing note rather
> than duplicating it. Delete notes that turn out to be wrong.

## Output Discipline

Dense output keeps the receiving agent's context clean. Every delegation
packet ends with:

> DO NOT send optional commentary. Answer only what was asked — no
> preamble, no unsolicited suggestions, no closing remarks. End with at
> most 3 lines of lessons learned.

This is measured, not folklore: a terse reviewer contract cut reviewer
output by 41% with no loss in judgment quality (Superpowers 6
autoresearch, 25+ controlled experiments).

## Choose Execution by Capability and Overhead

The driver owns architecture, task boundaries, integration and final acceptance.
Keep small tasks inline when delegation and review would cost more than doing
them directly. For a genuine delegated unit choose the lifecycle it needs:

| Channel | Shape | Use when |
|---|---|---|
| Partner `delegate-codex.sh` | Durable job, logs, resume and result evidence | Work needs a background lifecycle or bounded repair rounds. |
| One-shot host subagent | Isolated context and a returned answer | A bounded read-only scan or second opinion needs no durable job. |
| Current driver | No handoff or duplicate context | The task is small or requires shared state and sequential decisions. |

`backend` names a CLI. Authentication and routing determine provider and billing;
Claude Code may use GPT through CC Switch, and both clients may share a quota pool.
Record only observed model/usage facts and known billing sources. Different clients
are not proof of independent model judgments or cheaper execution.

For Claude-backed roles use the explicit namespaced agent routing in
`references/claude-driven.md`. A role name in prose does not select a model.

## Bound Context Before Tuning Effort

The outer host collects evidence for repository-heavy planning; the bounded
planner reasons over that packet with tools/subagents disabled. Implementation
jobs receive relevant paths and acceptance criteria, repair rounds receive only
failed checks/findings, and review receives original requirements plus the actual
change. Preserve business constraints while excluding unrelated files and history.

Reuse healthy sessions for repair. Allow fresh bounded sessions for stale context
or independent high-risk review. Compare total elapsed time, input/cache/output
usage and first-pass acceptance across comparable tasks before claiming a saving;
never derive subscription quota percentages from token counts.
