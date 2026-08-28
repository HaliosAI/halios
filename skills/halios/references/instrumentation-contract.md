# Instrumentation contract

Instrument the real application with standard OpenTelemetry. Reuse existing providers and context
propagation; a second global provider can lose spans or parents. Prefer ecosystem model/framework
instrumentation and add manual spans for missing application operations. Initialize instrumentation
before instrumented clients are created.

Halios normalizes standard GenAI and common framework attributes into stored span kind/input/output.
Those internal fields are not an additional vocabulary to emit. OTel `SpanKind` alone does not
identify a semantic operation.

## Evidence and topology

Preserve W3C parent context across model calls, tools, retrieval, and delegated agents. A typical
request has an agent/workflow root with those operations beneath it; only include operations the
application actually performs. Resource identity includes `service.name`, `service.version`, and
`deployment.environment.name`.

For new manual instrumentation:

| Operation | Attributes/evidence |
| --- | --- |
| Agent/workflow | `gen_ai.operation.name=invoke_agent` or `invoke_workflow`, `gen_ai.agent.name`, input/output messages |
| Model | Structured `gen_ai.input.messages` / `gen_ai.output.messages`, provider/model |
| Tool execution | `gen_ai.operation.name=execute_tool`, `gen_ai.tool.name`, `gen_ai.tool.call.id` if supplied, `gen_ai.tool.call.arguments` and `gen_ai.tool.call.result` |
| Retrieval | `gen_ai.operation.name=retrieval`, `gen_ai.retrieval.query.text`, `gen_ai.retrieval.documents` with IDs/content |
| Reranker | Query, candidate IDs, ordered output IDs/scores |
| Sub-agent | Stable agent identity, input/output, true parent context |

Use structured data or JSON strings for messages, arguments, and results/errors. Content needed by
the checks must be captured, not just span names. Do not export secrets, authorization headers,
embedding vectors, or hidden reasoning. Explain content-capture tradeoffs; production requires an
explicit redaction/allow-list policy and verification of the redacted evidence.

## Export and adapter

Let the OTel SDK/exporter resolve standard endpoint/header environment variables, including
signal-specific precedence. For example, unparameterized Python `OTLPSpanExporter()` uses that
resolution. Configure framework wrappers for Halios's OTLP/HTTP endpoint rather than a vendor cloud.

The `jsonl-v1` adapter attaches the incoming `traceparent` and calls the same instrumented
implementation; it does not initialize another tracing stack. Flush buffered spans before emitting
each JSON response (`trace.get_tracer_provider().force_flush()` in Python).

See the [deployment contract](deployment-instrumentation.md) for runtime endpoint, token, and
environment configuration. The optional Halios Python SDK serves explicit inline intervention,
not tracing; a gateway is needed only if provider proxying was requested.

## Verify what reached Halios

Use fresh adapter and real-runtime traces to establish both execution paths.
`halios trace verify <trace-id> --json` and stored trace content should show valid IDs/parents,
an ended root with messages, correct resource identity, and the required content for operations
that executed. Inspect the resulting check evidence too: successful ingest or visible spans alone
do not prove the judge received usable data.

If a tool span is absent, establish whether the application called the tool before diagnosing an
exporter failure. For unfamiliar instrumentation, inspect a representative trace, map its profile,
and report unsupported fields or missing normalization; do not rewrite working instrumentation
merely to match an example.

Specifications: [GenAI conventions](https://github.com/open-telemetry/semantic-conventions-genai)
and [OTLP exporter configuration](https://opentelemetry.io/docs/languages/sdk-configuration/otlp-exporter/).
