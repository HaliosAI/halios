# Halios deployment instrumentation contract

Use this reference for deployed staging and production runtimes and for non-interactive CI. The
canonical semantic shape remains [the GenAI instrumentation contract](instrumentation-contract.md).

## Keep the paths separate

| Path | Executes the agent | Telemetry owner | Environment identity |
| --- | --- | --- | --- |
| Local/ad hoc eval | `halios eval run` → jsonl adapter → real app code | CLI injects OTLP settings; app emits child spans | `ad_hoc` |
| CI eval | `halios eval run` → jsonl adapter → checked-out app code | CLI injects OTLP settings; app emits child spans | `ci` |
| Deployed staging | Real staging API/worker | Application OTel SDK/exporter | `staging` |
| Deployed production | Real production API/worker | Application OTel SDK/exporter | `production` |

The adapter only converts Halios simulation turns into calls to the application. It is never a
production/staging proxy, tracer bootstrap, user simulator, or replacement application.

## Credentials and exporter values

Use an agent-scoped OTLP ingest token for trace export. Do not put the organization API key in an
OTLP header. The API key is only for CLI control-plane/query commands.

```text
OTEL_EXPORTER_OTLP_PROTOCOL=http/protobuf
OTEL_EXPORTER_OTLP_TRACES_ENDPOINT=<halios-base-url>/v1/traces
OTEL_EXPORTER_OTLP_HEADERS=Authorization=Bearer%20<agent-scoped-otlp-token>
OTEL_SERVICE_NAME=<stable-application-service-name>
OTEL_RESOURCE_ATTRIBUTES=service.version=<immutable-release>,deployment.environment.name=<staging-or-production>,service.instance.id=<replica-or-task-id>
OTEL_PROPAGATORS=tracecontext,baggage
```

`service.version` must identify the deployed code—normally a full Git SHA or immutable image
digest—not `latest`. Keep `service.name` stable across releases. Make `service.instance.id` unique
per replica/task when it is available. Use exactly `staging` or `production` for the deployment
environment; staging appears in Halios's `qa` evidence context while production appears in
`production`.

`halios project instrumentation --environment <name>` prints the endpoint, protocol, service name,
and non-secret resource configuration. Its default output intentionally contains a token
placeholder. A human may use `--show-secret` to transfer the real token directly into a secret
manager.

For ephemeral CI evaluation runners, provide these process variables instead of writing a profile:

```text
HALIOS_API_KEY=<organization-control-plane-key>
HALIOS_OTLP_TOKEN=<agent-scoped-otlp-token>
HALIOS_BASE_URL=<optional-non-default-control-plane-url>
HALIOS_CI_PUBLISH_TOKEN=<trusted-default-branch-only-attestation>
```

## Required trace identity and evidence

Let the OTel SDK generate valid W3C trace/span IDs. For one agent request or conversational turn,
emit one ended root agent/workflow span and keep the real parent/child topology for model, tool,
retrieval, reranker, queue, and sub-agent work. Propagate `traceparent` and `tracestate` rather than
copying IDs manually.

At minimum send:

- resource `service.name`, immutable `service.version`, and `deployment.environment.name`;
- root `gen_ai.operation.name=invoke_agent` or `invoke_workflow`, stable agent/workflow identity,
  and input/output messages allowed by the content policy;
- model operation/provider/model plus structured input/output messages;
- tool name, call ID when supplied, structured arguments, result or error;
- retrieval query and returned-document IDs/content allowed by policy;
- explicit span error status and exception/error evidence when an operation fails.

Prefer stock provider/framework instrumentation, then add only missing application-level spans.
Never install a second global tracer provider. Do not rely on span names or OTel `SpanKind` as the
semantic operation type.

## Sampling, batching, and shutdown

Use parent-based sampling so a sampled root keeps its model/tool/retrieval children. Start staging
and low-volume launch production with complete traces; introduce deliberate sampling only after
measuring cost and ensuring important safety/error paths remain observable. Batch exporters in
long-running services, flush on graceful shutdown, and explicitly flush short-lived jobs/functions.
Exporter retry/drop logs belong in the application's operational logging.

## Privacy boundary

Local/CI evaluation usually requires message, tool, and retrieval content. Production capture is a
separate decision: define an allow-list/redaction policy, test it on representative traffic, and
record which checks lose evidence when content is omitted. Never send credentials, authorization
headers, hidden reasoning, embedding vectors, or unbounded raw records.

## Verification queries

After each deployment, obtain the W3C trace ID from the smoke request or application logs:

```bash
halios trace show <trace-id> --include spans,checks --json
halios trace verify <trace-id> --json
```

For staging use `halios trace failures --environment qa --json`; for production use
`halios trace failures --environment production --json`. Verification requires stored, ended,
structurally complete evidence and the expected checks—not merely exporter success.
