"""Read-only trace evidence commands for coding agents."""

from __future__ import annotations

import json
import re

import typer

from .cli_support import (
    ApiClient,
    emit_review_links,
    halios_ui_links,
    load_project_config,
    resolve_credentials,
)

app = typer.Typer(help="Inspect trace evidence and production failures.", no_args_is_help=True)


def _context():
    _root, config = load_project_config()
    agent_id = str((config.get("agent") or {}).get("id") or "")
    credentials = resolve_credentials(str(config.get("profile") or "default"), agent_id)
    return agent_id, credentials


def _emit(value: object, json_output: bool) -> None:
    if json_output:
        typer.echo(json.dumps(value, indent=2, sort_keys=True, default=str))
    else:
        links = value.get("links") if isinstance(value, dict) else None
        display_value = (
            {key: item for key, item in value.items() if key != "links"}
            if isinstance(value, dict)
            else value
        )
        items = (
            display_value.get("data", display_value)
            if isinstance(display_value, dict)
            else display_value
        )
        if isinstance(items, list):
            for item in items:
                if isinstance(item, dict):
                    typer.echo(
                        "\t".join(
                            str(item.get(key) or "") for key in ("trace_id", "status", "created_at")
                        )
                    )
        else:
            typer.echo(json.dumps(display_value, indent=2, default=str))
        if isinstance(links, dict):
            emit_review_links(links)


@app.command("list")
def list_traces(
    environment: str | None = typer.Option(None, "--environment"),
    limit: int = typer.Option(50, "--limit", min=1, max=100),
    json_output: bool = typer.Option(False, "--json"),
) -> None:
    agent_id, credentials = _context()
    params = {"agent_id": agent_id, "limit": limit}
    if environment:
        params["traffic_scope"] = environment
    with ApiClient(credentials) as api:
        result = api.request("GET", "/api/v1/traces", params=params)
    _emit(result, json_output)


@app.command("show")
def show(
    trace_id: str,
    include: str = typer.Option("spans,checks", "--include"),
    json_output: bool = typer.Option(False, "--json"),
) -> None:
    agent_id, credentials = _context()
    with ApiClient(credentials) as api:
        result = api.request("GET", f"/api/v1/traces/{trace_id}")
    allowed = {item.strip() for item in include.split(",") if item.strip()}
    if isinstance(result, dict):
        if "spans" not in allowed:
            result.pop("spans", None)
        if "checks" not in allowed:
            result.pop("check_executions", None)
        result["links"] = halios_ui_links(credentials.ui_base_url, agent_id, trace_id=trace_id)
    _emit(result, json_output)


@app.command("failures")
def failures(
    environment: str = typer.Option("production", "--environment"),
    limit: int = typer.Option(100, "--limit", min=1, max=100),
    json_output: bool = typer.Option(False, "--json"),
) -> None:
    """List failed evaluator evidence for the selected environment."""
    agent_id, credentials = _context()
    with ApiClient(credentials) as api:
        result = api.request(
            "GET",
            f"/api/v1/agents/{agent_id}/check-executions",
            params={
                "mode": "evaluator",
                "evaluation_context": environment,
                "limit": limit,
                "include_progress": False,
            },
        )
    items = result.get("data") or []
    result["data"] = [
        item
        for item in items
        if item.get("passed") is False
        or item.get("triggered") is True
        or item.get("status") in {"failed", "error"}
        or item.get("error")
    ]
    _emit(result, json_output)


@app.command("cluster")
def cluster(
    environment: str = typer.Option("production", "--environment"),
    json_output: bool = typer.Option(False, "--json"),
) -> None:
    """Cluster recent evaluator failures in one evidence environment."""
    agent_id, credentials = _context()
    with ApiClient(credentials) as api:
        result = api.request(
            "GET",
            "/api/v1/scenarios/failure-clusters",
            params={"agent_id": agent_id, "evaluation_context": environment},
        )
    _emit(result, json_output)


@app.command("verify")
def verify(
    trace_id: str,
    json_output: bool = typer.Option(False, "--json"),
) -> None:
    """Fail closed unless a stored runtime trace has usable standard OTel evidence."""
    agent_id, credentials = _context()
    with ApiClient(credentials) as api:
        detail = api.request("GET", f"/api/v1/traces/{trace_id}")
    spans = detail.get("spans") or []
    issues: list[str] = []
    if not re.fullmatch(r"[0-9a-f]{32}", trace_id) or trace_id == "0" * 32:
        issues.append("trace id is not a valid non-zero W3C trace id")
    if detail.get("trace_id") != trace_id:
        issues.append("trace identity does not match")
    if not spans:
        issues.append("trace contains no spans")
    span_ids = {str(span.get("span_id")) for span in spans if isinstance(span, dict)}
    roots = [span for span in spans if isinstance(span, dict) and not span.get("parent_span_id")]
    if len(roots) != 1:
        issues.append(f"trace must contain exactly one root span; found {len(roots)}")
    for span in spans:
        if not isinstance(span, dict):
            issues.append("trace contains a malformed span")
            continue
        span_id = str(span.get("span_id") or "")
        if not re.fullmatch(r"[0-9a-f]{16}", span_id) or span_id == "0" * 16:
            issues.append(f"span {span_id or '<missing>'} has an invalid W3C span id")
        parent = span.get("parent_span_id")
        if parent and str(parent) not in span_ids:
            issues.append(f"span {span.get('span_id')} has a missing parent")
        if not span.get("ended_at"):
            issues.append(f"span {span.get('span_id')} has no end time")
    has_semantic_content = any(
        isinstance(span, dict) and (span.get("input") or span.get("output")) for span in spans
    )
    if not has_semantic_content:
        issues.append("trace has no captured input or output evidence")
    attributes = [span.get("attributes") or {} for span in spans if isinstance(span, dict)]
    if not any(value.get("resource.service.name") for value in attributes):
        issues.append("trace has no service.name resource identity")
    if not any(
        value.get("resource.deployment.environment.name")
        or value.get("resource.deployment.environment")
        for value in attributes
    ):
        issues.append("trace has no deployment.environment.name resource identity")
    result = {
        "trace_id": trace_id,
        "verified": not issues,
        "span_count": len(spans),
        "root_count": len(roots),
        "issues": issues,
        "links": halios_ui_links(credentials.ui_base_url, agent_id, trace_id=trace_id),
    }
    _emit(result, json_output)
    if issues:
        raise typer.Exit(2)
