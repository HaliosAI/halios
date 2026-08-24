# Graduate to coding-agent optimization

Offer prompt optimization only after the scenario bank covers important goals and risks. The
coding agent proposes each bounded prompt edit; Halios freezes the baseline, supplies failure
guidance, records immutable eval evidence, enforces protected gates, and approves or rejects the
candidate. There is no SDK optimizer or separate optimization target server.

1. Locate the application's canonical system-prompt source. Do not create a second prompt copy just
   for Halios.
2. Run `halios eval review --json`, then establish the immutable baseline with
   `halios eval run -k <k> --json`. Keep its `run_id`; do not edit checks or scenarios afterward.
3. Start the control-plane run:

   ```bash
   halios optimize start \
     --baseline-run <run-id> \
     --prompt-file <canonical-prompt-file> \
     --max-iterations 5 \
     --json
   ```

   Preserve `links.optimization_run` from the result and include it in progress and final summaries.

4. Read `guidance.mutation_contract`. Diagnose the sampled failures against code and the current
   prompt. If the failure requires a tool, retrieval, schema, or control-flow change, cancel the
   optimization and fix code directly. Otherwise make exactly one focused prompt edit within the
   character budget. Do not modify tools, evals, or scenarios to make it pass.
5. Run the unchanged suite with the same repetition count: `halios eval run -k <k> --json`.
6. Record the candidate evidence:

   ```bash
   halios optimize record <optimization-run-id> \
     --evaluation-run <candidate-eval-run-id> \
     --prompt-file <canonical-prompt-file> \
     --json
   ```

   Exit code 2 means the backend rejected it. Restore the prior prompt with a focused edit, inspect
   `next_action`/negative memory, and try a materially different edit only while budget remains.
7. For an accepted iteration, retrieve the approved handoff into the canonical source:

   ```bash
   halios optimize apply <candidate-id> --output <canonical-prompt-file> --json
   ```

8. Run one final fresh unchanged-suite eval, then verify:

   ```bash
   halios optimize verify <optimization-run-id> \
     --evaluation-run <final-eval-run-id> \
     --json
   ```

Verification requires the same suite digest and trial count, complete telemetry, no check errors or
protected-check failures, a passing reliability gate, and no pass@k regression. Keep the prompt
change only after verification passes; otherwise restore the baseline prompt and report the reasons.
Include the CLI-provided optimization run and final evaluation run links in the verification summary.
