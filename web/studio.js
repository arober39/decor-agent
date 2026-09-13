const form = document.getElementById("chat-form");
const promptInput = document.getElementById("prompt");
const sendButton = document.getElementById("send");
const messages = document.getElementById("messages");
const boardBtn = document.getElementById("board-btn");
const CONTEXT_STORAGE_KEY = "decora-context-key";
const BOARD_MAPPED_PREFIX = "decora-board-mapped:";

const PIN_COLORS = {
  "Linen sofa, oak legs": "#8d8578",
  "Rust 8x10 rug": "#9a4a2a",
  "Marble coffee table": "#d7d1c7",
  "Ceramic table lamp": "#cfc4b0",
  "Mohair lounge chair": "#6f7a4f",
  "Linen drapery": "#e6dfd2",
};

const PIN_SKUS = {
  "Linen sofa, oak legs": "ART-SOFA-721",
  "Rust 8x10 rug": "RUG-8X10-RST",
  "Marble coffee table": "ART-COF-MRB",
  "Ceramic table lamp": "ART-LAMP-CER",
  "Mohair lounge chair": "ART-CHAIR-MOH",
  "Linen drapery": "WSM-DRAPE-LN",
};

function loadContextKey() {
  try {
    const existing = localStorage.getItem(CONTEXT_STORAGE_KEY);
    if (existing) return existing;
    const created = crypto.randomUUID();
    localStorage.setItem(CONTEXT_STORAGE_KEY, created);
    return created;
  } catch {
    return crypto.randomUUID();
  }
}

const contextKey = loadContextKey();
let selectedPin = "";

function boardMappedKey() {
  return `${BOARD_MAPPED_PREFIX}${contextKey}`;
}

function boardWasMapped() {
  try {
    return localStorage.getItem(boardMappedKey()) === "1";
  } catch {
    return false;
  }
}

function markBoardMapped() {
  try {
    localStorage.setItem(boardMappedKey(), "1");
  } catch {
    // private mode
  }
}

function askedForSampleBoard(message) {
  const lower = (message || "").toLowerCase();
  return ["sample board", "map the board", "map sample", "map the sample"].some((phrase) =>
    lower.includes(phrase)
  );
}

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

function money(cents) {
  if (cents == null) return "—";
  return `$${(cents / 100).toFixed(0)}`;
}

const LANE_LABELS = { must: "Keep", close: "Optional", skip: "Skip" };

function laneLabel(lane) {
  return LANE_LABELS[lane] || lane;
}

function prettyStatus(status) {
  const labels = {
    intake: "Intake",
    planning: "In progress",
    awaiting_approval: "Ready to approve",
    complete: "Approved",
  };
  return labels[status] || (status || "intake").replaceAll("_", " ");
}

function hasDraftSpec(project) {
  return (project.spec_list || []).some((item) => item.status !== "committed");
}

function listIsLocked(project) {
  const specs = project.spec_list || [];
  return specs.length > 0 && !hasDraftSpec(project) && !project.pending_approval;
}

function setChangePanel(open) {
  setHidden("change-panel", !open);
  if (open) {
    const input = document.getElementById("change-input");
    input.value = "";
    input.focus();
    document.querySelector(".ask-dock")?.scrollIntoView({ behavior: "smooth", block: "end" });
  }
}

function appendMessage(role, text, extraClass) {
  const entry = document.createElement("article");
  entry.className = extraClass ? `note ${role} ${extraClass}` : `note ${role}`;
  entry.textContent = text;
  messages.appendChild(entry);
  messages.scrollTop = messages.scrollHeight;
}

const WELCOME = "Tell me the room and the budget.";

function showTypingIndicator() {
  const entry = document.createElement("article");
  entry.className = "note bot typing";
  entry.id = "typing-indicator";
  entry.textContent = "Decora is looking at the catalog…";
  messages.appendChild(entry);
  messages.scrollTop = messages.scrollHeight;
}

function hideTypingIndicator() {
  document.getElementById("typing-indicator")?.remove();
}

