"""Canonical local scenario evaluation commands."""

from __future__ import annotations

import json
import os
import pathlib
import queue
import re
import secrets
import shlex
import subprocess
import tempfile
import threading
import time
import urllib.parse
from functools import lru_cache
from importlib import resources
from typing import Any

import httpx
import typer
from jsonschema import Draft202012Validator

from .cli_support import (
    ApiClient,
    emit_review_links,
    evaluation_suite_digest,
    git_provenance,
    halios_ui_links,
    load_project_config,
    load_yaml,
    resolve_credentials,
)
from .discovery import review_discovery

app = typer.Typer(help="Review, run, and report agent reliability.", no_args_is_help=True)
TRACE_LIMIT = 10_000
MAX_ADAPTER_RESPONSE_BYTES = 1_048_576
SCENARIO_FIELD_REPLACEMENTS = {
    "arc_hints": "arc_messages",
    "context": "agent_context",
    "initial_context": "agent_context",
    "intent": "goal",
    "message": "initial_message",
    "name": "title",
    "risk": "risk_label",
    "tags": "situation_tags",
    "user_messages": "arc_messages",
}


@lru_cache(maxsize=1)
def _scenarios_validator() -> Draft202012Validator:
    schema_resource = resources.files("halios_cli").joinpath("schemas/scenarios.schema.json")
    schema = json.loads(schema_resource.read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema)


@lru_cache(maxsize=1)
def _eval_validator() -> Draft202012Validator:
    schema_resource = resources.files("halios_cli").joinpath("schemas/eval.schema.json")
    schema = json.loads(schema_resource.read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema)


