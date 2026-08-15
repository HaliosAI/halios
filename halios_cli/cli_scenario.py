"""Git-owned scenario authoring and inspection commands."""

from __future__ import annotations

import json

import typer

from .cli_support import ApiClient, load_project_config, load_yaml, resolve_credentials, write_yaml

app = typer.Typer(help="Generate and inspect durable test scenarios.", no_args_is_help=True)


def _local_suite():
    root, config = load_project_config()
    path = root / ".halios" / "scenarios.yml"
    payload = load_yaml(path)
    scenarios = payload.get("scenarios") or []
    if not isinstance(scenarios, list):
        raise typer.BadParameter("scenarios.yml scenarios must be a list")
    return root, config, path, payload, scenarios


@app.command("generate")
def generate(
    from_trace: str | None = typer.Option(None, "--from-trace"),
    count: int = typer.Option(12, "--count", min=1, max=100),
    max_turns: int = typer.Option(6, "--max-turns", min=1, max=20),
    json_output: bool = typer.Option(False, "--json"),
) -> None:
    """Generate scenarios into Git, optionally from one production failure."""
    _root, config, path, payload, scenarios = _local_suite()
    agent_id = str((config.get("agent") or {}).get("id") or "")
    credentials = resolve_credentials(str(config.get("profile") or "default"), agent_id)
    with ApiClient(credentials) as api:
        if from_trace:
            drafted = api.request(
                "POST",
                f"/api/v1/scenarios/draft-from-trace/{from_trace}",
                json={"agent_id": agent_id, "max_turns": max_turns},
            )["draft"]
            scenario = {
                "id": f"regression-{from_trace[:12]}",
                **drafted,
                "source_trace_id": from_trace,
                "generation_mode": "simulation",
            }
            generated = [scenario]
        else:
            response = api.request(
                "POST",
                "/api/v1/scenarios/generate",
                json={
                    "agent_id": agent_id,
                    "scenario_count": count,
                    "generation_mode": "simulation-with-arc-hint",
                    "max_turns": max_turns,
                },
            )
            generated = response.get("scenarios") or []

    existing_ids = {str(item.get("id")) for item in scenarios}
    added = [item for item in generated if str(item.get("id")) not in existing_ids]
    payload["version"] = 1
    payload["scenarios"] = [*scenarios, *added]
    write_yaml(path, payload)
    result = {"added": len(added), "path": str(path), "scenarios": added}
    typer.echo(
        json.dumps(result, indent=2, sort_keys=True)
        if json_output
        else f"Added {len(added)} scenarios to {path}"
    )


@app.command("list")
def list_scenarios(json_output: bool = typer.Option(False, "--json")) -> None:
    """List scenarios from the current Git branch."""
    _root, _config, _path, _payload, scenarios = _local_suite()
    if json_output:
        typer.echo(json.dumps(scenarios, indent=2, sort_keys=True))
        return
    for scenario in scenarios:
        typer.echo(f"{scenario.get('id')}\t{scenario.get('title') or scenario.get('goal') or ''}")


@app.command("show")
def show(scenario_id: str, json_output: bool = typer.Option(False, "--json")) -> None:
    """Show one local scenario by stable id."""
    _root, _config, _path, _payload, scenarios = _local_suite()
    scenario = next((item for item in scenarios if str(item.get("id")) == scenario_id), None)
    if not scenario:
        raise typer.BadParameter(f"Scenario not found: {scenario_id}")
    if json_output:
        typer.echo(json.dumps(scenario, indent=2, sort_keys=True))
    else:
        typer.echo(f"{scenario_id}: {scenario.get('title') or ''}\n{scenario.get('goal') or ''}")
