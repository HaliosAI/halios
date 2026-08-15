"""Opinionated Halios CLI entry point."""

import typer

from ._version import __version__
from .cli_auth import app as auth_app
from .cli_eval import app as eval_app
from .cli_optimize import app as optimize_app
from .cli_project import app as project_app
from .cli_scenario import app as scenario_app
from .cli_trace import app as trace_app

app = typer.Typer(
    name="halios",
    help="Scenario simulations and reliability gates for AI agents.",
    no_args_is_help=True,
    add_completion=False,
)
app.add_typer(auth_app, name="auth")
app.add_typer(project_app, name="project")
app.add_typer(eval_app, name="eval")
app.add_typer(scenario_app, name="scenario")
app.add_typer(trace_app, name="trace")
app.add_typer(optimize_app, name="optimize")


def _version_callback(value: bool) -> None:
    if value:
        typer.echo(__version__)
        raise typer.Exit()


@app.callback()
def main(
    version: bool = typer.Option(
        False,
        "--version",
        callback=_version_callback,
        is_eager=True,
        help="Show the installed Halios CLI version.",
    ),
) -> None:
    """Scenario simulations and reliability gates for AI agents."""


if __name__ == "__main__":
    app()