def _eval_schema_errors(eval_plan: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    for error in sorted(_eval_validator().iter_errors(eval_plan), key=lambda item: list(item.path)):
        path = ".".join(str(part) for part in error.absolute_path)
        label = f"eval.yml: {path}" if path else "eval.yml"
        if error.validator == "required":
            missing = str(error.message).split("'")[1]
            errors.append(f"{label}: {missing} is required")
        elif error.validator == "additionalProperties":
            errors.append(f"{label}: {error.message}")
        else:
            errors.append(f"{label}: {error.message}")
    checks = eval_plan.get("checks")
    if isinstance(checks, list):
        ids = [str(check.get("id") or "") for check in checks if isinstance(check, dict)]
        explicit_ids = [item for item in ids if item]
        if len(explicit_ids) != len(set(explicit_ids)):
            errors.append("eval.yml: check ids must be unique")
        for index, check in enumerate(checks):
            if not isinstance(check, dict) or not isinstance(check.get("rules"), list):
                continue
            rule_ids = [
                str(rule.get("id") or "")
                for rule in check["rules"]
                if isinstance(rule, dict) and rule.get("id")
            ]
            if len(rule_ids) != len(set(rule_ids)):
                check_id = str(check.get("id") or index)
                errors.append(f"eval.yml: check '{check_id}' rule ids must be unique")
    return errors


def _format_scenario_schema_error(error: Any, payload: dict[str, Any]) -> str | None:
    path = list(error.absolute_path)
    label = "scenarios.yml"
    field_path = path
    if len(path) >= 2 and path[0] == "scenarios" and isinstance(path[1], int):
        index = path[1]
        raw_scenarios = payload.get("scenarios")
        item = (
            raw_scenarios[index]
            if isinstance(raw_scenarios, list) and index < len(raw_scenarios)
            else None
        )
        scenario_id = str(item.get("id") or "").strip() if isinstance(item, dict) else ""
        label = f"Scenario '{scenario_id}'" if scenario_id else f"scenarios[{index}]"
        field_path = path[2:]
    field = ".".join(str(part) for part in field_path)
    prefix = f"{label}: {field}" if field else label

    if error.validator == "additionalProperties":
        return None
    if error.validator == "required":
        missing = str(error.message).split("'")[1]
        return f"{label}: {missing} is required"
    if error.validator == "anyOf":
        return f"{label}: initial_message or a non-empty arc_messages entry is required"
    if error.validator == "const" and field == "version":
        return "scenarios.yml: version must be 1"
    if error.validator == "enum":
        choices = ", ".join(str(choice) for choice in error.validator_value)
        return f"{prefix} must be one of: {choices}"
    if error.validator == "type":
        type_name = {
            "array": "a list",
            "boolean": "true or false",
            "integer": "an integer",
            "object": "an object",
            "string": "a string",
        }.get(str(error.validator_value), str(error.validator_value))
        return f"{prefix} must be {type_name}"
    if error.validator in {"minimum", "maximum"} and field == "max_turns":
        return f"{label}: max_turns must be an integer from 1 to 20"
    if error.validator == "minLength":
        return f"{prefix} must not be empty"
    if error.validator == "minItems":
        return f"{prefix} must contain at least one entry"
    if error.validator == "pattern":
        return f"{prefix} contains unsupported characters"
    return f"{prefix}: {error.message}"


def _explicit_trace_ids(value: str | None) -> list[str]:
    if not value:
        return []
    if value.startswith("@"):
        path = pathlib.Path(value[1:])
        if not path.exists():
            raise typer.BadParameter(f"Trace id file not found: {path}")
        values = [
            line.strip() for line in path.read_text(encoding="utf-8").splitlines() if line.strip()
        ]
    else:
        values = [item.strip() for item in value.split(",") if item.strip()]
    if len(values) > TRACE_LIMIT:
        raise typer.BadParameter(f"A run accepts at most {TRACE_LIMIT:,} explicit trace ids")
    malformed = [
        item
        for item in values
        if len(item) != 32 or any(c not in "0123456789abcdefABCDEF" for c in item)
    ]
    if malformed:
        raise typer.BadParameter(f"Malformed W3C trace id: {malformed[0]}")
    if len(set(item.lower() for item in values)) != len(values):
        raise typer.BadParameter("Explicit trace ids must be unique")
    return [item.lower() for item in values]


def _compare_reports(current: dict[str, Any], baseline: dict[str, Any], baseline_id: str) -> dict:
    return {
        "baseline_run_id": baseline_id,
        "pass_at_k_delta": float(current.get("pass_at_k") or 0)
        - float(baseline.get("pass_at_k") or 0),
        "gate_changed": bool(current.get("gate_passed")) != bool(baseline.get("gate_passed")),
        "telemetry_incomplete_delta": int(current.get("telemetry_incomplete_count") or 0)
        - int(baseline.get("telemetry_incomplete_count") or 0),
        "attempted_trial_count_delta": int(current.get("attempted_trial_count") or 0)
        - int(baseline.get("attempted_trial_count") or 0),
    }


def _contains_llm_judge(value: Any) -> bool:
    if isinstance(value, dict):
        if value.get("type") == "llm_judge" or value.get("rule_type") == "llm_judge":
            return True
        return any(_contains_llm_judge(item) for item in value.values())
    if isinstance(value, list):
        return any(_contains_llm_judge(item) for item in value)
    return False


def _initial_scenario_message(scenario: dict[str, Any]) -> dict[str, str]:
    initial = scenario.get("initial_message") or scenario.get("message")
    if isinstance(initial, str) and initial.strip():
        return {"role": "user", "content": initial.strip()}
    raw_turns = scenario.get("arc_messages") or scenario.get("user_messages") or []
    for raw in raw_turns:
        if isinstance(raw, str):
            message = {"role": "user", "content": raw.strip()}
        elif isinstance(raw, dict) and raw.get("role", "user") == "user":
            message = {"role": "user", "content": str(raw.get("content") or "").strip()}
        else:
            continue
        if message["content"]:
            return message
    raise typer.BadParameter(f"Scenario {scenario.get('id')} has no first user message")


def _scenario_schema_errors(
    scenarios_payload: dict[str, Any],
) -> tuple[list[dict[str, Any]], list[str]]:
    errors: list[str] = []
    schema = _scenarios_validator().schema
    root_fields = set(schema["properties"])
    for field in sorted(set(scenarios_payload) - root_fields):
        errors.append(f"scenarios.yml: unknown root field '{field}'")
    raw_scenarios = scenarios_payload.get("scenarios")
    scenario_fields = set(schema["$defs"]["scenario"]["properties"])
    if isinstance(raw_scenarios, list):
        for index, item in enumerate(raw_scenarios):
            if not isinstance(item, dict):
                continue
            scenario_id = str(item.get("id") or "").strip()
            label = f"Scenario '{scenario_id}'" if scenario_id else f"scenarios[{index}]"
            for field in sorted(set(item) - scenario_fields):
                replacement = SCENARIO_FIELD_REPLACEMENTS.get(field)
                if field == "protected":
                    errors.append(
                        f"{label}: unknown field 'protected'; use risk_label: adversarial and "
                        "expected_guardrail_trigger: true when applicable"
                    )
                elif replacement:
                    errors.append(f"{label}: unknown field '{field}'; use '{replacement}'")
                else:
                    errors.append(f"{label}: unknown field '{field}'")

    for error in sorted(
        _scenarios_validator().iter_errors(scenarios_payload),
        key=lambda item: (list(item.absolute_path), item.message),
    ):
        formatted = _format_scenario_schema_error(error, scenarios_payload)
        if formatted and formatted not in errors:
            errors.append(formatted)

    if not isinstance(raw_scenarios, list):
        return [], errors

    scenarios: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    for index, item in enumerate(raw_scenarios):
        location = f"scenarios[{index}]"
        if not isinstance(item, dict):
            errors.append(f"{location}: scenario must be an object")
            continue
        scenarios.append(item)
        scenario_id = str(item.get("id") or "").strip()
        label = f"Scenario '{scenario_id}'" if scenario_id else location
        if not scenario_id:
            errors.append(f"{location}: id is required")
        elif scenario_id in seen_ids:
            errors.append(f"{label}: id must be unique")
        else:
            seen_ids.add(scenario_id)

    return scenarios, errors


def _eval_quality_gaps(eval_plan: dict[str, Any], scenarios: list[dict[str, Any]]) -> list[str]:
    """Return high-confidence semantic smells that should block configuration."""
    gaps: list[str] = []
    for index, check in enumerate(eval_plan.get("checks") or []):
        if not isinstance(check, dict):
            continue
        check_id = str(check.get("id") or check.get("name") or f"checks[{index}]")
        check_text = " ".join(
            str(check.get(field) or "") for field in ("name", "description")
        ).lower()
        for rule in check.get("rules") or []:
            if not isinstance(rule, dict) or rule.get("type") != "llm_judge":
                continue
            config = rule.get("config") or {}
            if not isinstance(config, dict):
                continue
            prompt = str(config.get("prompt_template") or config.get("rubric") or "").strip()
            prompt_lower = prompt.lower()
            if len(prompt) < 80:
                gaps.append(
                    f"Check '{check_id}': LLM rubric is too vague; define one observable "
                    "passing outcome, one failing outcome, and insufficient evidence"
                )
            if not any(
                phrase in prompt_lower
                for phrase in (
                    "cannot determine",
                    "insufficient evidence",
                    "not applicable",
                    'score": null',
                    "unknown",
                )
            ):
                gaps.append(
                    f"Check '{check_id}': LLM rubric must define an insufficient-evidence "
                    "or not-applicable outcome"
                )
            numbered_criteria = re.findall(r"(?m)^\s*\d+[.)]\s+", prompt)
            if prompt.count("?") > 1 or len(numbered_criteria) > 1:
                gaps.append(
                    f"Check '{check_id}': LLM rubric appears to grade multiple criteria; "
                    "split it into one check per criterion"
                )
            competitor_text = f"{check_text} {prompt_lower}"
            requires_recommendation = re.search(
                r"\b(?:must|should|required to)\s+recommend\b", prompt_lower
            )
            preserves_boundary = re.search(
                r"\b(?:must not|should not|do not|does not|never)\s+recommend\b|"
                r"\b(?:refus|redirect|unsupported|supported catalog|supported catalogue)\w*",
                prompt_lower,
            )
            if (
                "competitor" in competitor_text
                and requires_recommendation
                and not preserves_boundary
            ):
                gaps.append(
                    f"Check '{check_id}': competitor-policy rubric appears inverted because it "
                    "requires a recommendation; grade refusal/redirection to supported options"
                )

    for scenario in scenarios:
        scenario_id = str(scenario.get("id") or "unnamed")
        constraints = " ".join(str(item) for item in scenario.get("constraints") or [])
        if re.search(
            r"\b(?:assistant|agent)\s+must\s+(?:say|reply|respond with|recommend)\b",
            constraints,
            re.IGNORECASE,
        ):
            gaps.append(
                f"Scenario '{scenario_id}': constraints prescribe an assistant answer; "
                "describe the user pressure and let checks grade the outcome"
            )
        simulator_context = scenario.get("simulator_context")
        arc_messages = scenario.get("arc_messages") or []
        max_turns = int(scenario.get("max_turns") or 1)
        if (
            (max_turns > 1 or len(arc_messages) > 0)
            and not simulator_context
            and scenario.get("generation_mode") != "single-turn"
        ):
            gaps.append(
                f"Scenario '{scenario_id}': simulator_context is empty for a multi-turn scenario; "
                "populate private user facts/preferences/state in simulator_context so the "
                "simulator can reveal them dynamically upon agent request"
            )
    return list(dict.fromkeys(gaps))


def _review_suite(eval_plan: dict[str, Any], scenarios_payload: dict[str, Any]) -> dict[str, Any]:
    scenarios, schema_errors = _scenario_schema_errors(scenarios_payload)
    eval_schema_errors = _eval_schema_errors(eval_plan)
    checks = eval_plan.get("checks") or []
    schema_errors = [*eval_schema_errors, *schema_errors]
    gaps = list(schema_errors)
    if not eval_plan.get("goals"):
        gaps.append("Define at least one agent goal")
    if not eval_plan.get("risks"):
        gaps.append("Define concrete failure risks")
    if not scenarios:
        gaps.append("Add at least one scenario")
    if not checks:
        gaps.append("Add deterministic or evaluator checks")
    if scenarios and not any(item.get("risk_label") == "adversarial" for item in scenarios):
        gaps.append("Add at least one scenario with risk_label: adversarial")
    quality_gaps = _eval_quality_gaps(eval_plan, scenarios)
    gaps.extend(quality_gaps)
    return {
        "status": "ready" if not gaps else "needs-work",
        "scenario_count": len(scenarios),
        "check_count": len(checks),
        "schema_errors": schema_errors,
        "quality_gaps": quality_gaps,
        "coverage_gaps": gaps,
    }


def _invoke_adapter(
    *,
    command: str,
    root: pathlib.Path,
    trial_id: str,
    traceparent: str,
    scenario: dict[str, Any],
    environment: dict[str, str],
    api: ApiClient,
    run_id: str,
    turn_timeout_seconds: float = 120,
) -> tuple[list[dict[str, str]], str, str | None, dict[str, Any]]:
    if not command:
        raise typer.BadParameter("No agent.command in .halios/config.toml")
    if turn_timeout_seconds <= 0:
        raise typer.BadParameter("Adapter turn timeout must be greater than zero")
    conversation: list[dict[str, str]] = []
    stderr_file = tempfile.TemporaryFile(mode="w+", encoding="utf-8")
    process = subprocess.Popen(
        shlex.split(command),
        cwd=root,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=stderr_file,
        text=True,
        bufsize=1,
        env=environment,
    )
    stdout_lines: queue.Queue[tuple[str, str]] = queue.Queue()

    def read_stdout() -> None:
        assert process.stdout is not None
        try:
            for line in process.stdout:
                stdout_lines.put(("line", line))
        except Exception as exc:  # pragma: no cover - OS stream failures are platform-specific.
            stdout_lines.put(("error", str(exc)))
        finally:
            stdout_lines.put(("eof", ""))

    threading.Thread(target=read_stdout, daemon=True).start()

    def stderr_excerpt() -> str:
        stderr_file.flush()
        stderr_file.seek(0)
        return stderr_file.read()[-4096:].strip()

    try:
        assert process.stdin is not None and process.stdout is not None
        user_message = _initial_scenario_message(scenario)
        max_turns = int(scenario.get("max_turns") or 6)
        outcome = "completed"
        stop_reason: str | None = None
        for _turn_index in range(max_turns):
            conversation.append(user_message)
            request = {
                "version": "1",
                "trial_id": trial_id,
                "message": user_message,
                "messages": conversation,
                "context": scenario.get("agent_context") or {},
                "traceparent": traceparent,
            }
            process.stdin.write(json.dumps(request, separators=(",", ":")) + "\n")
            process.stdin.flush()
            try:
                event, raw_response = stdout_lines.get(timeout=turn_timeout_seconds)
            except queue.Empty as exc:
                raise RuntimeError(
                    f"Adapter did not respond within {turn_timeout_seconds:g}s"
                ) from exc
            if event == "error":
                raise RuntimeError(f"Could not read adapter response: {raw_response}")
            if event == "eof":
                detail = stderr_excerpt()
                suffix = f": {detail}" if detail else ""
                raise RuntimeError(f"Adapter exited without a response{suffix}")
            if len(raw_response.encode("utf-8")) > MAX_ADAPTER_RESPONSE_BYTES:
                raise RuntimeError("jsonl-v1 response exceeds the 1 MiB limit")
            try:
                response = json.loads(raw_response)
            except json.JSONDecodeError as exc:
                raise RuntimeError("Adapter stdout must contain only jsonl-v1 responses") from exc
            message = response.get("message") if isinstance(response, dict) else None
            if not isinstance(message, dict) or message.get("role") != "assistant":
                raise RuntimeError("jsonl-v1 response must contain one assistant message")
            content = message.get("content")
            if not isinstance(content, str):
                raise RuntimeError("jsonl-v1 assistant message content must be a string")
            conversation.append({"role": "assistant", "content": content})
            next_turn = api.request(
                "POST",
                f"/api/v1/runs/evaluations/{run_id}/trials/{trial_id}/next-turn",
                json={"messages": conversation},
            )
            outcome = str(next_turn.get("outcome") or outcome)
            if next_turn.get("stop"):
                stop_reason = str(next_turn.get("stop_reason") or "") or None
                break
            next_message = next_turn.get("message")
            if not isinstance(next_message, dict) or next_message.get("role") != "user":
                raise RuntimeError("Simulated-user response must contain one user message")
            user_message = {
                "role": "user",
                "content": str(next_message.get("content") or ""),
            }
        return conversation, outcome, stop_reason, {}
    except Exception as exc:
        return (
            conversation,
            "errored",
            "adapter_error",
            {"code": "adapter_error", "message": str(exc)},
        )
    finally:
        if process.stdin:
            try:
                process.stdin.close()
            except BrokenPipeError:
                pass
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)
        if process.stdout:
            process.stdout.close()
        stderr_file.close()


