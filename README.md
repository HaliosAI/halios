# Halios CLI and Agent Skill

The `halios` command is the machine-facing client used by the Halios Agent Skill and CI. It owns
repository setup, evaluation-suite authoring, fresh scenario execution, evidence inspection, and
prompt-optimization handoffs. Applications export their runtime telemetry with stock
OpenTelemetry; the CLI is not an application tracing SDK.

```bash
uv tool install 'haliosai-cli>=2.0.0'
halios --version
```

Use `pipx install 'haliosai-cli>=2.0.0'` when `uv` is unavailable. Install the cross-harness skill
separately:

```bash
npx skills add HaliosAI/halios --skill halios
```

The stable project workflow is:

```bash
halios auth login
halios project init --agent support-assistant --command "python tests/halios_adapter.py"
halios eval review --json
halios project configure --json
halios project check --json
halios eval run -k 3 --json
```

Prompt optimization is driven by the coding agent and the normal immutable eval workflow:

```bash
halios optimize start --baseline-run <run-id> --prompt-file path/to/system-prompt.txt --json
# make one bounded prompt edit from the returned guidance, then run the unchanged suite
halios eval run -k 3 --json
halios optimize record <optimization-run-id> \
  --evaluation-run <candidate-eval-run-id> \
  --prompt-file path/to/system-prompt.txt \
  --json
```

Credentials are stored outside the repository. The repository contains only `.halios/config.toml`,
`.halios/eval.yml`, and `.halios/scenarios.yml`.

In non-interactive CI, use `HALIOS_API_KEY` for control-plane commands and the separate
agent-scoped `HALIOS_OTLP_TOKEN` for adapter trace export. Only trusted default-branch jobs should
receive `HALIOS_CI_PUBLISH_TOKEN`. The jsonl adapter is used by local/CI simulation only; deployed
staging and production applications export their own stock OpenTelemetry directly to Halios.

See the repository's
[`skills/halios`](https://github.com/HaliosAI/halios/tree/main/skills/halios) workflow for
coding-agent setup and
[`OTEL_SCHEMA.md`](https://github.com/HaliosAI/haliosai-python-sdk/blob/main/OTEL_SCHEMA.md)
for the telemetry accepted by Halios.

## Development

```bash
python -m pip install -e '.[dev]'
python -m pytest -q
```

See [CONTRIBUTING.md](CONTRIBUTING.md) for the contribution and release process.
