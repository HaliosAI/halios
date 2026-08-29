# Design evals

Discover the application's goals and failure modes from its code, prompts, tests, examples, and
available evidence. Reuse useful cases; explore further where they leave important uncertainty.
For retrieval-backed answers, use [RAG guidance](../references/rag-evals.md). Missing information
belongs in [discovery notes](../references/discovery.md), not invented domain expectations.

## Author the existing suite

- `.halios/eval.yml`: goals, risks, checks/rubrics, and the reliability bar.
- `.halios/scenarios.yml`: reusable starting conditions.
- `.halios/config.toml`: project identity and adapter configuration.

Read the [check contract](../references/halios-check-config.md) when designing checks.
Use the paired examples linked by the RAG guidance for retrieval-backed work; otherwise
[eval.example.yml](../assets/eval.example.yml) supplies general patterns. Neither is a checklist.
Choose cases and dimensions that expose plausible mistakes; there is no mandatory domain matrix
or prescribed number of scenarios. The current CLI does require an adversarial scenario.

Use the schema's risk labels: `benign`, `boundary`, `adversarial`. Supported generation modes are
`simulation` and `simulation-with-arc-hint`. A fixed question can be as small as:

```yaml
version: 1
scenarios:
  - id: missing-topic
    title: Request with no topic
    goal: Handle an underspecified document request
    initial_message: Can you help me find something in the documents?
    agent_context: {}
    simulator_context: {}
    risk_label: boundary
    generation_mode: simulation
    max_turns: 1
```

For single-turn cases, omit `arc_messages` entirely; the schema rejects an explicit empty array.
For multi-turn cases, use `arc_messages` for user intentions and `simulator_context` for relevant
user-private facts. Open naturally for the task; greetings and closing exchanges are not required.
Constraints shape the simulated user, while checks grade the assistant.

`agent_context` is delivered to the application and must fit its runtime contract. The simulator
can reveal `simulator_context` in dialogue, so neither field is grader-only answer storage.
A scenario goal describes intent; it is not an executable assertion. Put expected outcomes in
checks with an evidence path that can actually evaluate them.

## Expanding coverage

Treat "expand the scenarios", "add more test cases", or "build a question dataset" as authoring
requests, not requests for more repetitions. Inspect the existing suite and available evidence:
for fixed-question tasks, grow a dataset of distinct evidence-backed questions using ordinary
scenarios; for conversational tasks, add distinct situations, starting states, or user intentions.
Mixed suites may need both. Preserve useful cases and stable IDs, and extend applicable checks
with verified expectations so new cases are actually graded. Choose a bounded useful expansion;
ask for missing evidence, not for the user to understand `max_turns` or choose an internal format.
Explain added coverage and remaining gaps in plain language. Expansion alone does not authorize
publishing the suite or running it; those remain separate requested actions.

## Review and configure

`halios eval review --json` validates local files against the packaged
`halios_cli/schemas/{eval,scenarios}.schema.json`. Fix schema/quality errors without padding cases
with meaningless fields. Separately assess whether the checks can distinguish realistic correct
and incorrect behavior; `ready` is not proof of adequate coverage.

When configuration is in scope, `halios project configure --json` atomically publishes both YAML
files as one server revision and rewrites them from the canonical response. Require its
materialization verification. Draft-only work stops before this step.

On revision conflict, Halios preserves the rejected proposal and refreshes the checkout. Reconcile
intended changes with that current state. Local edits are inactive until configuration succeeds.
