# Add a CI/CD reliability gate

Read [the deployment contract](../references/deployment-instrumentation.md) before editing a
workflow. Keep these two jobs conceptually separate:

- **Evaluation gate:** `halios eval run` launches the project-owned adapter and simulates users
  against the checked-out application code. This is the correct adapter use in CI.
- **Deployed staging smoke:** the repository's deploy workflow calls the actual staging service.
  Staging emits its own OTLP with `deployment.environment.name=staging`. Do not call the adapter and
  describe that as staging verification.

## GitHub Actions gate

Adapt [the bundled workflow](../assets/github-actions-eval-gate.yml) to the repository's existing
dependency setup and default branch. Preserve the command's exit status and upload both its log and
JSON report with `if: always()` so a blocked release remains diagnosable.

Store these values in GitHub Actions secrets, never in YAML or `.halios/`:

| Value | Scope | Purpose |
| --- | --- | --- |
| `HALIOS_API_KEY` | organization/control plane | Read the suite, create runs, and query reports |
| `HALIOS_OTLP_TOKEN` | one Halios agent | Export the simulated application's spans |
| `HALIOS_CI_PUBLISH_TOKEN` | trusted default-branch job only | Attest immutable published evidence |

Set `HALIOS_BASE_URL` as a repository/environment variable only when not using the hosted default.
Do not expose any of these values to fork-authored pull requests. Use an environment with approval
or a separately permissioned trusted workflow when outside contributors are in scope.

For example, with the repository's agreed trial count and reliability bar:

```bash
halios project check
halios eval review --json
halios eval run -k 5 --fail-below 0.95 --tag ci --tag "pr-${PR_NUMBER}" --json
```

For trusted default-branch CI, add `--publish --default-branch <branch>`. Publishing records which
immutable suite and commit the agent-level definition points to; it does not turn a failed run into
a pass. Never publish from pull-request code, an untrusted runner, or a dirty local checkout.

Keep deterministic tool/schema checks and protected safety checks as hard gates. Preserve the CLI's
exit code: `0` means terminal verified evidence passed and any nonzero value blocks the job. Use the
JSON report and stderr log—not the numeric code alone—to distinguish reliability, telemetry, setup,
auth, adapter, backend, publication, and timeout failures.

## Staging smoke after deploy

Add this to the repository's existing staging deployment job, after the service is healthy:

1. Deploy with the production tracing setup but set `deployment.environment.name=staging` and an
   immutable `service.version` equal to the deployed commit or image digest.
2. Send one deterministic request through the real staging API, queue consumer, or user-facing
   entrypoint. Have the smoke harness capture or return its W3C trace ID.
3. Run `halios trace show <trace-id> --include spans,checks --json` and
   `halios trace verify <trace-id> --json`.
4. Confirm the stored resource identity is the staging service/version/environment and the expected
   checks executed. An accepted OTLP request alone is not a smoke-test pass.

Use `halios trace failures --environment qa --json` to query staging evaluator failures because
Halios normalizes the `staging` deployment value into the QA/Staging evidence context.

## Explain a blocked release

First determine whether GitHub or Halios blocked it:

```bash
gh pr checks <pr-number>
gh run list --workflow "Halios evaluation gate" --branch <branch> --limit 10
gh run view <github-run-id> --log-failed
```

Read the uploaded `halios-eval.log` to recover the Halios run ID, then query the immutable report:

```bash
halios eval report <run-id> --failures --json
```

Report the exact category and evidence:

- setup/auth/suite error: project check, missing secret, stale revision, or unconfigured edits;
- adapter failure: trial outcome/error and the application stderr in the CI log;
- `telemetry_incomplete_count > 0`: expected spans did not arrive before the deadline;
- `check_execution_error_count > 0`: a frozen check errored rather than judged the behavior;
- `protected_failure = true`: a protected scenario/check failed;
- `pass_at_k < threshold` or `gate_passed = false`: reliability missed the configured bar;
- publish/attestation error: the trusted default-branch publication step was not authorized.

Inspect the failing scenario and trace and recommend a focused change rather than a blind rerun.
Apply a fix and rerun affected/protected cases only when authorized.
