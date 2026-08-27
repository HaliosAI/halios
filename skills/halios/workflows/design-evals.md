# Design evals

Before authoring or reviewing checks, read the bundled
[`halios-check-config`](../references/halios-check-config.md) contract completely. It is part of
this skill, not an optional external dependency.

1. Inspect the system prompt, tool schemas, routes, policies, error handling, and user-facing claims.
2. Edit `.halios/eval.yml` first. Capture concrete goals, risks, stable check IDs, and a measurable
   reliability bar. Read and adapt [`../assets/eval.example.yml`](../assets/eval.example.yml) as a
   structural example; it is a pattern library, not a checklist of rules every agent should have.
   The CLI validates its packaged `halios_cli/schemas/eval.schema.json`.
3. Map each critical requirement to the simplest evaluator that can measure it correctly:
   - Use deterministic rules for mechanically observable facts such as presence, exact structured
     values, numeric bounds, tool arguments, JSON shape, or an intrinsically formatted identifier.
   - Do not use regex or string matching as a proxy for meaning. If a valid paraphrase could fail
     the rule, use a semantic evaluator instead.
   - Use a focused LLM judge when correctness depends on meaning, context, policy adherence, task
     completion, or acceptable paraphrasing. Keep one semantic criterion per rubric.
   - Add only checks that map to an actual goal, risk, policy, or tool contract. Do not copy every
     rule form from the example merely because it is available.
4. Mark safety, policy, and strict tool/schema checks as protected hard gates.
5. Edit `.halios/scenarios.yml` using the canonical field names. The CLI validates the packaged
   `halios_cli/schemas/scenarios.schema.json` JSON Schema before review and before every run. The
   schema is strict: use `title`, `goal`, `initial_message`, `agent_context`, `simulator_context`,
   `persona`, `constraints`, `arc_messages`, `risk_label`, and bounded `max_turns`.

   **Context Partitioning**:
   - `agent_context`: State intentionally available to the target application at startup (e.g., `channel`, `workspace_root`, `account_tier`). The author/coding agent **must inspect the target agent's code, entrypoint, or adapter** to determine which runtime attributes the agent expects. Halios stores this and delivers it to the agent adapter. If the agent needs no initial attributes, use `{}`.
   - `simulator_context`: User-private facts, ground-truth data, synthetic test credentials, customer preferences, and hidden test conditions. Halios stores this and keeps it strictly on the backend/simulator environment — it is **never** sent to the application. The simulator uses this private context to answer the agent's questions dynamically across turns. Never leave `simulator_context` empty for multi-turn conversational scenarios. Never commit real secrets.

   **Scenario Archetype Guidelines**:
   - **Conversational / Exploratory Agents (Chatbots, Customer Support, Sales, Intake)**:
     - `initial_message`: Keep opening sentences natural and minimal (e.g., `"Hi"`, `"Hello"`, or a single introductory inquiry). Do **not** preload customer names, emails, phone numbers, and multi-part questions into the opening sentence unless the scenario is explicitly an adversarial test, stress test, or specifically testing preloaded user dumps.
     - `arc_messages`: Write **behavioral guidelines and milestone intents** (e.g., *"Provide contact details from simulator_context when asked"*, *"Confirm email when prompted"*, *"Ask what alternatives exist"*), not rigid verbatim transcripts.
   - **Task-Oriented / Execution Agents (Coding Agents, CI/CD Runners, Workflow Automations)**:
     - The interaction is not exploratory. Preloading complete task specifications, issue descriptions, repository files, or input payloads directly into `initial_message` and `agent_context` is natural and standard practice.

   ```yaml
   version: 1
   scenarios:
     - id: customer-inquiry-multi-turn
       title: Customer material honesty inquiry
       goal: Verify assistant follows onboarding, states material boundaries, and offers valid alternatives
       initial_message: Hi
       agent_context:
         channel: web-chat
       simulator_context:
         customer_name: Jane Smith
         email: jane@example.com
         phone: "555-987-6543"
         desired_material: genuine leather
         willing_to_share_email: true
       persona: A quality-conscious shopper looking specifically for leather furniture
       constraints:
         - Must confirm customer details before starting session
         - Must state company does not carry genuine leather
         - Must only offer vinyl/polyurethane alternatives and exclude fabric/tweed
       arc_messages:
         - Provide contact details from simulator_context when asked
         - Confirm email when asked
         - Ask if genuine leather chairs are available
         - Ask what alternatives are available
         - Conclude and exit once alternatives are presented
       risk_label: boundary
       generation_mode: simulation-with-arc-hint
       max_turns: 6
   ```
6. Include happy paths, realistic ambiguity, tool failures, adversarial cases, and production
   regressions. Do not invent expected assistant wording when a behavioral rubric is the real need.
7. Run `halios eval review --json`. Treat every `schema_errors` and `quality_gaps` entry as blocking.
   Then perform the semantic review from `halios-check-config`: verify requirement polarity,
   outcome-vs-example generality, one criterion per rubric, and positive/negative scenario evidence.
   Show the user the resulting contract when it contains business judgments that require
   confirmation. A schema-valid suite is not automatically a meaningful suite.
8. Run `halios project configure --json`. It atomically creates one persistent server revision containing
   both checks/rules and scenarios, then rewrites both YAML files from the canonical response. Do
   not continue unless the command reports materialization verified with the expected check, rule,
   rubric, and scenario counts. Preserve the CLI-provided `links.scenarios` and `links.rules` for
   the final review handoff so the user can inspect the materialized suite in Halios.
9. If configure reports a revision conflict, note the recovery location, accept the automatic
   server-to-local refresh, compare the rejected proposal with the refreshed checkout, and reapply
   intended changes against the new revision. Never restore the rejected files wholesale.
