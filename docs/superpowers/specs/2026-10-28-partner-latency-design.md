# Shorten Partner orchestration without weakening acceptance

Status: approved for direct implementation and autonomous verification by the user;
live improvement demonstrated in the final controlled tryout; see the validation record.

## Objective and baseline

Keep the existing role routing, independent reasoning/arbiter tasks, strict
output acceptance, permissions, and evidence requirements while shortening
end-to-end execution. The latest supplied tryout provides the comparison:

| Stage | Seconds |
| --- | ---: |
| Request to first job starting | 205.1 |
| First job starting to last subagent completing | 47.5 |
| Last subagent completing to final report | 293.9 |
| Total | 546.5 |

The largest measured opportunity is orchestration. Missing CLI arguments,
guessing result formats, ad-hoc validators, and receipt construction account
for avoidable model turns. Individual job latency is not the target of this
round. Keep configured models and efforts unchanged.

## Approaches

1. Correct only the prose and command examples: smallest diff, but leaves
   routing, parsing, waiting, and report assembly to the driver each time.
2. Recommended: a thin tryout entry point over the existing helpers, with a
   fixed dispatch packet and programmatic collection/validation/reporting.
   This removes repeated command discovery while retaining host-native Claude
   subagents and human/model judgment for the reasoning tasks.

No new service, dependency, generic workflow engine, model substitution,
answer caching, or relaxed JSON acceptance is proposed.

## Execution contract

- Resolve host, repository and configuration once. Fail before dispatch when
  required identities are missing. Produce explicit routing and scope evidence.
- Use the existing delegate script for Codex-backed roles; start independent
  jobs together. Return a bounded, ready-to-use packet for host-native Claude
  subagents. Do not replace them with another execution channel.
- Keep the three existing micro-task prompts and the analysis-only constraint.
  The two reasoning prompts remain identical and uncontaminated.
- Collect through the existing result JSON interface. Use execution timestamps
  and process outcomes from job evidence, not file mtimes or polling time.
  A wait timeout must preserve the running job and its ID, without resubmission.
- Validate the fast-worker answer in code: raw JSON only, exact values and
  array order, recursively sorted keys, and no duplicate keys or extra text.
  Fenced content may receive a diagnostic content result, never a strict pass.
- Leave reasoning acceptance and declared model-route intent to the driver.
  Report requested and observed models separately, including unknown evidence.
- Reuse the existing receipt generator and validator. Keep current-run results
  separate from pre-existing verification flags and timestamps.
- Generate explicit verification-update commands for the resolved scope;
  permission denial is reported as an incomplete write, never worked around.
  Do not silently mark an identity verified or overwrite routing configuration.
- Make the same stable result collection and timing conventions explicit in
  the normal collaboration adapter; do not remove planning or review gates.

## Verification and completion

1. Reproduce the supplied malformed-validator counterexample, then require
   rejection of wrong order, wrong nested values, changed array order, fences,
   duplicate keys, extra text, failed jobs and incomplete execution.
2. Exercise mixed backends, blind prompts, explicit scope, unknown model
   evidence, permission-denied writes and wait/resume behavior with fixtures.
3. Run the full existing suite and package checks. Preserve old CLI commands,
   configuration schema and receipt schema.
4. Replay the supplied completed jobs read-only to verify the new collector
   reaches the same honest verdict without exploratory commands.
5. Perform a fresh end-to-end Claude-driven tryout with the same configured
   identities and original tasks. Record preparation, execution, collection,
   permission waits, and reporting separately, including all failures.
6. Compare total time and time outside the execution window with the baseline.
   A useful target is under 60 seconds of orchestration excluding explicit user
   approval waits; it is a target, not a claim or a reason to skip acceptance.
   If the real run does not improve, investigate rather than call mock speed
   or fewer commands proof of the user's goal.

Implementation and testing stay in the existing isolated worktree. Updating
the shared installation and publishing additional changes remain separate
delivery actions. This design does not authorize bypassing permissions.
