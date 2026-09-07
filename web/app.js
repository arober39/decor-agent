const form = document.getElementById("chat-form");
const promptInput = document.getElementById("prompt");
const tierSelect = document.getElementById("tier");
const sendButton = document.getElementById("send");
const messages = document.getElementById("messages");

const contextKey = crypto.randomUUID();

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

function renderProject(project) {
  if (!project) return;
  document.getElementById("project-status").textContent = (project.status || "intake").replaceAll("_", " ");
  const budget = project.budget || {};
  const planned = (budget.committed_cents || 0) + (budget.draft_cents || 0);
  document.getElementById("project-budget").textContent =
    budget.total_cents == null
      ? "Not set"
      : `${money(planned)} planned of ${money(budget.total_cents)}`;

  const brief = project.brief || {};
  const bits = [
    brief.lifestyle,
    brief.style_preferences ? `style: ${brief.style_preferences}` : "",
    (brief.keep || []).length ? `keep ${brief.keep.join(", ")}` : "",
  ].filter(Boolean);
  document.getElementById("project-brief").textContent = bits.join(" · ") || "Waiting for a brief.";

  const roomsEl = document.getElementById("project-rooms");
  const rooms = Object.values(project.rooms || {});
  roomsEl.innerHTML = rooms.length
    ? rooms.map((room) => {
        const dims = room.width_ft && room.length_ft ? ` · ${room.width_ft}×${room.length_ft} ft` : "";
        return `<li>${room.name} (${room.room_type}${dims})</li>`;
      }).join("")
    : '<li class="muted">None yet</li>';

  const specsEl = document.getElementById("project-specs");
  const specs = project.spec_list || [];
  specsEl.innerHTML = specs.length
    ? specs.map((item) => `<li>${item.name} · ${money(item.price_cents)} · ${item.status}</li>`).join("")
    : '<li class="muted">Empty until catalog SKUs are added.</li>';

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
    body: JSON.stringify({ context_key: contextKey, user_tier: tierSelect.value, ...extra }),
  });
  const payload = await response.json();
  if (!response.ok) throw new Error(payload?.detail || "Project update failed.");
  renderProject(payload);
  return payload;
}

appendMessage(
  "bot",
  "Hi — I am Decora. Tell me the room and budget. I will source catalog pieces and ask before anything is committed."
);

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  const message = promptInput.value.trim();
  if (!message) return;

  appendMessage("user", message);
  promptInput.value = "";
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
        user_tier: tierSelect.value,
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