def _otlp_root_payload(
    *,
    trace_id: str,
    span_id: str,
    started_ns: int,
    ended_ns: int,
    conversation: list[dict[str, str]],
    app_name: str,
    service_version: str | None,
    evaluation_context: str = "ad_hoc",
    outcome: str = "completed",
    error: dict[str, Any] | None = None,
) -> dict[str, Any]:
    def otel_messages(messages: list[dict[str, str]]) -> list[dict[str, Any]]:
        return [
            {
                "role": message.get("role") or "user",
                "parts": [{"type": "text", "content": message.get("content") or ""}],
            }
            for message in messages
        ]

    resource_attributes = [
        {"key": "service.name", "value": {"stringValue": app_name}},
        {
            "key": "deployment.environment.name",
            "value": {"stringValue": evaluation_context},
        },
    ]
    if service_version:
        resource_attributes.append(
            {"key": "service.version", "value": {"stringValue": service_version}}
        )
    return {
        "resourceSpans": [
            {
                "resource": {"attributes": resource_attributes},
                "scopeSpans": [
                    {
                        "scope": {"name": "halios.cli", "version": "1"},
                        "spans": [
                            {
                                "traceId": trace_id,
                                "spanId": span_id,
                                "name": "execute_agent",
                                "kind": 1,
                                "startTimeUnixNano": str(started_ns),
                                "endTimeUnixNano": str(ended_ns),
                                "attributes": [
                                    {
                                        "key": "gen_ai.operation.name",
                                        "value": {"stringValue": "invoke_agent"},
                                    },
                                    {
                                        "key": "gen_ai.input.messages",
                                        "value": {
                                            "stringValue": json.dumps(
                                                otel_messages(conversation[:-1])
                                            )
                                        },
                                    },
                                    {
                                        "key": "gen_ai.output.messages",
                                        "value": {
                                            "stringValue": json.dumps(
                                                otel_messages(conversation[-1:])
                                            )
                                        },
                                    },
                                ],
                                "status": {
                                    "code": 2 if outcome == "errored" else 1,
                                    **(
                                        {"message": str((error or {}).get("message") or "")}
                                        if outcome == "errored"
                                        else {}
                                    ),
                                },
                            }
                        ],
                    }
                ],
            }
        ]
    }


