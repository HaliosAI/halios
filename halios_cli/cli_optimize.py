"""Prompt-optimization control plane for coding agents."""

from __future__ import annotations

import json
import pathlib
from typing import Any

import typer

from .cli_support import ApiClient, atomic_write_text, load_project_config, resolve_credentials

app = typer.Typer(
    help="Guide, record, and verify coding-agent prompt optimization.",
    no_args_is_help=True,
)


def _context() -> tuple[str, Any]:
    _root, config = load_project_config()
    agent_id = str((config.get("agent") or {}).get("id") or "")
    credentials = resolve_credentials(str(config.get("profile") or "default"), agent_id)
    return agent_id, credentials


def _emit(value: dict[str, Any], json_output: bool) -> None:
    if json_output:
        typer.echo(json.dumps(value, indent=2, sort_keys=True, default=str))
    else:
        typer.echo(json.dumps(value, indent=2, default=str))


def _resolve_baseline(api: ApiClient, agent_id: str, explicit_run_id: str | None) -> dict[str, Any]:
    if explicit_run_id:
        baseline = api.request("GET", f"/api/v1/runs/evaluations/{explicit_run_id}")
    else:
        listing = api.request(
            "GET", "/api/v1/runs/evaluations", params={"agent_id": agent_id, "limit": 20}
        )
        baseline = next(
            (
                item
                for item in listing.get("items") or []
                if item.get("status") in {"completed", "failed"}
                and int(item.get("attempted_trial_count") or 0) > 0
                and int(item.get("telemetry_incomplete_count") or 0) == 0
            ),
            None,
        )
        if baseline is None:
            raise typer.BadParameter(
                "No complete canonical eval run is available; run `halios eval run` first"
            )
        baseline = api.request("GET", f"/api/v1/runs/evaluations/{baseline['run_id']}")
    if baseline.get("status") not in {"completed", "failed"}:
        raise typer.BadParameter("Optimization baseline must be a complete evaluation run")
    if int(baseline.get("telemetry_incomplete_count") or 0):
        raise typer.BadParameter("Optimization baseline has incomplete telemetry")
    return baseline


def _scorecard(report: dict[str, Any]) -> dict[str, Any]:
    return {
        "overall_score": float(report.get("pass_at_k") or 0),
        "gate_passed": bool(report.get("gate_passed")),
        "protected_failure": bool(report.get("protected_failure")),
        "telemetry_incomplete_count": int(report.get("telemetry_incomplete_count") or 0),
        "check_execution_error_count": int(report.get("check_execution_error_count") or 0),
        "attempted_trial_count": int(report.get("attempted_trial_count") or 0),
        "suite_digest": report.get("suite_digest"),
    }


def _safe_gate(report: dict[str, Any]) -> bool:
    return (
        bool(report.get("gate_passed"))
        and not bool(report.get("protected_failure"))
        and not (
            int(report.get("telemetry_incomplete_count") or 0)
            or int(report.get("check_execution_error_count") or 0)
        )
    )


