# Discovery notes

Keep useful work moving while making limitations visible. This applies to any application,
not only RAG. Explore accessible code, data, tests, and traces; ask the user when examples,
access, or a decision would materially help. Available evidence does not need a ritual question.

During authoring/fixes, record unresolved evidence, coverage, capability, or verification needs
in optional `.halios/discovery.yml`. For read-only work, describe proposed updates in the response.
Do not create gaps merely to fill a file, or infer complete coverage from its absence.

```yaml
version: 1
gaps:
  - id: knowledge-correctness
    status: open
    reason: No source sample or representative question is available.
    affects:
      - Source-backed knowledge cases
    next_step: Ask for typical questions, a sanitized sample, or existing access details.
  - id: refund-approval-policy
    status: open
    reason: The approval threshold is unspecified.
    affects:
      - High-value refund authorization
    next_step: Ask the owner which amounts require approval.
```

Use stable unique IDs and preserve unrelated entries. Required fields are shown above.
`status` is `open` or `resolved`; resolved entries also need `resolution` describing the
evidence and completed work. Partial answers narrow a gap; deferred work remains open.
Revisit relevant entries when evidence or user direction changes.

Keep notes concise and sanitized: no secrets, raw customer content, or answer keys. The schema
allows at most 100 gaps / 64 KiB, without YAML aliases.

These are local notes, not another suite, authorization, or input to the simulator/judge.
Configure does not upload them; they do not affect suite digests or run gates.
Review reports `not-recorded`, `partial`, `no-open-gaps`, or `invalid` separately from suite
validation. Invalid notes warrant a warning, not replacement; older CLIs may omit this field.
Even a passing suite can leave requested coverage or verification unresolved—say what and why.
