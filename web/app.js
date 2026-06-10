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

appendMessage("bot", "Hi, I am your decor assistant. What space are you working on?");

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