@app.command("start")
def start(
    prompt_file: pathlib.Path = typer.Option(..., "--prompt-file", exists=True, dir_okay=False),
    baseline_run: str | None = typer.Option(None, "--baseline-run"),
    name: str = typer.Option("coding-agent-optimization", "--name"),
    max_iterations: int = typer.Option(5, "--max-iterations", min=1, max=20),
    max_character_delta: int = typer.Option(300, "--max-character-delta", min=1, max=5000),
    json_output: bool = typer.Option(False, "--json"),
) -> None:
    """Freeze a canonical baseline and open a coding-agent optimization run."""
    agent_id, credentials = _context()
    starting_prompt = prompt_file.read_text(encoding="utf-8")
    if not starting_prompt.strip():
        raise typer.BadParameter("--prompt-file must contain the current system prompt")
    with ApiClient(credentials) as api:
        baseline = _resolve_baseline(api, agent_id, baseline_run)
        created = api.request(
            "POST",
            "/api/v1/optimization-runs",
            json={
                "agent_id": agent_id,
                "name": name,
                "strategy": "simple",
                "starting_prompt": starting_prompt,
                "baseline_run_id": baseline["run_id"],
                "config": {
                    "stopping": {
                        "max_iterations": max_iterations,
                        "max_character_delta": max_character_delta,
                    },
                    "preflight": {"skip": True},
                    "require_t1_gate": True,
                    "minimum_improvement": 0.000001,
                },
            },
        )
        run_id = str(created["id"])
        api.request("POST", f"/api/v1/optimization-runs/{run_id}/start")
        scorecard = _scorecard(baseline)
        api.request(
            "POST",
            f"/api/v1/optimization-runs/{run_id}/iterations",
            json={
                "iteration_number": 0,
                "verdict": "baseline",
                "harness_verdict": "baseline",
                "prompt_before": starting_prompt,
                "prompt_after": starting_prompt,
                "scorecard_json": scorecard,
                "scorecard_delta_json": {"delta": 0.0, "check_deltas": {}},
                "t1_gate_passed": _safe_gate(baseline),
                "trace_run_tag": baseline.get("run_tag"),
            },
        )
        guidance = api.request("POST", f"/api/v1/optimization-runs/{run_id}/next-action")
    result = {
        "optimization_run_id": run_id,
        "baseline_run_id": baseline["run_id"],
        "baseline_scorecard": scorecard,
        "prompt_file": str(prompt_file.resolve()),
        "guidance": guidance,
        "next": (
            "Make one focused prompt edit within the mutation contract, run the unchanged "
            "canonical suite with `halios eval run --json`, then record it with "
            f"`halios optimize record {run_id} --evaluation-run <run-id> "
            f"--prompt-file {prompt_file}`."
        ),
    }
    _emit(result, json_output)


@app.command("guidance")
def guidance(run_id: str, json_output: bool = typer.Option(False, "--json")) -> None:
    """Return the next bounded edit contract and negative memory for a coding agent."""
    _agent_id, credentials = _context()
    with ApiClient(credentials) as api:
        result = api.request("POST", f"/api/v1/optimization-runs/{run_id}/next-action")
    _emit(result, json_output)


@app.command("record")
def record(
    run_id: str,
    evaluation_run_id: str = typer.Option(..., "--evaluation-run"),
    prompt_file: pathlib.Path = typer.Option(..., "--prompt-file", exists=True, dir_okay=False),
    json_output: bool = typer.Option(False, "--json"),
) -> None:
    """Record one candidate using evidence from the unchanged canonical eval suite."""
    _agent_id, credentials = _context()
    prompt_after = prompt_file.read_text(encoding="utf-8")
    with ApiClient(credentials) as api:
        run = api.request("GET", f"/api/v1/optimization-runs/{run_id}")
        report = api.request("GET", f"/api/v1/runs/evaluations/{evaluation_run_id}")
        if report.get("status") not in {"completed", "failed"}:
            raise typer.BadParameter("Candidate evaluation run is not complete")
        baseline = api.request(
            "GET", f"/api/v1/runs/evaluations/{run['baseline_evaluation_run_id']}"
        )
        if report.get("suite_digest") != baseline.get("suite_digest"):
            raise typer.BadParameter("Candidate evaluation suite differs from the frozen baseline")
        if int(report.get("attempted_trial_count") or 0) != int(
            baseline.get("attempted_trial_count") or 0
        ):
            raise typer.BadParameter("Candidate trial count differs from the frozen baseline")
        iterations = run.get("iterations") or []
        candidates = [item for item in iterations if int(item.get("iteration_number") or 0) > 0]
        iteration_number = len(candidates) + 1
        prompt_before = str(run.get("current_prompt") or run.get("starting_prompt") or "")
        scorecard = _scorecard(report)
        delta = scorecard["overall_score"] - float(baseline.get("pass_at_k") or 0)
        iteration = api.request(
            "POST",
            f"/api/v1/optimization-runs/{run_id}/iterations",
            json={
                "iteration_number": iteration_number,
                "verdict": "accept" if delta > 0 and _safe_gate(report) else "discard",
                "harness_verdict": "accept" if delta > 0 and _safe_gate(report) else "discard",
                "prompt_before": prompt_before,
                "prompt_after": prompt_after,
                "scorecard_json": scorecard,
                "scorecard_delta_json": {"delta": delta, "check_deltas": {}},
                "t1_gate_passed": _safe_gate(report),
                "trace_run_tag": report.get("run_tag"),
            },
        )
        accepted = iteration.get("backend_verdict") == "accept"
        if accepted:
            api.request(
                "PATCH",
                f"/api/v1/optimization-runs/{run_id}",
                json={"status": "complete", "accepted_iteration_id": iteration["id"]},
            )
        next_action = (
            None
            if accepted
            else api.request("POST", f"/api/v1/optimization-runs/{run_id}/next-action")
        )
    result = {
        "optimization_run_id": run_id,
        "iteration": iteration,
        "accepted": accepted,
        "next_action": next_action,
        "next": (
            f"halios optimize apply {iteration['id']} --output {prompt_file} --json"
            if accepted
            else "Revert the rejected prompt edit, inspect next_action, and try one different edit."
        ),
    }
    _emit(result, json_output)
    if not accepted:
        raise typer.Exit(2)


