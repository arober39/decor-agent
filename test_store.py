import tempfile
from pathlib import Path

from app import store


def setup_function() -> None:
    store.disable_persist()
    store.reset()


def test_snapshot_starts_empty() -> None:
    data = store.snapshot("p1")
    assert data["status"] == "intake"
    assert data["spec_list"] == []
    assert data["budget"]["total_cents"] is None


def test_add_spec_rejects_unknown_sku() -> None:
    store.upsert_room("p1", name="living room", room_type="living")
    try:
        store.add_spec("p1", "FAKE-SKU", "living room")
        raise AssertionError("expected unknown sku")
    except ValueError as exc:
        assert "Unknown sku" in str(exc)


def test_approve_commits_drafts() -> None:
    store.upsert_room("p1", name="office", room_type="office")
    store.add_spec("p1", "IKE-DESK-BEK", "office")
    store.request_approval("p1", "spec", "WFH desk")
    project = store.get_or_create("p1")
    assert project.spec_list[0].status == "draft"
    store.approve("p1", "spec")
    assert project.spec_list[0].status == "committed"
    assert project.status == "complete"


def test_add_spec_keeps_lane() -> None:
    store.upsert_room("p1", name="living room", room_type="living")
    store.add_spec(
        "p1", "RUG-8X10-JUT", "living room", lane="close", why="jute, not rust"
    )
    item = store.get_or_create("p1").spec_list[0]
    assert item.lane == "close"
    assert item.why == "jute, not rust"


def test_add_spec_rejects_skip_lane() -> None:
    store.upsert_room("p1", name="living room", room_type="living")
    try:
        store.add_spec("p1", "ART-SOFA-721", "living room", lane="skip")
        raise AssertionError("expected skip rejection")
    except ValueError as exc:
        assert "skip" in str(exc)


def test_apply_sample_board_maps_lanes_and_skips() -> None:
    project = store.apply_sample_board("board-1")
    data = project.as_public_dict()
    lanes = {item.sku: item.lane for item in project.spec_list}
    assert lanes["ART-SOFA-721"] == "must"
    assert lanes["RUG-8X10-RST"] == "must"
    assert lanes["ART-COF-MRB"] == "close"
    assert lanes["ART-LAMP-CER"] == "close"
    assert lanes["ART-CHAIR-MOH"] == "close"
    assert lanes["WSM-DRAPE-LN"] == "close"
    assert project.skipped == []
    assert all(item.sku for item in project.spec_list)
    assert data["pending_approval"] is True
    assert data["budget"]["over_budget"] is True
    assert data["budget"]["planned_cents"] == 326400
    assert data["budget"]["over_cents"] == 126400
    assert "over the $2000 cap" in data["pending_approval_summary"]
    sofa = next(item for item in data["spec_list"] if item["sku"] == "ART-SOFA-721")
    assert any(option["sku"] == "IKE-SOFA-KL1" for option in sofa["cheaper"])
    rust = next(item for item in data["spec_list"] if item["sku"] == "RUG-8X10-RST")
    assert any(option["sku"] == "RUG-5X7-JUT" for option in rust["cheaper"])
    assert all(option["sku"] != "RUG-BATH-TER" for option in rust["cheaper"])
    assert all(item["image_url"] for item in data["spec_list"])
    assert all(pin["image_url"] for pin in data["board"])


def test_fit_budget_keeps_must_lines() -> None:
    store.apply_sample_board("fit-1")
    project = store.fit_budget("fit-1")
    skus = {item.sku for item in project.spec_list}
    assert "ART-SOFA-721" in skus
    assert "RUG-8X10-RST" in skus
    assert "RUG-BATH-TER" not in skus
    assert project.over_budget is False


def test_rooms_persist_across_reload() -> None:
    with tempfile.TemporaryDirectory() as folder:
        path = Path(folder) / "projects.json"
        store.disable_persist()
        store.reset()
        store.enable_persist(path)
        try:
            created = store.create_room("Living room")
            key = created.context_key
            store.append_transcript(key, "user", "keep the oak")
            store.set_budget(key, 2000)
            store.reset()
            store.enable_persist(path)
            rooms = store.list_rooms()
            assert [room["context_key"] for room in rooms] == [key]
            assert rooms[0]["name"] == "Living room"
            assert rooms[0]["budget_cents"] == 200000
            assert store.transcript(key) == [{"role": "user", "text": "keep the oak"}]
            renamed = store.rename_room(key, "Den")
            assert renamed.rooms["den"].name == "Den"
        finally:
            store.disable_persist()
            store.reset()


