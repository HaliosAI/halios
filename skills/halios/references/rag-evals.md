# Evidence-aware RAG authoring

Read when code/tools show retrieval, document lookup, catalog search, or another external knowledge
source feeding an answer—even if the prompt is generic or never says RAG. RAG can be one capability
of a larger application; retain its other requirements and use [discovery.md](discovery.md) for gaps.

## Bootstrap without guessing the corpus

- Start with user examples, real failures/traces, or bounded accessible source samples. Inspect the
  existing data-access implementation; a tool accepting only `query` does not tell you what to ask.
- If a source supports listing/sampling, use a small authorized sample with source locators. Prefer
  existing application readers/extraction over new connectors. Do not scan/export the whole corpus.
- If only search is available, use known questions/topics as seeds. With no seeds or metadata, ask
  for representative questions, a source sample, or access details and record affected coverage.
  Random queries or asking the assistant what it knows do not establish corpus contents.
- Questions supplied by the user are search seeds, not answer keys. Generated use cases are drafts;
  confirm their domain assumptions. Synthetic fixture documents test the fixture, not the real corpus.
- Check expected facts against source text, preserving units, qualifiers, and effective versions.
  A missing search result does not prove the corpus has no answer. Search-only samples are biased
  toward what the current retriever finds; say so. Bound reads and obtain authorization for egress;
  never ask for credentials in chat or install Ragas/DeepEval as a prerequisite.

## Author a small, meaningful suite

Choose a few dimensions from observed requirements/evidence (such as customer tier, policy version,
or missing information), select useful valid combinations, then phrase natural questions. This is
an authoring technique, not an exhaustive matrix or new generation service. Include known failures
and plausible counterexamples; verify generated expectations separately from question diversity.

Use the existing deterministic and focused LLM-judge checks. Ask separately:

| Question | Evidence the grader needs |
| --- | --- |
| Did the search preserve the user's relevant constraints? | User/history plus tool arguments |
| Are the returned results useful for the information need? | Question/query plus returned content |
| Are answer claims supported? | Answer plus the evidence actually available at that point |
| Does the answer address the request? | User request plus answer |
| Is it correct for the applicable policy/domain? | Reliable expected facts/version rules where needed |

Use a supported context-bearing scope; assistant text alone cannot establish source support.
Account for follow-up document fetches and repeated tool calls: do not borrow evidence from a later
or unrelated call. Citation syntax is not citation validity, nonempty search is not good retrieval,
and a grounded answer can still repeat a superseded policy. Honest abstention can be good response
behavior while retrieval or task completion still fails; do not reward refusal on answerable cases.

Use deterministic checks for actual structure/exact facts, not proxies for meaning. Keep each
semantic rubric focused, with passing/failing examples and an insufficient-evidence outcome. Review
judge verdicts against human-labeled counterexamples before trusting them as release gates; a few
examples are a sanity check, not a calibrated accuracy claim. Missing required evidence is a gap,
not a reason to claim the check passed.

Reference-dependent tests need a supported grading path. The existing scenario `simulator_context`
is not grader-only storage: a simulated user can disclose its contents. Do not hide expected answers
there, in `agent_context`, or in discovery notes. Use a correctly scoped existing rubric only when
it can express the requirement; otherwise record the missing capability rather than fake support.

For a fixed knowledge question, use exact `initial_message`, `max_turns: 1`, and no follow-up arc;
keep an existing supported generation mode. Do not invent `single-turn` as a schema enum or require
a greeting/thank-you exchange. Use multi-turn simulation when clarification or recovery matters.
Do not claim general n−1/tool-boundary resume support. Fresh agent decisions and fixed tool inputs
test different things.

Standard retrieval metrics are useful when their inputs and runner exist; do not attach a mandatory
metric bundle or ask an LLM to calculate ranking arithmetic. A known source hit is not full recall;
unlabeled documents are not automatically irrelevant. Reranker-specific claims require observing
candidate and final rankings. Unsupported metrics/stages remain explicit discovery gaps, not a new
engine or instrumentation overhaul unless the user requests that work.

After an authorized run, separate label mistakes, grader mistakes, missing telemetry, and agent
failures. Propose focused regressions from observed failures within the user's scope, not automatic
reruns or prompt repairs. The output stays in the existing suite plus unresolved discovery notes.

## Basis

- [Hamel's evals FAQ](https://hamel.dev/blog/posts/evals-faq/): error analysis, source-backed
  questions, bounded dimensional generation, and validating judges against human judgments.
- [Jason Liu's six RAG evals](https://jxnl.co/writing/2025/05/19/there-are-only-6-rag-evals/):
  distinguish question/context/answer relationships. Use them as diagnostic questions, not six
  compulsory checks or a claim that they cover every operational failure.
