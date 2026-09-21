"""Resolve named vector-DB environments from environments.yaml.

No Qdrant client. No embeddings. Callers pass an explicit name.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
REGISTRY_PATH = ROOT / "environments.yaml"

_KEY_BY_SENSITIVITY = {
    "local": "QDRANT_LOCAL_API_KEY",
    "shared": "QDRANT_SHARED_API_KEY",
}

_READ_ONLY_KEY_BY_SENSITIVITY = {
    "local": "QDRANT_LOCAL_READ_ONLY_API_KEY",
    "shared": "QDRANT_SHARED_READ_ONLY_API_KEY",
}


@dataclass(frozen=True)
class VectorEnvironment:
    name: str
    sensitivity: str
    hosts: tuple[str, ...]
    notes: str = ""

    @property
    def url(self) -> str:
        return f"http://{self.hosts[0]}"

    @property
    def api_key_env(self) -> str:
        try:
            return _KEY_BY_SENSITIVITY[self.sensitivity]
        except KeyError as exc:
            raise ValueError(
                f"unknown sensitivity {self.sensitivity!r} for {self.name}"
            ) from exc

    def api_key(self) -> str:
        value = os.environ.get(self.api_key_env, "").strip()
        if not value:
            raise RuntimeError(f"{self.api_key_env} is not set")
        return value

    @property
    def read_only_api_key_env(self) -> str:
        try:
            return _READ_ONLY_KEY_BY_SENSITIVITY[self.sensitivity]
        except KeyError as exc:
            raise ValueError(
                f"unknown sensitivity {self.sensitivity!r} for {self.name}"
            ) from exc

    def read_only_api_key(self) -> str:
        value = os.environ.get(self.read_only_api_key_env, "").strip()
        if not value:
            raise RuntimeError(f"{self.read_only_api_key_env} is not set")
        return value


def load_registry(path: Path | None = None) -> list[VectorEnvironment]:
    data = yaml.safe_load((path or REGISTRY_PATH).read_text()) or {}
    rows = data.get("environments") or []
    environments = []
    for row in rows:
        hosts = tuple(row["hosts"])
        if not hosts:
            raise ValueError(f"{row.get('name')!r} has no hosts")
        environments.append(
            VectorEnvironment(
                name=row["name"],
                sensitivity=row["sensitivity"],
                hosts=hosts,
                notes=str(row.get("notes") or ""),
            )
        )
    return environments


def resolve(name: str, path: Path | None = None) -> VectorEnvironment:
    needle = (name or "").strip()
    if not needle:
        raise ValueError("environment name is required")
    known = load_registry(path)
    for env in known:
        if env.name == needle:
            return env
    names = ", ".join(env.name for env in known) or "(none)"
    raise KeyError(f"unknown environment {needle!r}; expected one of: {names}")


def _hostport(value: str) -> str:
    needle = (value or "").strip()
    if needle.startswith("http://"):
        needle = needle[7:]
    elif needle.startswith("https://"):
        needle = needle[8:]
    return needle.split("/", 1)[0]


def resolve_by_host(host: str, path: Path | None = None) -> VectorEnvironment:
    needle = _hostport(host)
    if not needle:
        raise ValueError("host is required")
    known = load_registry(path)
    for env in known:
        listed = {_hostport(item) for item in env.hosts}
        if needle in listed:
            return env
    hosts = ", ".join(h for env in known for h in env.hosts) or "(none)"
    raise KeyError(f"unknown host {needle!r}; expected one of: {hosts}")