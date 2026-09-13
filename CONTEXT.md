# Decora domain

Words we use on `main`. Chat is not the product.

| Term | Meaning |
| --- | --- |
| **Job** | One client’s design work. Lives on `project://{context_key}`. |
| **Brief** | Lifestyle, keep, avoid, style. Not a chat transcript. |
| **Catalog** | PIM rows in `app/pim/catalog.json` (identity, price, room, color, size, stock). Photos are on disk at `web/images/{sku}.jpg`. If search is empty, inventory is empty. |
| **Spec line** | A catalog SKU on the project. Status is `draft` until the host Approves. |
| **Lane** | `must` = the look. `close` = substitute SKU. `skip` = not in inventory, not a spend line. |
| **Board** | Curated pins mapped to lanes. No vision API. No invented SKUs. |
| **Approve** | Host-only. Commits draft spec lines. The model cannot do this. |
| **AI Config** | Model only (`decor-agent-main`). The host owns `AGENT_SYSTEM_PROMPT`. |
| **Product flag** | Boolean on a product surface, e.g. `decor-board-intake`. Not a specialist-router rewrite. |
| **spec_saved / spec_approved** | Custom events for the shopping-list loop. Offline is a no-op. |
