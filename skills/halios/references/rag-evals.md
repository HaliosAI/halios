# RAG evidence and evaluation

Use for retrieval-backed answers, including catalog search and document lookup.

Existing benchmarks, real failures, and bounded source samples are useful starting points.
Inspect the application's data-access path. A generic `query` tool does not establish what its
corpus contains; if no seeds or source access are available, ask for help and record the gap.
Reuse existing authorized readers; a new connector or evaluation framework is not a prerequisite.

Verify expected facts against source text, including units and policy versions. Questions are
seeds, not answer keys; synthetic fixtures test their own corpus. An empty search does not prove
absence from the corpus, and search-derived samples reflect the current retriever's blind spots.

Choose the relationships relevant to the application:

| Concern | Evidence needed |
| --- | --- |
| Query preserves the request | User/history and tool arguments |
| Retrieval is useful | Question/query and returned content |
| Answer is grounded; citations support claims | Answer and preceding source evidence |
| Answer completes the task | Request and answer |
| Domain/policy correctness | Applicable source-backed facts and versions |

These are diagnostic options, not a mandatory metric bundle. Nonempty queries and well-formatted
citations are not evidence of relevance or truth. A grounded answer may still be incomplete or use
an obsolete policy; refusal is not success on an answerable question.

Inspect what evidence actually reaches the chosen judge scope. Account for repeated retrievals
and full-document fetches; later results cannot justify earlier claims. Missing required evidence
is unresolved verification even when the judge returns N/A. Check useful pass/fail counterexamples
before relying on a judge.

Use the [scenario/check contracts](../workflows/design-evals.md) for fixed questions and context
separation. Reference answers need a supported grader path, not simulator-visible storage.
Ranking metrics require labels and an appropriate runner; reranker claims need candidate/final
rankings. Record unsupported capabilities without pretending arbitrary tool-boundary resume,
complete recall, or new metrics are already available.

Further rationale: [Hamel's FAQ](https://hamel.dev/blog/posts/evals-faq/) and
[Jason Liu's RAG eval relationships](https://jxnl.co/writing/2025/05/19/there-are-only-6-rag-evals/).
