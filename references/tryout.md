# Partner Tryout (搭子，试跑)

A live check after configuration, not a benchmark of engineering quality or
quota savings. Run only the role the user changed/requested when appropriate;
a full first-run tryout covers all three. Use a bounded context and execute
independent micro-tasks concurrently; avoid full-repo discovery.

`partner-setup.py --smoke` checks Codex configuration through dry-run and does
not promote those roles to `verified`. Claude smoke obtains a minimal live
response; this alone does not prove the returned model or enforced effort.
For tryout, capture requested/observed model and report missing observations as
`unknown`. Intentional routing mappings are valid when declared; never infer
actual provider from the CLI or a role name in the prompt.

## The three micro-tasks

Fixed content, independent of the target repo's state. Run them through
each identity's configured backend (explicit namespaced/model-selected
subagent for `backend=claude`,
`delegate-codex.sh --host <driver> --role <identity>` for `backend=codex`):

1. **fast_worker — mechanical**: "Sort the keys of this JSON object
   alphabetically at every nesting level and return only the formatted
   result:
   `{"b":{"z":1,"a":{"c":3}},"a":[2,1],"c":"x"}`"
   Pass = returns exactly the correctly sorted, valid JSON, nothing else.
   Parse and check keys programmatically; Markdown fences are a format failure,
   distinct from connection failure. Do not change the standard between runs.
2. **deep_reasoner — reasoning**: "A CLI tool stores per-project config. A
   is one dotfile per project in the repo (committed); B is one central
   file in the user's home keyed by project path. Name the decisive
   tradeoff and pick one for a tool whose users frequently rename and move
   project directories. Conclusion first, then at most three sentences of
   reasoning."
   Pass = takes a clear position and the reasoning addresses the
   directory-move consequence (B's key breaks on move / A travels with the
   repo).
3. **arbiter — blind cross-check**: the same question as task 2, sent
   verbatim, with zero mention of deep_reasoner or its answer (the
   contamination rule in `references/claude-driven.md`'s Arbiter Protocol
   applies in full). Pass = an independent position; agreement or a
   documented divergence are both healthy outcomes — the point is proving
   the second, independent channel works.

## Fixed execution sequence

Use the helper instead of inventing shell commands or JSON validators. Keep one
driver writing a run manifest; do not run collect/finalize concurrently on it.

1. `python3 "$PARTNER_DIR/scripts/partner-tryout.py" start --host <driver> --repo "$REPO"`
   (optionally `--role <identity>`). This validates configuration before any
   dispatch, submits independent Codex jobs read-only, and returns `run` plus
   `native_agent` packets for Claude-backed roles. Each packet contains the
   configured model/effort and exact blind prompt. Submit those packets through
   the host's Claude subagent mechanism immediately, while Codex jobs run.
   Never replace a Claude packet with a Codex subagent. If the current host
   cannot launch the configured Claude channel, report the unsupported route.
2. After a native Agent returns, save its evidence in the run directory as JSON:
   `{"completed":true,"source":"actual Agent result ID or transcript path","agent_message":"verbatim final answer","observed_models":[],"execution":{"returncode":0,"elapsed_seconds":null}}`.
   `completed` means the Agent call ended; use returncode 0 only for a successful
   call, nonzero for a failure, and null when unknown. Copy measured elapsed time
   and observed model names only from actual tool/transcript evidence. Keep
   unavailable values null/empty; requested effort is not observed enforcement.
3. `python3 "$PARTNER_DIR/scripts/partner-tryout.py" collect <run.json> --wait-seconds 60 --agent-result deep_reasoner=<native.json>`.
   Repeat collect on the same run if jobs remain running. Omit agent-result when
   absent; multiple Claude roles accept repeated arguments. This command never
   resubmits, cancels, or relaxes acceptance. Failed/partial submissions retain
   IDs and submission output; inspect them before deliberately starting a new run.
4. Inspect both reasoning answers against the original criteria; record judgments
   as a JSON object keyed by role. Example entry:
   `"arbiter":{"accepted":true,"reason":"A travels on rename; independent answer agrees","routing_established":false,"verification_write":"pending"}`.
   Include fast_worker routing judgment too, but its acceptance is always computed
   from raw output. Routing is established only from observed/configured evidence
   or an explicitly declared mapping; do not infer it from a successful answer.
   Run `python3 "$PARTNER_DIR/scripts/partner-tryout.py" finalize <run.json> --judgments <judgments.json>`.
   It saves the fixed receipt and returns per-role results, old verification
   metadata, current verification, actual execution evidence and total run timing.
   Pass known `--claude-session`, `--new-claude-p` (from session-snapshot diff) and
   `--monitoring-level` evidence; absent session count remains unknown.
5. For eligible rows, execute only the emitted `verification_command` under normal
   permissions; it includes the role's actual `--scope`. Then finalize again to
   read back the timestamp and routing. On denial, set `verification_write` to
   `denied` and finalize without retrying the write through another path.
   Prior `verified=true` does not count as verification in this run. A changed
   route suppresses the update command; resolve that change before another run.

The helper stores run evidence under `.partner/receipts/tryout-*/`; the existing
delegate tool also stores its job evidence under `.partner/jobs/`. It never
changes source files or routing configuration. Report preparation, the execution
window and finalization separately; do not confuse a faster collector with a
measured end-to-end speed improvement.

## The tryout report (fixed format)

```text
[Partner tryout report]
identity       backend  model         effort  elapsed  result
fast_worker    codex    gpt-5.6-sol   medium  28s      PASS
deep_reasoner  claude   opus          high    1m42s    PASS
arbiter        codex    gpt-5.6-sol   xhigh   2m10s    PASS (agrees with deep_reasoner: B)
verdict: all identities live
```

- `elapsed` is each job's actual start-to-finish duration, not time from a shared
  launch marker to result collection. Never use an unrelated file mtime. If no
  valid timing evidence exists, report `unknown`.
- The table's model is the request. Append observed model and effort evidence
  separately; advisory effort is not an enforced parameter.
- `result` for the arbiter row states agreement or names the divergence in
  a few words. A divergence is not a failure.
- A failed row states the actual error (CLI missing, model rejected,
  timeout) and the fix pointer — rerun `搭子，配置` or install the missing
  CLI. `verdict` then lists which identities are live and which are not;
  never report `all identities live` on a partial pass.
- After a passing live row with its routing established, write `verified=true`
  + `verified_at` back to
  the config via
  the emitted scope-correct `verification_command` from finalize
  (goes through the same lock as every config write).
- Save a Partner Session Receipt containing only roles actually run and their
  actual verification state. Partial or format failures must not become
  `verified: true`; show connectivity and format results separately.

## Rules

- Never substitute a different model to make a row pass; a failing row
  fails visibly (no silent fallback — same principle as setup).
- Do not add source files or commits: all three tasks are answer-only. Writes
  are limited to `.partner/` execution/receipt evidence and permitted config
  verification flags; do not modify model, effort or backend to make a row pass.
- If the user has not run `搭子，配置` yet, say so and route them there
  first instead of improvising unconfigured identities.