def _evaluation_telemetry_identity(*, ci: bool) -> tuple[str, str, str]:
    """Return check source, trace origin, and legacy context for a CLI eval run."""
    if ci:
        return "ci", "replay", "ci"
    return "sdk", "synthetic", "ad_hoc"


def _otlp_endpoint(base_url: str, *, trace_origin: str, evaluation_context: str) -> str:
    query = urllib.parse.urlencode(
        {"source": trace_origin, "evaluation_context": evaluation_context}
    )
    return f"{base_url}/v1/traces?{query}"


def _resource_attributes_with_environment(existing: str | None, environment: str) -> str:
    attributes = [
        item.strip()
        for item in str(existing or "").split(",")
        if item.strip() and not item.strip().startswith("deployment.environment.name=")
    ]
    attributes.append(f"deployment.environment.name={environment}")
    return ",".join(attributes)


def _verify_simulation_telemetry(
    api: ApiClient,
    *,
    report: dict[str, Any],
    agent_id: str,
    expected_roots: dict[str, str],
) -> dict[str, Any]:
    expected_count = len(expected_roots)
    if int(report.get("attempted_trial_count") or 0) != expected_count:
        raise typer.BadParameter(
            "Telemetry verification failed: attempted trial count does not match simulation"
        )
    if int(report.get("telemetry_incomplete_count") or 0):
        raise typer.BadParameter(
            "Telemetry verification failed: one or more simulation traces were not received "
            "before the telemetry deadline"
        )
    if int(report.get("completed_trial_count") or 0) != expected_count:
        raise typer.BadParameter(
            "Telemetry verification failed: not every simulation trace completed evaluation"
        )
    if int(report.get("evaluated_trial_count") or 0) != expected_count:
        raise typer.BadParameter(
            "Evaluation verification failed: not every simulation trace produced check executions"
        )

    expected_check_ids = {
        str(check.get("id"))
        for check in ((report.get("snapshot") or {}).get("checks") or [])
        if isinstance(check, dict) and check.get("id")
    }

    for trace_id, root_span_id in expected_roots.items():
        detail = api.request("GET", f"/api/v1/traces/{trace_id}")
        if str(detail.get("trace_id") or "") != trace_id:
            raise typer.BadParameter(
                f"Telemetry verification failed for {trace_id}: trace mismatch"
            )
        if str(detail.get("agent_id") or "") != agent_id:
            raise typer.BadParameter(
                f"Telemetry verification failed for {trace_id}: agent scope mismatch"
            )
        membership = detail.get("evaluation_membership") or {}
        if membership.get("run_id") != report.get("run_id"):
            raise typer.BadParameter(
                f"Telemetry verification failed for {trace_id}: evaluation membership is missing"
            )
        spans = detail.get("spans") or []
        if not isinstance(spans, list):
            raise typer.BadParameter(
                f"Telemetry verification failed for {trace_id}: spans must be a list"
            )
        span_by_id = {str(span.get("span_id")): span for span in spans if isinstance(span, dict)}
        root = span_by_id.get(root_span_id)
        if not root:
            raise typer.BadParameter(
                f"Telemetry verification failed for {trace_id}: expected root span was not stored"
            )
        if root.get("parent_span_id"):
            raise typer.BadParameter(
                f"Telemetry verification failed for {trace_id}: root span has a parent"
            )
        if not root.get("ended_at"):
            raise typer.BadParameter(
                f"Telemetry verification failed for {trace_id}: root span has no end time"
            )
        for field in ("input", "output"):
            content = root.get(field)
            if not isinstance(content, dict) or not isinstance(content.get("messages"), list):
                raise typer.BadParameter(
                    f"Telemetry verification failed for {trace_id}: root span {field} messages "
                    "are missing"
                )
        for span_id, span in span_by_id.items():
            if len(span_id) != 16 or any(
                character not in "0123456789abcdef" for character in span_id
            ):
                raise typer.BadParameter(
                    f"Telemetry verification failed for {trace_id}: malformed W3C span id"
                )
            if str(span.get("trace_id") or "") != trace_id:
                raise typer.BadParameter(
                    f"Telemetry verification failed for {trace_id}: a span belongs to another trace"
                )
            parent_span_id = str(span.get("parent_span_id") or "")
            if parent_span_id and parent_span_id not in span_by_id:
                raise typer.BadParameter(
                    f"Telemetry verification failed for {trace_id}: span {span_id} has an "
                    "unknown parent"
                )
        child_spans = [span for span_id, span in span_by_id.items() if span_id != root_span_id]
        incomplete_tool_spans = []
        for span in child_spans:
            attributes = span.get("attributes") if isinstance(span.get("attributes"), dict) else {}
            span_name = str(span.get("name") or "").lower()
            is_tool_span = (
                str(span.get("kind") or "").lower() == "tool"
                or span_name.startswith(("tool.", "execute_tool"))
                or bool(attributes.get("tool.name") or attributes.get("gen_ai.tool.name"))
                or attributes.get("gen_ai.operation.name") == "execute_tool"
            )
            if is_tool_span and (span.get("input") is None or span.get("output") is None):
                incomplete_tool_spans.append(str(span.get("span_id") or "unknown"))
        if incomplete_tool_spans:
            raise typer.BadParameter(
                f"Telemetry verification failed for {trace_id}: "
                f"{len(incomplete_tool_spans)} tool spans are missing structured "
                "arguments or results"
            )
        has_child_content = any(span.get("input") or span.get("output") for span in child_spans)
        if child_spans and not has_child_content:
            raise typer.BadParameter(
                f"Telemetry verification failed for {trace_id}: instrumented child spans have "
                "no captured input or output"
            )

        execution_page = api.request(
            "GET", f"/api/v1/traces/{trace_id}/checks", params={"mode": "evaluator", "limit": 100}
        )
        executions = execution_page.get("data") or []
        observed_check_ids = {
            str(execution.get("check_id"))
            for execution in executions
            if isinstance(execution, dict) and execution.get("check_id")
        }
        missing_check_ids = expected_check_ids - observed_check_ids
        if missing_check_ids:
            raise typer.BadParameter(
                f"Evaluation verification failed for {trace_id}: "
                f"{len(missing_check_ids)} configured checks produced no execution"
            )
        execution_errors = [
            execution
            for execution in executions
            if isinstance(execution, dict)
            and (execution.get("error") or execution.get("status") == "error")
        ]
        if execution_errors:
            raise typer.BadParameter(
                f"Evaluation verification failed for {trace_id}: "
                f"{len(execution_errors)} check executions contain errors"
            )
    return {"verified": True, "trace_count": expected_count}


