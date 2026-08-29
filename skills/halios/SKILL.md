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
