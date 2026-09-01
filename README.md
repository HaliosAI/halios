# Halios

[![PyPI version](https://img.shields.io/pypi/v/haliosai-cli.svg)](https://pypi.org/project/haliosai-cli/)
[![License](https://img.shields.io/badge/license-Apache--2.0-blue.svg)](LICENSE)

# Halios

**Evals for any agent in minutes.**

Halios brings evals to your coding agent. Add the open-source Halios skill to **Codex**, **Claude Code**, **Cursor**, or another coding agent, then create scenarios, run fresh multi-turn trials, investigate failures, and verify improvements from your development workflow.

---

## Quickstart

### 1. Install the Halios skill

```bash
npx skills add HaliosAI/halios --skill halios
```

Works with coding agents and harnesses that support the open Agent Skills format.

### 2. Ask your coding agent

```text
Set up evals for this agent.
```

Your coding agent inspects the project and uses Halios to create an evaluation suite, connect your agent, and run an initial evaluation.

From there, keep working through prompts:

```text
Add adversarial scenarios around refund eligibility.
```

```text
Run the eval suite and investigate what failed.
```

```text
Add this production failure as a regression scenario.
```

```text
Add a GitHub Action that blocks regressions.
```

---

## How it works

### Build

Your coding agent creates scenarios and checks based on your agent's code, tools, policies, and expected behavior. The evaluation suite lives in `.halios/` alongside your code.

### Run

Halios runs fresh multi-turn interactions against your agent and evaluates what actually happened across the resulting traces.

### Investigate

Ask your coding agent what failed, why it failed, or which behavior changed. Halios provides the evaluation results and trace evidence it needs to investigate.

### Improve

Make a change and run the evaluation again. Use the same suite during development, in CI, and against production traces to catch regressions and expand coverage over time.

---

## What Halios is opinionated about

**Evals live with your code.**  
Scenarios and checks are stored in your repository and versioned with the application they evaluate.

**Fresh runs over static replays.**  
Halios exercises the agent again instead of treating an old transcript as the test.

**Evaluate behavior, not frameworks.**  
Use Halios with OpenAI Agents SDK, LangChain, LlamaIndex, PydanticAI, or your own agent runtime.

**Standard OpenTelemetry.**  
Your application emits standard OpenTelemetry GenAI traces rather than depending on a proprietary tracing SDK or proxy.

**One evaluation loop.**  
Use the same scenarios and checks while developing locally, gating changes in CI, and learning from production failures.

---

## Resources

- [Documentation](https://docs.halios.ai)
- [Halios](https://halios.ai)
- [Halios skill source](./skills/halios)
- [Python SDK](https://github.com/HaliosAI/haliosai-python-sdk)

---

## Development

```bash
git clone https://github.com/HaliosAI/halios.git
cd halios
python -m pip install -e '.[dev]'
python -m pytest -q
```

See [CONTRIBUTING.md](./CONTRIBUTING.md) for contribution guidelines.

---

## License

Apache 2.0 © Anomalytica Inc. 2026
