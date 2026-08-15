# Contributing

Thank you for improving the Halios CLI or Agent Skill.

1. Open an issue for substantial behavior or public-contract changes.
2. Create a focused branch and keep CLI and skill commands compatible.
3. Run `python -m pip install -e '.[dev]'` and `python -m pytest -q`.
4. Validate the skill from a clean directory with
   `npx skills add /path/to/halios --skill halios --agent codex --copy --yes`.
5. Open a pull request describing user-visible behavior and verification.

Never commit credentials, `.halios/` runtime state, customer data, or private Halios service
implementation details. Public API changes must remain backward compatible with supported Halios
Cloud releases.
