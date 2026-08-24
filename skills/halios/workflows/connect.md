# Connect a repository

## Architecture: Main Application Code vs. Adapter Bridge

Halios connects to repositories using a clean two-tier separation:
1. **Main Application / Agent Code (Permanent Instrumentation)**:
   - Always instrument the **real application codebase and runtime entrypoints** (whether in Python, TypeScript/Node.js, Go, etc.).
   - Configure OpenTelemetry SDK, framework/provider instrumentors (e.g. model clients, tool handlers, retrieval pipelines), and tool execution spans inside the real application code.
   - This ensures telemetry is emitted consistently across all environments: local development, eval simulations, staging, and production.
2. **The Test Adapter is ONLY a Thin Simulation Bridge**:
   - The adapter exists solely for `halios eval run` simulations (`jsonl-v1` line-by-line JSON on stdin/stdout).
   - The adapter **must invoke the already-instrumented agent implementation from the main codebase**.
   - The adapter must **NEVER** contain its own separate tracer initialization, framework re-instrumentation, or duplicate tracing stack. Its only tasks are: extract/attach incoming W3C `traceparent`, invoke the agent implementation, call `force_flush()`, and write the assistant JSON response to `stdout`.

---

## Steps

1. Inspect the agent entrypoint, prompt/tool definitions, runtime, and current OpenTelemetry setup.
2. Run `halios --version` and require version 2.0.6 or newer. If the CLI is absent or older, install or
   replace it as an isolated user-level tool with `uv tool install 'haliosai-cli>=2.0.6'` when `uv`
   is available, otherwise `pipx install --force 'haliosai-cli>=2.0.6'`. If neither tool is
   present, explain that Python 3.10+ and an isolated Python application installer are required
   instead of modifying the application's virtual environment. Do not add the CLI to the
   application's runtime dependencies. If the package index cannot resolve version 2.0 or newer,
   stop and report that the required CLI release is not yet published; never continue with the
   incompatible public 1.x package or install mutable source from a default branch.
3. Run `halios auth status`. If credentials are absent, run `halios auth login`; do not write them to
   the project or ask the user to paste them into chat.
4. Choose a display name for a fresh agent. Run
   `halios project init --agent <new-name> --command '<adapter-command>' --json`. Never reuse an agent by
   name or slug. Use `--link-agent <uuid>` only when the user explicitly requests existing state.
5. Project initialization must report that a newly created agent has suite revision `0`, zero
   checks, and zero scenarios. Immediately tell the user the agent display name, UUID, and dashboard
   URL from the CLI `links` object; repeat all three in the final onboarding summary. Do not
   construct the URL from the agent id yourself.
   Project initialization uses Halios Managed AI by default and must not open provider setup or ask
   for a key. A previously selected custom model is used when configured by the organization.
6. Read [the instrumentation contract](../references/instrumentation-contract.md) and
   [the deployment contract](../references/deployment-instrumentation.md), then configure
   official OpenTelemetry SDK/exporter packages and provider/framework instrumentation in every real
   application entrypoint that serves users or background agent work. Initialize tracing before
   importing the provider/framework client. Do not count instrumentation added only to the eval
   adapter as production instrumentation.
   - Run `halios project instrumentation` for the non-secret deployment configuration.
   - Tell the user to run `halios project instrumentation --show-secret` themselves and copy the
     token directly into their deployment secret manager. Never invoke the secret-revealing form or
     expose its output in chat.
   - The endpoint is the same `<base-url>/v1/traces` URL used by the CLI. Set `service.name`,
     immutable `service.version`, and `deployment.environment.name` in the actual runtime.
   - `halios eval run` injects the eval endpoint/token into the adapter process automatically; that
     does not configure a deployed application.
   - **Environment Variable Resolution**: Never write hand-rolled `os.getenv()` string-parsing or splits.
     Pass unparameterized `OTLPSpanExporter()` or let the OpenTelemetry SDK / wrapper read the environment
     natively so standard OTel precedence (`OTEL_EXPORTER_OTLP_TRACES_ENDPOINT` > `OTEL_EXPORTER_OTLP_ENDPOINT`)
     and header parsing operate as specified.
   - **Framework Wrappers (Traceloop / OpenLLMetry / LiteLLM / LangChain)**: Halios backend ingest
     automatically normalizes standard OpenTelemetry GenAI attributes (`gen_ai.*`) and common wrapper
     spans (`traceloop.span.kind`, etc.). Configure wrappers to export via standard OTLP/HTTP to the
     provided endpoint/headers rather than defaulting to vendor cloud endpoints.
7. Follow the contract's existing-instrumentation decision flow. Do not install a second tracer
   provider when the application already has one; attach Halios's OTLP exporter/processor to the
   existing provider and preserve its context propagation. Prefer ecosystem instrumentation over
   handwritten provider spans, then fill only missing application operations (tools, retrieval,
   agent delegation) with manual spans.
8. Enable GenAI content capture for local/CI eval-ready telemetry. Explain the privacy tradeoff
   before enabling equivalent production capture. Provider instrumentation usually captures model
   calls, not application tool bodies. Missing tool arguments/results, retrieval query/documents, or
   sub-agent identity/topology is incomplete evaluation telemetry even when span names appear.
   OTel `SpanKind` is not the semantic operation type; use one of the contract's accepted semantic
   profiles.
9. Adapt one template from `../assets/` to the repository's real imports and state model. The adapter
   must call the same agent implementation as the real runtime and should only attach the incoming
   `traceparent`; do not build a second instrumentation stack in the adapter.
   - **Mandatory `force_flush()`**: In `jsonl-v1` adapters, spans are buffered asynchronously by
     `BatchSpanProcessor`. The adapter **must** invoke `trace.get_tracer_provider().force_flush()`
     at the end of each turn before printing the JSON response line to `stdout` so spans reach Halios
     before evaluation runs.
10. After the design workflow has configured the persistent server suite, run
   `halios project check`, then verify two paths separately:
   - Send one JSON request through the adapter and confirm its eval trace reaches Halios.
   - Send one request through the application's real local/staging entrypoint and confirm a trace
     with the correct non-evaluation `deployment.environment.name` reaches Halios.
   For each trace, run `halios trace verify <trace-id> --json` and inspect the returned structure:
   one root, valid parent links, ordered model/tool/retrieval/sub-agent children, captured required content,
   and correct environment/service identity. Treat either missing or structurally incomplete trace
   as incomplete instrumentation; do not proceed to simulations/evals.
   - **Distinguish Telemetry Gaps from Model Decisions**: If a tool span is absent, check whether the
     LLM actually emitted a structured `tool_calls` payload or responded conversationally in text.
     A model's decision not to invoke a tool is an agent steering/prompt issue, not an exporter bug.

Do not introduce the Halios gateway unless the user explicitly asks for provider proxying. Do not
use proprietary SDK tracing when the framework can emit OTLP.