def test_swap_spec_rejects_bathroom_mat_for_living_rug() -> None:
    store.apply_sample_board("swap-rug-1")
    try:
        store.swap_spec("swap-rug-1", "RUG-8X10-RST", "RUG-BATH-TER")
        raise AssertionError("expected bathroom mat rejection")
    except ValueError as exc:
        assert "living" in str(exc)


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            setup_function()
            fn()
            print(f"PASS {name}")


def test_home_registry():
    import uuid
    import tempfile
    from pathlib import Path
    from app import store

    # Save/restore helpers for switching between memory/persistent and flag on/off
    def flag_on():
        orig = getattr(store, "_should_use_home_registry")
        store._should_use_home_registry = lambda: True
        return orig

    def flag_restore(orig):
        store._should_use_home_registry = orig

    # In-memory registry, create/list/rename
    orig_flag = flag_on()
    store.disable_home_registry_persist()
    store.reset_home_registry()
    try:
        # create accepts display names with whitespace trim, unique IDs generated
        a1 = store.create_home("Livinghaus")
        a2 = store.create_home("LegacyHome")
        a3 = store.create_home("Livinghaus")  # allow duplicate name
        # names are as given, trimmed; IDs differ
        assert a1["display_name"] == "Livinghaus"
        assert a3["display_name"] == "Livinghaus"
        assert a1["home_id"] != a3["home_id"]
        homes = store.list_homes()
        assert isinstance(homes, list)
        ids = {h["home_id"] for h in homes}
        assert len(ids) == 3
        # test display name duplicates and sort order (alpha, ties allowed)
        names = [h["display_name"] for h in homes]
        assert sorted(names, key=lambda s: s.lower()) == names
        # whitespace-only names are rejected
        try:
            store.create_home("   ")
            raise AssertionError("expected whitespace validation error")
        except ValueError:
            pass
        # unknown ID for rename errors
        fake_id = str(uuid.uuid4())
        try:
            store.rename_home(fake_id, "Whatever")
            raise AssertionError("expected error on unknown home_id")
        except store.HomeRegistryError:
            pass
        # rename updates display_name, leaves ID, others untouched
        renamed = store.rename_home(a2["home_id"], "East Side")
        assert renamed["display_name"] == "East Side"
        # old registry in memory mode is unaffected by rename
        assert a1["display_name"] == "Livinghaus"
        # confirm registry survives in-memory reset as empty (no persistence)
        store.reset_home_registry()
        assert store.list_homes() == []
    finally:
        flag_restore(orig_flag)

    # Persistent roundtrip: create and verify survives reload
    with tempfile.TemporaryDirectory() as tmp:
        persist_path = Path(tmp) / "projects.json"
        flag_on()
        store.reset_home_registry()
        store.enable_home_registry_persist(persist_path)
        try:
            home = store.create_home("MyPersisted")
            hid = home["home_id"]
            assert isinstance(hid, str) and len(hid) > 20
            stored = store.list_homes()
            assert len(stored) == 1
            # reload...
            store.reset_home_registry()
            store.enable_home_registry_persist(persist_path)
            after = store.list_homes()
            assert len(after) == 1
            assert after[0]["home_id"] == hid
            assert after[0]["display_name"] == "MyPersisted"
            # no legacy data touched
            with open(persist_path) as f:
                data = f.read()
                assert "projects" not in data or isinstance(
                    json.loads(data).get("projects", {}), dict
                )
        finally:
            store.disable_home_registry_persist()
            store.reset_home_registry()

    # Registry off: all methods raise HomeRegistryError
    store.disable_home_registry_persist()
    store.reset_home_registry()
    store._should_use_home_registry = lambda: False
    for func, args in [
        (store.create_home, ("Test",)),
        (store.list_homes, ()),
        (store.rename_home, (str(uuid.uuid4()), "X")),
    ]:
        try:
            func(*args)
            raise AssertionError(f"expected HomeRegistryError for {func.__name__}")
        except store.HomeRegistryError:
            pass
    del store._should_use_home_registry


# end test_home_registry
