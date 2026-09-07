from app.llm import workspace_headers


def test_workspace_header_omitted_when_empty() -> None:
    assert workspace_headers("") is None
    assert workspace_headers("   ") is None


def test_workspace_header_uses_anthropic_name() -> None:
    assert workspace_headers(" ws_demo ") == {"anthropic-workspace-id": "ws_demo"}


if __name__ == "__main__":
    test_workspace_header_omitted_when_empty()
    print("PASS test_workspace_header_omitted_when_empty")
    test_workspace_header_uses_anthropic_name()
    print("PASS test_workspace_header_uses_anthropic_name")
