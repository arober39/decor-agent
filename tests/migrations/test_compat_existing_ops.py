import json
import copy
from migrations import migration_0001_room_home as migration

FIXTURES = __import__("pathlib").Path(__file__).parent / "fixtures"


def _load_json(fname):
    return json.loads((FIXTURES / fname).read_text())


def _roundtrip_through_migration(raw_projects):
    data = copy.deepcopy(raw_projects)
    result = migration.migrate_project_dict(data)
    return result


def test_legacy_to_homeaware_migration_preserves_all_fields():
    src = _load_json("legacy_rooms.json")
    newdict = _roundtrip_through_migration(src)
    for context_key, pdata in newdict["projects"].items():
        rooms = pdata["rooms"]
        # All keys must be JSON string lists of length 2
        for k in rooms:
            kobj = json.loads(k)
            assert isinstance(kobj, list) and len(kobj) == 2
            assert rooms[k]["home_id"] == context_key
            # All original fields in legacy must survive in migrated
            orig_room = src["projects"][context_key]["rooms"][kobj[1]]
            for orig_field in orig_room:
                assert orig_room[orig_field] == rooms[k].get(orig_field)


def test_migration_idempotency_on_repeated_runs():
    src = _load_json("legacy_rooms.json")
    migrated = _roundtrip_through_migration(src)
    # Second run shouldn't change existing project dict
    second_pass = _roundtrip_through_migration(migrated)
    assert migrated == second_pass


def test_partial_migration_recovery():
    partial = _load_json("partial_failure.json")
    full = _roundtrip_through_migration(partial)
    # All room keys must be migrated for both projects
    for proj_key, pdata in full["projects"].items():
        rooms = pdata["rooms"]
        for k in rooms:
            kobj = json.loads(k)
            assert isinstance(kobj, list) and len(kobj) == 2


def test_already_migrated_dict_is_noop():
    already = _load_json("already_migrated.json")
    unchanged = _roundtrip_through_migration(already)
    assert already == unchanged


def test_mixed_legacy_and_migrated_supported():
    # Contains both: migration should update legacy and skip migrated
    src = _load_json("partial_failure.json")
    newdata = _roundtrip_through_migration(src)
    for proj_key, pdata in newdata["projects"].items():
        for k in pdata["rooms"]:
            kobj = json.loads(k)
            assert isinstance(kobj, list) and len(kobj) == 2
    # No room lost
    for proj_key in src["projects"]:
        orig_rooms = src["projects"][proj_key]["rooms"]
        new_rooms = newdata["projects"][proj_key]["rooms"]
        assert len(orig_rooms) == len(new_rooms)


def test_context_keys_and_nonroom_data_preserved():
    src = _load_json("legacy_rooms.json")
    migrated = _roundtrip_through_migration(src)
    for context_key, pdata in migrated["projects"].items():
        assert pdata["context_key"] == context_key
        assert "brief" in pdata
        assert set(pdata.keys()).issuperset(
            {"brief", "rooms", "cart", "approvals", "context_key"}
        )
        # Board pins and cart should not be mutated
        orig = src["projects"][context_key]
        if "cart" in orig:
            assert orig["cart"] == pdata.get("cart")
        if "board_pins" in orig:
            assert orig["board_pins"] == pdata.get("board_pins")


# END OF PART 6
