from __future__ import annotations

import json
import sys
from types import SimpleNamespace
from typing import Any

import pytest
import typer
from typer.testing import CliRunner

from halios_cli import cli_project, cli_support, cli_trace
from halios_cli.cli import app
from halios_cli.cli_eval import _invoke_adapter, _otlp_root_payload, _scenario_schema_errors


class FakeApiClient:
    calls: list[dict[str, Any]] = []
    response: dict[str, Any] = {}

    def __init__(self, _credentials: object) -> None:
        pass

    def __enter__(self) -> "FakeApiClient":
        return self

    def __exit__(self, *_args: object) -> None:
        return None

    def request(self, method: str, path: str, **kwargs: Any) -> dict[str, Any]:
        self.calls.append({"method": method, "path": path, **kwargs})
        return self.response


def _patch_trace_context(monkeypatch) -> None:
    FakeApiClient.calls = []
    credentials = SimpleNamespace(ui_base_url="https://app.halios.ai")
    monkeypatch.setattr(cli_trace, "_context", lambda: ("agent-id", credentials))
    monkeypatch.setattr(cli_trace, "ApiClient", FakeApiClient)


def test_top_level_exposes_agent_workflows() -> None:
    result = CliRunner().invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "optimize" in result.output
    assert "trace" in result.output


def test_ci_credentials_accept_agent_scoped_otlp_token_from_environment(monkeypatch) -> None:
    monkeypatch.setattr(cli_support, "_read_credentials", lambda: {"profiles": {}})
    monkeypatch.setenv("HALIOS_API_KEY", "halios_control_plane_key")
    monkeypatch.setenv("HALIOS_OTLP_TOKEN", "halios_agent_ingest_token")
    monkeypatch.setenv("HALIOS_BASE_URL", "https://api.halios.ai")
    monkeypatch.setenv("HALIOS_UI_URL", "https://app.halios.ai")

    credentials = cli_support.resolve_credentials(agent_id="agent-id")

    assert credentials.api_key == "halios_control_plane_key"
    assert credentials.otlp_token == "halios_agent_ingest_token"
    assert credentials.base_url == "https://api.halios.ai"
    assert credentials.ui_base_url == "https://app.halios.ai"


def test_ui_links_are_encoded_and_strip_credentials() -> None:
    links = cli_support.halios_ui_links(
        "https://user:secret@app.halios.ai/api?token=do-not-copy",
        "agent/id",
        include_suite=True,
        run_tag="run:hello world",
        trace_id="1" * 32,
        optimization_run_id="opt/id",
    )

    assert links["agent"] == "https://app.halios.ai/agents/agent%2Fid"
    assert links["scenarios"].endswith("/evaluations?tab=scenarios")
    assert links["rules"].endswith("/evaluations?tab=rules")
    assert links["evaluation_run"].endswith("/evaluations/run%3Ahello%20world")
    assert links["evaluation_traces"].endswith("/traces?eval_run=run%3Ahello+world")
    assert links["optimization_run"].endswith("/optimize/opt%2Fid")
    assert "secret" not in "\n".join(links.values())
    assert "token" not in "\n".join(links.values())


def test_ui_links_require_agent_identity() -> None:
    assert cli_support.halios_ui_links("https://app.halios.ai", "") == {}

    with pytest.raises(typer.BadParameter, match="Invalid Halios base URL"):
        cli_support.halios_ui_links("ftp://app.halios.ai", "agent-id")


def test_project_init_json_returns_agent_review_link(monkeypatch, tmp_path) -> None:
    agent_id = "11111111-1111-4111-8111-111111111111"
    credentials = SimpleNamespace(
        base_url="https://api.halios.ai",
        ui_base_url="https://app.halios.ai",
        otlp_token="stored-token",
    )

    class InitApi:
        def __init__(self, _credentials: object) -> None:
            pass

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def request(self, method: str, path: str, **_kwargs):
            if method == "GET" and path == "/api/v1/ai/capability":
                return {"evaluation_available": True}
            if method == "POST" and path == "/api/v1/agents":
                return {"id": agent_id, "name": "Support agent", "slug": "support-agent"}
            if path == f"/api/v1/agents/{agent_id}/evaluation-suite":
                return {
                    "revision": 0,
                    "digest": "",
                    "eval": {},
                    "scenarios": {"version": 1, "scenarios": []},
                }
            raise AssertionError(f"Unexpected request: {method} {path}")

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(cli_project, "resolve_credentials", lambda *_args: credentials)
    monkeypatch.setattr(cli_project, "ApiClient", InitApi)

    result = CliRunner().invoke(
        app,
        [
            "project",
            "init",
            "--agent",
            "Support agent",
            "--command",
            "python adapter.py",
            "--json",
        ],
    )

    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert payload["agent"]["id"] == agent_id
    assert payload["links"]["agent"] == f"https://app.halios.ai/agents/{agent_id}"


def test_trace_list_uses_backend_traffic_scope(monkeypatch) -> None:
    _patch_trace_context(monkeypatch)
    FakeApiClient.response = {"data": []}
    result = CliRunner().invoke(app, ["trace", "list", "--environment", "production", "--json"])
    assert result.exit_code == 0
    assert FakeApiClient.calls[0]["params"]["traffic_scope"] == "production"
    assert "source" not in FakeApiClient.calls[0]["params"]


