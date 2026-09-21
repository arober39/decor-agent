# Decora backlog (out of current slice)

Items here are **not** part of semantic search, Qdrant environments, or the Jev/LaunchDarkly flinch post. Capture them when they show up in a demo; do not fix them in that same slice unless we explicitly switch goals.

## Open

### Brief replace vs SKU swap
- **Seen:** 20 Sep 2026, studio chat on a warm-minimalist project.
- **What happened:** User said `12x14 living room, $2000, midcentury`, then `yes replace` meaning *replace the job brief* (room / budget / style). Decora asked which *piece* to swap.
- **Why it matters:** `replace` in this product should distinguish “new brief on this project” from `swap_spec`.
- **Likely area:** `app/harness.py` revision parsing, `update_project`, prompts.

### Same-thread budget / style drift
- **Seen:** Same session. Agent treated an existing ~$1,500 project as in conflict with a new $2,000 midcentury ask instead of applying the new facts to that `context_key`.
- **Why it matters:** One studio session is one job unless the user starts a new context. New room/budget/style in chat should update `project://`, not fork a debate.
- **Likely area:** `inject_job_facts`, `parse_job_facts`, `update_project` on later turns.

### Style vs budget in the shopping list
- **Seen:** Combined prompt `12x14 living room, $2000, midcentury, warm minimalist, low-pile pet-friendly rug`.
- **Search was fine:** `RUG-8X10-RST` (low-pile rust), `ART-COF-48R` (Seno walnut, mid-century), all real SKUs.
- **Planning miss:** List kept **KIVIK** (`IKE-SOFA-KL1`, modern, $799) instead of **Sven** (`ART-SOFA-721`, mid-century, $1,299). Math: Sven + rust rug + Seno table exceeds $2,000; KIVIK fits. The host preferred budget over the midcentury token and never said so clearly.
- **Why it matters:** When style and budget fight, say so and offer the on-style over-budget option vs the on-budget off-style option. Do not silently drop the style match.
- **Likely area:** harness persist / spec selection, `app/prompts.py`.

### Asking for room/budget before a catalog-only ask
- **Seen:** First UI probe: user only sent `warm minimalist low-pile rug, pet-friendly`. Decora asked for room and budget first, then (or in parallel) returned good SKUs.
- **Why it matters:** A rug search should not block on a full brief. Room/budget matter for `add_spec`, not for `search_catalog`.

### Room list: create, click in, work saved
- **Asked:** 20 Sep 2026. Want to create rooms, see a list, click into one, and have that room’s spec/chat/board survive.
- **Today:** `app/store.py` is **in-memory** keyed by `context_key`. Restarting the server drops work. The studio is one session, not a navigable list of rooms. `DesignProject` already has rooms on a project; the UI does not treat them as first-class destinations.
- **Product slice (do first, no auth):** “My rooms” — create/rename, list, open a room, persist that project somewhere durable (sqlite/json on disk is enough for a personal demo). Deep-link `context_key` so refresh does not wipe the list.
- **Later, maybe: Clerk + real-user storage.** Logins so *people* keep their rooms across devices. Do **not** block the room list on Clerk. Decide only when we want multi-user: Clerk (or similar) for identity, then store projects by `user_id` + `room_id` instead of an anonymous `context_key`. Until then, local persistence without accounts.
- **Open question:** one project with many rooms vs one room = one project. List UX is easier if each clickable room is its own saved job.
- **Likely area:** `web/studio.html` / `web/studio.js`, `app/store.py`, `server.py` project routes. Auth only if we take the Clerk path: new session middleware, do not put Clerk inside the MCP server.

## Done in other slices (do not reopen here)

- Semantic + keyword merge so a full Qdrant page cannot hide token matches like folded `midcentury` → `ART-SOFA-721` (`app/catalog.py` `search_products`).
