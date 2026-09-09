# LinkedIn shortform script: Agentifying Decora

Target: 3–5 minutes. Spoken pace ~150 words/minute.

Visual language you already set: Decora starts as a blinking mouth-and-eyes wrapper, then fills out into an animated brown girl as she becomes actually agentic. Keep that. Each feature below can add a body part or a prop so the metaphor stays visual.

---

## Cold open (your draft — keep as-is)

So I just did a talk at API World on how to operate long-running LLM calls and I based it around Decora, my decor agent. And yes I did just add an A to the end of Decor. But truthfully it has agent in the title but there’s really nothing agentic about it. It’s essentially just an LLM wrapper *(a mouth and eyes appear blinking at me as I talk)*, a chat assistant with a system prompt. So technically not an agent…yet. To change this I went to the AI Agentic Foundation for help with agentifying my homegirl Decora *(mouth and eyes fill out to an animated brown girl who looks around as her body appears, pleased with the outcome)* not just on the feature side but in my approach to development as well.

~40 seconds.

---

## The rest of the script

### Beat 1 — What “not an agent” actually meant (~25s)

Old Decora could talk a great paint color. She could *not* hold a job.

You’d say “12 by 14 living room, two grand, keep grandma’s credenza.” She’d write three confident paragraphs… and forget you tomorrow. No home. No budget ledger. No shopping list. Just vibes and a system prompt.

*(Decora shrugs. The chat bubble she’s standing in pops. She’s standing in an empty room.)*

That’s agent-washing. A title, a loop of LLM calls, no environment.

### Beat 2 — I did not start with more prompts (~20s)

The Agentic AI Foundation’s first standard is MCP — Model Context Protocol. Think USB-C for agents.

Not “write a better personality.” Not “add a feng shui specialist.” Those are still wrappers.

MCP says: put the *world* outside the model. Tools the model can run. Resources the app can read. Prompts the *user* kicks off. Then any agent — mine, or goose, which is AAIF’s reference agent — can plug into the same world.

*(Decora picks up a labeled cable: MCP. She plugs it into the empty room. Lights come on.)*

### Beat 3 — Feature: a real catalog (~25s)

First thing I built was inventory. Seeded SKUs. Article sofa. Benjamin Moore White Dove. IKEA desk. If it’s not in the catalog, it does not exist.

Old Decora hallucinated West Elm in her sleep. New Decora has to `search_catalog`. That’s an MCP *tool* — the model decides to search, the server returns rows. No Claude inside the catalog. It’s just furniture.

*(Decora opens a closet. Real hangtags. She rejects a ghost chair that isn’t on a tag.)*

### Beat 4 — Feature: the project is the job (~30s)

Chat is not the database. The job lives on `project://` — brief, rooms, budget, spec list.

That’s an MCP *resource*. I don’t ask the model “please remember the sofa.” The host *reads* the project every turn. Draft items stay draft. Committed means a human said yes.

*(A clipboard appears in her hand. Rooms sketch themselves. A budget bar fills as she adds the sofa.)*

If this panel only showed her last paragraph, we’d be back to a wrapper. The artifact is the spec list.

### Beat 5 — Feature: she asks before she commits (~25s)

She can `update_project`. She cannot spend.

When the room is covered and the budget holds, she calls `request_approval` and *stops*. Approve and Reject are buttons on *my* side — host routes, not model tools. If I gave her `approve`, she could commit the cart by herself. That’s not a designer. That’s a toddler with a credit card.

*(Decora holds up the clipboard. You tap Approve. The spec stamps COMMITTED. She looks relieved, not sneaky.)*

### Beat 6 — Feature: a prompt you choose (~15s)

`plan_room` is an MCP *prompt*. You invoke it. Room, budget, keep, avoid.

It is not her system prompt. A hello does not trigger a whole-home renovation. User-controlled. That’s the third primitive. Tools, resources, prompts. Who decides: model, app, you.

*(You tap a slash command. She nods and gets to work. She does not start on “hey.”)*

### Beat 7 — How I built it (~25s)

Development approach, not just features.

Small commits. One sentence. No “and.” Catalog before the protocol. Protocol before the chat UI. I can undo the UI and still inspect the server with no LLM.

I did *not* pull in Temporal from the API World talk for this. Durable workflows are how you *operate* a long call. MCP is how an agent *acts*. Different problems. I learned that the hard way by almost stacking another wrapper on a better chatbot.

*(Quick cut: Inspector on screen, `tools/list`, no chat app. Then the Decor UI lighting up from that same server.)*

### Close (~20s)

So Decora’s not a mouth anymore. She’s a host with a harness: read the project, discover tools, act, ask me before anything irreversible.

Next I can point goose at the same `decor-design` server. If goose can’t furnish a room from my catalog, my MCP isn’t done. A2A — her talking to a retailer agent — comes after she can act.

Agent in the title. Agent in the protocol. Homegirl’s employed.

*(Decora looks at the finished room, then at you. She winks. Cut.)*

---

## Timing check

| Beat | ~seconds |
|---|---|
| Your open | 40 |
| Not an agent | 25 |
| MCP not prompts | 20 |
| Catalog tool | 25 |
| Project resource | 30 |
| Approval gate | 25 |
| plan_room prompt | 15 |
| How I built | 25 |
| Close | 20 |
| **Total** | **~3:45** |

If you need to hit 3:00, drop Beat 6 and the Temporal sentence in Beat 7. If you have 5:00, linger on Inspector (`tools/list` / `resources/read` / `prompts/get`) as the “no Claude required” proof.

---

## B-roll / screen list

1. Old chat: one question, three paragraphs, empty tomorrow
2. MCP Inspector: `search_catalog`, then `catalog://sku/ART-SOFA-721`
3. `project://demo` JSON — status, budget, spec_list
4. Decor UI: chat left, project panel right
5. Approve button flipping a line from `draft` to `committed`
6. Optional: goose config pointing at `python mcp_servers/decor_design.py`

---

## Lines you can steal if you go off-script

- “A system prompt is a personality. An environment is a job.”
- “If goose can’t use it, it’s not MCP. It’s a private function.”
- “She can decorate. She cannot checkout. That’s the whole product.”