function setHidden(id, hidden) {
  document.getElementById(id).classList.toggle("hidden", hidden);
}

function renderBoard(project) {
  const pins = boardWasMapped() ? project.board_pins || [] : [];
  const empty = document.getElementById("empty-board");
  const grid = document.getElementById("board-grid");
  empty.classList.toggle("hidden", pins.length > 0);
  grid.classList.toggle("hidden", pins.length === 0);
  if (!pins.length) {
    document.getElementById("pin-detail").textContent = "";
    return;
  }
  if (!selectedPin || !pins.includes(selectedPin)) selectedPin = pins[0];
  const specs = project.spec_list || [];
  const skipped = project.skipped || [];
  const board = project.board || [];
  grid.innerHTML = pins
    .map((label) => {
      const spec = specs.find((item) => item.sku === PIN_SKUS[label]);
      const skip = skipped.find((item) => item.label === label);
      const lane = skip ? "skip" : spec?.lane || "close";
      const selected = label === selectedPin ? " selected" : "";
      const color = PIN_COLORS[label] || "#d7d1c7";
      const imageUrl = (board.find((pin) => pin.label === label) || {}).image_url || "";
      const photo = imageUrl
        ? `<img src="${escapeHtml(imageUrl)}" alt="${escapeHtml(label)}" onerror="this.remove()">`
        : "";
      return `<button type="button" class="pin${selected}" data-pin="${escapeHtml(label)}" style="background:${color}">
        ${photo}
        <span class="pin-copy">
          <span class="lane lane-${lane}">${laneLabel(lane)}</span>
          <p>${escapeHtml(label)}</p>
        </span>
      </button>`;
    })
    .join("");
  const skip = skipped.find((item) => item.label === selectedPin);
  const spec = specs.find((item) => item.sku === PIN_SKUS[selectedPin]);
  let detail = "";
  if (skip) detail = `${selectedPin} — ${skip.why}`;
  else if (spec) {
    const color = spec.color ? ` · ${spec.color}` : "";
    detail = `${spec.name} · ${spec.sku}${color} · ${money(spec.price_cents)}. ${spec.why}`;
  }
  document.getElementById("pin-detail").textContent = detail;
}

