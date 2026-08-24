# Inspect runtime failures and create regressions

## Answer “what is failing in production?”

Use read-only evidence queries before reading or changing application code:

```bash
halios trace list --environment production --limit 50 --json
halios trace failures --environment production --limit 100 --json
halios trace cluster --environment production --json
```

`trace list` proves whether Halios is receiving production-origin traffic. `trace failures` returns
failed/error evaluator check executions. `trace cluster` groups those failures by check and similar
first-user intent. These commands diagnose Halios agent evidence; they are not substitutes for
service logs, uptime monitoring, deployment health, or infrastructure metrics.

Interpret an empty failure result carefully:

- no production traces: inspect deployment OTLP configuration and runtime exporter errors;
- production traces but no check executions: confirm the expected checks are attached and runtime
  evaluation/finalization is enabled;
- check executions but no failures: Halios has no failing evaluator evidence in the queried window;
- unclassified or staging traces: fix `deployment.environment.name`; do not relabel them in analysis.

For each representative failure:

1. Fetch `halios trace show <trace-id> --include spans,checks --json`.
2. Run `halios trace verify <trace-id> --json` before trusting missing evidence as agent behavior.
   Preserve `links.trace` for the final human-review handoff.
3. Identify the user intent, deployed `service.version`, failure mechanism, check/rubric, and affected
   tool/retrieval/policy path—not merely the old assistant text.
4. Run `halios scenario generate --from-trace <trace-id>` to create a local Git draft.
5. Review its scenario id, goal, first turn, constraints, risk label, and arc hints; remove sensitive
   or production-specific values.
6. Run the new scenario against the current agent, then include it in the protected regression bank.

Use `halios eval report <run-id> --failures --json` when the failure belongs to a bounded run. For a
blocked GitHub release, follow [the CI diagnosis workflow](ci.md). Preserve run, scenario, trace,
check, commit, and GitHub run IDs in coding-agent handoffs so another agent can retrieve the same
evidence. Include the CLI-provided exact run and representative trace links in the diagnosis summary.
