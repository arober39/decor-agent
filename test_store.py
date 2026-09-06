from app import store


def setup_function() -> None:
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


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            setup_function()
            fn()
            print(f"PASS {name}")
