# Halios GenAI instrumentation contract

Use this contract when connecting any agent runtime, especially when it already has tracing, uses
tools or retrieval, delegates to sub-agents, or is not built with LangGraph. OpenTelemetry is the
transport; semantic attributes describe what each operation means. Never infer semantic operation
type from OTel `SpanKind` alone.

## Integration decision flow

1. Inventory the real runtime entrypoints, current `TracerProvider`, span processors/exporters,
   propagators, provider/framework instrumentors, and content-capture/privacy settings.
2. If tracing exists, keep its provider and propagation. Add a Halios OTLP exporter/processor to
   that provider. A second global provider commonly causes missing parents or silently dropped spans.
3. Prefer maintained ecosystem instrumentation for model/framework calls. Keep its native OTel
   GenAI profile; do not hand-wrap calls the instrumentor already covers.
4. Add manual spans only for missing application-level work: agent/workflow boundaries, tool
   execution, retrieval/reranking, and explicit sub-agent delegation. Use OTel GenAI structured
   attributes consistently for new manual spans.
5. Initialize instrumentation before importing/constructing instrumented provider or framework
   clients. The jsonl adapter attaches the incoming `traceparent` and calls the same agent code; it
   does not create another tracing stack.

The LangGraph adapter assets demonstrate the `jsonl-v1` execution bridge and state handling only.
They are not a universal instrumentation implementation.

## Trace topology

Represent one user request/turn as one W3C trace:

```text
agent or workflow root
├── model call
├── tool execution
├── retrieval
│   ├── embedding (optional)
│   └── reranker (optional)
└── delegated sub-agent
    ├── model call
    └── tool execution
```

Preserve real parent/child context across async tasks, queues, services, and sub-agents. Use links
only for causal work that cannot share a parent. Do not flatten a multi-agent run into unrelated
traces merely because different frameworks execute its nodes.

Every resource must identify `service.name`; add `service.version` and
`deployment.environment.name`. Halios classifies local/CI/test/staging versus production from
explicit context, not guesses based on service names.

## OTel GenAI semantic profile

The public instrumentation contract is standard OTLP plus the dedicated OpenTelemetry GenAI
semantic conventions. Halios normalizes these into internal `span.kind`, `span.input`, and
`span.output`; those internal fields are not another attribute vocabulary applications should emit.

Use structured `gen_ai.input.messages` / `gen_ai.output.messages` for model or agent messages. For a
tool execution span provide:

- `gen_ai.operation.name = execute_tool`
- `gen_ai.tool.name`
- `gen_ai.tool.call.id` when a provider supplies one
- `gen_ai.tool.call.arguments` as structured data or a JSON string
- `gen_ai.tool.call.result` as structured data or a JSON string

For retrieval provide `gen_ai.operation.name = retrieval`, `gen_ai.retrieval.query.text`, and
`gen_ai.retrieval.documents`. For an agent/workflow provide `gen_ai.operation.name = invoke_agent`
or `invoke_workflow`, plus stable `gen_ai.agent.name`/identity where available.

## Minimum evidence by operation

| Operation | Required for eval-ready traces | Useful additions |
| --- | --- | --- |
| Root agent/workflow | input/output messages, stable agent/workflow name | conversation ID, version, prompt ID |
| Model | input/output messages, provider/model | token counts, finish reason, tool definitions |
| Tool | semantic name, call ID if present, structured arguments and result/error | tool version, latency, retry count |
| Retrieval | query and returned document IDs/content allowed for evaluation | scores, collection/data-source ID, filters |
| Reranker | query, input document IDs, ordered output IDs/scores | reranker model/version |
| Sub-agent | stable agent name/ID, input/output, true parent context | handoff reason, agent version |

Do not export embedding vectors, secrets, credentials, authorization headers, or hidden reasoning.
Local/CI evaluation normally needs captured messages, tool bodies, and retrieval evidence. Production
capture requires an explicit redaction/allow-list policy; validate the redacted shape as well as the
unredacted development shape.

## Framework policy

Halios owns normalization, not framework-specific trace schemas. Maintain a small compatibility
matrix and focused recipes for commonly used instrumentors, but keep this contract as the acceptance
boundary. A framework recipe may explain installation order and how to enable content capture; it
must not redefine the canonical evidence requirements.

When an unknown instrumentor is encountered:

1. Export one representative trace locally.
2. Map its semantic attributes to this contract without replacing working instrumentation.
3. Add the smallest missing manual spans or a Halios ingest normalizer.
4. Add an ingest fixture/regression test for that convention before declaring support.

## Verification gate

Before simulations or evaluations, create two fresh traces: one through the jsonl adapter and one
through the application's real runtime. Verification passes only when:

- exactly one root exists and W3C IDs/parent links are valid;
- root input/output messages are captured;
- each executed tool has name, arguments, result/error, and a stable call ID when available;
- retrieval spans contain query plus returned-document evidence;
- sub-agent spans retain their identity and nest under the caller;
- model/tool/retrieval/agent events appear in execution order;
- service, environment, and Halios agent scope are correct; and
- expected checks execute and attach to the relevant evidence spans.

Do not treat a successful OTLP HTTP response, visible span name, `halios project check`, or a coding
agent's statement that a process "is running" as proof. Poll the run/trace status to a terminal state
and inspect the normalized trace structure returned by Halios.

## Primary specifications

- [OpenTelemetry GenAI semantic conventions](https://github.com/open-telemetry/semantic-conventions-genai)
- [OpenTelemetry OTLP exporter configuration](https://opentelemetry.io/docs/languages/sdk-configuration/otlp-exporter/)
