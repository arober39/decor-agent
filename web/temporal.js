const contextKey = crypto.randomUUID();

// ---------- Single-turn chat (Temporal) ----------
const chatInput = document.getElementById("chat-input");
const chatSend = document.getElementById("chat-send");
const chatAnswer = document.getElementById("chat-answer");

// Same animated loading widget as the original chat (app.js).
const THINKING_WIDGET = `
  <div class="message bot typing" aria-label="Assistant is thinking">
    <span class="thinking-ring" aria-hidden="true"></span>
    <span class="thinking-label">
      <span class="thinking-text" data-text="Designing your space">Designing your space</span>
      <span class="thinking-ellipsis"><span></span><span></span><span></span></span>
    </span>
  </div>
`;

function showChatAnswer(text) {
  chatAnswer.classList.remove("thinking");
  chatAnswer.textContent = text;
}

chatSend.addEventListener("click", async () => {
  const message = chatInput.value.trim();
  if (!message) return;
  chatSend.disabled = true;
  chatSend.textContent = "Thinking...";
  chatAnswer.classList.remove("hidden");
  chatAnswer.classList.add("thinking");
  chatAnswer.innerHTML = THINKING_WIDGET;
  try {
    const res = await fetch("/api/temporal/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ message, context_key: contextKey }),
    });
    const data = await res.json();
    showChatAnswer(data.response || data.detail || "No response.");
  } catch (e) {
    showChatAnswer("Error: " + e.message);
  } finally {
    chatSend.disabled = false;
    chatSend.textContent = "Ask";
  }
});

// ---------- Whole-home approval flow ----------
const planStart = document.getElementById("plan-start");
const planBudget = document.getElementById("plan-budget");
const statusBlock = document.getElementById("status-block");
const phaseBadge = document.getElementById("phase-badge");
const planThinking = document.getElementById("plan-thinking");
const planThinkingText = planThinking.querySelector(".thinking-text");
const roomProgress = document.getElementById("room-progress");
const draftBlock = document.getElementById("draft-block");
const draftPlans = document.getElementById("draft-plans");
const finalBlock = document.getElementById("final-block");
const finalOutput = document.getElementById("final-output");

let currentWorkflowId = null;
let pollTimer = null;
let decisionSubmitted = false;   // a decision button was clicked, awaiting the phase change
let pendingLabel = null;         // optimistic widget label until the phase advances
let snapshotFailures = 0;        // consecutive failed snapshot polls (stale tab / reset server)

function setPlanWidget(label) {
  if (label) {
    planThinkingText.textContent = label;
    planThinkingText.setAttribute("data-text", label);
    planThinking.classList.remove("hidden");
  } else {
    planThinking.classList.add("hidden");
  }
}

function stopPolling(message) {
  if (pollTimer) { clearInterval(pollTimer); pollTimer = null; }
  setPlanWidget(null);
  draftBlock.classList.add("hidden");
  phaseBadge.textContent = "unavailable";
  if (message) roomProgress.textContent = message;
}

function resetBlocks() {
  statusBlock.classList.remove("hidden");
  draftBlock.classList.add("hidden");
  finalBlock.classList.add("hidden");
  planThinking.classList.add("hidden");
  decisionSubmitted = false;
  pendingLabel = null;
  snapshotFailures = 0;
  draftPlans.innerHTML = "";
  finalOutput.textContent = "";
  roomProgress.innerHTML = "";
}

