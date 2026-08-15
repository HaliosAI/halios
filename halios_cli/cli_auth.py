"""User-level CLI authentication commands."""

from __future__ import annotations

import json
import secrets
import threading
import urllib.parse
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import httpx
import typer

from .cli_support import (
    DEFAULT_BASE_URL,
    ApiClient,
    ApiError,
    delete_profile,
    normalize_url,
    resolve_credentials,
    save_profile,
    stored_profile_credentials,
)

app = typer.Typer(help="Authenticate the Halios CLI.", no_args_is_help=True)


@app.command("login")
def login(
    profile: str = typer.Option("default", "--profile"),
    base_url: str = typer.Option(DEFAULT_BASE_URL, "--base-url"),
    api_key: str | None = typer.Option(None, "--api-key", envvar="HALIOS_API_KEY", hidden=True),
) -> None:
    """Authorize this machine and store credentials outside the repository."""
    normalized_url = normalize_url(base_url)
    if api_key:
        save_profile(profile, base_url=normalized_url, api_key=api_key)
        typer.echo(f"Logged in as profile '{profile}'.")
        return

    result: dict[str, str] = {}
    completed = threading.Event()
    state = secrets.token_urlsafe(24)

    class CallbackHandler(BaseHTTPRequestHandler):
        def _cors(self) -> None:
            self.send_header("Access-Control-Allow-Origin", normalized_url)
            self.send_header("Access-Control-Allow-Methods", "POST, OPTIONS")
            self.send_header("Access-Control-Allow-Headers", "Content-Type")

        def do_OPTIONS(self) -> None:  # noqa: N802
            self.send_response(204)
            self._cors()
            self.end_headers()

        def do_POST(self) -> None:  # noqa: N802
            if self.path != "/callback":
                self.send_error(404)
                return
            length = int(self.headers.get("content-length") or 0)
            try:
                body = json.loads(self.rfile.read(length))
            except (ValueError, UnicodeDecodeError):
                self.send_error(400)
                return
            if not isinstance(body, dict) or not secrets.compare_digest(
                str(body.get("state") or ""), state
            ):
                self.send_error(422)
                return
            if body.get("error"):
                result["error"] = str(body["error"])
            elif body.get("api_key"):
                result.update({key: str(value) for key, value in body.items() if value is not None})
            else:
                self.send_error(422)
                return
            self.send_response(204)
            self._cors()
            self.end_headers()
            completed.set()

        def log_message(self, _format: str, *_args: object) -> None:
            return

    server = ThreadingHTTPServer(("127.0.0.1", 0), CallbackHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    login_url = f"{normalized_url}/cli-login?" + urllib.parse.urlencode(
        {"port": server.server_port, "profile": profile, "state": state}
    )
    typer.echo(f"Open this URL to authorize the CLI:\n{login_url}")
    webbrowser.open(login_url)
    try:
        if not completed.wait(timeout=300):
            raise typer.BadParameter("Login timed out after 5 minutes")
    finally:
        server.shutdown()
        server.server_close()

    if result.get("error") == "access_denied":
        raise typer.BadParameter("Authorization was cancelled in the browser")
    if result.get("error"):
        raise typer.BadParameter(f"Authorization failed: {result['error']}")

    save_profile(
        profile,
        base_url=normalized_url,
        api_key=result["api_key"],
        organization_id=result.get("organization_id"),
        api_key_id=int(result["api_key_id"]) if result.get("api_key_id") else None,
        expires_at=result.get("expires_at"),
    )
    typer.echo(f"Logged in as profile '{profile}'.")


@app.command("status")
def status(profile: str = typer.Option("default", "--profile")) -> None:
    """Verify the selected profile without exposing its credential."""
    credentials = resolve_credentials(profile)
    with ApiClient(credentials) as api:
        api.request("GET", "/api/v1/agents", params={"limit": 1})
    expiry = f" Credential expires {credentials.expires_at}." if credentials.expires_at else ""
    typer.echo(f"Authenticated profile '{profile}' at {credentials.base_url}.{expiry}")


@app.command("logout")
def logout(
    profile: str = typer.Option("default", "--profile"),
    local_only: bool = typer.Option(
        False,
        "--local-only",
        help="Remove local credentials without revoking the remote key.",
    ),
) -> None:
    """Revoke one CLI credential, then remove its local profile."""
    credentials = stored_profile_credentials(profile)
    if credentials is None:
        typer.echo(f"Profile '{profile}' was not stored.")
        return

    if not local_only:
        try:
            with ApiClient(credentials) as api:
                api.request("DELETE", "/api/v1/api-keys/current")
        except ApiError as exc:
            if exc.status_code != 401:
                raise typer.BadParameter(
                    "Remote revocation failed; local credentials were kept. "
                    "Retry, or use --local-only if the server is permanently unavailable."
                ) from exc
            typer.echo("The remote credential was already invalid or expired.")
        except httpx.HTTPError as exc:
            raise typer.BadParameter(
                "Could not reach Halios to revoke the credential; local credentials were kept. "
                "Retry, or use --local-only if the server is permanently unavailable."
            ) from exc

    delete_profile(profile)
    suffix = " locally (remote key unchanged)" if local_only else " and revoked its API key"
    typer.echo(f"Removed profile '{profile}'{suffix}.")
