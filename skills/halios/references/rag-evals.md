# RAG evidence and evaluation

Use for retrieval-backed answers, including catalog search and document lookup.

Existing benchmarks, real failures, and bounded source samples are useful starting points.
Inspect the application's data-access path. A generic `query` tool does not establish what its
corpus contains; if no seeds or source access are available, ask for help and record the gap.
Reuse existing authorized readers; a new connector or evaluation framework is not a prerequisite.

Verify expected facts against source text, including units and policy versions. Questions are
seeds, not answer keys; synthetic fixtures test their own corpus. An empty search does not prove
absence from the corpus, and search-derived samples reflect the current retriever's blind spots.

Choose the relationships relevant to the application; retrieval and generation are evaluation
areas, not extra scores to combine with every check below:

| Concern | What to compare |
| --- | --- |
| Retrieval effectiveness | Known relevant evidence versus retrieved IDs/ranks; report label coverage before calling it recall. |
| Context relevance | User's information need versus returned content, not merely topical similarity or a nonempty result. |
| Answer faithfulness | Each material claim versus preceding source evidence, without outside knowledge filling gaps. |
| Answer relevance | Requested information versus the answer; a related topic or relevant refusal need not complete the task. |
| Answer correctness | Answer versus independently verified facts, applicable versions, and constraints, not only the retrieved subset. |
| Citation support | Each cited ID/text versus its associated claim; syntax alone is a separate structural check. |

These are diagnostic options, not a mandatory metric bundle. Nonempty queries and well-formatted
citations are not evidence of relevance or truth. A grounded answer may still be incomplete or use
an obsolete policy; refusal is not success on an answerable question.

For authoring, use the paired [RAG check example](../assets/rag-eval.example.yml) and
[scenario example](../assets/rag-scenarios.example.yml) instead of loading the generic commerce
example too. They show one fictional source snapshot, grader-only expectations, and contrasting
verdicts. Adapt relevant patterns; do not copy their facts or treat them as required coverage.
Query-intent checks compare user/history with tool arguments when query rewriting matters.

Inspect what evidence actually reaches the chosen judge scope. Account for repeated retrievals
and full-document fetches; later results cannot justify earlier claims. Missing required evidence
is unresolved verification even when the judge returns N/A. Check useful pass/fail counterexamples
before relying on a judge.

Use the [scenario/check contracts](../workflows/design-evals.md) for fixed questions and context
separation. Reference answers need a supported grader path, not simulator-visible storage.

A small fixed-input dataset can be ordinary scenarios: one stable ID and `initial_message` per
question, with `max_turns: 1`. Author distinct, evidence-backed questions from corpus facts,
benchmarks, or real failures; verify their supporting sources and grader-only expectations.
Paraphrases test wording sensitivity but do not replace coverage of different information needs.
Freeze cases before execution and reuse them for comparisons; do not generate a new question
inside each repetition. No special scenario type, generator service, or additional LLM key is
needed to author these cases in the coding-agent session. Add import/sampling glue only when data
access or scale warrants it; unavailable evidence remains a discovery gap, not invented truth.

Ranking metrics require labels and an appropriate runner; reranker claims need candidate/final
rankings. Record unsupported capabilities without pretending arbitrary tool-boundary resume,
complete recall, or new metrics are already available.

Further rationale: [Hamel's FAQ](https://hamel.dev/blog/posts/evals-faq/) and
[Jason Liu's RAG eval relationships](https://jxnl.co/writing/2025/05/19/there-are-only-6-rag-evals/).
