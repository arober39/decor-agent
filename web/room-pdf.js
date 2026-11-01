function escapePlanHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

function planMoney(cents) {
  if (cents == null || cents === "") return "—";
  const amount = Number(cents);
  if (Number.isNaN(amount)) return "—";
  return `$${(amount / 100).toFixed(0)}`;
}

const PLAN_LANES = { must: "Keep", close: "Optional", skip: "Skip" };
const PLAN_STATUS = {
  intake: "Intake",
  planning: "In progress",
  awaiting_approval: "Ready to approve",
  complete: "Approved",
  draft: "Draft",
  committed: "Committed",
};

function planLabel(map, key) {
  return map[key] || key || "";
}

function planJoin(parts) {
  return parts.filter(Boolean).join(" · ");
}

function planIsLocked(project) {
  const specs = project.spec_list || [];
  const hasDraft = specs.some((item) => item.status !== "committed");
  return specs.length > 0 && !hasDraft && !project.pending_approval;
}

function planBudgetCopy(project) {
  const budget = project.budget || {};
  if (budget.total_cents == null) return { headline: "Budget not set", detail: "" };
  const planned =
    budget.planned_cents != null
      ? budget.planned_cents
      : (budget.committed_cents || 0) + (budget.draft_cents || 0);
  const locked = planIsLocked(project);
  const headline = locked
    ? `${planMoney(budget.committed_cents || planned)} committed of ${planMoney(budget.total_cents)}`
    : `${planMoney(planned)} planned of ${planMoney(budget.total_cents)}`;
  const bits = [
    `Committed ${planMoney(budget.committed_cents || 0)}`,
    `Draft ${planMoney(budget.draft_cents || 0)}`,
  ];
  if (budget.over_budget && !locked) {
    bits.push(`${planMoney(budget.over_cents || planned - budget.total_cents)} over the cap`);
  }
  return { headline, detail: bits.join(" · ") };
}

function planBriefCopy(project) {
  const brief = project.brief || {};
  const rooms = Object.values(project.rooms || {});
  const lines = [];
  const intro = planJoin([brief.lifestyle, brief.style_preferences]);
  if (intro) lines.push(`<p>${escapePlanHtml(intro)}</p>`);
  if (brief.keep && brief.keep.length) {
    lines.push(`<p>Keep: ${escapePlanHtml(brief.keep.join(", "))}</p>`);
  }
  if (brief.avoid && brief.avoid.length) {
    lines.push(`<p>Avoid: ${escapePlanHtml(brief.avoid.join(", "))}</p>`);
  }
  const existing = rooms.flatMap((room) => room.existing_pieces || []);
  if (existing.length) {
    lines.push(`<p>Already in the room: ${escapePlanHtml(existing.join(", "))}</p>`);
  }
  const notes = rooms.map((room) => room.style_notes).filter(Boolean);
  if (notes.length) lines.push(`<p>${escapePlanHtml(notes.join(" · "))}</p>`);
  if (!lines.length) lines.push("<p>No brief yet.</p>");
  return lines.join("");
}

function planSpecRows(project) {
  const specs = project.spec_list || [];
  if (!specs.length) return "<p>No pieces on the list yet.</p>";
  const rows = specs
    .map((item) => {
      const lane = item.lane || "must";
      const qty = Number(item.qty) > 1 ? ` ×${item.qty}` : "";
      const meta = planJoin([item.sku, item.color, planLabel(PLAN_STATUS, item.status)]);
      const why = item.why ? `<p class="plan-why">${escapePlanHtml(item.why)}</p>` : "";
      return `<tr>
        <td><span class="lane lane-${escapePlanHtml(lane)}">${escapePlanHtml(planLabel(PLAN_LANES, lane))}</span></td>
        <td>
          <strong>${escapePlanHtml(item.name || "Piece")}${escapePlanHtml(qty)}</strong>
          <p class="plan-meta">${escapePlanHtml(meta)}</p>
          ${why}
        </td>
        <td>${escapePlanHtml(planMoney(item.price_cents))}</td>
      </tr>`;
    })
    .join("");
  return `<table>
    <thead><tr><th>Lane</th><th>Piece</th><th>Price</th></tr></thead>
    <tbody>${rows}</tbody>
  </table>`;
}

function planSkipped(project) {
  const skipped = project.skipped || [];
  if (!skipped.length) return "";
  const items = skipped
    .map((item) => {
      const why = item.why ? ` — ${escapePlanHtml(item.why)}` : "";
      return `<li>${escapePlanHtml(item.label || "Pin")}${why}</li>`;
    })
    .join("");
  return `<h2>Skipped</h2><ul>${items}</ul><p class="plan-meta">Skip is not a spend line.</p>`;
}

function planCart(project) {
  const cart = project.cart || [];
  if (!cart.length) return "";
  const items = cart
    .map((item) => {
      const qty = Number(item.qty) || 1;
      const line = planMoney((item.price_cents || 0) * qty);
      const qtyLabel = qty > 1 ? ` ×${qty}` : "";
      return `<li>${escapePlanHtml(item.name || item.sku || "Piece")}${escapePlanHtml(qtyLabel)} · ${escapePlanHtml(line)}</li>`;
    })
    .join("");
  return `<h2>Held in cart</h2><p class="plan-meta">Not on the list and not in the budget until you move it.</p><ul>${items}</ul>`;
}

function planNotes(project) {
  const notes = project.rejected || [];
  if (!notes.length) return "";
  const items = notes.map((note) => `<li>${escapePlanHtml(note)}</li>`).join("");
  return `<h2>Client notes</h2><ul>${items}</ul>`;
}

function roomPlanBody(project) {
  const source = project || {};
  const rooms = Object.values(source.rooms || {});
  const room = rooms[0] || {};
  const roomName = room.name || "No room yet";
  const size = room.width_ft && room.length_ft ? `${room.width_ft} × ${room.length_ft} ft` : "";
  const sub = planJoin([room.room_type, size, planLabel(PLAN_STATUS, source.status || "intake")]);
  const extraRooms = rooms
    .slice(1)
    .map((item) => escapePlanHtml(item.name))
    .filter(Boolean);
  const extra = extraRooms.length
    ? `<p class="plan-meta">Also in this file: ${extraRooms.join(", ")}</p>`
    : "";
  const budget = planBudgetCopy(source);
  const detail = budget.detail ? `<p class="plan-meta">${escapePlanHtml(budget.detail)}</p>` : "";
  return `<article class="plan">
    <p class="plan-mark">decora</p>
    <p class="plan-kicker">Room plan</p>
    <h1>${escapePlanHtml(roomName)}</h1>
    <p class="plan-sub">${escapePlanHtml(sub)}</p>
    ${extra}
    <h2>Brief</h2>
    ${planBriefCopy(source)}
    <h2>Budget</h2>
    <p>${escapePlanHtml(budget.headline)}</p>
    ${detail}
    <h2>Shopping list</h2>
    ${planSpecRows(source)}
    ${planSkipped(source)}
    ${planCart(source)}
    ${planNotes(source)}
    <p class="plan-foot">Saved from Decora. This copy does not approve the list or purchase anything.</p>
  </article>`;
}
