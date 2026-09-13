from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from app.harness import (
    _final_text,
    asked_for_sample_board,
    bindings_from_mcp_tools,
    commentary_from_project,
    inject_context_key,
    inject_job_facts,
    parse_job_facts,
    parse_revision_intent,
    persist_talked_about_project,
    run_agent,
    run_agent_async,
    search_skus_from_messages,
    skus_named_in_text,
)
from app import store
from mcp import Client
from mcp_servers.decor_design import server
import anyio


def test_empty_message_rejected() -> None:
    out = run_agent("", "guard-empty")
    assert out["metadata"]["routed_to"] == "rejected"
    assert out["response"]


def test_long_message_rejected() -> None:
    out = run_agent("a" * 3000, "guard-long")
    assert out["metadata"]["routed_to"] == "rejected"


def test_final_text_keeps_preamble_on_tool_turn() -> None:
    msg = AIMessage(
        content=[
            {"type": "text", "text": "Sourcing the living room now."},
            {"type": "tool_use", "name": "search_catalog"},
        ],
        tool_calls=[{"name": "search_catalog", "args": {"query": "sofa"}, "id": "1"}],
    )
    assert (
        _final_text([HumanMessage(content="plan a room"), msg])
        == "Sourcing the living room now."
    )


def test_final_text_empty_when_only_tools() -> None:
    msg = AIMessage(
        content="",
        tool_calls=[{"name": "search_catalog", "args": {}, "id": "1"}],
    )
    assert _final_text([msg, ToolMessage(content="{}", tool_call_id="1")]) == ""


def test_commentary_from_project_names_catalog_rows() -> None:
    text = commentary_from_project(
        {"spec_list": [{"name": "Sven 72-inch sofa", "sku": "ART-SOFA-721"}]}
    )
    assert "ART-SOFA-721" in text
    assert "Sven" in text


def test_parse_job_facts_from_demo_query() -> None:
    facts = parse_job_facts(
        "Plan a 12x14 living room with a $2000 budget. Keep it mid-century."
    )
    assert facts["budget_dollars"] == 2000
    assert facts["width_ft"] == 12
    assert facts["length_ft"] == 14
    assert facts["room_name"] == "living room"
    assert facts["style_preferences"] == "mid-century"


def test_inject_job_facts_fills_omitted_budget() -> None:
    args = inject_job_facts(
        "update_project",
        {"action": "set_budget"},
        "job-1",
        "12x14 living room, $2000",
    )
    assert args["budget_dollars"] == 2000
    assert args["context_key"] == "job-1"


def test_named_skus_come_from_search_hits() -> None:
    messages = [
        ToolMessage(
            content='{"matches": [{"sku": "ART-SOFA-721", "name": "Sven 72-inch sofa"}]}',
            tool_call_id="1",
            name="search_catalog",
        )
    ]
    found = search_skus_from_messages(messages)
    assert found == ["ART-SOFA-721"]
    named = skus_named_in_text("The Sven 72-inch sofa anchors the room.", found)
    assert named == ["ART-SOFA-721"]
    from_reply_only = skus_named_in_text(
        "Sven 72-inch sofa, Seno 48-inch round coffee table, Arca floor lamp.",
        [],
    )
    assert "ART-SOFA-721" in from_reply_only
    assert "ART-COF-48R" in from_reply_only
    assert "ART-LAMP-ARC" in from_reply_only


def test_persist_writes_named_search_hits() -> None:
    store.reset()

    async def inner() -> None:
        async with Client(server) as client:
            messages = [
                ToolMessage(
                    content='{"matches": [{"sku": "ART-SOFA-721", "name": "Sven 72-inch sofa"}]}',
                    tool_call_id="1",
                    name="search_catalog",
                )
            ]
            project, note = await persist_talked_about_project(
                client,
                "panel-1",
                "Plan a 12x14 living room with a $2000 budget. Keep it mid-century.",
                messages,
                "The Sven 72-inch sofa anchors the room.",
            )
            assert note is None
            assert project["budget"]["total_cents"] == 200000
            assert "living room" in project["rooms"]
            assert project["brief"]["style_preferences"] == "mid-century"
            assert project["spec_list"][0]["sku"] == "ART-SOFA-721"

    anyio.run(inner)


def test_parse_revision_intent_swap_lamp() -> None:
    intent = parse_revision_intent(
        "swap the lamp for the brass lamp they have in inventory"
    )
    assert intent == {"kind": "swap", "category": "lighting"}
    assert parse_revision_intent("hello") is None


def test_host_swap_keeps_arca_when_it_is_already_the_brass_lamp() -> None:
    store.reset()
    store.apply_sample_board("swap-lamp-1")
    store.reject("swap-lamp-1", "Client rejected the current plan")

    async def inner() -> None:
        async with Client(server) as client:
            project, note = await persist_talked_about_project(
                client,
                "swap-lamp-1",
                "swap the lamp for the brass lamp they have in inventory",
                [],
                "The spec is $2,376 against a $2,000 budget.",
            )
            lighting = [
                item for item in project["spec_list"] if item["category"] == "lighting"
            ]
            assert [item["sku"] for item in lighting] == ["ART-LAMP-ARC"]
            assert lighting[0]["color"] == "brass"
            assert project["pending_approval"] is True
            assert note is not None
            assert "ART-LAMP-ARC" in note
            skus = {item["sku"] for item in project["spec_list"]}
            assert "WSM-HW-BRS" not in skus
            assert "WSM-MIRR-RND" not in skus

    anyio.run(inner)


