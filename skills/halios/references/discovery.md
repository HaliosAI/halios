# Discovery gaps and honest handoffs

Use this workflow for any unresolved evidence, access, policy decision, runtime capability,
verification, or requested action—not only RAG. Its output is useful work in the existing suite
plus explicit limitations, not another executable evaluation plan.

## Work with what is known

1. Inspect the relevant code, prompt, tools, examples, and existing `.halios/discovery.yml` if present.
   Revisit only gaps relevant to this request; do not restart completed work or assume old notes
   prove current state. When retrieval supplies application knowledge, also read [rag-evals.md](rag-evals.md).
2. Continue safe, supportable work within the user's scope. Ask one targeted question if an answer
   would unblock meaningful work: a representative example, source sample, business decision, or
   existing access method. Do not guess facts or request secrets in chat.
3. Separate missing information from unavailable capabilities or authorization. More documents do
   not enable unsupported adapter state restoration; a pending production check is not permission
   to deploy. Do not repeatedly retry an unchanged blocker or add new infrastructure to avoid asking.
4. During authorized setup/authoring/fix work, create or update the optional discovery file only
   when something remains unresolved. For read-only review/diagnosis, report proposed gap updates
   in the response without writing files. If writes are unavailable, report that limitation too.
5. When information arrives, verify it and add only supported checks/scenarios to `eval.yml` and
   `scenarios.yml`. Resolve the specific gap only after the affected work is actually complete,
   with a short verification/source locator. Partial information narrows a gap; it does not close
   it. User-deferred or out-of-scope work stays open with the reason in `next_step`.

Do not mark a gap resolved merely because the user replied, a command returned zero, or the
currently configured checks passed. Keep meaningful failure cases; do not remove or weaken an
existing required check to obtain a passing subset. If no safe, meaningful scenario can run,
report that instead of inventing one to satisfy setup's smoke step.

## Local file contract

`.halios/discovery.yml` is optional, Git-friendly, local authoring bookkeeping. It is not uploaded
by configure, part of the suite digest, a run snapshot, an answer-key store, or input to the
adapter/simulator/judge. It cannot execute `next_step` or authorize an action. Do not create
`rag-eval.yml`, disabled placeholder checks, or unsupported suite fields to represent gaps.

```yaml
version: 1
gaps:
  - id: knowledge-correctness
    status: open
    reason: Search accepts a query, but no source sample or representative question is available.
    affects:
      - Retrieval finds supporting evidence
      - Domain answers are correct
    next_step: Ask for 2-3 typical questions, a sample document, or existing data-access details.
  - id: refund-approval-policy
    status: open
    reason: Code supports refunds but the approval threshold is unspecified.
    affects:
      - High-value refund authorization scenarios
    next_step: Ask the owner which amounts require approval; do not guess a threshold.
```

Use stable, unique IDs; edit the existing entry rather than appending duplicates. Required fields
are `id`, `status` (`open` or `resolved`), `reason`, nonempty `affects`, and `next_step`. A resolved
entry also requires `resolution`, explaining the evidence and completed work (for example,
"Owner confirmed the threshold; policy check and boundary cases configured in suite revision 4").
Preserve other entries and useful resolved history. Keep notes short: at most 100 gaps / 64 KiB;
no YAML aliases. Never include credentials, raw customer content, sensitive source excerpts, or
private answer keys; use sanitized descriptions and non-secret locators instead.

## Review and handoff

`halios eval review --json` reports `discovery` separately from suite `status`, `schema_errors`,
`quality_gaps`, and `coverage_gaps`. Discovery status is `not-recorded`, `partial`, `no-open-gaps`,
or `invalid`. Missing notes or no open entries do not prove complete application coverage.
Malformed notes produce a visible warning; never overwrite them or interpret them as no gaps.
Older CLI builds may omit `discovery`; inspect the file yourself and state that limitation rather
than claiming the CLI validated it. Keep the normal supported-version installation workflow.

Discovery warnings do not change review exit codes or executable-suite gates. This allows a valid
subset to be used, not broken checks or missing required execution evidence to be ignored. Explain
which requested coverage is absent; a release gate remains a gate on its configured suite only.

Every handoff should concisely distinguish:

- **Completed:** concrete edits/configuration and verified evidence.
- **Not completed / not verified:** unresolved IDs, affected coverage/actions, and why.
- **Next input or action:** what would unblock the relevant work and who needs to provide it.

Include partial failures and skipped work even when another command succeeded. Read-only diagnoses
can say "recommended, not implemented." Revisit gaps at relevant setup/review/run handoffs, not
through unsolicited reminders or background polling. Preserve the existing bounded smoke, full-run,
diagnosis, and repair authorization rules.