def _raise_for_failed_run(report: dict[str, Any], run_id: str) -> None:
    trials = [trial for trial in (report.get("trials") or []) if isinstance(trial, dict)]
    quota_trials = [
        trial
        for trial in trials
        if trial.get("completeness_status") == "incomplete_quota"
        or trial.get("outcome") == "ineligible"
        or "managed ai allowance" in str(trial.get("error") or "").lower()
        or "monthly allowance" in str(trial.get("error") or "").lower()
        or "quota" in str(trial.get("error") or "").lower()
    ]
    if quota_trials or report.get("completeness_status") == "incomplete_quota":
        raise typer.BadParameter(
            f"Evaluation run {run_id} marked incomplete_quota: monthly usage allowance reached.\n"
            f"Managed AI or check evaluation quota is exhausted. Stop automated retries.\n"
            f"Enable pay-as-you-go: https://app.halios.ai/settings/billing or configure BYOK."
        )

    check_execution_error_count = int(report.get("check_execution_error_count") or 0)
    failed_trials = [
        trial
        for trial in trials
        if (
            trial.get("error")
            or trial.get("state") == "evaluation_failed"
            or trial.get("outcome") in {"error", "errored", "timed_out", "blocked"}
        )
    ]
    if report.get("status") != "failed" and not failed_trials and check_execution_error_count == 0:
        return

    details: list[str] = []
    if check_execution_error_count:
        details.append(f"{check_execution_error_count} check execution(s) errored")
    for trial in failed_trials[:3]:
        error = trial.get("error") if isinstance(trial.get("error"), dict) else {}
        message = str(error.get("message") or trial.get("outcome") or trial.get("state"))
        details.append(f"{trial.get('scenario_id') or trial.get('id')}: {message}")
    suffix = f" ({'; '.join(details)})" if details else ""
    run_url = str((report.get("links") or {}).get("evaluation_run") or "")
    review = f" Review in Halios: {run_url}." if run_url else ""
    raise typer.BadParameter(
        f"Evaluation run {run_id} failed{suffix}. "
        f"Inspect `halios eval report {run_id} --failures --json`.{review}"
    )


