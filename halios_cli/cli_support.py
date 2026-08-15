"""Shared CLI configuration, credentials, HTTP, and project helpers."""

from __future__ import annotations

import hashlib
import json
import os
import pathlib
import platform
import re
import subprocess
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

import httpx
import typer

DEFAULT_BASE_URL = "https://app.halios.ai"


class ApiError(typer.BadParameter):
    def __init__(self, status_code: int, detail: Any):
        self.status_code = status_code
        self.detail = detail
        super().__init__(f"Halios API {status_code}: {detail}")


def normalize_url(value: str) -> str:
    return (value if "://" in value else f"http://{value}").rstrip("/")


def credentials_path() -> pathlib.Path:
    if os.getenv("HALIOS_CONFIG_HOME"):
        root = pathlib.Path(os.environ["HALIOS_CONFIG_HOME"])
    elif os.getenv("XDG_CONFIG_HOME"):
        root = pathlib.Path(os.environ["XDG_CONFIG_HOME"]) / "halios"
    elif platform.system() == "Darwin":
        root = pathlib.Path.home() / "Library" / "Application Support" / "halios"
    elif platform.system() == "Windows" and os.getenv("APPDATA"):
        root = pathlib.Path(os.environ["APPDATA"]) / "Halios"
    else:
        root = pathlib.Path.home() / ".config" / "halios"
    return root / "credentials.json"


def _read_credentials() -> dict[str, Any]:
    path = credentials_path()
    if not path.exists():
        return {"version": 1, "profiles": {}}
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise typer.BadParameter(f"Invalid CLI credential file: {exc}") from exc
    return value if isinstance(value, dict) else {"version": 1, "profiles": {}}


