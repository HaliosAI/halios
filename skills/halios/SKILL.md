---
name: halios
description: >
  Make an AI agent reliable with Halios: connect a repository, configure stock OpenTelemetry,
  generate a jsonl-v1 test adapter, design eval goals/checks/scenarios, run fresh multi-turn
  simulations and CI gates, instrument staging and production, diagnose production failures or
  blocked releases, and graduate to prompt optimization.
  Use this skill whenever a user asks to "setup agent evaluation for this project using Halios",
  set up agent evaluation for a project, set up Halios,
  evaluate or test an agent, improve agent
  reliability, inspect a failed trace, turn failures into regression tests, add AI-agent CI gates,
  configure Halios guardrails, or optimize an agent prompt—even when they do not name Halios.
license: Apache-2.0
compatibility: Requires shell access and Python 3.10+ to install and run haliosai-cli 2.0 or newer.
metadata:
  version: "2.0.2"
  min_halios_cli: "2.0.2"
---

# Halios agent reliability

Treat the repository as the authoring surface and Halios as the execution and evidence service.
Scenarios describe what the agent must handle; every run generates fresh trajectories. Never
replay old assistant output as proof that changed code works.

## Route the request

Read only the workflow needed for the current task:

| Intent | Workflow |
| --- | --- |
| Connect/setup/instrument a repository | [workflows/connect.md](workflows/connect.md) |
| Design goals, risks, checks, and scenarios | [workflows/design-evals.md](workflows/design-evals.md) |
| Run evals, report reliability, fix failures | [workflows/run-evals.md](workflows/run-evals.md) |
| Inspect production evidence or create regressions | [workflows/inspect-failures.md](workflows/inspect-failures.md) |
| Add a merge/release gate | [workflows/ci.md](workflows/ci.md) |
| Instrument a staging/production deployment | [workflows/deploy-instrumentation.md](workflows/deploy-instrumentation.md) |
| Optimize after the suite is healthy | [workflows/optimize.md](workflows/optimize.md) |

For an end-to-end request, use them in that order, stopping only for credentials, a genuinely
ambiguous agent identity, or a product decision that changes the reliability contract.

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
- Instrument the real application entrypoint with stock OpenTelemetry and ecosystem instrumentation;
  initialize it before provider/framework clients are imported. Production users do not run through
  the eval adapter. Use the optional Halios Python SDK only for explicit inline intervention with
  `Client.evaluate_request(...)` and `Client.evaluate_response(...)`; it never configures tracing.
- Keep three execution paths explicit. The adapter is used only by `halios eval run` to simulate a
  user against the real application code. CI evaluation runs use that adapter. A deployed staging
  or production service emits OTLP directly from its real runtime and never runs through the
  adapter. Use [the deployment contract](references/deployment-instrumentation.md) for its values.
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

## Diagnose in code terms

Retrieve machine-readable evidence before proposing a fix:

```bash
halios eval report <run-id> --failures --json
halios scenario show <scenario-id> --json
halios trace show <trace-id> --include spans,checks --json
```

Map evidence to the prompt, tool schema, retrieval, policy, or control-flow code that produced it.
Implement a focused fix, rerun the failing scenario plus protected scenarios, then explain the
behavioral change and reliability evidence. Add or promote runtime guardrails only when the failure
shows that inline intervention is warranted.

## Success criteria

Finish only when the requested workflow is verified: evaluation AI is live-verified, local files
validate, the adapter completes a smoke trial, and both an adapter-driven eval request and a request
through the application's real runtime produce fresh Halios traces with standard W3C/OTel
propagation. Checks must execute and the requested pass@k or protected gate must be reported. If
evaluation AI remains unavailable, report Halios's structured remediation and stop the onboarding
or eval workflow.
