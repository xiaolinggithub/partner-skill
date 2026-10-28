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
  `python3 "$PARTNER_DIR/scripts/partner-config.py" --host <driver> set --role <identity> --verified --verified-at <utc>`
  (goes through the same lock as every config write).
- Save a Partner Session Receipt containing only roles actually run and their
  actual verification state. Partial or format failures must not become
  `verified: true`; show connectivity and format results separately.

## Rules

- Never substitute a different model to make a row pass; a failing row
  fails visibly (no silent fallback — same principle as setup).
- Do not add project files, commits, or state: all three tasks are
  answer-only. The only writes are config `verified` flags and the
  `.partner/receipts/` entry.
- If the user has not run `搭子，配置` yet, say so and route them there
  first instead of improvising unconfigured identities.
