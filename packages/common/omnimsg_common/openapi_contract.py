"""Load and cache the public OpenAPI contract (ADR-0005, ADR-0021)."""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

# Well-known locations (Docker WORKDIR /app, then repo-relative for local/tests).
_CANDIDATE_PATHS = (
    Path("/app/packages/contracts/openapi/openapi.yaml"),
    Path(__file__).resolve().parents[3] / "packages" / "contracts" / "openapi" / "openapi.yaml",
)


class OpenAPIContractError(RuntimeError):
    """Contract missing or invalid — gateway must fail-fast."""


@dataclass(frozen=True)
class LoadedOpenAPIContract:
    """Preloaded contract bytes for public /openapi.json."""

    path: Path
    document: dict[str, Any]
    json_bytes: bytes
    etag: str
    contract_version: str


def resolve_contract_path(explicit: str | None = None) -> Path:
    """Resolve openapi.yaml path (OPENAPI_CONTRACT_PATH or well-known locations)."""
    if explicit is not None:
        raw = explicit
    else:
        raw = os.environ.get("OPENAPI_CONTRACT_PATH", "")
    env_path = raw.strip()
    if env_path:
        path = Path(env_path)
        if path.is_file():
            return path.resolve()
        raise OpenAPIContractError(f"OpenAPI contract not found: {path}")

    candidates = list(_CANDIDATE_PATHS)
    cwd = Path.cwd() / "packages" / "contracts" / "openapi" / "openapi.yaml"
    candidates.append(cwd)
    for path in candidates:
        if path.is_file():
            return path.resolve()
    searched = ", ".join(str(p) for p in candidates)
    raise OpenAPIContractError(f"OpenAPI contract not found; searched: {searched}")


def load_openapi_contract(path: Path | None = None) -> LoadedOpenAPIContract:
    """Load YAML, validate shape, materialize JSON bytes + ETag."""
    resolved = path if path is not None else resolve_contract_path()
    if not resolved.is_file():
        raise OpenAPIContractError(f"OpenAPI contract not found: {resolved}")
    try:
        raw = resolved.read_text(encoding="utf-8")
        document = yaml.safe_load(raw)
    except OSError as exc:
        raise OpenAPIContractError(f"Cannot read OpenAPI contract: {resolved}") from exc
    except yaml.YAMLError as exc:
        raise OpenAPIContractError(f"Invalid OpenAPI YAML: {resolved}") from exc

    if not isinstance(document, dict):
        raise OpenAPIContractError("OpenAPI root must be a mapping")
    if "openapi" not in document:
        raise OpenAPIContractError("OpenAPI document missing 'openapi' field")
    if not isinstance(document.get("paths"), dict) or not document["paths"]:
        raise OpenAPIContractError("OpenAPI document missing non-empty 'paths'")

    info = document.get("info")
    if not isinstance(info, dict):
        raise OpenAPIContractError("OpenAPI document missing 'info'")
    contract_version = info.get("x-contract-version")
    if not isinstance(contract_version, str) or not contract_version.strip():
        raise OpenAPIContractError("OpenAPI info.x-contract-version is required")

    json_bytes = json.dumps(document, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    digest = hashlib.sha256(json_bytes).hexdigest()
    etag = f'"{digest}"'
    return LoadedOpenAPIContract(
        path=resolved,
        document=document,
        json_bytes=json_bytes,
        etag=etag,
        contract_version=contract_version.strip(),
    )


def public_v1_operations(document: dict[str, Any]) -> set[tuple[str, str]]:
    """Return (METHOD, path) pairs under /v1 from the contract."""
    methods = {"get", "post", "put", "patch", "delete", "options", "head"}
    found: set[tuple[str, str]] = set()
    paths = document.get("paths") or {}
    for path, item in paths.items():
        if not isinstance(path, str) or not path.startswith("/v1"):
            continue
        if not isinstance(item, dict):
            continue
        for method, op in item.items():
            if method.lower() in methods and isinstance(op, dict):
                found.add((method.upper(), path))
    return found
