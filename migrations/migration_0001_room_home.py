"""
Migration 0001: Safely migrate legacy room dicts to a default home-aware structure.

Recovery and Rollback Procedure:
- This migration is idempotent: re-running will *not* corrupt data and will pick up incomplete work.
- Partial writes/interrupted migration: restore from pre-migration backup (copy your data/projects.json or configured project path). Then re-run.
- Rollback: restore backup file (pre-migration projects.json). Alternatively, to reverse the migration after completion, restore all `rooms` dicts to single-key (context_key) with string room keys, moving any home_id fields to None. This reversal is not automatic.
- Safe to run with mixed legacy/migrated data; every room will end up associated to a valid home_id (the context_key by default). All fields are preserved, including briefs, boards, cart, approvals, context keys, project links (context_key), and per-room metadata. Crash at any point is recoverable by restoring from backup and re-running.

USAGE: Run as a script:
    python -m migrations.migration_0001_room_home <project_json_path>
"""

import sys
import json
from pathlib import Path

PROJECTS_KEY = "projects"

# Accepts the file to migrate as an argument
if __name__ == "__main__":
    if len(sys.argv) != 2:
        print(
            "Usage: python -m migrations.migration_0001_room_home <project_json_path>"
        )
        sys.exit(1)
    fpath = Path(sys.argv[1])
    raw = json.loads(fpath.read_text())
    changed = False
    for context_key, pdata in (raw.get(PROJECTS_KEY) or {}).items():
        rooms = pdata.get("rooms")
        if not rooms:
            continue
        # Already-migrated check: if all keys are JSON lists of length 2, treat as migrated
        all_migrated = True
        for k in rooms.keys():
            if isinstance(k, str) and k.startswith("["):
                try:
                    dec = json.loads(k)
                    if not (isinstance(dec, list) and len(dec) == 2):
                        all_migrated = False
                        break
                except Exception:
                    all_migrated = False
                    break
            else:
                all_migrated = False
                break
        if all_migrated:
            continue  # No change needed
        # Migrate legacy dict
        migrated = {}
        for room_key, room_dict in rooms.items():
            orig_key = room_key
            # Unify path: if room_key is JSONified tuple
            if isinstance(room_key, str) and room_key.startswith("["):
                try:
                    k_dec = json.loads(room_key)
                    if isinstance(k_dec, list) and len(k_dec) == 2:
                        migrated[tuple(k_dec)] = room_dict
                        continue
                except Exception:
                    pass
            if isinstance(room_key, list) and len(room_key) == 2:
                migrated[tuple(room_key)] = room_dict
                continue
            # legacy string key
            new_home_id = room_dict.get("home_id") or context_key
            new_key = (new_home_id, room_key)
            if not room_dict.get("home_id"):
                room_dict = dict(room_dict)
                room_dict["home_id"] = new_home_id
            migrated[new_key] = room_dict
        migrated_json = {}
        for k, v in migrated.items():
            k_json = json.dumps(list(k))
            migrated_json[k_json] = v
        # Only set pdata['rooms'] if it's different (prevents writing/backups for no-ops)
        if rooms != migrated_json:
            pdata["rooms"] = migrated_json
            changed = True
    if changed:
        backup = fpath.with_suffix(fpath.suffix + ".bak")
        fpath.replace(backup)
        fpath.write_text(json.dumps(raw, indent=2))
        print(f"Migrated and backed up original to: {backup}")
    else:
        print("No migration needed; all records are already home-aware.")


# Utility for import (for test loaders):
def migrate_project_dict(projects_dict: dict) -> dict:
    """
    Run the migration logic on an in-memory decoded dict (as parsed from JSON).
    Mutates in place and returns the migrated dict.
    """
    for context_key, pdata in (projects_dict.get(PROJECTS_KEY) or {}).items():
        rooms = pdata.get("rooms")
        if not rooms:
            continue
        if all(
            (isinstance(k, list) and len(k) == 2)
            or (k.startswith("[") and len(json.loads(k)) == 2)
            for k in rooms.keys()
        ):
            continue  # already migrated
        migrated = {}
        for room_key, room_dict in rooms.items():
            orig_key = room_key
            if isinstance(room_key, str) and room_key.startswith("["):
                try:
                    k_dec = json.loads(room_key)
                    if isinstance(k_dec, list) and len(k_dec) == 2:
                        migrated[tuple(k_dec)] = room_dict
                        continue
                except Exception:
                    pass
            if isinstance(room_key, list) and len(room_key) == 2:
                migrated[tuple(room_key)] = room_dict
                continue
            # legacy string key
            new_home_id = room_dict.get("home_id") or context_key
            new_key = (new_home_id, room_key)
            if not room_dict.get("home_id"):
                room_dict = dict(room_dict)
                room_dict["home_id"] = new_home_id
            migrated[new_key] = room_dict
        migrated_json = {}
        for k, v in migrated.items():
            k_json = json.dumps(list(k))
            migrated_json[k_json] = v
        pdata["rooms"] = migrated_json
    return projects_dict


# END

# Test coverage and fixtures are required and will be provided in a subsequent step.
# This script is importable and testable; see migrate_project_dict for in-memory ops.
