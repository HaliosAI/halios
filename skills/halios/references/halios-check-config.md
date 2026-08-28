# Halios check configuration and quality contract

Read this reference before creating or reviewing `.halios/eval.yml`. Its purpose is to make check
quality independent of whichever coding model happens to author the first draft.

## Configuration invariants

- Every check has one target and a compatible scope:
  - `user_message` or `assistant_message`: `all`, `last_n`, `first_n`, or `after_tool`.
  - `tool_usage`: `tool_name`, `input_arguments`, `output_values`, or `tool_call_context`.
  - `full_conversation`: `entire`.
- `after_tool` requires `scope_params.tool_name`.
- A check must contain at least one validation rule and at most one AI rule (`llm_judge` or
  `classifier`). Split independent semantic criteria into separate checks.
- `evaluation_config.task_name` is required. Use a stable, human-readable task name and a score
  threshold from 0 to 1.
- Choose the simplest evaluator that can measure the requirement correctly. Deterministic rules are
  for mechanically observable structure and exact facts; classifiers fit established classification
  problems; LLM judges fit meaning or outcome quality. If a valid paraphrase could fail a regex or
  string match, the requirement is semantic and needs a focused semantic evaluator instead.

## Deterministic rule polarity

- Violation detectors such as forbidden terms, PII patterns, competitor mentions, or prohibited
  claims use `pass_condition: not_match`.
- Required phrases or exact allowed values use `pass_condition: match`.
- `not_empty`, `not_null`, `exists`, numeric comparisons, and `one_of` encode their own direction;
  do not add `pass_condition` to them.
- `pass_logic: all` means every rule is a requirement. Use `any` only when the rules represent
  genuinely interchangeable acceptable outcomes.

## Semantic design rules

1. **Preserve requirement polarity.** Translate the product rule into the passing outcome before
   writing the grader. “Do not recommend competitor products” must grade refusal, redirection, or
   staying within the supported catalogue. It must never become “recommend these preferred
   competitor attributes.”
2. **Grade the invariant, not one example.** Product names, colors, cities, or example values from a
   scenario are evidence inputs, not the policy itself. A rubric should still work for an unseen
   competitor, product, wording, or turn order.
3. **One criterion per LLM rubric.** If a rubric asks about policy compliance, factual grounding,
   and tone, split it into three checks.
4. **Grade outcomes, not brittle paths.** Require the correct result, not an exact tool sequence or
   assistant sentence unless the sequence/text is itself a contractual requirement.
5. **Give judges an out (Tri-State N/A).** A condition-dependent rubric must explicitly state:
   "If [condition] does not occur in the conversation, return insufficient evidence."
   When returned, Halios marks the check execution as `status: not_applicable` (`score: null`,
   `passed: null`) and excludes it from the pass-rate denominator.
6. **Protect hard requirements.** Safety, privacy, policy boundaries, and strict tool schemas should
   be protected checks and should have adversarial scenarios.

## Scenario evidence & context partitioning

For every important invariant, include:

- a positive case where the behavior should occur;
- a counterexample where a plausible wrong behavior should fail;
- a boundary or ambiguous case;
- an adversarial case for protected policy;
- a multi-turn continuation when the behavior could degrade after the first response.

### Context partitioning & archetype rules:
- **`agent_context`**: State delivered directly to the target application/adapter at runtime. The scenario designer must inspect the target agent's codebase/adapter to determine what runtime parameters the agent expects (e.g. `channel`, `workspace_root`). Leave `{}` if none.
- **`simulator_context`**: User-private facts/preferences the simulator may disclose in conversation, not grader-only ground truth. Backend-only storage does not prevent the simulator from saying an answer key aloud. Never commit real credentials.
- **Conversational / Exploratory scenarios**: Use a natural opening appropriate to the task, such as a greeting or concise question. Let the agent elicit information when that interaction is under test. Write `arc_messages` as behavioral intent milestones, not rigid scripts. Fixed knowledge questions need no greeting/thank-you exchange: use `max_turns: 1` with no follow-up arc and a supported generation mode.
- **Task-Oriented / Execution scenarios**: Preloading complete task specifications, instructions, or repo files in `initial_message` and `agent_context` is natural and standard.
- Scenarios must not prescribe the desired assistant wording in `constraints`.

## Mandatory review questions

For each check, answer all of the following before configuration:

1. Which exact goal, risk, policy, tool contract, or user-facing claim does it cover?
2. What behavior makes it pass? State this without referring to the current scenario example.
3. What realistic wrong behavior makes it fail?
4. Is the rule direction correct for that pass/fail statement?
5. Would the check still work with different entities and wording?
6. Is there at least one scenario capable of passing it and one capable of failing it?
7. If it is an LLM judge, does it ask one question and define insufficient evidence?

Flag the suite as not ready when any answer is missing. Do not accept “the YAML validates” as a
quality argument.

For proposed work outside the executable suite that cannot yet be supported, use
[discovery notes](discovery.md) instead of placeholder checks or fabricated references. Do not
remove existing requirements to obtain a pass. For retrieval-backed requirements, read
[RAG authoring](rag-evals.md): citation syntax, factual support, task completion, and source/policy
correctness are distinct; each needs the right evidence. A discovery gap cannot excuse missing
required evidence in an executed check.

## Canonical competitor-policy example

Bad:

> Assistant must recommend solid Black or Brown alternatives and exclude Blackberry/Red for IKEA
> requests.

This overfits example attributes and still instructs the assistant to recommend competitor goods.

Good:

> When the user asks for a competitor product, pass only if the assistant does not recommend or
> compare specific competitor products and instead redirects to supported catalogue options or
> clearly states the boundary. Return insufficient evidence when no competitor request occurs.

Pair this rubric with a positive supported-product request, a direct competitor request, an
ambiguous brand mention, and a persistent multi-turn competitor request.
