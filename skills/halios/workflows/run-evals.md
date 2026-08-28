# Run evals

Use `halios project check` to confirm a matching, nonempty configured suite and ready evaluation
AI, and `halios eval review --json` for local validation. Open discovery notes describe limitations;
they do not override executable-suite errors or run outcomes.

For setup, choose one meaningful safe scenario:

```bash
halios eval run --scenario <id> -k 1 --json
```

For an explicitly requested full run, use `halios eval run -k <user-count> --json`. Use fresh
trajectories after code/prompt changes; `--from-traces <ids>` is for requested audits/backfills
only (at most 10,000 explicit IDs).

Wait for the command's terminal result and retain its exit status and run ID. Retrieve an existing
report with `halios eval report <run-id> --failures --json` when needed; a run card or successful
`project check` does not establish completion.

Explain the actual result: execution and telemetry verification, check errors/failures/N/A, and
`gate_passed`, `pass_at_k`, and `protected_failure`. N/A can mean a condition did not occur or
required evidence was unavailable; distinguish these by the execution's reason. Neither is a
passing check. If aggregate and individual results disagree, report the discrepancy without
reinterpreting the gate or weakening checks.

After the setup smoke, stop with the handoff described in the root Skill. A failed smoke is still
a result to report; missing required telemetry or grading evidence leaves verification incomplete.
Ask before full-suite runs or behavioral repairs. If no meaningful smoke is possible, explain why.
