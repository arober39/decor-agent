# Decora environment — stop conditions

This file is for any host of `decor-design` (goose, Inspector, a future retailer). It is not the Decora website. Chat is not the job.

## Who decides

| Primitive | Who | Do |
| --- | --- | --- |
| Tools | Model | `search_catalog`, `update_project`, `apply_board`, `request_approval` |
| Resources | Host | `project://{context_key}`, `catalog://sku/{sku}` |
| Prompts | User | `plan_room` |
| Approve | Human on the host | Not an MCP tool. Never commit spend yourself. |

## Inventory

Search the catalog. Add only SKUs that `search_catalog` returned this turn. If search is empty, inventory is empty. Do not invent IKEA, Article, West Elm, or prices from memory.

Rows live in the PIM (`app/pim/catalog.json`). Photos are on disk. Do not `cat` those files. Use the tools.

`search_catalog` may query Qdrant. If Qdrant is down, keyword search on the same PIM still returns real SKUs.

## The job

Persist on `project://` with `update_project`: brief, room, budget, then `add_spec`.

- Lane `must` is Keep.
- Lane `close` is Optional.
- Skip is not a spend line.

Call `apply_board` only if the user explicitly asks to map the sample board. A room, budget, or style brief is not that.

Keep draft plus committed spend at or under the cap. When the spec covers the room and the budget holds, call `request_approval` (`kind=spec`) and **stop**.

## Consent

After `request_approval`, do not source more product. Do not mark items `committed`. There is no `approve` tool. If you could checkout, the human gate failed.

## What this file is not

Not `AGENT_SYSTEM_PROMPT` in `app/prompts.py`. That prompt is for the Decora FastAPI host. Goose should not load the developer extension for this job — reading the repo would fake MCP.
