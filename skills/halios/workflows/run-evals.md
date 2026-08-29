# Run evals

Use `halios project check` to confirm a matching, nonempty configured suite and ready evaluation
AI, and `halios eval review --json` for local validation. Open discovery notes describe limitations;
they do not override executable-suite errors or run outcomes.

On a 402 Usage Limit Exceeded error or run marked `incomplete_quota` (e.g. `Halios usage allowance exhausted: Monthly managed ai tokens allowance is exhausted`),
recognize that the organization's monthly allowance has been reached. Stop automated retries immediately.
Inform the user with the direct billing URL to enable pay-as-you-go (`/settings/billing`) or switch to BYOK custom models.
Do not retry or treat quota exhaustion as an agent code bug.

For setup, choose one meaningful safe scenario:

```bash
halios eval run --scenario <id> -k 1 --json
```

For an explicitly requested full run, use `halios eval run -k <user-count> --json` and preserve
the user's count. `-k` repeats each scenario; it does not generate new questions. For fixed-input
suites, recommend broader evidence-backed question coverage at `-k 1` before more repetitions
when coverage is thin. Repetitions investigate execution variability, not systematic judge bias;
judge validation against trusted labels is a separate concern.

Report selected scenarios (distinct questions for fixed-input suites) × repetitions separately
from completed trials, so execution volume is not mistaken for coverage. Use fresh trajectories
after code/prompt changes; `--from-traces <ids>` is for requested audits/backfills only (at most
10,000 explicit IDs), not a new scenario run.

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
Choose the next step from the evidence: missing telemetry or grading evidence calls for
verification; a thin fixed-question suite calls for offering "expand the scenarios" using the
[authoring guidance](design-evals.md), then a proposed `-k 1` run. Suggest repetitions for
consistency questions and prompt/retrieval changes for observed failures, not as a generic menu.