def _representative_trace_id(report: dict[str, Any]) -> str | None:
    for trial in report.get("trials") or []:
        if isinstance(trial, dict) and trial.get("trace_id"):
            return str(trial["trace_id"])
    return None


def _evaluation_links(*, base_url: str, agent_id: str, report: dict[str, Any]) -> dict[str, str]:
    return halios_ui_links(
        base_url,
        agent_id,
        include_evaluations=True,
        run_tag=str(report.get("run_tag") or "") or None,
        trace_id=_representative_trace_id(report),
    )


@app.command("review")
def review(json_output: bool = typer.Option(False, "--json")) -> None:
    """Validate the local suite and report design/coverage gaps without mutating it."""
    root, _config = load_project_config()
    eval_plan = load_yaml(root / ".halios" / "eval.yml")
    scenarios_payload = load_yaml(root / ".halios" / "scenarios.yml")
    result = _review_suite(eval_plan, scenarios_payload)
    # INVARIANT: Local discovery notes never alter executable-suite validation or gates.
    result["discovery"] = review_discovery(root)
    if json_output:
        typer.echo(json.dumps(result, indent=2, sort_keys=True))
    else:
        typer.echo(
            f"Eval review: {result['status']} "
            f"({result['scenario_count']} scenarios, {result['check_count']} checks)"
        )
        for gap in result["coverage_gaps"]:
            typer.echo(f"- {gap}")
        discovery = result["discovery"]
        typer.echo(
            f"Discovery: {discovery['status']} "
            "(local notes, not a proof of complete coverage)"
        )
        for gap in discovery["open_gaps"]:
            typer.echo(f"- [{gap['id']}] {gap['reason']}")
            typer.echo(f"  Affects: {', '.join(gap['affects'])}")
            typer.echo(f"  Next step: {gap['next_step']}")
        for error in discovery["errors"]:
            typer.echo(f"- Warning: {error}")
    if result["status"] != "ready":
        raise typer.Exit(code=1)


