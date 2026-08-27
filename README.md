# Halios

[![PyPI version](https://img.shields.io/pypi/v/haliosai-cli.svg)](https://pypi.org/project/haliosai-cli/)
[![License](https://img.shields.io/badge/license-Apache--2.0-blue.svg)](LICENSE)

**Your pair programmer for AI agent evaluations.**

Halios helps you build reliable AI agents in minutes. Add the Halios skill to **Codex**, **Claude Code**, **Cursor**, or your favorite coding agent, and create eval suites, run multi-turn simulations, investigate failures, and gate pull requests directly from your repository. 

Halios provides the evaluation framework, developer tools, and hosted evaluation runtime underneath.

---

## Quickstart

### 1. Install the Agent Skill

Add the Halios skill to your coding agent environment:

```bash
npx skills add HaliosAI/halios --skill halios
```

*(Works with Codex, Claude Code, Cursor, GitHub Copilot, Gemini CLI, OpenCode, and any harness supporting the open Agent Skills format).*

### 2. Ask Your Coding Agent

Prompt your agent to set up evaluations for your project:

```text
"Set up evals for this agent: inspect the repository, create realistic test scenarios and checks, run one smoke test, and summarize before asking whether to run the full suite."
```

Your agent will inspect your application entrypoint, configure standard OpenTelemetry, draft
scenarios in `.halios/`, and run one smoke scenario. It stops with a verification summary before
asking whether to run the full suite and how many trials per scenario to use. The summary includes
direct Halios UI links for reviewing the materialized suite, smoke run, and trace evidence.

If the Halios CLI is missing, the coding agent will tell you before installing `haliosai-cli` as
user-level tooling that can be reused across projects. It is kept separate from your application's
runtime dependencies.

---

### Standalone CLI Installation

If you prefer to drive evaluations directly from the command line or CI:

```bash
# Recommended: Install with uv tool
uv tool install 'haliosai-cli>=2.0.6'

# Or install with pipx
pipx install 'haliosai-cli>=2.0.6'

# See available commands and usage
halios --help
```

The API and UI use the same origin by default. For a self-hosted deployment with separate origins,
set `HALIOS_UI_URL` so structured review links point to the web application without changing the
API endpoint used by `HALIOS_BASE_URL`.

---

## How It Works

1. **Inspect & Connect**: Your coding agent inspects your agent's tools, policies, and runtime, then configures standard OpenTelemetry export.
2. **Author Scenarios & Checks**: Test cases, rubrics, and failure criteria are stored directly in your repository (`.halios/scenarios.yml` and `.halios/eval.yml`). You own the evaluation suite.
3. **Simulate Multi-Turn Trajectories**: Halios runs fresh simulation passes against your agent across edge cases, tool dependencies, and user personas.
4. **Investigate & Fix Failures**: Pinpoint hallucinated parameters, broken tool handoffs, or policy violations from complete trace evidence.
5. **Gate Pull Requests**: Run protected checks in CI to block regressions before merging to production.
6. **Monitor Production**: Evaluate production traces using the same checks, and turn real-world failures into new regression test scenarios.

---

## Key Principles

- **You own the evaluation suite**: Scenarios and checks are clean YAML files stored in your Git repository.
- **Fresh simulations, not static replays**: Halios tests real agent execution across multiple turns, rather than replaying outdated completions.
- **Framework agnostic**: Works with any agent architecture—OpenAI Agents SDK, LangChain, LlamaIndex, PydanticAI, or custom workflows.
- **Stock OpenTelemetry**: Applications emit standard OpenTelemetry GenAI spans; no proprietary vendor lock-in in your production runtime.
- **Unified local, CI, and production loop**: The same checks run during local development, gate merge requests in CI, and monitor live production traces.

---

## Resources

- **Website**: [halios.ai](https://halios.ai)
- **Documentation**: [docs.halios.ai](https://docs.halios.ai)
- **Python SDK**: [github.com/HaliosAI/haliosai-python-sdk](https://github.com/HaliosAI/haliosai-python-sdk)
- **Public Skill Source**: [`skills/halios/`](skills/halios/)

---

## Development

```bash
# Clone and install locally in editable mode
git clone https://github.com/HaliosAI/halios.git
cd halios
python -m pip install -e '.[dev]'

# Run the test suite
python -m pytest -q
```

---

## License

[Apache 2.0](LICENSE) © Anomalytica Inc. 2026
