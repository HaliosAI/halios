# Releasing `haliosai-cli`

Tags named `vX.Y.Z` publish `haliosai-cli` to PyPI and version the bundled Halios Agent Skill.
Before tagging, update `halios_cli/_version.py` and the skill `metadata.version`, keep
`metadata.min_halios_cli` compatible, run the CLI test matrix, and verify clean installs and skill
discovery on macOS, Linux, and Windows.