function renderSnapshot(snap) {
  phaseBadge.textContent = (snap.phase || "").replace(/_/g, " ");

  // Once the workflow advances past the decision point, drop the optimistic
  // state we set when the user clicked a decision button.
  if (snap.phase !== "awaiting_decision") decisionSubmitted = false;

  // Loading widget. While a decision is in flight (button clicked but the
  // snapshot still reports "awaiting_decision"), keep the optimistic label so
  // the widget doesn't flicker back to the draft. build_shopping_list can
  // finish between 1s polls, so we can't rely on observing "building_list".
  if (decisionSubmitted && snap.phase === "awaiting_decision") {
    setPlanWidget(pendingLabel);            // null => stays hidden (reject)
  } else {
    const busy = !["awaiting_decision", "completed", "rejected"].includes(snap.phase);
    setPlanWidget(busy
      ? (snap.phase === "building_list" ? "Locking in your designs" : "Designing your space")
      : null);
  }

  // per-room progress chips
  if (snap.rooms_total > 0) {
    const done = new Set(snap.rooms_done || []);
    // show done rooms as green; show a count for not-yet-done
    roomProgress.innerHTML = "";
    (snap.rooms_done || []).forEach((r) => {
      const chip = document.createElement("span");
      chip.className = "room-chip done";
      chip.textContent = r + " ✓";
      roomProgress.appendChild(chip);
    });
    const remaining = snap.rooms_total - (snap.rooms_done || []).length;
    if (remaining > 0) {
      const chip = document.createElement("span");
      chip.className = "room-chip";
      chip.textContent = `${remaining} planning…`;
      roomProgress.appendChild(chip);
    }
  }

  // draft + decision buttons once awaiting decision
  if (snap.phase === "awaiting_decision" && !decisionSubmitted && (snap.draft_plans || []).length) {
    draftBlock.classList.remove("hidden");
    draftPlans.innerHTML = "";
    snap.draft_plans.forEach((p) => {
      const div = document.createElement("div");
      div.className = "draft-plan";
      div.innerHTML = `<h3></h3><pre></pre>`;
      div.querySelector("h3").textContent = p.room;
      div.querySelector("pre").textContent = p.plan_text;
      draftPlans.appendChild(div);
    });
  } else {
    draftBlock.classList.add("hidden");
  }
}

async function poll() {
  if (!currentWorkflowId) return;
  try {
    const res = await fetch(`/api/temporal/plan/${currentWorkflowId}/snapshot`);
    if (!res.ok) {
      // workflow not found (stale tab / dev server reset) — give up after a few tries
      if (++snapshotFailures >= 3) {
        stopPolling("This plan is no longer available — start a new one.");
      }
      return;
    }
    snapshotFailures = 0;
    const snap = await res.json();
    renderSnapshot(snap);

    if (snap.phase === "completed" || snap.phase === "rejected") {
      clearInterval(pollTimer);
      pollTimer = null;
      await showResult();
    }
  } catch (e) {
    // transient network error; keep polling
  }
}

async function showResult() {
  draftBlock.classList.add("hidden");
  finalBlock.classList.remove("hidden");
  finalOutput.textContent = "Fetching result...";
  try {
    const res = await fetch(`/api/temporal/plan/${currentWorkflowId}/result`);
    const data = await res.json();
    finalOutput.textContent = data.response || data.detail || "No result.";
  } catch (e) {
    finalOutput.textContent = "Error fetching result: " + e.message;
  }
}

planStart.addEventListener("click", async () => {
  resetBlocks();
  // show the widget right away, before the first snapshot poll arrives
  setPlanWidget("Designing your space");
  planStart.disabled = true;
  planStart.textContent = "Starting...";
  try {
    const res = await fetch("/api/temporal/plan", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        message: "plan my whole apartment",
        budget: planBudget.value || "not specified",
        context_key: contextKey,
      }),
    });
    const data = await res.json();
    currentWorkflowId = data.workflow_id;
    if (!currentWorkflowId) throw new Error(data.detail || "No workflow id");
    pollTimer = setInterval(poll, 1000);
    poll();
  } catch (e) {
    phaseBadge.textContent = "error";
    statusBlock.classList.remove("hidden");
    roomProgress.textContent = e.message;
  } finally {
    planStart.disabled = false;
    planStart.textContent = "Draft whole-home plan";
  }
});

async function sendDecision(decision, newBudget) {
  // Optimistically reflect the decision right away — the next phase is brief
  // (build_shopping_list can finish between 1s polls), so don't wait for one.
  decisionSubmitted = true;
  pendingLabel = decision === "approve" ? "Locking in your designs"
    : decision === "tweak_budget" ? "Designing your space"
    : null;                                  // reject -> no widget
  draftBlock.classList.add("hidden");
  setPlanWidget(pendingLabel);

  const body = { decision };
  if (newBudget) body.new_budget = newBudget;
  await fetch(`/api/temporal/plan/${currentWorkflowId}/decision`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  // resume polling so we see re-plan (tweak) or completion (approve/reject)
  if (!pollTimer) pollTimer = setInterval(poll, 1000);
}

document.getElementById("btn-approve").addEventListener("click", () =>
  sendDecision("approve"));
document.getElementById("btn-reject").addEventListener("click", () =>
  sendDecision("reject"));
document.getElementById("btn-tweak").addEventListener("click", () => {
  const nb = prompt("New budget?", planBudget.value);
  if (nb) sendDecision("tweak_budget", nb);
});