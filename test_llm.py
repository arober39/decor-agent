from app.llm import chat_kwargs, rejects_sampling, workspace_headers


def test_workspace_header_omitted_when_empty() -> None:
    assert workspace_headers("") is None
    assert workspace_headers("   ") is None


def test_workspace_header_uses_anthropic_name() -> None:
    assert workspace_headers(" ws_demo ") == {"anthropic-workspace-id": "ws_demo"}


def test_sonnet_5_omits_temperature() -> None:
    assert rejects_sampling("claude-sonnet-5")
    kwargs = chat_kwargs("claude-sonnet-5", 1024, 1.0, "key", "")
    assert "temperature" not in kwargs
    assert kwargs["thinking"] == {"type": "disabled"}


def test_sonnet_4_snapshot_keeps_temperature() -> None:
    assert not rejects_sampling("claude-sonnet-4-20250514")
    kwargs = chat_kwargs("claude-sonnet-4-20250514", 1024, 0.7, "key", "")
    assert kwargs["temperature"] == 0.7
    assert "thinking" not in kwargs


if __name__ == "__main__":
    test_workspace_header_omitted_when_empty()
    print("PASS test_workspace_header_omitted_when_empty")
    test_workspace_header_uses_anthropic_name()
    print("PASS test_workspace_header_uses_anthropic_name")
    test_sonnet_5_omits_temperature()
    print("PASS test_sonnet_5_omits_temperature")
    test_sonnet_4_snapshot_keeps_temperature()
    print("PASS test_sonnet_4_snapshot_keeps_temperature")
