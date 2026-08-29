---
name: halios
description: >
  Set up AI-agent evaluations with Halios, author checks, expand scenarios or question datasets,
  run evaluations, inspect failures, add reliability gates, or optimize an agent prompt. Use for agent
  evaluation and reliability workflows, including requests that do not yet name Halios.
license: Apache-2.0
compatibility: Requires shell access and Python 3.10+ to install and run haliosai-cli 2.0.8 or newer.
metadata:
  version: "2.0.8"
  min_halios_cli: "2.0.8"
---

# Halios agent reliability

The repository holds evaluation intent; Halios runs tests and stores evidence. Use your judgment
to explore the application, adapt examples, and investigate unexpected results. These notes supply
Halios-specific contracts, not a script for every application. Adjust your approach as evidence
and user feedback arrive.

## Choose the relevant workflow

| Task | Reference |
| --- | --- |
| Set up a repository | [Connect](workflows/connect.md) |
| Author, expand scenarios, or review a suite | [Design evals](workflows/design-evals.md) |
| Run a smoke test or evaluation | [Run evals](workflows/run-evals.md) |
| Diagnose failures or create regressions | [Inspect failures](workflows/inspect-failures.md) |
| Add a CI gate | [CI](workflows/ci.md) |
| Instrument a deployment | [Deployment](workflows/deploy-instrumentation.md) |
| Optimize a prompt | [Optimization](workflows/optimize.md) |

Read supporting material when it becomes relevant, not the entire bundle upfront. CLI help,
examples, source code, and observed results are available when a contract needs clarification.

## Scope and judgment

- **Setup** includes instrumentation, adapter integration, suite authoring, and one `-k 1` smoke
  scenario. Explore and troubleshoot the integration within that scope. After the smoke, summarize
  and stop; agent-behavior repairs and a full-suite run need a separate request.
- **Run** the requested evaluation once with the user's trial count; ask for the count if absent.
  Report results without changing the agent.
- **Review/diagnose** is read-only. A **fix** permits a focused change and targeted verification;
  additional repair cycles or optimization need authorization.

## Stable product contract

- Keep skill installation separate from product setup. The skill is distributed by an Agent Skills
  installer such as `npx skills add`; when Halios work begins, install or upgrade the
  `haliosai-cli` Python tool through the connect workflow. Never invent a `halios skill install`
  command.
- Keep exactly `.halios/config.toml`, `.halios/eval.yml`, and `.halios/scenarios.yml` as Halios
  project state. Keep all three in Git. The YAML files are a revisioned checkout of the single
  server-owned suite; edits are inactive until `halios project configure` succeeds.
- Run `halios auth login` only when `halios auth status` shows credentials are missing. Login and
  repository initialization are separate operations; credentials live outside the repository.
- Call `halios project init --agent <new-display-name>` to create a fresh, empty agent. Reuse is
  allowed only through `--link-agent <uuid>` after the user explicitly chooses existing state.
  Immediately report the resulting Halios agent display name, UUID, and dashboard URL to the user,
  and repeat them in the final onboarding summary. Never leave the user to infer which server agent
  was created from `.halios/config.toml`.
- Instrument the real application codebase and runtime entrypoints (Python, TypeScript/Node.js, Go, etc.)
  with OpenTelemetry SDK and ecosystem instrumentations; initialize tracing before provider/framework
  clients are imported. Never instrument only the eval adapter. Production and staging users run against
  the real application code, not the eval adapter. Use the optional Halios Python SDK only for explicit
  inline intervention with `Client.evaluate_request(...)` and `Client.evaluate_response(...)`; it never
  configures tracing.
- Keep execution paths explicit. The adapter is used only by `halios eval run` to simulate a
  user against the real application code. The adapter must invoke the already-instrumented agent
  implementation from the codebase and only attach the incoming W3C `traceparent`. A deployed staging or production
  service emits OTLP directly from its real runtime and never runs through the adapter. Use
  [the deployment contract](references/deployment-instrumentation.md) for its values.
- Generate a project-owned `jsonl-v1` adapter that calls the same instrumented agent implementation,
  then smoke-test it. The adapter is only an eval/optimization execution bridge. Use `trial_id` for
  stateful agent sessions, the latest `message` for stateful agents, and full `messages` for stateless
  agents. Pass only scenario `agent_context` into the application. Keep `simulator_context` on the
  Halios backend so private user facts and hidden test state cannot leak into the system under test.
- Run application tools against project-owned test accounts, sandboxes, mocks, or fixtures. The
  simulated user supplies conversation turns; it never executes tools or fabricates tool results.
- Author reliability intent directly in `.halios/eval.yml`; there is no `eval plan` or `eval-spec`
  command. Author scenarios in `.halios/scenarios.yml`, run `halios eval review --json`, then run
  `halios project configure`. Confirm its materialization verification before evaluation. On a
  revision conflict Halios preserves the rejected checkout outside the repository and refreshes
  both YAML files from the server; reconcile deliberately and never auto-reapply stale edits.
- Use `halios eval run` for fresh simulation. Existing traces are an explicit audit/backfill mode,
  never a substitute for rerunning changed agent behavior.
- Prefer deterministic rules, then classifiers, and use LLM judges only for semantic judgments.
- Keep user approval at actual product boundaries. Never ask the user to paste an API key into chat.
  Halios Managed is ready by default, so onboarding must not pause for provider setup.
  `halios project check` must report `Evaluation AI: ready (Halios Managed)` or the explicitly
  selected custom model. BYOK is optional and configured directly by an organization owner.
- Handle HTTP 402 usage allowance limits explicitly: when CLI commands report
  `Halios usage allowance exhausted`, surface the structured remediation, billing URL
  (`/settings/billing`), and BYOK alternatives directly to the user. Never retry in a loop or treat
  quota exhaustion as an agent code error.

Exploration does not authorize production changes, external data export, or side-effecting tool
calls. Use project-owned test environments for such tools. Keep credentials out of chat and Git.

## Discovery and completion

Use accessible code, prompts, examples, tests, and data to understand what matters. Ask for input
when it would unblock useful work, not simply because the agent uses RAG. During authoring or fixes,
record unresolved evidence, policy, capability, or verification needs in
[`.halios/discovery.yml`](references/discovery.md), including gaps found after a run.
Continue supportable work; do not weaken requirements or invent answers to appear finished.

End with what changed, what was verified, what failed or remains unknown, and the next useful
input/action. For runs, distinguish execution/telemetry status, check results (including missing
evidence), and the reported gate outcome. A completed process is not a passing evaluation.

Include the agent identity for setup and a few relevant URLs from the CLI's `links` object.
Links supplement the explanation; they do not replace it.
