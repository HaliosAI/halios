"""Read optional local discovery notes; never use them as execution or grading input."""

from __future__ import annotations

import json
from functools import lru_cache
from importlib import resources
from pathlib import Path
from typing import Any

import yaml
from jsonschema import Draft202012Validator

MAX_DISCOVERY_BYTES = 65_536


class _DiscoveryLoader(yaml.SafeLoader):
    """Reject duplicate keys rather than silently losing an unresolved gap."""

    def construct_mapping(self, node: yaml.MappingNode, deep: bool = False) -> dict:
        mapping: dict = {}
        for key_node, value_node in node.value:
            key = self.construct_object(key_node, deep=deep)
            if not isinstance(key, str) or key in mapping:
                raise yaml.YAMLError("Discovery keys must be unique strings")
            mapping[key] = self.construct_object(value_node, deep=deep)
        return mapping


@lru_cache(maxsize=1)
def _validator() -> Draft202012Validator:
    resource = resources.files("halios_cli").joinpath("schemas/discovery.schema.json")
    schema = json.loads(resource.read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema)


def review_discovery(root: Path) -> dict[str, Any]:
    """Report recorded gaps without inferring completeness or changing suite readiness."""
    result: dict[str, Any] = {
        "path": ".halios/discovery.yml",
        "status": "not-recorded",
        "open_gaps": [],
        "resolved_count": 0,
        "errors": [],
    }
    path = root / result["path"]
    try:
        with path.open("rb") as source:
            raw = source.read(MAX_DISCOVERY_BYTES + 1)
        if len(raw) > MAX_DISCOVERY_BYTES:
            raise ValueError("Discovery file exceeds 64 KiB")
        text = raw.decode("utf-8")
        # WHY: Notes need no aliases; disallow cycles and expansion before validation.
        if any(isinstance(token, yaml.tokens.AliasToken) for token in yaml.scan(text)):
            raise ValueError("YAML aliases are not supported in discovery notes")
        payload = yaml.load(text, Loader=_DiscoveryLoader)
    except FileNotFoundError:
        return result
    except (OSError, UnicodeError, yaml.YAMLError, ValueError, RecursionError):
        # Do not echo parser excerpts, which could contain accidentally pasted secrets.
        result["status"] = "invalid"
        result["errors"] = [
            "Cannot read discovery.yml: use UTF-8 YAML under 64 KiB with unique keys, "
            "no aliases, and the discovery schema."
        ]
        return result

    for error in _validator().iter_errors(payload):
        location = ".".join(str(part) for part in error.absolute_path) or "root"
        result["errors"].append(f"discovery.yml: {location}: violates {error.validator}")
    if not result["errors"]:
        ids = [gap["id"] for gap in payload["gaps"]]
        if len(ids) != len(set(ids)):
            result["errors"].append("discovery.yml: gap ids must be unique")
    if result["errors"]:
        result["status"] = "invalid"
        return result

    result["open_gaps"] = [gap for gap in payload["gaps"] if gap["status"] == "open"]
    result["resolved_count"] = len(payload["gaps"]) - len(result["open_gaps"])
    result["status"] = "partial" if result["open_gaps"] else "no-open-gaps"
    return result
