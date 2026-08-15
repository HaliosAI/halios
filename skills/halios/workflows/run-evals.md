# Run and improve evals

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
3. Run the bank with `halios eval run -k 3`; use `-k 5 --fail-below 0.95` for merge/release evidence.
   Any missing/incomplete telemetry or malformed stored trace is a hard CLI failure, even when the
   adapter itself returned successfully.
4. Inspect failures with the three JSON commands in the root skill. Treat telemetry-incomplete
   attempts as failures; never remove them from the denominator.
5. Fix the agent code/prompt/tools, not the frozen run snapshot. Re-run the same scenario id so the
   new run records a new content hash and fresh trajectory.
6. Commit application changes together with the canonical YAML checkout written by the successful
   `halios project configure` response.

Use `halios eval run --from-traces <ids>` only for explicit audits or backfills. Validate all ids
before starting; the hard limit is 10,000. Never create a tag query or hidden selector.