@app.command("run")
def run(
    repetitions: int = typer.Option(3, "--repetitions", "-k", min=1, max=20),
    fail_below: float | None = typer.Option(None, "--fail-below", min=0.0, max=1.0),
    scenario_id: str | None = typer.Option(None, "--scenario"),
    from_traces: str | None = typer.Option(None, "--from-traces"),
    tag: list[str] | None = typer.Option(None, "--tag"),
    run_name: str = typer.Option("eval", "--run-name"),
    publish: bool = typer.Option(
        False, "--publish", help="Publish from trusted default-branch CI."
    ),
    default_branch: str = typer.Option("main", "--default-branch"),
    timeout: int = typer.Option(600, "--timeout", min=10),
    adapter_timeout: int = typer.Option(
        120,
        "--adapter-timeout",
        min=1,
        max=900,
        help="Maximum seconds allowed for each agent response.",
    ),
    json_output: bool = typer.Option(False, "--json"),
) -> None:
    """Run the current verified server-owned evaluation suite."""
    root, config = load_project_config()
    agent_config = config.get("agent") or {}
    agent_id = str(agent_config.get("id") or "")
    profile = str(config.get("profile") or "default")
    credentials = resolve_credentials(profile, agent_id)
    trace_ids = _explicit_trace_ids(from_traces)
    if not trace_ids:
        if agent_config.get("protocol") != "jsonl-v1":
            raise typer.BadParameter("agent.protocol must be jsonl-v1")
        if not str(agent_config.get("command") or "").strip():
            raise typer.BadParameter("No agent.command in .halios/config.toml")
        if not credentials.otlp_token:
            raise typer.BadParameter("Missing OTLP token; rerun `halios project init --agent ...`")
    provenance = git_provenance(root)
    source, trace_origin, evaluation_context = _evaluation_telemetry_identity(
        ci=bool(os.getenv("CI"))
    )
    otlp_endpoint = _otlp_endpoint(
        credentials.base_url,
        trace_origin=trace_origin,
        evaluation_context=evaluation_context,
    )
    with ApiClient(credentials) as api:
        suite = api.request("GET", f"/api/v1/agents/{agent_id}/evaluation-suite")
        suite_revision = int(suite.get("revision") or 0)
        if suite_revision < 1:
            raise typer.BadParameter(
                "Evaluation suite is not configured; run `halios project configure`"
            )
        local_revision = int((config.get("suite") or {}).get("revision") or 0)
        if local_revision != suite_revision:
            raise typer.BadParameter(
                "Local evaluation suite checkout is stale; run `halios project refresh`"
            )
        local_eval = load_yaml(root / ".halios" / "eval.yml")
        local_scenarios = load_yaml(root / ".halios" / "scenarios.yml")
        if evaluation_suite_digest(local_eval, local_scenarios) != suite.get("digest"):
            raise typer.BadParameter(
                "Local evaluation suite has unconfigured edits; run "
                "`halios project configure` or `halios project refresh`"
            )
        if (suite.get("verification") or {}).get("verified") is not True:
            raise typer.BadParameter("Persistent evaluation suite verification failed")
        eval_plan = suite.get("eval") or {}
        scenarios = [] if trace_ids else (suite.get("scenarios") or {}).get("scenarios") or []
        if scenario_id:
            scenarios = [item for item in scenarios if str(item.get("id")) == scenario_id]
            if not scenarios:
                raise typer.BadParameter(f"Scenario not found: {scenario_id}")
        requires_ai = (
            scenarios and any(int(item.get("max_turns") or 6) > 1 for item in scenarios)
        ) or _contains_llm_judge(eval_plan)
        if requires_ai:
            capability = api.request("GET", "/api/v1/ai/capability")
            if not capability.get("evaluation_available"):
                raise typer.BadParameter(
                    capability.get("remediation") or "Evaluation BYOK provider is unavailable"
                )
        created = api.request(
            "POST",
            "/api/v1/runs/evaluations",
            json={
                "agent_id": agent_id,
                "run_name": run_name,
                "source": source,
                "suite_revision": suite_revision,
                "scenario_ids": [scenario_id] if scenario_id else [],
                "repetitions": 1 if trace_ids else repetitions,
                "trace_ids": trace_ids,
                "labels": tag or [],
                "gate": {"fail_below": fail_below} if fail_below is not None else {},
                "provenance": provenance,
            },
        )
        run_id = str(created["run_id"])
        typer.echo(f"Evaluation run {run_id} created; waiting for completion.", err=True)
        if publish:
            attestation = os.getenv("HALIOS_CI_PUBLISH_TOKEN")
            if not attestation:
                raise typer.BadParameter("HALIOS_CI_PUBLISH_TOKEN is required for --publish")
            api.request(
                "POST",
                f"/api/v1/runs/evaluations/{run_id}/publish",
                json={"default_branch": default_branch},
                headers={"X-Halios-CI-Attestation": attestation},
            )

        expected_roots: dict[str, str] = {}
        if not trace_ids:
            scenarios_by_id = {str(item["id"]): item for item in scenarios}
            for trial in created["trials"]:
                trace_id = secrets.token_hex(16)
                root_span_id = secrets.token_hex(8)
                expected_roots[trace_id] = root_span_id
                traceparent = f"00-{trace_id}-{root_span_id}-01"
                api.request(
                    "POST",
                    f"/api/v1/runs/evaluations/{run_id}/trials/{trial['id']}/start",
                    json={"trace_id": trace_id, "root_span_id": root_span_id},
                )
                started_ns = time.time_ns()
                adapter_environment = {
                    **os.environ,
                    "OTEL_EXPORTER_OTLP_TRACES_ENDPOINT": otlp_endpoint,
                    "OTEL_EXPORTER_OTLP_HEADERS": (
                        f"Authorization=Bearer%20{credentials.otlp_token}"
                    ),
                    "OTEL_SERVICE_NAME": str(
                        config.get("app_name") or agent_config.get("slug") or "agent"
                    ),
                    "OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT": "true",
                    "DEPLOYMENT_ENV": evaluation_context,
                    "OTEL_RESOURCE_ATTRIBUTES": _resource_attributes_with_environment(
                        os.getenv("OTEL_RESOURCE_ATTRIBUTES"), evaluation_context
                    ),
                }
                conversation, outcome, stop_reason, error = _invoke_adapter(
                    command=str(agent_config.get("command") or ""),
                    root=root,
                    trial_id=str(trial["id"]),
                    traceparent=traceparent,
                    scenario=scenarios_by_id[str(trial["scenario_id"])],
                    environment=adapter_environment,
                    api=api,
                    run_id=run_id,
                    turn_timeout_seconds=adapter_timeout,
                )
                ended_ns = time.time_ns()
                api.request(
                    "POST",
                    f"/api/v1/runs/evaluations/{run_id}/trials/{trial['id']}/complete",
                    json={
                        "trace_id": trace_id,
                        "root_span_id": root_span_id,
                        "outcome": outcome,
                        "stop_reason": stop_reason,
                        "error": error,
                    },
                )
                otlp_response = httpx.post(
                    otlp_endpoint,
                    headers={"Authorization": f"Bearer {credentials.otlp_token}"},
                    json=_otlp_root_payload(
                        trace_id=trace_id,
                        span_id=root_span_id,
                        started_ns=started_ns,
                        ended_ns=ended_ns,
                        conversation=conversation,
                        app_name=str(config.get("app_name") or "agent"),
                        service_version=provenance.get("commit_sha"),
                        evaluation_context=evaluation_context,
                        outcome=outcome,
                        error=error,
                    ),
                    timeout=30,
                )
                if otlp_response.is_error:
                    if otlp_response.status_code == 402:
                        try:
                            detail = otlp_response.json().get("detail", otlp_response.text)
                        except Exception:
                            detail = otlp_response.text
                        from .cli_support import ApiError

                        raise ApiError(402, detail)
                    raise typer.BadParameter(
                        f"OTLP root export failed: {otlp_response.status_code}"
                    )

        deadline = time.monotonic() + timeout
        report: dict[str, Any] = {}
        last_status: str | None = None
        while time.monotonic() < deadline:
            report = api.request("GET", f"/api/v1/runs/evaluations/{run_id}")
            current_status = str(report.get("status") or "unknown")
            if current_status != last_status:
                typer.echo(f"Evaluation run {run_id}: {current_status}.", err=True)
                last_status = current_status
            if current_status in {"completed", "failed"}:
                break
            time.sleep(2)
        else:
            raise typer.BadParameter(
                f"Evaluation run {run_id} did not finish within {timeout}s. "
                f"Inspect `halios eval report {run_id} --failures --json`."
            )
        report["links"] = _evaluation_links(
            base_url=credentials.ui_base_url, agent_id=agent_id, report=report
        )
        _raise_for_failed_run(report, run_id)
        if expected_roots:
            report["telemetry_verification"] = _verify_simulation_telemetry(
                api,
                report=report,
                agent_id=agent_id,
                expected_roots=expected_roots,
            )

    if json_output:
        typer.echo(json.dumps(report, indent=2, sort_keys=True))
    else:
        pass_at_k = float(report.get("pass_at_k") or 0)
        k = 1 if trace_ids else repetitions
        gate = "pass" if report.get("gate_passed") else "fail"
        telemetry = report.get("telemetry_verification") or {}
        if telemetry.get("verified"):
            typer.echo(f"Telemetry: verified ({telemetry['trace_count']} traces)")
        typer.echo(f"Run {run_id}: pass@{k}={pass_at_k:.1%} gate={gate}")
        emit_review_links(report["links"])
    if not report.get("gate_passed"):
        raise typer.Exit(2)


