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


def test_add_spec_keeps_lane() -> None:
    store.upsert_room("p1", name="living room", room_type="living")
    store.add_spec("p1", "RUG-8X10-JUT", "living room", lane="close", why="jute, not rust")
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
