# Instrument staging and production

Read [the deployment contract](../references/deployment-instrumentation.md) and inspect the actual
service/worker entrypoints before changing dependencies or environment configuration.

1. Inventory the existing OTel provider, processors/exporters, propagators, framework/provider
   instrumentors, and content-redaction settings. Reuse the provider when one already exists.
2. Run `halios project instrumentation --environment staging` or `--environment production` to
   render non-secret configuration. The command does not modify a deployment.
3. Ask the user to run the same command with `--show-secret` and place the agent-scoped ingest token
   directly in the deployment secret manager. Never run the secret-revealing form yourself.
4. Set the immutable build SHA/image digest as `service.version` and a replica/task identifier as
   `service.instance.id`. Ensure every HTTP handler, queue worker, scheduler, and agent worker that
   can begin work uses the same service/environment convention.
5. Initialize instrumentation before constructing provider/framework clients. Preserve W3C
   `tracecontext,baggage` propagation across HTTP, queues, tools, and delegated services.
6. Capture the structured GenAI evidence required by the instrumentation contract. In production,
   use an explicit allow-list/redaction policy; do not export secrets, authorization headers,
   embedding vectors, hidden reasoning, or unrestricted customer content.
7. Send a fresh request through the real deployed entrypoint. Retrieve its trace, run
   `halios trace verify <trace-id> --json`, and confirm the service name, exact build version,
   environment, topology, content policy, and expected checks.

The jsonl adapter is not part of either deployment. It remains a local/CI simulation bridge used by
`halios eval run`; moving the adapter into a production service would test a second execution path
and produce misleading evidence.
