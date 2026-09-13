const form = document.getElementById("chat-form");
const promptInput = document.getElementById("prompt");
const sendButton = document.getElementById("send");
const messages = document.getElementById("messages");
const boardBtn = document.getElementById("board-btn");

const CONTEXT_STORAGE_KEY = "decora-context-key";

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

function appendMessage(role, text) {
  const entry = document.createElement("article");
  entry.className = `message ${role}`;
  entry.textContent = text;
  messages.appendChild(entry);
  messages.scrollTop = messages.scrollHeight;
}

function showTypingIndicator() {
  const entry = document.createElement("article");
  entry.className = "message bot typing";
  entry.id = "typing-indicator";
  entry.setAttribute("aria-label", "Assistant is thinking");
  entry.innerHTML = `
    <span class="thinking-ring" aria-hidden="true"></span>
    <span class="thinking-label">
      <span class="thinking-text" data-text="Designing your space">Designing your space</span>
      <span class="thinking-ellipsis">
        <span></span><span></span><span></span>
      </span>
    </span>
  `;
  messages.appendChild(entry);
  messages.scrollTop = messages.scrollHeight;
}

function hideTypingIndicator() {
  const entry = document.getElementById("typing-indicator");
  if (entry) entry.remove();
}

function money(cents) {
  if (cents == null) return "—";
  return `$${(cents / 100).toFixed(0)}`;
}

function prettyStatus(status) {
  return (status || "intake")
    .replaceAll("_", " ")
    .replace(/\b\w/g, (letter) => letter.toUpperCase());
}

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

function setSection(id, visible) {
  const section = document.getElementById(id);
  if (section) section.hidden = !visible;
}

function renderProject(project) {
  if (!project) return;
  document.getElementById("project-status").textContent = prettyStatus(project.status);
  const budget = project.budget || {};
  const planned = budget.planned_cents != null
    ? budget.planned_cents
    : (budget.committed_cents || 0) + (budget.draft_cents || 0);
  document.getElementById("project-budget").textContent =
    budget.total_cents == null
      ? "Not set"
      : `${money(planned)} planned of ${money(budget.total_cents)}`;
  const over = document.getElementById("project-over");
  over.hidden = !budget.over_budget;
  const meter = document.getElementById("budget-meter");
  const fill = document.getElementById("budget-fill");
  if (budget.total_cents) {
    meter.hidden = false;
    const pct = Math.min(140, Math.round((planned / budget.total_cents) * 100));
    fill.style.width = `${pct}%`;
    meter.classList.toggle("over", Boolean(budget.over_budget));
  } else {
    meter.hidden = true;
  }

  const brief = project.brief || {};
  const bits = [
    brief.lifestyle,
    brief.style_preferences ? `style: ${brief.style_preferences}` : "",
    (brief.keep || []).length ? `keep ${brief.keep.join(", ")}` : "",
  ].filter(Boolean);
  document.getElementById("project-brief").textContent = bits.join(" · ") || "Waiting for a brief.";

  const pins = project.board_pins || [];
  setSection("pins-section", pins.length > 0);
  document.getElementById("project-pins").innerHTML = pins
    .map((label) => `<span class="pin">${escapeHtml(label)}</span>`)
    .join("");

  const rooms = Object.values(project.rooms || {});
  setSection("rooms-section", rooms.length > 0);
  document.getElementById("project-rooms").innerHTML = rooms
    .map((room) => {
      const dims = room.width_ft && room.length_ft ? ` · ${room.width_ft}×${room.length_ft} ft` : "";
      return `<li>${escapeHtml(room.name)} (${escapeHtml(room.room_type)}${dims})</li>`;
    })
    .join("");

  const specsEl = document.getElementById("project-specs");
  const specs = project.spec_list || [];
  specsEl.innerHTML = specs.length
    ? specs.map((item) => {
        const lane = item.lane || "must";
        const why = item.why ? `<p class="spec-why">${escapeHtml(item.why)}</p>` : "";
        return `<li class="spec-row">
          <div class="spec-top">
            <span class="lane lane-${escapeHtml(lane)}">${escapeHtml(lane === "must" ? "Keep" : lane === "close" ? "Optional" : lane)}</span>
            <strong class="spec-name">${escapeHtml(item.name)}</strong>
            <span class="spec-price">${money(item.price_cents)}</span>
          </div>
          <p class="spec-meta">${escapeHtml(item.sku)} · ${escapeHtml(item.status)}</p>
          ${why}
        </li>`;
      }).join("")
    : '<li class="muted">Empty until catalog SKUs are added.</li>';

  const skipped = project.skipped || [];
  setSection("skipped-section", skipped.length > 0);
  document.getElementById("project-skipped").innerHTML = skipped
    .map((item) => `<li>${escapeHtml(item.label)}${item.why ? ` — ${escapeHtml(item.why)}` : ""}</li>`)
    .join("");

  const rejected = project.rejected || [];
  setSection("rejected-section", rejected.length > 0);
  document.getElementById("project-rejected").innerHTML = rejected
    .map((note) => `<li>${escapeHtml(note)}</li>`)
    .join("");

  const card = document.getElementById("approval-card");
  if (project.pending_approval) {
    card.hidden = false;
    document.getElementById("approval-summary").textContent =
      project.pending_approval_summary || "Approve to commit the current spec list.";
  } else {
    card.hidden = true;
  }
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
    boardBtn.hidden = !caps.board_intake;
  } catch {
    boardBtn.hidden = false;
  }
}

