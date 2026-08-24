# Run evals within the requested scope

## Setup smoke

1. Run `halios project check`. It must report a matching, non-empty server suite revision and
   ready Evaluation AI before continuing. Halios Managed requires no provider setup. Then run
   `halios eval review`.
2. Smoke-test one scenario with `halios eval run --scenario <id> -k 1 --json` after adapter changes.
   Wait for that exact shell command to exit. Never replace its terminal result with
   `halios project check`, a task-status narration, or the appearance of a run card. Capture the
   printed run id and require a completed JSON report plus exit code `0`; exit code `2`, timeout,
   interruption, or an abandoned background shell means the evaluation did not succeed.
   Do not continue unless `telemetry_verification.verified` is true. The CLI must fetch each stored
   trace back from Halios and verify its organization-visible agent scope, evaluation membership,
   W3C trace/span IDs, parent topology, ended root span, structured input/output messages, captured
   content on instrumented child spans, and one error-free evaluator execution for every configured
   check. A run card appearing in the UI is not proof that evaluation completed.
3. For a setup, connect, or configure request, stop after this one smoke command. Report the agent
   identity, configured suite counts, smoke run id, trace id, telemetry verification, and check
   results. Do not run the full bank, investigate behavioral failures beyond this summary, or edit
   the agent prompt, tools, or code. Ask whether the user wants a full-suite evaluation and require
   them to choose the number of trials per scenario. If the smoke command fails, report the exact
   setup or telemetry blocker and stop rather than expanding into a repair loop.

## Full evaluation

Run a full evaluation only when the user explicitly requests it or accepts the post-smoke handoff.
Use the trial count they supplied and invoke `halios eval run -k <count>` exactly once. If no count
was supplied, ask before running. For an explicit merge/release gate, recommend
`-k 5 --fail-below 0.95`, but still confirm any cost- or policy-sensitive choice required by the
repository.

Any missing/incomplete telemetry or malformed stored trace is a hard CLI failure, even when the
adapter itself returned successfully. Retrieve failure evidence for the report, but do not edit the
agent unless the user separately asks to fix or improve it.

## Diagnose or fix

- For a diagnosis request, inspect failures with the three JSON commands in the root skill. Treat
  telemetry-incomplete attempts as failures and never remove them from the denominator. Explain the
  likely prompt, tool, retrieval, policy, telemetry, or control-flow cause without editing or
  rerunning.
- For an explicit fix or improve request, change the agent code/prompt/tools rather than the frozen
  run snapshot. Make one focused change, rerun the same scenario id plus protected scenarios once so
  the new run records a new content hash and fresh trajectory, then summarize and stop. Do not begin
  another repair cycle unless the user explicitly requests continued iteration.
- Keep application changes together with the canonical YAML checkout written by the successful
  `halios project configure` response when the user asks for a commit or pull request.

Use `halios eval run --from-traces <ids>` only for explicit audits or backfills. Validate all ids
before starting; the hard limit is 10,000. Never create a tag query or hidden selector.