function renderProject(project) {
  if (!project) return;
  document.getElementById("project-status").textContent = prettyStatus(project.status);
  const rooms = Object.values(project.rooms || {});
  document.getElementById("project-room").textContent = rooms[0]?.name || "No room yet";

  const budget = project.budget || {};
  const locked = listIsLocked(project);
  const planned = budget.planned_cents != null
    ? budget.planned_cents
    : (budget.committed_cents || 0) + (budget.draft_cents || 0);
  const budgetEl = document.getElementById("project-budget");
  if (budget.total_cents == null) {
    budgetEl.textContent = "Budget not set";
  } else if (locked) {
    budgetEl.textContent = `${money(budget.committed_cents || planned)} committed of ${money(budget.total_cents)}`;
  } else {
    budgetEl.textContent = `${money(planned)} planned of ${money(budget.total_cents)}`;
  }
  budgetEl.classList.toggle("over", Boolean(budget.over_budget) && !locked);
  const meter = document.getElementById("budget-meter");
  const fill = document.getElementById("budget-fill");
  if (budget.total_cents) {
    meter.classList.remove("hidden");
    fill.style.width = `${Math.min(140, Math.round((planned / budget.total_cents) * 100))}%`;
    meter.classList.toggle("over", Boolean(budget.over_budget) && !locked);
  } else {
    meter.classList.add("hidden");
  }
  const overCopy = document.getElementById("project-over-copy");
  if (budget.over_budget && budget.total_cents != null && !locked) {
    overCopy.textContent = `${money(budget.over_cents || planned - budget.total_cents)} over ${money(budget.total_cents)}. Drop an optional line, pick a cheaper catalog SKU, or raise the cap.`;
  }
  setHidden("project-over", !budget.over_budget || locked);

  const brief = project.brief || {};
  const bits = [brief.lifestyle, brief.style_preferences].filter(Boolean);
  document.getElementById("project-brief").textContent =
    bits.join(" · ") || "No brief yet. Use a starter chip or tell me the room.";

  const specs = project.spec_list || [];
  const summary = project.pending_approval_summary || "";
  const rejected = project.rejected || [];
  const listNote = document.getElementById("list-note");
  if (summary) {
    listNote.textContent = summary;
  } else if (rejected.length && hasDraftSpec(project)) {
    listNote.textContent = `Asked: ${rejected[rejected.length - 1]}. Approve stays on the list.`;
  } else {
    listNote.textContent = "";
  }
  listNote.classList.toggle("hidden", !listNote.textContent);
  document.getElementById("project-specs").innerHTML = specs.length
    ? specs
        .map((item) => {
          const lane = item.lane || "must";
          const why = item.why ? `<p class="spec-why">${escapeHtml(item.why)}</p>` : "";
          const thumb = item.image_url
            ? `<img class="spec-thumb" src="${escapeHtml(item.image_url)}" alt="${escapeHtml(item.name)}" onerror="this.remove()">`
            : "";
          const noticed = Boolean(summary && item.sku && summary.includes(item.sku));
          const committed = item.status === "committed";
          const cheaper = !committed && (item.cheaper || [])[0];
          const cheaperBtn = cheaper
            ? `<button type="button" class="btn btn-ghost spec-act" data-swap-sku="${escapeHtml(item.sku)}" data-to-sku="${escapeHtml(cheaper.sku)}">Cheaper: ${escapeHtml(cheaper.name)} · ${money(cheaper.price_cents)}</button>`
            : "";
          const acts = committed
            ? ""
            : `<div class="spec-acts">
                <button type="button" class="btn btn-ghost spec-act" data-drop-sku="${escapeHtml(item.sku)}">Drop</button>
                ${cheaperBtn}
              </div>`;
          return `<li class="spec-row${noticed ? " noticed" : ""}">
            ${thumb}
            <div class="spec-body">
              <div class="spec-top">
                <span><span class="lane lane-${escapeHtml(lane)}">${escapeHtml(laneLabel(lane))}</span> <span class="spec-name">${escapeHtml(item.name)}</span></span>
                <span>${money(item.price_cents)}</span>
              </div>
              <p class="spec-meta">${escapeHtml(item.sku)} · ${escapeHtml(item.color || "")} · ${escapeHtml(item.status)}</p>
              ${why}
              ${acts}
            </div>
          </li>`;
        })
        .join("")
    : '<li class="muted">Empty until you map the sample board, tap a starter brief, or ask about a room.</li>';

  const skipped = project.skipped || [];
  setHidden("skipped-section", skipped.length === 0);
  document.getElementById("project-skipped").innerHTML = skipped
    .map((item) => `<li>${escapeHtml(item.label)} — ${escapeHtml(item.why)}</li>`)
    .join("");

  setHidden("rejected-section", rejected.length === 0);
  document.getElementById("project-rejected").innerHTML = rejected
    .map((note) => `<li>${escapeHtml(note)}</li>`)
    .join("");

  const started = specs.length > 0 || boardWasMapped();
  setHidden("start-guide", started);

  const roomName = rooms[0]?.name || "this room";
  const lockEl = document.getElementById("list-locked");
  lockEl.textContent = `Locked for the ${roomName}. This is the spec.`;
  setHidden("list-locked", !locked);
  document.querySelector(".list-panel")?.classList.toggle("is-locked", locked);

  const showApprove = !locked && (hasDraftSpec(project) || Boolean(project.pending_approval));
  setHidden("approval-actions", !showApprove);
  setHidden("list-actions", !showApprove);
  renderBoard(project);
}

async function mutateProject(path, extra) {
  const response = await fetch(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ context_key: contextKey, ...extra }),
  });
  const payload = await response.json();
  if (!response.ok) throw new Error(payload?.detail || "Project update failed.");
  renderProject(payload);
  return payload;
}

