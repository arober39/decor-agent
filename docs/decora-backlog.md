# Decora backlog (out of current slice)

Items here are **not** part of semantic search, Qdrant environments, or the Jev/LaunchDarkly flinch post. Capture them when they show up in a demo; do not fix them in that same slice unless we explicitly switch goals.

## Open

### Later, maybe: Clerk + real-user storage
- **Left open:** 21 Sep 2026, when the room list shipped without accounts.
- Logins so people keep their rooms across devices. Do not block the room list on Clerk. Decide only when we want multi-user: Clerk (or similar) for identity, then store projects by `user_id` + `room_id` instead of an anonymous `context_key`. Until then, local persistence without accounts.
- Auth only if we take that path: new session middleware, do not put Clerk inside the MCP server.

## Done

### Brief replace vs SKU swap
- **Fixed:** 21 Sep 2026. Bare `replace` / `yes replace` updates the job brief. A piece swap still requires a named piece (`replace the sofa`).

### Same-thread budget / style drift
- **Fixed:** 21 Sep 2026. A later room, budget, or style on the same `context_key` overwrites that job and the reply says so.

### Style vs budget in the shopping list
- **Fixed:** 21 Sep 2026. The host keeps the style match (Sven over KIVIK) and names the cheaper off-style SKU when the style list is over the cap.

### Asking for room/budget before a catalog-only ask
- **Fixed:** 21 Sep 2026. A product search such as a rug returns catalog SKUs without `add_spec` and without asking for a room or budget first.

### Room list: create, click in, work saved
- **Fixed:** 21 Sep 2026. One room is one saved job. Studio lists, creates, renames, and deep-links `?room=`. Projects and chat transcripts persist in `data/projects.json`. Clerk stays a later slice.

## Done in other slices (do not reopen here)

- Semantic + keyword merge so a full Qdrant page cannot hide token matches like folded `midcentury` → `ART-SOFA-721` (`app/catalog.py` `search_products`).
