"""Thin, explicit, idempotent project setup commands."""

from __future__ import annotations

import json
import pathlib
import re
import secrets
import shlex
import shutil
import tempfile
import urllib.parse
from typing import Any

import typer

from .cli_support import (
    ApiClient,
    ApiError,
    emit_review_links,
    evaluation_suite_digest,
    git_provenance,
    halios_ui_links,
    load_project_config,
    load_yaml,
    preserve_suite_recovery,
    resolve_credentials,
    save_agent_ingest_token,
    write_suite_checkout,
    write_yaml,
)

app = typer.Typer(help="Initialize and validate a Halios project.", no_args_is_help=True)


def _slug(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")


def _write_once(path: pathlib.Path, content: str) -> bool:
    if path.exists():
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        "w", dir=path.parent, delete=False, encoding="utf-8"
    ) as handle:
        handle.write(content)
        temporary = pathlib.Path(handle.name)
    temporary.replace(path)
    return True


def _find_or_create_agent(api: ApiClient, explicit_agent: str) -> dict[str, Any]:
    """Create a fresh agent; retained name avoids breaking direct SDK imports."""
    slug = _slug(explicit_agent)
    if not slug:
        raise typer.BadParameter("--agent must contain letters or numbers")
    return api.request(
        "POST",
        "/api/v1/agents",
        json={
            "name": explicit_agent,
            "slug": f"{slug[:240]}-{secrets.token_hex(3)}",
            "description": (
                f"Evaluation, simulation, and production observability for {explicit_agent}."
            ),
        },
    )


def _link_existing_agent(api: ApiClient, agent_id: str) -> dict[str, Any]:
    if not re.fullmatch(
        r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[1-5][0-9a-fA-F]{3}-[89abAB][0-9a-fA-F]{3}-[0-9a-fA-F]{12}",
        agent_id,
    ):
        raise typer.BadParameter("--link-agent requires an agent UUID")
    return api.request("GET", f"/api/v1/agents/{agent_id}")


def _evaluation_ai_capability(api: ApiClient) -> dict[str, Any]:
    capability = api.request("GET", "/api/v1/ai/capability")
    if not capability.get("evaluation_available"):
        raise typer.BadParameter(capability.get("remediation") or "Evaluation AI is unavailable")
    return capability


