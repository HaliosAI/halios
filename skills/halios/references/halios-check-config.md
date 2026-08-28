# Check contract

Use [eval.example.yml](../assets/eval.example.yml) for complete authoring syntax and the packaged
eval schema for exact accepted fields. Checks group ordered rules; `pass_logic: all` requires
all rules, while `any` is for genuine alternatives. A check needs at least one rule and allows
at most one AI rule (`llm_judge` or `classifier`).

## Targets and evidence

| Target | Scopes |
| --- | --- |
| `user_message`, `assistant_message` | `all`, `last_n`, `first_n`, `after_tool` |
| `tool_usage` | `tool_name`, `input_arguments`, `output_values`, `tool_call_context` |
| `full_conversation` | `entire` |

Use `scope_params.n` for first/last counts and `scope_params.tool_name` for `after_tool` or tool
filtering (`tool_name` is also an authoring shorthand). A rule's `field` selects a nested tool
value, e.g. `filters.category`. Each check needs `evaluation_config.task_name` and a threshold.

Choose a scope containing the evidence the question requires. `assistant_message/all` cannot
establish a relationship to unseen user requests or sources. `after_tool` includes a post-tool
window, but verify its captured content; a configured scope is not proof that evidence arrived.

## Rules and polarity

Use deterministic rules for structure/exact facts, focused LLM judges for meaning, and classifiers
when an appropriate classification model exists. Valid paraphrases should not fail a semantic
requirement because of a regex.

- Violation detectors: `pass_condition: not_match`. This includes `json_schema`, which fires on
  invalid data.
- Required matches, e.g. `equals`: `pass_condition: match`.
- Presence and numeric comparison rules encode their own direction; no `pass_condition`.

Protect actual hard requirements such as safety, policy boundaries, and strict tool contracts.
Do not weaken those requirements to make a subset pass.

## Judge quality

A rubric should state one criterion, what passes/fails, and when evidence is insufficient or the
condition does not apply. Grade the actual requirement across plausible wording/entities, not one
example or an unnecessary tool sequence. For instance, a competitor boundary should assess refusal
or redirection to supported options, not prescribe a particular brand/color recommendation.

Use realistic correct and incorrect examples to check the grader, with boundary or multi-turn cases
where they matter. A source-dependent rubric needs source evidence; a plausible verdict without it
is not verification. Distinguish missing evidence from legitimate non-applicability, inspect actual
execution reasons and gate results, and report discrepancies. Scenario variety and schema validity
alone do not establish judge reliability.