async function hydrateProject() {
  try {
    const response = await fetch(`/api/project?context_key=${encodeURIComponent(contextKey)}`);
    if (!response.ok) return;
    renderProject(await response.json());
  } catch {
    // Empty intake panel is the fallback.
  }
}

async function sendChat(message) {
  appendMessage("user", message);
  sendButton.disabled = true;
  sendButton.textContent = "Sending...";
  showTypingIndicator();

  try {
    const response = await fetch("/api/chat", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        message,
        context_key: contextKey,
      }),
    });

    const payload = await response.json();
    if (!response.ok) {
      const detail = payload?.detail || "Something went wrong.";
      throw new Error(detail);
    }

    hideTypingIndicator();
    renderProject(payload.project);
    try {
      const projectRes = await fetch(`/api/project?context_key=${encodeURIComponent(contextKey)}`);
      if (projectRes.ok) {
        renderProject(await projectRes.json());
      }
    } catch {
      // Chat payload.project is the fallback if the resource read fails.
    }
    appendMessage("bot", payload.response || "No response returned.");
  } catch (error) {
    hideTypingIndicator();
    appendMessage("bot", `Sorry, I hit an error: ${error.message}`);
  } finally {
    sendButton.disabled = false;
    sendButton.textContent = "Send";
    promptInput.focus();
  }
}

appendMessage(
  "bot",
  "Hi — I am Decora. Pick a starter, map the sample board, or tell me the room and budget. I will source catalog pieces and ask before anything is committed."
);

loadCapabilities();
hydrateProject();

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  const message = promptInput.value.trim();
  if (!message) return;
  promptInput.value = "";
  await sendChat(message);
});

document.getElementById("starter-chips").addEventListener("click", async (event) => {
  const chip = event.target.closest(".chip");
  if (!chip || chip.id === "board-btn") return;
  const brief = chip.dataset.brief;
  if (!brief) return;
  await sendChat(brief);
});

boardBtn.addEventListener("click", async () => {
  boardBtn.disabled = true;
  appendMessage("user", "Map the sample living-room board.");
  try {
    const project = await mutateProject("/api/project/from-board");
    const must = (project.spec_list || []).filter((item) => item.lane === "must").length;
    const close = (project.spec_list || []).filter((item) => item.lane === "close").length;
    const skip = (project.skipped || []).length;
    appendMessage(
      "bot",
      `Board mapped: ${must} keep, ${close} optional, ${skip} skipped. Skips are not spend. Approve when the list is right.`
    );
    document.getElementById("approval-card").scrollIntoView({ behavior: "smooth", block: "nearest" });
  } catch (error) {
    appendMessage("bot", `Could not map the board: ${error.message}`);
  } finally {
    boardBtn.disabled = false;
  }
});

document.getElementById("approve-btn").addEventListener("click", async () => {
  try {
    await mutateProject("/api/project/approve");
    appendMessage("bot", "Approved. Draft spec items are now committed.");
  } catch (error) {
    appendMessage("bot", `Could not approve: ${error.message}`);
  }
});

document.getElementById("reject-btn").addEventListener("click", async () => {
  const reason = window.prompt("What should Decora change?") || "Client rejected the current plan";
  try {
    await mutateProject("/api/project/reject", { reason });
    appendMessage("bot", "Rejected. Tell me what to change.");
  } catch (error) {
    appendMessage("bot", `Could not reject: ${error.message}`);
  }
});
