from app import store
from app.events import SPEC_APPROVED, SPEC_SAVED, track


def setup_function() -> None:
    store.reset()


def test_track_is_noop_offline() -> None:
    track(SPEC_SAVED, "offline-1", {"sku": "ART-SOFA-721"}, 1)
    track(SPEC_APPROVED, "offline-1", {"sku": "ART-SOFA-721"}, 1)


def test_store_mutations_stay_offline_safe() -> None:
    store.upsert_room("e1", name="office", room_type="office")
    store.add_spec("e1", "IKE-DESK-BEK", "office")
    store.request_approval("e1", "spec", "desk")
    store.approve("e1", "spec")
    assert store.get_or_create("e1").spec_list[0].status == "committed"


if __name__ == "__main__":
    setup_function()
    test_track_is_noop_offline()
    setup_function()
    test_store_mutations_stay_offline_safe()
    print("PASS test_events")
