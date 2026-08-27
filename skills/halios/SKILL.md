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
compatibility: Requires shell access and Python 3.10+ to install and run haliosai-cli 2.0.7 or newer.
metadata:
  version: "2.0.7"
  min_halios_cli: "2.0.7"
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
| Smoke-test setup or run the requested evaluation | [workflows/run-evals.md](workflows/run-evals.md) |
| Inspect production evidence or create regressions | [workflows/inspect-failures.md](workflows/inspect-failures.md) |
| Add a merge/release gate | [workflows/ci.md](workflows/ci.md) |
| Instrument a staging/production deployment | [workflows/deploy-instrumentation.md](workflows/deploy-instrumentation.md) |
| Optimize after the suite is healthy | [workflows/optimize.md](workflows/optimize.md) |

Treat the user's verb as an authorization boundary:

- **Set up, connect, or configure**: connect and design the suite, run exactly one `-k 1` smoke
  scenario, summarize the evidence, and stop. Ask whether to run the full suite and how many trials
  per scenario to use. Do not inspect behavioral failures beyond the smoke summary or change the
  agent's prompt, tools, or code.
- **Run or evaluate**: execute one evaluation using the trial count the user supplied. If they did
  not supply one, ask before starting a full-suite run. Report failures without editing the agent.
- **Diagnose or inspect**: retrieve evidence, explain the cause, and recommend a focused change.
  Do not edit or rerun.
- **Fix or improve**: make one focused change and perform one targeted verification run, then
  summarize and stop. Repeat only when the user explicitly requests continued iteration or a
  bounded optimization workflow.

These boundaries keep setup predictable: a request to set up, run, or diagnose evals does not imply
permission to enter an open-ended repair loop.

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
- Treat Halios UI links as optional human-review handoffs. Use only the URLs returned in the CLI
  `links` object; never guess frontend routes or embed credentials. The repository and CLI remain
  sufficient for execution, while the UI helps the user inspect persistent scenarios, rubrics,
  runs, traces, and optimization evidence.

## Diagnose in code terms

Retrieve machine-readable evidence before proposing a fix:

```bash
halios eval report <run-id> --failures --json
halios scenario show <scenario-id> --json
halios trace show <trace-id> --include spans,checks --json
```

Map evidence to the prompt, tool schema, retrieval, policy, or control-flow code that produced it.
For a diagnosis request, explain the evidence and proposed change without editing. Only when the
user explicitly requests a fix, implement one focused change, rerun the failing scenario plus
protected scenarios once, and explain the behavioral change and reliability evidence. Add or
promote runtime guardrails only when the failure shows that inline intervention is warranted.

## Success criteria

Finish when the requested scope is verified, not when every possible reliability workflow has run:

- Setup finishes after evaluation AI and local files validate, one adapter-driven `-k 1` smoke
  scenario completes with verified telemetry/check execution, and the application's real runtime
  produces a fresh trace with standard W3C/OTel propagation. Summarize and stop before a full run.
- A requested evaluation finishes after its single requested run and trial count are reported.
- Diagnosis finishes with evidence and a recommendation; a requested fix finishes after one focused
  change and one targeted verification run.
- A requested merge/release gate must report its pass@k and protected-gate result.

If evaluation AI remains unavailable, report Halios's structured remediation and stop the
onboarding or eval workflow.

## Review handoff

At the end of a completed workflow, include a compact **Review in Halios** section using the most
relevant CLI-provided links. Prefer the exact run, trace, or optimization link over a collection
page, include no more than five links, and do not require the user to open them. For setup, include
the agent, scenarios, rules/rubrics, smoke run, and representative trace when returned. For a run or
diagnosis, include the exact run and trace evidence. Explain in one sentence what the user can
verify there.