@app.command("apply")
def apply_candidate(
    candidate_id: str,
    output: pathlib.Path | None = typer.Option(None, "--output", dir_okay=False),
    json_output: bool = typer.Option(False, "--json"),
) -> None:
    """Retrieve one backend-approved prompt candidate for repository application."""
    _agent_id, credentials = _context()
    with ApiClient(credentials) as api:
        handoff = api.request(
            "POST",
            "/api/v1/optimization-runs/candidate-handoff",
            json={"candidate_id": candidate_id},
        )
    prompt = str(handoff["prompt"])
    if output:
        atomic_write_text(output, prompt)
        handoff["output_path"] = str(output.resolve())
    handoff["next"] = (
        "Run `halios eval run --json` after applying the prompt, then use "
        f"`halios optimize verify {handoff['optimization_run_id']} --evaluation-run <run-id>`."
    )
    if json_output:
        _emit(handoff, True)
    elif output:
        typer.echo(f"Wrote backend-approved prompt to {output.resolve()}")
    else:
        typer.echo(prompt)


@app.command("verify")
def verify_candidate(
    run_id: str,
    evaluation_run_id: str = typer.Option(..., "--evaluation-run"),
    json_output: bool = typer.Option(False, "--json"),
) -> None:
    """Verify the applied candidate against the frozen baseline and unchanged suite."""
    _agent_id, credentials = _context()
    with ApiClient(credentials) as api:
        result = api.request(
            "POST",
            f"/api/v1/optimization-runs/{run_id}/verify",
            json={"evaluation_run_id": evaluation_run_id},
        )
    _emit(result, json_output)
    if not result.get("passed"):
        raise typer.Exit(2)


@app.command("list")
def list_runs(json_output: bool = typer.Option(False, "--json")) -> None:
    agent_id, credentials = _context()
    with ApiClient(credentials) as api:
        result = api.request("GET", "/api/v1/optimization-runs", params={"agent_id": agent_id})
    _emit(result, json_output)


@app.command("status")
def status(run_id: str, json_output: bool = typer.Option(False, "--json")) -> None:
    _agent_id, credentials = _context()
    with ApiClient(credentials) as api:
        result = api.request("GET", f"/api/v1/optimization-runs/{run_id}")
    _emit(result, json_output)


@app.command("cancel")
def cancel(run_id: str, json_output: bool = typer.Option(False, "--json")) -> None:
    _agent_id, credentials = _context()
    with ApiClient(credentials) as api:
        result = api.request("POST", f"/api/v1/optimization-runs/{run_id}/cancel")
    _emit(result, json_output)
