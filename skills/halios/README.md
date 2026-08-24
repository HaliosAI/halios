# Halios agent skill

The Halios skill follows the open Agent Skills format and is designed for Codex, Claude Code,
Cursor, GitHub Copilot, Gemini CLI, OpenCode, and other compatible coding harnesses.

## Install

Use the cross-harness Skills CLI. It discovers supported harnesses and lets the user choose the
installation target and scope:

```bash
npx skills add HaliosAI/halios --skill halios
```

To target one harness or install for the current user, use the Skills CLI flags:

```bash
npx skills add HaliosAI/halios --skill halios --agent codex
npx skills add HaliosAI/halios --skill halios --global
```

The source bundle is
[`skills/halios`](https://github.com/HaliosAI/halios/tree/main/skills/halios). A coding agent can
also be asked directly:

```text
Install the Halios Agent Skill from github.com/HaliosAI/halios and use it to set up evaluation for this project.
```

The Skills CLI installs this instruction bundle. When the skill runs, its connect workflow installs
or upgrades the separate `haliosai-cli` Python tool with `uv` or `pipx`. There is intentionally no
`halios skill install` command.

After installation, ask the harness to set up Halios, evaluate an agent, add reliability gates,
inspect a failed trace, configure guardrails, or optimize a prompt. Restart the harness only if it
does not discover newly installed skills automatically.

A setup request configures the suite and runs one smoke scenario, then stops with a verification
summary. The harness asks before running the full suite so the user can choose the number of trials
per scenario. Running, diagnosing, and fixing are separate scopes; none implicitly starts an
open-ended repair loop.

## Local development

Install directly from a checkout so the Skills CLI exercises the same discovery path as users:

```bash
npx skills add /absolute/path/to/halios --skill halios --agent codex
```

Use `--copy` when the environment cannot create symlinks. Manual copying or linking into a
harness-specific skill directory is a fallback, not the primary self-serve path.