def test_trace_failures_filters_failed_evidence_locally(monkeypatch) -> None:
    _patch_trace_context(monkeypatch)
    FakeApiClient.response = {
        "data": [
            {"id": "pass", "passed": True, "status": "passed"},
            {"id": "fail", "passed": False, "status": "failed"},
        ]
    }
    result = CliRunner().invoke(app, ["trace", "failures", "--json"])
    assert result.exit_code == 0
    assert '"id": "fail"' in result.output
    assert '"id": "pass"' not in result.output
    assert FakeApiClient.calls[0]["path"] == "/api/v1/agents/agent-id/check-executions"


def test_trace_verify_accepts_complete_root(monkeypatch) -> None:
    _patch_trace_context(monkeypatch)
    trace_id = "1" * 32
    FakeApiClient.response = {
        "trace_id": trace_id,
        "spans": [
            {
                "span_id": "2" * 16,
                "parent_span_id": None,
                "ended_at": "2026-01-01T00:00:01Z",
                "input": {"messages": [{"role": "user", "content": "hello"}]},
                "output": {"messages": [{"role": "assistant", "content": "hi"}]},
                "attributes": {
                    "resource.service.name": "support-agent",
                    "resource.deployment.environment.name": "production",
                },
            }
        ],
    }
    result = CliRunner().invoke(app, ["trace", "verify", trace_id, "--json"])
    assert result.exit_code == 0
    assert '"verified": true' in result.output
    assert '"trace": "https://app.halios.ai/agents/agent-id/traces/' in result.output


def test_cli_root_span_uses_standard_genai_message_parts() -> None:
    payload = _otlp_root_payload(
        trace_id="1" * 32,
        span_id="2" * 16,
        started_ns=1,
        ended_ns=2,
        conversation=[
            {"role": "user", "content": "hello"},
            {"role": "assistant", "content": "hi"},
        ],
        app_name="support-agent",
        service_version="abc123",
    )
    attributes = payload["resourceSpans"][0]["scopeSpans"][0]["spans"][0]["attributes"]
    input_value = next(
        item["value"]["stringValue"]
        for item in attributes
        if item["key"] == "gen_ai.input.messages"
    )
    assert '"parts": [{"type": "text", "content": "hello"}]' in input_value


def test_scenario_schema_separates_agent_and_simulator_context() -> None:
    canonical = {
        "version": 1,
        "scenarios": [
            {
                "id": "account-help",
                "title": "Account help",
                "goal": "Recover access",
                "initial_message": "I cannot sign in",
                "agent_context": {"channel": "support"},
                "simulator_context": {"synthetic_account_id": "acct-test-123"},
                "risk_label": "benign",
                "max_turns": 3,
            }
        ],
    }
    scenarios, errors = _scenario_schema_errors(canonical)
    assert len(scenarios) == 1
    assert errors == []

    deprecated = {
        **canonical,
        "scenarios": [{**canonical["scenarios"][0], "initial_context": {}}],
    }
    assert "initial_context" in "\n".join(_scenario_schema_errors(deprecated)[1])


def test_adapter_receives_only_agent_context(tmp_path) -> None:
    adapter = tmp_path / "adapter.py"
    adapter.write_text(
        "import json, sys\n"
        "for line in sys.stdin:\n"
        "    request = json.loads(line)\n"
        "    print(json.dumps({'message': {'role': 'assistant', "
        "'content': json.dumps(request['context'], sort_keys=True)}}), flush=True)\n",
        encoding="utf-8",
    )

    class StopApi:
        def request(self, *_args, **_kwargs):
            return {
                "stop": True,
                "outcome": "completed",
                "stop_reason": "goal_resolved",
            }

    conversation, outcome, stop_reason, error = _invoke_adapter(
        command=f"{sys.executable} {adapter}",
        root=tmp_path,
        trial_id="trial-1",
        traceparent=f"00-{'1' * 32}-{'2' * 16}-01",
        scenario={
            "initial_message": "Help me",
            "agent_context": {"channel": "support"},
            "simulator_context": {"private_fact": "do-not-leak"},
            "max_turns": 2,
        },
        environment={},
        api=StopApi(),
        run_id="run-1",
    )

    assert conversation[-1]["content"] == '{"channel": "support"}'
    assert outcome == "completed"
    assert stop_reason == "goal_resolved"
    assert error == {}


def test_eval_quality_gaps_flags_empty_simulator_context() -> None:
    from halios_cli.cli_eval import _eval_quality_gaps

    scenarios = [
        {
            "id": "multi-turn-missing-context",
            "title": "Account check",
            "goal": "Verify email check",
            "initial_message": "Hi",
            "agent_context": {},
            "simulator_context": {},
            "arc_messages": ["Provide email when asked"],
            "max_turns": 4,
        }
    ]
    gaps = _eval_quality_gaps(eval_plan={}, scenarios=scenarios)
    assert any("simulator_context is empty for a multi-turn scenario" in gap for gap in gaps)
