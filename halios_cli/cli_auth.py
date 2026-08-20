"""User-level CLI authentication commands."""

from __future__ import annotations

import time

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

# INVARIANT: Match the server-side poll interval from CLIAuthRequestResponse.interval.
_POLL_INTERVAL_S = 2


@app.command("login")
def login(
    profile: str = typer.Option("default", "--profile"),
    base_url: str = typer.Option(DEFAULT_BASE_URL, "--base-url"),
    api_key: str | None = typer.Option(None, "--api-key", envvar="HALIOS_API_KEY", hidden=True),
) -> None:
    """Authorize this machine and store credentials outside the repository.

    Opens your browser to complete authorization.  No local HTTP server is
    started; the CLI polls the Halios API until you approve or the session expires.
    """
    normalized_url = normalize_url(base_url)

    # Fast path: explicit API key provided (e.g. CI environments or manual --api-key flag).
    if api_key:
        save_profile(profile, base_url=normalized_url, api_key=api_key)
        typer.echo(f"Logged in as profile '{profile}'.")
        return

    # --- Step 1: Request a device-code session from the backend ---
    try:
        with httpx.Client(timeout=10) as http:
            resp = http.post(
                f"{normalized_url}/api/v1/cli-auth/request",
                params={"base_url": normalized_url},
            )
            resp.raise_for_status()
            session_data = resp.json()
    except httpx.HTTPStatusError as exc:
        if exc.response.content:
            detail = exc.response.json().get("detail", exc.response.text)
        else:
            detail = str(exc)
        raise typer.BadParameter(f"Could not start login session: {detail}") from exc
    except httpx.HTTPError as exc:
        raise typer.BadParameter(
            f"Could not reach {normalized_url}. Check your network or --base-url."
        ) from exc

    device_code: str = session_data["device_code"]
    # INTENT: CLI builds verification_url itself so it uses its own configured base_url,
    # not whatever the server returned (which may differ in local dev setups).
    verification_url = f"{normalized_url}/cli-auth?code={device_code}&profile={profile}"
    expires_in: int = session_data.get("expires_in", 300)

    # --- Step 2: Open the browser and tell the user what's happening ---
    typer.echo(f"\nOpening your browser to authorize the CLI:\n  {verification_url}\n")
    typer.echo("Waiting for authorization in browser…  (Ctrl+C to cancel)\n")

    import webbrowser
    webbrowser.open(verification_url)

    # --- Step 3: Poll until authorized, denied, or expired ---
    poll_url = f"{normalized_url}/api/v1/cli-auth/poll"
    deadline = time.monotonic() + expires_in

    try:
        with httpx.Client(timeout=10) as http:
            while time.monotonic() < deadline:
                time.sleep(_POLL_INTERVAL_S)
                try:
                    poll_resp = http.get(poll_url, params={"code": device_code})
                    poll_resp.raise_for_status()
                    result = poll_resp.json()
                except httpx.HTTPError:
                    # WHY: Transient network errors should not abort the wait.
                    continue

                poll_status: str = result.get("status", "expired")

                if poll_status == "pending":
                    continue

                if poll_status == "authorized":
                    save_profile(
                        profile,
                        base_url=normalized_url,
                        api_key=result["api_key"],
                        organization_id=result.get("organization_id"),
                        api_key_id=int(result["api_key_id"]) if result.get("api_key_id") else None,
                        expires_at=result.get("expires_at"),
                    )
                    typer.echo(f"Logged in as profile '{profile}'.")
                    return

                if poll_status == "denied":
                    raise typer.BadParameter("Authorization was cancelled in the browser.")

                # status == "expired" or unknown
                raise typer.BadParameter(
                    "Login session expired. Please run 'halios auth login' again."
                )

    except KeyboardInterrupt:
        typer.echo("\nLogin cancelled.")
        raise typer.Exit(code=1)

    raise typer.BadParameter("Login timed out. Please run 'halios auth login' again.")


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
