from __future__ import annotations

import json
from pathlib import Path

import jsonschema
import yaml


def test_single_turn_skill_example_matches_schema_without_filler():
    root = Path(__file__).resolve().parents[1]
    reference = root / "skills/halios/workflows/design-evals.md"
    example = reference.read_text(encoding="utf-8").split("```yaml\n", 1)[1].split("```", 1)[0]
    document = yaml.safe_load(example)
    schema = json.loads((root / "halios_cli/schemas/scenarios.schema.json").read_text())
    jsonschema.validate(document, schema)
    scenario = document["scenarios"][0]
    assert scenario["max_turns"] == 1
    assert "arc_messages" not in scenario
    assert scenario["agent_context"] == scenario["simulator_context"] == {}