def test_host_swap_replaces_sofa_when_inventory_has_another() -> None:
    store.reset()
    store.add_spec("swap-sofa-1", "ART-SOFA-721", "living room")

    async def inner() -> None:
        async with Client(server) as client:
            project, note = await persist_talked_about_project(
                client,
                "swap-sofa-1",
                "swap the sofa for the IKEA KIVIK",
                [],
                "",
            )
            sofas = [item for item in project["spec_list"] if item["category"] == "sofa"]
            assert [item["sku"] for item in sofas] == ["IKE-SOFA-KL1"]
            assert project["pending_approval"] is True
            assert note is not None
            assert "IKE-SOFA-KL1" in note

    anyio.run(inner)


def test_host_does_not_swap_living_rug_for_bath_mat() -> None:
    store.reset()
    store.apply_sample_board("swap-white-rug")

    async def inner() -> None:
        async with Client(server) as client:
            project, note = await persist_talked_about_project(
                client,
                "swap-white-rug",
                "swap my initial 8x10 rug for a white one",
                [],
                "",
            )
            rugs = [item for item in project["spec_list"] if item["category"] == "rug"]
            assert [item["sku"] for item in rugs] == ["RUG-8X10-IVO"]
            assert "RUG-BATH-TER" not in {item["sku"] for item in project["spec_list"]}
            assert note is not None
            assert "RUG-8X10-IVO" in note

    anyio.run(inner)


def test_inject_context_key() -> None:
    args = inject_context_key("update_project", {"action": "set_budget"}, "job-9")
    assert args["context_key"] == "job-9"
    search = inject_context_key("search_catalog", {"query": "sofa"}, "job-9")
    assert "context_key" not in search
    board = inject_context_key("apply_board", {}, "job-9")
    assert board["context_key"] == "job-9"


def test_asked_for_sample_board() -> None:
    assert asked_for_sample_board("Map the sample living-room board.")
    assert asked_for_sample_board("please map the sample board")
    assert not asked_for_sample_board(
        "Plan a 12x14 living room with a $2000 budget. Mid-century, warm woods."
    )
    assert not asked_for_sample_board("Small bedroom, $1200. Keep the oak dresser.")


async def _list_bindings() -> None:
    store.reset()
    async with Client(server) as client:
        listed = await client.list_tools()
        bindings = bindings_from_mcp_tools(listed.tools)
        names = {item["name"] for item in bindings}
        assert names == {"search_catalog", "update_project", "request_approval", "apply_board"}
        for item in bindings:
            assert "input_schema" in item


def test_bindings_come_from_tools_list() -> None:
    anyio.run(_list_bindings)


def test_async_entry_works_inside_running_loop() -> None:
    """FastAPI already has an event loop. anyio.run() would raise there."""

    async def inner() -> dict:
        return await run_agent_async("   ", "guard-nested-loop")

    out = anyio.run(inner)
    assert out["metadata"]["routed_to"] == "rejected"
    assert out["response"]


def test_chat_route_does_not_start_a_second_loop() -> None:
    from fastapi.testclient import TestClient

    from server import app

    client = TestClient(app)
    response = client.post(
        "/api/chat",
        json={"message": "   ", "context_key": "guard-http-loop"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["metadata"]["routed_to"] == "rejected"


if __name__ == "__main__":
    test_empty_message_rejected()
    print("PASS test_empty_message_rejected")
    test_long_message_rejected()
    print("PASS test_long_message_rejected")
    test_final_text_keeps_preamble_on_tool_turn()
    print("PASS test_final_text_keeps_preamble_on_tool_turn")
    test_final_text_empty_when_only_tools()
    print("PASS test_final_text_empty_when_only_tools")
    test_commentary_from_project_names_catalog_rows()
    print("PASS test_commentary_from_project_names_catalog_rows")
    test_parse_job_facts_from_demo_query()
    print("PASS test_parse_job_facts_from_demo_query")
    test_inject_job_facts_fills_omitted_budget()
    print("PASS test_inject_job_facts_fills_omitted_budget")
    test_named_skus_come_from_search_hits()
    print("PASS test_named_skus_come_from_search_hits")
    test_persist_writes_named_search_hits()
    print("PASS test_persist_writes_named_search_hits")
    test_parse_revision_intent_swap_lamp()
    print("PASS test_parse_revision_intent_swap_lamp")
    test_host_swap_keeps_arca_when_it_is_already_the_brass_lamp()
    print("PASS test_host_swap_keeps_arca_when_it_is_already_the_brass_lamp")
    test_host_swap_replaces_sofa_when_inventory_has_another()
    print("PASS test_host_swap_replaces_sofa_when_inventory_has_another")
    test_host_does_not_swap_living_rug_for_bath_mat()
    print("PASS test_host_does_not_swap_living_rug_for_bath_mat")
    test_inject_context_key()
    print("PASS test_inject_context_key")
    test_bindings_come_from_tools_list()
    print("PASS test_bindings_come_from_tools_list")
    test_async_entry_works_inside_running_loop()
    print("PASS test_async_entry_works_inside_running_loop")
    test_chat_route_does_not_start_a_second_loop()
    print("PASS test_chat_route_does_not_start_a_second_loop")