@app.command("init")
def init(
    agent: str | None = typer.Option(None, "--agent", help="Name for a new Halios agent."),
    link_agent: str | None = typer.Option(
        None, "--link-agent", help="Explicit UUID of an existing Halios agent."
    ),
    profile: str = typer.Option("default", "--profile"),
    command: str = typer.Option(
        "", "--command", help="Project adapter command; may be added later by the coding agent."
    ),
    json_output: bool = typer.Option(False, "--json"),
) -> None:
    """Create a fresh agent, or explicitly link one by UUID, and initialize the checkout."""
    root = pathlib.Path.cwd().resolve()
    config_path = root / ".halios" / "config.toml"
    if bool(agent) == bool(link_agent) and not config_path.exists():
        raise typer.BadParameter("Provide exactly one of --agent or --link-agent")
    credentials = resolve_credentials(profile)
    with ApiClient(credentials) as api:
        _evaluation_ai_capability(api)
        created_agent = False
        if config_path.exists():
            _, existing = load_project_config(root)
            bound_id = str((existing.get("agent") or {}).get("id") or "")
            if link_agent and link_agent != bound_id:
                raise typer.BadParameter(f"Project is already bound to agent {bound_id}")
            resolved_agent = api.request("GET", f"/api/v1/agents/{bound_id}")
            if agent and agent != str(resolved_agent.get("name") or ""):
                raise typer.BadParameter(
                    f"Project is already bound to {resolved_agent.get('name')} ({bound_id})"
                )
        elif link_agent:
            resolved_agent = _link_existing_agent(api, link_agent)
        else:
            resolved_agent = _find_or_create_agent(api, str(agent))
            created_agent = True
        suite = api.request("GET", f"/api/v1/agents/{resolved_agent['id']}/evaluation-suite")
        if created_agent and (
            int(suite.get("revision") or 0) != 0
            or (suite.get("eval") or {}).get("checks")
            or (suite.get("scenarios") or {}).get("scenarios")
        ):
            raise typer.BadParameter("Fresh agent unexpectedly contains evaluation state")
        bound_credentials = resolve_credentials(profile, str(resolved_agent["id"]))
        if not bound_credentials.otlp_token:
            ingest = api.request("POST", f"/api/v1/agents/{resolved_agent['id']}/otel-token")
            save_agent_ingest_token(profile, str(resolved_agent["id"]), str(ingest["token"]))
    halios_dir = root / ".halios"

    escaped_command = command.replace("\\", "\\\\").replace('"', '\\"')
    created: list[str] = []
    if _write_once(
        config_path,
        "\n".join(
            [
                'version = "1"',
                f'profile = "{profile}"',
                f'app_name = "{str(resolved_agent["name"]).replace(chr(34), chr(39))}"',
                f'halios_url = "{credentials.base_url}"',
                "",
                "[agent]",
                f'id = "{resolved_agent["id"]}"',
                f'slug = "{resolved_agent["slug"]}"',
                f'command = "{escaped_command}"',
                'protocol = "jsonl-v1"',
                "",
                "[suite]",
                f"revision = {int(suite.get('revision') or 0)}",
                f'digest = "{str(suite.get("digest") or "")}"',
                "",
            ]
        ),
    ):
        created.append(".halios/config.toml")

    eval_path = halios_dir / "eval.yml"
    if not eval_path.exists():
        write_yaml(eval_path, suite["eval"])
        created.append(".halios/eval.yml")

    scenarios_path = halios_dir / "scenarios.yml"
    if not scenarios_path.exists():
        write_yaml(scenarios_path, suite["scenarios"])
        created.append(".halios/scenarios.yml")

    verb = "Created" if created_agent else "Linked"
    links = halios_ui_links(credentials.ui_base_url, str(resolved_agent["id"]))
    result = {
        "created": created_agent,
        "agent": {
            "id": str(resolved_agent["id"]),
            "name": str(resolved_agent["name"]),
            "slug": str(resolved_agent["slug"]),
        },
        "suite": {
            "revision": int(suite.get("revision") or 0),
            "check_count": len((suite.get("eval") or {}).get("checks") or []),
            "scenario_count": len((suite.get("scenarios") or {}).get("scenarios") or []),
        },
        "created_files": created,
        "links": links,
    }
    if json_output:
        typer.echo(json.dumps(result, indent=2, sort_keys=True))
    else:
        typer.echo(f"{verb} Halios agent: {resolved_agent['name']}")
        typer.echo(f"Agent ID: {resolved_agent['id']}")
        if not created_agent:
            typer.echo(
                f"Existing evaluation suite: revision {suite['revision']}, "
                f"{result['suite']['check_count']} checks, "
                f"{result['suite']['scenario_count']} scenarios"
            )
        typer.echo(
            "Created: " + ", ".join(created) if created else "Project was already initialized."
        )
        emit_review_links(links)


def _apply_suite_response(root: pathlib.Path, response: dict[str, Any]) -> None:
    expected_digest = response.get("digest")
    actual_digest = evaluation_suite_digest(response["eval"], response["scenarios"])
    if int(response.get("revision") or 0) > 0 and expected_digest != actual_digest:
        raise typer.BadParameter("Halios returned an evaluation suite with an invalid digest")
    write_suite_checkout(
        root,
        eval_plan=response["eval"],
        scenarios=response["scenarios"],
        revision=int(response["revision"]),
        digest=response.get("digest"),
    )


