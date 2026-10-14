import pytest
from fastapi.testclient import TestClient
import server

client = TestClient(server.app)


def test_room_mood_capability_flag_off(monkeypatch):
    # Patch get_flag to always return False for decor-room-mood, True for board_intake
    def fake_get_flag(key, context, default=False):
        if key == "decor-room-mood":
            return False
        if key == server.BOARD_INTAKE_FLAG:
            return True
        return default
    monkeypatch.setattr(server, "get_flag", fake_get_flag)
    resp = client.get("/api/capabilities")
    assert resp.status_code == 200
    caps = resp.json()
    assert "room_mood" not in caps
    # legacy fields remain
    assert "board_intake" in caps
    assert "sample_board" in caps


def test_room_mood_capability_flag_on(monkeypatch):
    # Patch get_flag to return True for decor-room-mood and board_intake
    def fake_get_flag(key, context, default=False):
        if key == "decor-room-mood":
            return True
        if key == server.BOARD_INTAKE_FLAG:
            return True
        return default
    monkeypatch.setattr(server, "get_flag", fake_get_flag)
    resp = client.get("/api/capabilities")
    assert resp.status_code == 200
    caps = resp.json()
    # board_intake and sample_board remain
    assert "board_intake" in caps
    assert caps["board_intake"] is True
    assert "sample_board" in caps
    # room_mood is present and correct
    assert "room_mood" in caps
    assert caps["room_mood"] == "calm linen"


def test_feature_flag_must_stay_dark_by_default(monkeypatch):
    # Do not patch get_flag: test true default is off
    resp = client.get("/api/capabilities")
    caps = resp.json()
    assert "room_mood" not in caps