async function loadCapabilities() {
  try {
    const response = await fetch(`/api/capabilities?context_key=${encodeURIComponent(contextKey)}`);
    if (!response.ok) return;
    const caps = await response.json();
    boardBtn.classList.toggle("hidden", !caps.board_intake);
    document.getElementById("start-board")?.classList.toggle("hidden", !caps.board_intake);
  } catch {
    boardBtn.classList.remove("hidden");
  }
}

async function hydrateProject() {
  try {
    const response = await fetch(`/api/project?context_key=${encodeURIComponent(contextKey)}`);
    if (!response.ok) return;
    renderProject(await response.json());
  } catch {
    // Intake empty state is the fallback.
  }
}

async function sendChat(message) {
  if (askedForSampleBoard(message)) markBoardMapped();
  appendMessage("user", message);
  sendButton.disabled = true;
  showTypingIndicator();
  try {
    const response = await fetch("/api/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ message, context_key: contextKey }),
    });
    const payload = await response.json();
    if (!response.ok) throw new Error(payload?.detail || "Something went wrong.");
    hideTypingIndicator();
    renderProject(payload.project);
    try {
      const projectRes = await fetch(`/api/project?context_key=${encodeURIComponent(contextKey)}`);
      if (projectRes.ok) renderProject(await projectRes.json());
    } catch {
      // payload.project is the fallback
    }
    appendMessage("bot", payload.response || "No response returned.");
  } catch (error) {
    hideTypingIndicator();
    appendMessage("bot", `Could not reach the catalog just now. ${error.message}`);
  } finally {
    sendButton.disabled = false;
    promptInput.focus();
  }
}

appendMessage("bot", WELCOME, "welcome");
loadCapabilities();
hydrateProject();

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  const message = promptInput.value.trim();
  if (!message) return;
  promptInput.value = "";
  promptInput.style.height = "auto";
  await sendChat(message);
});

document.getElementById("start-board")?.addEventListener("click", () => {
  boardBtn.click();
});
document.getElementById("start-type")?.addEventListener("click", () => {
  promptInput.focus();
  document.querySelector(".ask-dock")?.scrollIntoView({ behavior: "smooth", block: "end" });
});

document.querySelectorAll(".chip").forEach((chip) => {
  chip.addEventListener("click", async () => {
    const brief = chip.dataset.brief;
    if (brief) await sendChat(brief);
  });
});

boardBtn.addEventListener("click", async () => {
  boardBtn.disabled = true;
  markBoardMapped();
  appendMessage("user", "Map the sample living-room board.");
  try {
    const project = await mutateProject("/api/project/from-board");
    const keep = (project.spec_list || []).filter((item) => item.lane === "must").length;
    const optional = (project.spec_list || []).filter((item) => item.lane === "close").length;
    const skip = (project.skipped || []).length;
    const over = project.budget || {};
    const overBit = over.over_budget
      ? ` ${money(over.over_cents)} over the cap — Fit the cap, drop an optional line, or raise it.`
      : " Approve when the list is right.";
    appendMessage("bot", `${keep} keep, ${optional} optional, ${skip} skipped.${overBit}`);
  } catch (error) {
    appendMessage("bot", `Could not map the board: ${error.message}`);
  } finally {
    boardBtn.disabled = false;
  }
});

document.getElementById("board-grid").addEventListener("click", (event) => {
  const pin = event.target.closest(".pin");
  if (!pin) return;
  selectedPin = pin.dataset.pin;
  hydrateProject();
});

async function approveList() {
  try {
    await mutateProject("/api/project/approve");
    setChangePanel(false);
    appendMessage("bot", "Approved. The list is locked.");
  } catch (error) {
    appendMessage("bot", `Could not approve: ${error.message}`);
  }
}

