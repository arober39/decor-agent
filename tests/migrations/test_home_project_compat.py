import tempfile
import json
from pathlib import Path
from app import store


def test_home_registry_compat_with_legacy_room_persistence():
    # Rooms persisted without home registry under flag-off
    with tempfile.TemporaryDirectory() as folder:
        path = Path(folder) / "projects.json"
        store.disable_persist()
        store.reset()
        store.enable_persist(path)
        try:
            created = store.create_room("Legacy Room")
            key = created.context_key
            store.set_budget(key, 500)
            store.reset()
            store.enable_persist(path)
            data = json.loads(path.read_text())
            # Only 'projects', no 'homes'
            assert "projects" in data
            assert "homes" not in data or data["homes"] == []
        finally:
            store.disable_persist()
            store.reset()


def test_home_registry_no_rewrite_of_existing_legacy_records():
    # Room legacy data is never rewritten, even if flag-on toggles home registry persistence; existing entries untouched
    with tempfile.TemporaryDirectory() as folder:
        path = Path(folder) / "projects.json"
        # First write some legacy data (simulate an older version)
        projects_data = {
            "projects": {"ctx-1": {"context_key": "ctx-1"}},
            "transcripts": {},
            "priors": {},
        }
        path.write_text(json.dumps(projects_data))
        store.disable_persist()
        store.reset()
        store.enable_persist(path)
        # Simulate turning on flag and home registry: registry changes will NOT alter legacy keys
        orig_should_use_home = getattr(store, "_should_use_home_registry")
        try:
            # Force-enable home registry for this test
            store._should_use_home_registry = lambda: True
            store.enable_home_registry_persist(path)
            # Add a home
            home = store.create_home("ABC Home")
            # Legacy project data is preserved
            store.reset_home_registry()
            with open(path) as f:
                out = json.load(f)
            assert "projects" in out
            assert out["projects"] == projects_data["projects"]
            assert any(h["display_name"] == "ABC Home" for h in out.get("homes", []))
        finally:
            store._should_use_home_registry = orig_should_use_home
            store.disable_home_registry_persist()
            store.reset_home_registry()
