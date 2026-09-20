# LinkedIn shortform script: Decora milestone 2 — goose

Target: ~2:30–3:00. Spoken pace ~150 words/minute. A 90-second cut is at the bottom.

This is the check you promised at the end of milestone 1: if goose cannot furnish a room from `decor-design`, the MCP is not done.

No body-part metaphor. The pictures are goose, the extension form, and tool calls. Decora’s website stays off camera until the last optional cut.

---

## Cold open (~20s)

Last time I hung a door on Decora’s world. MCP. Catalog, clipboard, ask-before-you-spend. I proved it in Inspector with no chat and no LLM.

That still could have been a private function wearing JSON-RPC. The only host in the room was me.

So this week a stranger drives. Goose. Block donated it to the Agentic AI Foundation. It is not how I *build* Decora. It is how I *gut-check* the room.

*(Screen: goose empty session. No Decora UI.)*

---

## Beat 1 — What goose is (~20s)

Goose is a ready-to-run agent. It already has a loop: look at tools, pick one, observe, repeat.

I did not import goose into Python. I did not rewrite my harness. I pointed it at the same server Inspector used: `mcp_servers/decor_design.py`. Standard IO. That’s the USB-C part. Any host that speaks MCP can plug in.

If this only works in my FastAPI app, I built a website. If goose can do the job, I built an environment.

*(Screen: goose → Extensions → Add custom extension.)*

---

## Beat 2 — Plug it in (~25s)

Film this live. Do not skip to a finished config.

- Type: Standard IO
- Name: `decor-design`
- Command: the **venv** Python, then the server file, from the **repo root**

```text
/Users/alexisroberson/Documents/Claude_Code_Projects/langgraph-projects/decor-agent/venv/bin/python
/Users/alexisroberson/Documents/Claude_Code_Projects/langgraph-projects/decor-agent/mcp_servers/decor_design.py
```

Working directory, if goose asks: the repo root. Not `mcp_servers/`.

Hit add. New session. Confirm the tools: `search_catalog`, `update_project`, `request_approval`. Same three Inspector showed. Same door.

*(If tools don’t appear: you used system Python, or you launched from the wrong folder. Cut, fix, keep going. That miss is the lesson.)*

---

## Beat 3 — Furnish the room (~45s)

Same job as milestone 1. Type this, don’t paraphrase:

> Plan a 12x14 living room with a $2000 budget. Keep it mid-century. Use only catalog SKUs. Do not invent products. When the spec covers the room and the budget holds, call request_approval and stop.

Watch the tool calls, not the prose.

Success looks like:

- `search_catalog` returns rows you recognize (Sven `ART-SOFA-721`, a lamp, a table)
- `update_project` writes budget, room, spec items
- `request_approval` and it **stops**
- No West Elm. No made-up prices.

Say this while it runs:

Goose does not know my CSS. It does not know my persist hacks. It only knows the protocol. The model picks the tool. The server returns furniture. That is the job.

*(Do not cut to the Decora side panel expecting the sofa to appear. Goose spawned its own server process. The catalog is the same. The RAM is not. Same door, new clipboard. If you imply they share one panel, you are lying.)*

---

## Beat 4 — What this proves (~20s)

Goose did not certify that “Decora is an agent.” Goose certified that `decor-design` is a world another agent can work in.

My UI is optional. Inspector was the no-LLM check. Goose is the other-agent check.

She can decorate. She still cannot checkout. `approve` is not on this tool list. If goose could commit spend, I would have failed the human gate on purpose.

---

## Close (~20s)

So the promise is not “a smarter paragraph in my app.” The promise is: a stranger can furnish the room.

Next is AGENTS.md — stop conditions in writing — then A2A, when she talks to a retailer instead of pretending to be the store.

Agent in the title. Agent on the wire. Homegirl’s employed — and she just had a coworker.

*(Optional last frame: split Inspector tools list | goose tool calls. Same names. Cut.)*

---

## Timing check

| Beat | ~seconds |
|---|---|
| Open | 20 |
| What goose is | 20 |
| Plug it in | 25 |
| Furnish the room | 45 |
| What this proves | 20 |
| Close | 20 |
| **Total** | **~2:30** |

---

## 90-second cut

Drop Beat 1. Open on the extension form. One sentence: “Last week Inspector. This week goose. Same server, no website.” Plug in. Paste the job. Show `search_catalog` → `request_approval`. Close: “If goose can’t use it, it’s a private function.”

~90 seconds.

---

## B-roll / screen list

1. Milestone 1 callback: Inspector `tools/list` (2 seconds, then wipe)
2. Goose Extensions → Add custom extension (fill the command live)
3. Goose tools list: `search_catalog`, `update_project`, `request_approval`
4. The typed job prompt
5. Tool-call log with real SKUs (`ART-SOFA-721`, not a ghost chair)
6. `request_approval` then idle — she stopped
7. Optional: config snippet in `~/.config/goose/config.yaml` under `extensions`
8. Do **not** show Decora chat as the proof

---

## Lines you can steal if you go off-script

- “Goose is not how I build Decora. Goose is a stranger at the wheel.”
- “If goose can’t use it, it’s not MCP. It’s a private function.”
- “Inspector proved the server with no brain. Goose proved it with someone else’s brain.”
- “Same closet. Different driver. That’s the whole milestone.”

---

## Before you hit record

1. Activate the project venv once so the path in Beat 2 actually runs.
2. Do a dry run of the job. If goose invents SKUs, stop and fix the server or the prompt before you film.
3. Keep Decora (`python3 server.py`) **quit**. This video is “the host was optional.”
4. Have a `context_key` in the prompt if you want a stable `project://` read (`project://goose-demo`).