async function sendChangeRequest(reason) {
  const note = reason.trim();
  if (!note) return;
  setChangePanel(false);
  try {
    await mutateProject("/api/project/reject", { reason: note });
    await sendChat(note);
  } catch (error) {
    appendMessage("bot", `Could not send the change: ${error.message}`);
  }
}

document.addEventListener("click", async (event) => {
  const drop = event.target.closest("[data-drop-sku]");
  if (drop) {
    try {
      const project = await mutateProject("/api/project/drop-spec", { sku: drop.dataset.dropSku });
      appendMessage("bot", project.pending_approval_summary || "Removed that line.");
    } catch (error) {
      appendMessage("bot", `Could not drop that line: ${error.message}`);
    }
    return;
  }
  const swap = event.target.closest("[data-swap-sku]");
  if (swap) {
    try {
      const project = await mutateProject("/api/project/swap-spec", {
        sku: swap.dataset.swapSku,
        to_sku: swap.dataset.toSku,
      });
      appendMessage("bot", project.pending_approval_summary || "Swapped to a cheaper catalog SKU.");
    } catch (error) {
      appendMessage("bot", `Could not swap that line: ${error.message}`);
    }
    return;
  }
  const action = event.target.closest("[data-job]")?.dataset.job;
  if (action === "approve") approveList();
  if (action === "change") setChangePanel(true);
  if (action === "fit") {
    try {
      const project = await mutateProject("/api/project/fit-budget");
      appendMessage("bot", project.pending_approval_summary || "Fitted the cap from the catalog.");
    } catch (error) {
      appendMessage("bot", `Could not fit the cap: ${error.message}`);
    }
  }
  if (action === "raise") {
    try {
      const project = await mutateProject("/api/project/raise-budget");
      appendMessage("bot", project.pending_approval_summary || "Raised the cap to the planned spend.");
    } catch (error) {
      appendMessage("bot", `Could not raise the cap: ${error.message}`);
    }
  }
});

const askDock = document.querySelector(".ask-dock");
const studioDock = document.querySelector(".studio-dock");
const chatResizer = document.getElementById("chat-resizer");
const CHAT_HEIGHT_KEY = "decora-chat-height";
const CHAT_MIN = 180;

function clampChatHeight(px) {
  const max = Math.round(window.innerHeight * 0.7);
  return Math.max(CHAT_MIN, Math.min(max, Math.round(px)));
}

function setChatHeight(px) {
  const next = clampChatHeight(px);
  studioDock.style.setProperty("--chat-h", `${next}px`);
  try {
    localStorage.setItem(CHAT_HEIGHT_KEY, String(next));
  } catch {
    // ignore
  }
  messages.scrollTop = messages.scrollHeight;
}

try {
  const saved = Number(localStorage.getItem(CHAT_HEIGHT_KEY));
  if (saved) setChatHeight(saved);
} catch {
  // default --chat-h
}

let chatDrag = null;
chatResizer.addEventListener("pointerdown", (event) => {
  event.preventDefault();
  chatResizer.setPointerCapture(event.pointerId);
  chatDrag = {
    startY: event.clientY,
    startH: studioDock.getBoundingClientRect().height,
  };
});
chatResizer.addEventListener("pointermove", (event) => {
  if (!chatDrag) return;
  setChatHeight(chatDrag.startH + (chatDrag.startY - event.clientY));
});
chatResizer.addEventListener("pointerup", () => {
  chatDrag = null;
});
chatResizer.addEventListener("keydown", (event) => {
  if (event.key !== "ArrowUp" && event.key !== "ArrowDown") return;
  event.preventDefault();
  const current = studioDock.getBoundingClientRect().height;
  setChatHeight(current + (event.key === "ArrowUp" ? 32 : -32));
});

promptInput.addEventListener("keydown", (event) => {
  if (event.key === "Enter" && !event.shiftKey) {
    event.preventDefault();
    form.requestSubmit();
  }
});

document.getElementById("change-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  await sendChangeRequest(document.getElementById("change-input").value);
});

document.getElementById("change-cancel").addEventListener("click", () => {
  setChangePanel(false);
});
