# Connect a repository

Aim for a reusable suite and a working connection to the actual application. Inspect its runtime,
entrypoints, existing instrumentation, and tests; choose an integration that fits. Setup is not a
request to deploy or redesign the agent.

## CLI and project

The Skill and CLI are separate installs. Check `halios --version` and require 2.0.7 or newer.
If installation is needed, explain that `haliosai-cli` will be a user-level tool and obtain the
required approval. Use an existing isolated installer:

```bash
uv tool install 'haliosai-cli>=2.0.7'
# For an existing uv installation:
uv tool upgrade haliosai-cli
# Or use an existing pipx:
pipx install --force 'haliosai-cli>=2.0.7'
```

If neither exists, choose a suitable official isolated installer for the platform. Keep the CLI
out of application dependencies. Verify the executable actually used; a user-requested branch
installation also needs source-revision verification, since package versions may be identical.
Do not fall back to an incompatible release or mutable default-branch source.

Use `halios auth status`, then `halios auth login` only if needed. For a new project:

```bash
halios project init --agent <display-name> --command '<adapter-command>' --json
```

A fresh agent starts at revision 0 with no checks/scenarios. Report its name, UUID, and returned
dashboard link. Link existing state with `--link-agent <uuid>` only when the user chooses it;
continue an already-linked project without creating another agent.

Halios Managed supplies evaluation AI by default. Provider setup and customer LLM keys are not
onboarding prerequisites; respect an organization's existing custom-model choice.

## Application and adapter

Use the [instrumentation contract](../references/instrumentation-contract.md) for OTel attributes
and verification. Instrument the real application, reusing its provider and propagation. The
`jsonl-v1` adapter calls that same implementation; it is a simulation bridge, not a second tracing
stack or a deployed service.

Adapt whichever example fits the state model:
[stateless](../assets/langgraph_stateless_adapter.py) or
[stateful](../assets/langgraph_stateful_adapter.py). The protocol is framework-independent:
one JSON request/response per line, incoming W3C `traceparent`, `message` for stateful turns,
`messages` for stateless history, and `trial_id` for session isolation. Flush telemetry before
emitting the response; keep diagnostics off stdout. Determine `agent_context` from the application.

`halios eval run` supplies the adapter's evaluation OTLP configuration. The real runtime needs its
own configuration from `halios project instrumentation`; see the
[deployment contract](../references/deployment-instrumentation.md) when wiring that path. Do not
introduce a gateway or proprietary SDK tracing for an application that can emit standard OTLP.

## Verification

[Design and configure the suite](design-evals.md), then use [run evals](run-evals.md) for one smoke
scenario. Verify fresh traces through both the adapter and the real runtime entrypoint, including
the correct service/environment and evidence required by the checks. A local runtime can establish
this path; do not claim staging/production verification without testing that environment.

Explore integration failures as needed. If access, meaningful cases, or required verification
cannot be obtained, preserve the useful setup and report the unresolved work.
