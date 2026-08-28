from __future__ import annotations

import json
from pathlib import Path

import jsonschema
import yaml

from halios_cli.cli_eval import _review_suite


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


def test_paired_rag_examples_pass_schema_and_local_review():
    root = Path(__file__).resolve().parents[1]
    assets = root / "skills/halios/assets"
    documents = {}
    for kind in ("eval", "scenarios"):
        document = yaml.safe_load((assets / f"rag-{kind}.example.yml").read_text())
        schema = json.loads((root / f"halios_cli/schemas/{kind}.schema.json").read_text())
        jsonschema.validate(document, schema)
        documents[kind] = document
    report = _review_suite(documents["eval"], documents["scenarios"])
    assert report["status"] == "ready", report


def test_rag_example_keeps_references_out_of_runtime_inputs():
    root = Path(__file__).resolve().parents[1]
    document = yaml.safe_load((root / "skills/halios/assets/rag-scenarios.example.yml").read_text())
    for scenario in document["scenarios"]:
        assert scenario["max_turns"] == 1
        assert scenario["generation_mode"] == "simulation"
        assert "arc_messages" not in scenario
        assert scenario["agent_context"] == scenario["simulator_context"] == {}


def test_rag_examples_use_supported_independent_judges():
    root = Path(__file__).resolve().parents[1]
    document = yaml.safe_load((root / "skills/halios/assets/rag-eval.example.yml").read_text())
    checks = document["checks"]
    assert len({check["id"] for check in checks}) == len(checks)
    rules = [rule for check in checks for rule in check["rules"]]
    assert len({rule["id"] for rule in rules}) == len(rules)
    for check in checks:
        assert sum(rule["type"] in {"llm_judge", "classifier"} for rule in check["rules"]) <= 1
        # This example compares requests, tool evidence, and answers together.
        assert (check["target"], check["scope"]) == ("full_conversation", "entire")