def _write_credentials(value: dict[str, Any]) -> None:
    path = credentials_path()
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    descriptor, temporary_name = tempfile.mkstemp(prefix="credentials-", dir=path.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(value, handle, indent=2, sort_keys=True)
            handle.write("\n")
        os.chmod(temporary_name, 0o600)
        os.replace(temporary_name, path)
        os.chmod(path, 0o600)
    finally:
        if os.path.exists(temporary_name):
            os.unlink(temporary_name)


def save_profile(
    profile: str,
    *,
    base_url: str,
    api_key: str,
    organization_id: str | None = None,
    api_key_id: int | None = None,
    expires_at: str | None = None,
) -> None:
    payload = _read_credentials()
    profiles = payload.setdefault("profiles", {})
    previous = profiles.get(profile) if isinstance(profiles.get(profile), dict) else {}
    profiles[profile] = {
        **previous,
        "base_url": normalize_url(base_url),
        "api_key": api_key,
        "organization_id": organization_id,
        "api_key_id": api_key_id,
        "expires_at": expires_at,
    }
    _write_credentials(payload)


def delete_profile(profile: str) -> bool:
    payload = _read_credentials()
    removed = payload.setdefault("profiles", {}).pop(profile, None) is not None
    if removed:
        _write_credentials(payload)
    return removed


def save_agent_ingest_token(profile: str, agent_id: str, token: str) -> None:
    payload = _read_credentials()
    entry = payload.setdefault("profiles", {}).get(profile)
    if not isinstance(entry, dict):
        raise typer.BadParameter(f"CLI profile '{profile}' is not logged in")
    agents = entry.setdefault("agents", {})
    agents[agent_id] = {"otlp_token": token}
    _write_credentials(payload)


@dataclass(frozen=True)
class Credentials:
    profile: str
    base_url: str
    api_key: str
    organization_id: str | None
    otlp_token: str | None = None
    api_key_id: int | None = None
    expires_at: str | None = None


def stored_profile_credentials(profile: str = "default") -> Credentials | None:
    """Return one stored profile without allowing environment variables to replace its key."""
    entry = _read_credentials().get("profiles", {}).get(profile)
    if not isinstance(entry, dict) or not entry.get("api_key"):
        return None
    raw_key_id = entry.get("api_key_id")
    return Credentials(
        profile=profile,
        base_url=normalize_url(str(entry.get("base_url") or DEFAULT_BASE_URL)),
        api_key=str(entry["api_key"]),
        organization_id=entry.get("organization_id"),
        api_key_id=raw_key_id if isinstance(raw_key_id, int) else None,
        expires_at=str(entry["expires_at"]) if entry.get("expires_at") else None,
    )


def resolve_credentials(profile: str = "default", agent_id: str | None = None) -> Credentials:
    payload = _read_credentials()
    entry = payload.get("profiles", {}).get(profile)
    env_key = os.getenv("HALIOS_API_KEY")
    if not isinstance(entry, dict) and not env_key:
        raise typer.BadParameter("Not logged in. Run `halios auth login` or set HALIOS_API_KEY.")
    entry = entry if isinstance(entry, dict) else {}
    base_url = normalize_url(
        os.getenv("HALIOS_BASE_URL") or str(entry.get("base_url") or DEFAULT_BASE_URL)
    )
    # INTENT: CI runners need both control-plane and agent-scoped ingest credentials without
    # writing a persistent profile to the ephemeral filesystem.
    token = os.getenv("HALIOS_OTLP_TOKEN")
    if agent_id:
        agent_entry = (entry.get("agents") or {}).get(agent_id)
        if not token and isinstance(agent_entry, dict):
            token = agent_entry.get("otlp_token")
    return Credentials(
        profile=profile,
        base_url=base_url,
        api_key=env_key or str(entry.get("api_key") or ""),
        organization_id=entry.get("organization_id"),
        otlp_token=token,
        api_key_id=entry.get("api_key_id") if isinstance(entry.get("api_key_id"), int) else None,
        expires_at=str(entry["expires_at"]) if entry.get("expires_at") else None,
    )


class ApiClient:
    def __init__(self, credentials: Credentials):
        from ._version import __version__

        self.credentials = credentials
        self.client = httpx.Client(
            base_url=credentials.base_url,
            headers={
                "Authorization": f"Bearer {credentials.api_key}",
                "User-Agent": f"haliosai-cli/{__version__}",
            },
            timeout=30.0,
        )

    def request(self, method: str, path: str, **kwargs: Any) -> Any:
        response = self.client.request(method, path, **kwargs)
        if response.is_error:
            try:
                detail = response.json().get("detail", response.text)
            except (ValueError, AttributeError):
                detail = response.text
            raise ApiError(response.status_code, detail)
        return response.json() if response.content else None

    def close(self) -> None:
        self.client.close()

    def __enter__(self) -> "ApiClient":
        return self

    def __exit__(self, *_args: Any) -> None:
        self.close()


def load_yaml(path: pathlib.Path) -> dict[str, Any]:
    import yaml

    if not path.exists():
        raise typer.BadParameter(f"Missing required file: {path}")
    value = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(value, dict):
        raise typer.BadParameter(f"YAML root must be an object: {path}")
    return value


def write_yaml(path: pathlib.Path, value: dict[str, Any]) -> None:
    import yaml

    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(prefix=f"{path.name}-", dir=path.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            yaml.safe_dump(value, handle, sort_keys=False)
        os.replace(temporary_name, path)
    finally:
        if os.path.exists(temporary_name):
            os.unlink(temporary_name)


def atomic_write_text(path: pathlib.Path, content: str) -> None:
    """Replace one text file atomically, preserving its existing permission bits."""
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(prefix=f"{path.name}-", dir=path.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        if path.exists():
            os.chmod(temporary_name, path.stat().st_mode & 0o777)
        os.replace(temporary_name, path)
    finally:
        if os.path.exists(temporary_name):
            os.unlink(temporary_name)


def evaluation_suite_digest(eval_plan: dict[str, Any], scenarios: dict[str, Any]) -> str:
    canonical = json.dumps(
        {"eval": eval_plan, "scenarios": scenarios},
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )
    return f"sha256:{hashlib.sha256(canonical.encode('utf-8')).hexdigest()}"


def write_suite_checkout(
    root: pathlib.Path,
    *,
    eval_plan: dict[str, Any],
    scenarios: dict[str, Any],
    revision: int,
    digest: str | None,
) -> None:
    """Replace both canonical YAML values and their shared checkout revision."""
    halios_dir = root / ".halios"
    write_yaml(halios_dir / "eval.yml", eval_plan)
    write_yaml(halios_dir / "scenarios.yml", scenarios)
    config_path = halios_dir / "config.toml"
    content = config_path.read_text(encoding="utf-8")
    suite_block = (
        f'[suite]\nrevision = {revision}\ndigest = "{str(digest or "").replace(chr(34), "")}"\n'
    )
    if "[suite]" in content:
        content = re.sub(r"(?ms)^\[suite\]\n.*?(?=^\[|\Z)", suite_block + "\n", content)
    else:
        content = content.rstrip() + "\n\n" + suite_block
    descriptor, temporary_name = tempfile.mkstemp(prefix="config-", dir=halios_dir)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(content)
        os.replace(temporary_name, config_path)
    finally:
        if os.path.exists(temporary_name):
            os.unlink(temporary_name)


def preserve_suite_recovery(
    *,
    agent_id: str,
    eval_plan: dict[str, Any],
    scenarios: dict[str, Any],
) -> pathlib.Path:
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    parent = credentials_path().parent / "recovery" / agent_id
    parent.mkdir(parents=True, exist_ok=True)
    recovery = pathlib.Path(tempfile.mkdtemp(prefix=f"{timestamp}-", dir=parent))
    write_yaml(recovery / "eval.yml", eval_plan)
    write_yaml(recovery / "scenarios.yml", scenarios)
    return recovery


def load_project_config(root: pathlib.Path | None = None) -> tuple[pathlib.Path, dict[str, Any]]:
    project_root = (root or pathlib.Path.cwd()).resolve()
    path = project_root / ".halios" / "config.toml"
    if not path.exists():
        raise typer.BadParameter("No .halios/config.toml. Run `halios project init --agent ...`.")
    try:
        import tomllib
    except ImportError:  # pragma: no cover - Python 3.10
        import tomli as tomllib  # type: ignore[no-redef]
    with path.open("rb") as handle:
        config = tomllib.load(handle)
    return project_root, config


def git_provenance(root: pathlib.Path) -> dict[str, Any]:
    from ._version import __version__

    def run(*args: str) -> str | None:
        result = subprocess.run(
            ["git", *args], cwd=root, text=True, capture_output=True, check=False
        )
        return result.stdout.strip() if result.returncode == 0 else None

    commit_sha = run("rev-parse", "HEAD")
    branch = run("branch", "--show-current")
    repository = run("config", "--get", "remote.origin.url")
    tracked_dirty = any(
        subprocess.run(["git", *args], cwd=root, check=False).returncode != 0
        for args in (("diff", "--quiet"), ("diff", "--cached", "--quiet"))
    )
    definition_paths = [
        ".halios/config.toml",
        ".halios/eval.yml",
        ".halios/scenarios.yml",
    ]
    definitions_tracked = (
        subprocess.run(
            ["git", "ls-files", "--error-unmatch", *definition_paths],
            cwd=root,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        ).returncode
        == 0
    )
    github_run_id = os.getenv("GITHUB_RUN_ID")
    github_repository = os.getenv("GITHUB_REPOSITORY")
    github_server = os.getenv("GITHUB_SERVER_URL")
    pipeline_url = os.getenv("CI_PIPELINE_URL")
    if github_run_id and github_repository and github_server:
        pipeline_url = f"{github_server}/{github_repository}/actions/runs/{github_run_id}"
    return {
        "repository": repository,
        "branch": branch,
        "commit_sha": commit_sha,
        "dirty_worktree": tracked_dirty or not definitions_tracked,
        "actor": os.getenv("GITHUB_ACTOR") or os.getenv("GITLAB_USER_LOGIN") or os.getenv("USER"),
        "pipeline_id": github_run_id or os.getenv("CI_PIPELINE_ID"),
        "pipeline_url": pipeline_url,
        "job_id": os.getenv("GITHUB_JOB") or os.getenv("CI_JOB_ID"),
        "environment": os.getenv("DEPLOYMENT_ENVIRONMENT")
        or ("ci" if os.getenv("CI") else "local"),
        "client_name": os.getenv("HALIOS_CLIENT_NAME") or "halios-cli",
        "client_version": __version__,
        # INTENT: Device identity is opt-in. Do not turn a raw hostname into a
        # durable product identifier or leak it into shared evaluation data.
        "source_label": os.getenv("HALIOS_SOURCE_LABEL"),
        "service_name": os.getenv("OTEL_SERVICE_NAME"),
        "service_instance_id": os.getenv("OTEL_SERVICE_INSTANCE_ID")
        or os.getenv("HALIOS_SOURCE_ID"),
    }
