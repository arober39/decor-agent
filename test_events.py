from unittest.mock import Mock

import pytest

from app import events, store
from app.events import REQUEST_ERROR, SPEC_APPROVED, SPEC_SAVED, track


def setup_function() -> None:
    store.reset()


def test_track_is_noop_offline(monkeypatch) -> None:
    monkeypatch.setattr(events, "get_client", lambda: None)
    track(SPEC_SAVED, "offline-1", {"sku": "ART-SOFA-721"}, 1)
    track(SPEC_APPROVED, "offline-1", {"sku": "ART-SOFA-721"}, 1)
    track(REQUEST_ERROR, "offline-1", {"route": "/api/chat", "status": 500})


@pytest.mark.parametrize("failure", ["get_client", "build_context", "sdk_track"])
def test_track_never_raises(monkeypatch, failure) -> None:
    def fail(*args, **kwargs):
        raise RuntimeError("SDK unavailable")

    client = Mock()
    monkeypatch.setattr(events, "get_client", lambda: client)
    if failure == "sdk_track":
        client.track.side_effect = fail
    else:
        monkeypatch.setattr(events, failure, fail)
    track(REQUEST_ERROR, "user-1", {"route": "/api/chat", "status": 500})


def test_store_mutations_stay_offline_safe() -> None:
    store.upsert_room("e1", name="office", room_type="office")
    store.add_spec("e1", "IKE-DESK-BEK", "office")
    store.request_approval("e1", "spec", "desk")
    store.approve("e1", "spec")
    assert store.get_or_create("e1").spec_list[0].status == "committed"