@app.command("configure")
def configure(json_output: bool = typer.Option(False, "--json")) -> None:
    """Atomically apply local eval and scenario working copies to Halios."""
    root, config = load_project_config()
    agent_id = str((config.get("agent") or {}).get("id") or "")
    profile = str(config.get("profile") or "default")
    expected_revision = int((config.get("suite") or {}).get("revision") or 0)
    eval_plan = load_yaml(root / ".halios" / "eval.yml")
    scenarios = load_yaml(root / ".halios" / "scenarios.yml")
    from .cli_eval import _eval_schema_errors, _scenario_schema_errors

    local_errors = [*_eval_schema_errors(eval_plan), *_scenario_schema_errors(scenarios)[1]]
    if local_errors:
        raise typer.BadParameter("Invalid evaluation suite:\n- " + "\n- ".join(local_errors))
    credentials = resolve_credentials(profile, agent_id)
    try:
        with ApiClient(credentials) as api:
            response = api.request(
                "PUT",
                f"/api/v1/agents/{agent_id}/evaluation-suite",
                json={
                    "expected_revision": expected_revision,
                    "eval": eval_plan,
                    "scenarios": scenarios,
                },
            )
    except ApiError as exc:
        if exc.status_code != 409 or not isinstance(exc.detail, dict):
            raise
        current = exc.detail.get("current")
        if not isinstance(current, dict):
            raise
        recovery = preserve_suite_recovery(
            agent_id=agent_id,
            eval_plan=eval_plan,
            scenarios=scenarios,
        )
        _apply_suite_response(root, current)
        raise typer.BadParameter(
            f"Evaluation suite revision conflict. Refreshed local YAML to revision "
            f"{current['revision']}; rejected edits were preserved at {recovery}"
        ) from exc
    verification = response.get("verification") or {}
    if verification.get("verified") is not True:
        raise typer.BadParameter("Halios did not verify the materialized evaluation suite")
    _apply_suite_response(root, response)
    result = {
        "configured": True,
        "revision": response["revision"],
        "digest": response.get("digest"),
        "verification": verification,
        "links": halios_ui_links(credentials.ui_base_url, agent_id, include_suite=True),
    }
    if json_output:
        typer.echo(json.dumps(result, indent=2, sort_keys=True))
    else:
        typer.echo(
            f"Evaluation suite revision {response['revision']} configured: "
            f"{verification['check_count']} checks, {verification['rule_count']} rules, "
            f"{verification['rubric_count']} rubrics, {verification['scenario_count']} scenarios"
        )
        emit_review_links(result["links"])


@app.command("refresh")
def refresh() -> None:
    """Replace both local YAML files with the authoritative Halios suite."""
    root, config = load_project_config()
    agent_id = str((config.get("agent") or {}).get("id") or "")
    profile = str(config.get("profile") or "default")
    credentials = resolve_credentials(profile, agent_id)
    with ApiClient(credentials) as api:
        response = api.request("GET", f"/api/v1/agents/{agent_id}/evaluation-suite")
    _apply_suite_response(root, response)
    typer.echo(f"Refreshed evaluation suite revision {response['revision']} from Halios")
    emit_review_links(halios_ui_links(credentials.ui_base_url, agent_id, include_suite=True))