@app.command("report")
def report(
    run_id: str,
    failures: bool = typer.Option(False, "--failures"),
    compare: str | None = typer.Option(None, "--compare", help="Baseline immutable run id."),
    json_output: bool = typer.Option(False, "--json"),
) -> None:
    """Return immutable run evidence in human- or machine-readable form."""
    _root, config = load_project_config()
    agent_id = str((config.get("agent") or {}).get("id") or "")
    credentials = resolve_credentials(str(config.get("profile") or "default"), agent_id)
    with ApiClient(credentials) as api:
        result = api.request("GET", f"/api/v1/runs/evaluations/{run_id}")
        baseline = api.request("GET", f"/api/v1/runs/evaluations/{compare}") if compare else None
    if baseline:
        result["comparison"] = _compare_reports(result, baseline, str(compare))
    if failures:
        result = {
            **result,
            "trials": [item for item in result.get("trials", []) if not item.get("passed")],
        }
    result["links"] = _evaluation_links(
        base_url=credentials.ui_base_url, agent_id=agent_id, report=result
    )
    if json_output:
        typer.echo(json.dumps(result, indent=2, sort_keys=True))
    else:
        comparison = result.get("comparison") or {}
        delta = (
            f" delta={float(comparison['pass_at_k_delta']):+.1%} vs {compare}" if comparison else ""
        )
        typer.echo(
            f"{run_id}: pass@k={float(result.get('pass_at_k') or 0):.1%} "
            f"gate={'pass' if result.get('gate_passed') else 'fail'} "
            f"check_errors={int(result.get('check_execution_error_count') or 0)} "
            f"trial_failures={int(result.get('evaluation_failed_count') or 0)} "
            f"revision={result.get('report_revision')}{delta}"
        )
        emit_review_links(result["links"])
