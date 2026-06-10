from __future__ import annotations

import argparse
from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from app.config import get_settings
from app.launchdarkly_projects import LaunchDarklyProjectError, LaunchDarklyProjectManager


def _upsert_env_value(env_path: Path, key: str, value: str) -> None:
    lines: list[str] = []
    if env_path.exists():
        lines = env_path.read_text(encoding="utf-8").splitlines()

    replaced = False
    for idx, line in enumerate(lines):
        if line.startswith(f"{key}="):
            lines[idx] = f"{key}={value}"
            replaced = True
            break

    if not replaced:
        lines.append(f"{key}={value}")

    env_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Create or fetch a LaunchDarkly project and SDK keys.")
    parser.add_argument("--project-key", help="LaunchDarkly project key (e.g. decor-agent-ai)")
    parser.add_argument("--project-name", help="LaunchDarkly project display name")
    parser.add_argument(
        "--write-env",
        action="store_true",
        help="Write production SDK key to .env as LD_SDK_KEY",
    )
    parser.add_argument(
        "--env-file",
        default=".env",
        help="Path to env file to update when --write-env is enabled",
    )
    args = parser.parse_args()

    settings = get_settings()
    project_key = args.project_key or settings.ld_project_key
    project_name = args.project_name or settings.ld_project_name or "Decor Agent AI"

    if not project_key:
        raise LaunchDarklyProjectError(
            "Project key required. Set LAUNCHDARKLY_PROJECT_KEY or pass --project-key."
        )

    manager = LaunchDarklyProjectManager(api_token=settings.ld_api_token)
    manager.create_or_get_project(key=project_key, name=project_name, tags=["ai-configs"])
    sdk_keys = manager.extract_sdk_keys(key=project_key)

    print(f"Project ready: {project_key}")
    for env, sdk_key in sdk_keys.items():
        print(f"{env}: {sdk_key}")

    if args.write_env:
        production_key = sdk_keys.get("production")
        if not production_key:
            raise LaunchDarklyProjectError("No production SDK key found in project environments.")
        _upsert_env_value(Path(args.env_file), "LD_SDK_KEY", production_key)
        print(f"Updated {args.env_file} with LD_SDK_KEY for production.")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