@app.command("check")
def check(
    profile: str | None = typer.Option(None, "--profile"),
    json_output: bool = typer.Option(False, "--json"),
) -> None:
    """Validate local files, credentials, adapter, provenance, and AI capability."""
    root, config = load_project_config()
    selected_profile = profile or str(config.get("profile") or "default")
    agent = config.get("agent") or {}
    agent_id = str(agent.get("id") or "")
    if not agent_id:
        raise typer.BadParameter("config.toml is missing agent.id")
    if agent.get("protocol") != "jsonl-v1":
        raise typer.BadParameter("agent.protocol must be jsonl-v1")
    local_eval = load_yaml(root / ".halios" / "eval.yml")
    local_scenarios = load_yaml(root / ".halios" / "scenarios.yml")
    credentials = resolve_credentials(selected_profile, agent_id)
    if not credentials.otlp_token:
        raise typer.BadParameter(
            "Missing agent OTLP token; rerun `halios project init --agent ...`"
        )

    command = str(agent.get("command") or "").strip()
    if not command:
        raise typer.BadParameter("No agent.command in .halios/config.toml")
    parts = shlex.split(command)
    if not parts:
        raise typer.BadParameter("agent.command must not be empty")
    executable = parts[0]
    if "/" in executable:
        if not (root / executable).exists():
            raise typer.BadParameter(f"Adapter executable does not exist: {executable}")
    elif shutil.which(executable) is None:
        raise typer.BadParameter(f"Adapter executable was not found: {executable}")
    candidate = (
        parts[1] if len(parts) > 1 and pathlib.Path(executable).name.startswith("python") else None
    )
    if candidate and candidate.endswith(".py") and not (root / candidate).exists():
        raise typer.BadParameter(f"Adapter command target does not exist: {candidate}")

    with ApiClient(credentials) as api:
        api.request("GET", f"/api/v1/agents/{agent_id}")
        suite = api.request("GET", f"/api/v1/agents/{agent_id}/evaluation-suite")
        local_revision = int((config.get("suite") or {}).get("revision") or 0)
        if int(suite.get("revision") or 0) != local_revision:
            raise typer.BadParameter(
                "Local evaluation suite checkout is stale; run `halios project refresh`"
            )
        if evaluation_suite_digest(local_eval, local_scenarios) != suite.get("digest"):
            raise typer.BadParameter(
                "Local evaluation suite has unconfigured edits; run "
                "`halios project configure` or `halios project refresh`"
            )
        if not (suite.get("eval") or {}).get("checks") or not (suite.get("scenarios") or {}).get(
            "scenarios"
        ):
            raise typer.BadParameter(
                "Evaluation suite is not configured; author YAML and run `halios project configure`"
            )
        if (suite.get("verification") or {}).get("verified") is not True:
            raise typer.BadParameter("Persistent evaluation suite verification failed")
        capability = _evaluation_ai_capability(api)

    provenance = git_provenance(root)
    branch = provenance.get("branch") or "detached"
    commit = str(provenance.get("commit_sha") or "unknown")[:12]
    dirty = str(bool(provenance.get("dirty_worktree"))).lower()
    mode = str(capability.get("execution_mode") or "managed")
    model = capability.get("default_model")
    evaluation_status = f"ready ({'Halios Managed' if mode == 'managed' else model})"
    result = {
        "ok": True,
        "agent_id": agent_id,
        "profile": selected_profile,
        "adapter_protocol": "jsonl-v1",
        "git": {"branch": branch, "commit": commit, "dirty": dirty == "true"},
        "evaluation_ai": evaluation_status,
        "suite": {"verified": True, "revision": suite["revision"]},
        "links": halios_ui_links(credentials.ui_base_url, agent_id, include_suite=True),
    }
    if json_output:
        typer.echo(json.dumps(result, indent=2, sort_keys=True))
    else:
        typer.echo(f"Project: ok ({agent_id})")
        typer.echo(f"Credentials: ok ({selected_profile})")
        typer.echo("Adapter: ok (jsonl-v1)")
        typer.echo(f"Git: {branch}@{commit} dirty={dirty}")
        typer.echo(f"Evaluation AI: {evaluation_status}")
        typer.echo(f"Evaluation suite: verified (revision {suite['revision']})")
        emit_review_links(result["links"])


@app.command("instrumentation")
def instrumentation(
    profile: str | None = typer.Option(None, "--profile"),
    environment: str = typer.Option("production", "--environment"),
    show_secret: bool = typer.Option(
        False,
        "--show-secret",
        help="Reveal the stored agent ingest token for manual secret-manager setup.",
    ),
    json_output: bool = typer.Option(False, "--json"),
) -> None:
    """Print deployment-safe OpenTelemetry configuration for the real agent runtime."""
    _root, config = load_project_config()
    selected_profile = profile or str(config.get("profile") or "default")
    agent = config.get("agent") or {}
    agent_id = str(agent.get("id") or "")
    if not agent_id:
        raise typer.BadParameter("config.toml is missing agent.id")
    credentials = resolve_credentials(selected_profile, agent_id)
    if not credentials.otlp_token:
        raise typer.BadParameter(
            "Missing agent OTLP token; rerun `halios project init --agent ...`"
        )
    environment_name = environment.strip()
    if not environment_name:
        raise typer.BadParameter("--environment must not be empty")
    token = credentials.otlp_token if show_secret else "<stored-agent-token>"
    authorization = urllib.parse.quote(f"Bearer {token}", safe="<>")
    values = {
        "OTEL_EXPORTER_OTLP_PROTOCOL": "http/protobuf",
        "OTEL_EXPORTER_OTLP_TRACES_ENDPOINT": f"{credentials.base_url}/v1/traces",
        "OTEL_EXPORTER_OTLP_HEADERS": f"Authorization={authorization}",
        "OTEL_SERVICE_NAME": str(config.get("app_name") or agent.get("slug") or "agent"),
        "OTEL_RESOURCE_ATTRIBUTES": f"deployment.environment.name={environment_name}",
    }
    if json_output:
        typer.echo(json.dumps(values, indent=2, sort_keys=True))
    else:
        for key, value in values.items():
            typer.echo(f"{key}={value}")
        if not show_secret:
            typer.echo(
                "Token hidden. Run this command yourself with --show-secret, then copy it "
                "directly into your deployment secret manager."
            )
