from __future__ import annotations

from dataclasses import dataclass

import requests

BASE_URL = "https://app.launchdarkly.com/api/v2"


class LaunchDarklyProjectError(RuntimeError):
    """Raised when LaunchDarkly project operations fail."""


@dataclass
class LaunchDarklyProjectManager:
    api_token: str
    timeout_seconds: int = 15

    def __post_init__(self) -> None:
        if not self.api_token:
            raise LaunchDarklyProjectError(
                "Missing LaunchDarkly API token. Set LAUNCHDARKLY_API_TOKEN."
            )
        self._headers = {
            "Authorization": self.api_token,
            "Content-Type": "application/json",
        }

    def create_or_get_project(self, *, key: str, name: str, tags: list[str] | None = None) -> dict:
        payload: dict[str, object] = {"key": key, "name": name}
        if tags:
            payload["tags"] = tags

        response = requests.post(
            f"{BASE_URL}/projects",
            headers=self._headers,
            json=payload,
            timeout=self.timeout_seconds,
        )

        if response.status_code == 201:
            return response.json()
        if response.status_code == 409:
            project = self.get_project(key=key)
            if project is None:
                raise LaunchDarklyProjectError(
                    f"Project '{key}' already exists but could not be fetched."
                )
            return project
        self._raise_for_failure(response)
        return {}

    def get_project(self, *, key: str) -> dict | None:
        response = requests.get(
            f"{BASE_URL}/projects/{key}",
            headers=self._headers,
            params={"expand": "environments"},
            timeout=self.timeout_seconds,
        )
        if response.status_code == 200:
            return response.json()
        if response.status_code == 404:
            return None
        self._raise_for_failure(response)
        return None

    def extract_sdk_keys(self, *, key: str) -> dict[str, str]:
        project = self.get_project(key=key)
        if not project:
            raise LaunchDarklyProjectError(f"Project '{key}' was not found.")

        environments = project.get("environments", {})
        items = environments.get("items", []) if isinstance(environments, dict) else environments
        sdk_keys: dict[str, str] = {}
        for env in items:
            env_key = env.get("key")
            api_key = env.get("apiKey")
            if env_key and api_key:
                sdk_keys[str(env_key)] = str(api_key)
        return sdk_keys

    @staticmethod
    def _raise_for_failure(response: requests.Response) -> None:
        try:
            payload = response.json()
        except ValueError:
            payload = {"message": response.text}
        message = payload.get("message") or payload.get("code") or "Unknown API error"
        raise LaunchDarklyProjectError(f"LaunchDarkly API error ({response.status_code}): {message}")
