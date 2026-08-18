const MODES = [
  { key: "chat", label: "Chat", icon: "bi-chat-dots" },
  { key: "knowledge", label: "Knowledge", icon: "bi-diagram-3" },
  { key: "create", label: "Create", icon: "bi-magic" },
  { key: "project", label: "Project", icon: "bi-kanban" },
  { key: "research", label: "Research", icon: "bi-search" },
  { key: "developer", label: "Developer", icon: "bi-code-slash" },
  { key: "automation", label: "Automation", icon: "bi-gear-wide-connected" },
];

let activeConversationId = null;
let claudeConfigured = false;
let isStreaming = false;
let newChatModal;
let userProjects = [];
let defaultMode = "chat";

// --- Voice input (speech-to-text) + output (text-to-speech) state ---
// Both use the browser's native Web Speech API (SpeechRecognition /
// speechSynthesis) — no backend involved, no new dependency, and no
// vendor cost: this is deliberately NOT the same pipeline as the
// separate Audio Generation studio (which produces downloadable files
// via a job queue over a few seconds — too slow for "click to hear this
// chat message instantly").
let speechRecognition = null;
let isRecording = false;
let currentSpeakerBtn = null;

const VOICE_LANG_STORAGE_KEY = "aiagent:chat-voice-language";
const AUTO_SPEAK_STORAGE_KEY = "aiagent:chat-auto-speak";

function agentEscapeHtml(str) {
  const div = document.createElement("div");
  div.textContent = str;
  return div.innerHTML;
}

function relativeTime(iso) {
  const diffMs = Date.now() - new Date(iso).getTime();
  const mins = Math.round(diffMs / 60000);
  if (mins < 1) return "just now";
  if (mins < 60) return `${mins}m ago`;
  const hours = Math.round(mins / 60);
  if (hours < 24) return `${hours}h ago`;
  const days = Math.round(hours / 24);
  return `${days}d ago`;
}

function modeMeta(key) {
  return MODES.find((m) => m.key === key) || MODES[0];
}

async function loadStatus() {
  try {
    const s = await window.AIAgentApi.get("/agent/status");
    claudeConfigured = s.configured;
    const badge = document.getElementById("claude-status-badge");
    const providerLabel = window.AIAgentConfig.aiProviderLabel(s.provider);
    if (s.configured) {
      badge.className = "badge-pill badge-success";
      badge.innerHTML = `<span class="dot dot-success"></span> ${providerLabel} connected (${s.model})`;
      document.getElementById("provider-banner").classList.add("d-none");
    } else {
      badge.className = "badge-pill badge-warning";
      badge.innerHTML = `<span class="dot dot-muted"></span> ${providerLabel} not configured`;
      document.getElementById("provider-banner").classList.remove("d-none");
      document.getElementById("provider-banner-text").textContent =
        `${s.detail} You can still create conversations — messages will show this same error until it's configured.`;
    }
  } catch (err) {
    window.AIAgentToast.show("Could not check AI provider connection status.", "error");
  }
}

function renderModePicker(container, { onSelect, selected = "chat" } = {}) {
  container.innerHTML = MODES.map(
    (m) => `<button type="button" class="mode-pill ${m.key === selected ? "active" : ""}" data-mode="${m.key}"><i class="bi ${m.icon}"></i> ${m.label}</button>`
  ).join("");
  container.querySelectorAll("[data-mode]").forEach((btn) => {
    btn.addEventListener("click", () => {
      container.querySelectorAll("[data-mode]").forEach((b) => b.classList.remove("active"));
      btn.classList.add("active");
      if (onSelect) onSelect(btn.dataset.mode);
    });
  });
}

async function loadProjectOptions() {
  try {
    userProjects = await window.AIAgentApi.get("/projects?status=active");
    const select = document.getElementById("new-chat-project");
    select.innerHTML = '<option value="">No project</option>';
    userProjects.forEach((p) => {
      const opt = document.createElement("option");
      opt.value = p.id;
      opt.textContent = p.name;
      select.appendChild(opt);
    });
    document.getElementById("new-chat-project-wrap").classList.toggle("d-none", userProjects.length === 0);
  } catch {
    // Non-fatal: project scoping is optional.
  }
}

async function loadConversations() {
  const container = document.getElementById("conv-items");
  try {
    const conversations = await window.AIAgentApi.get("/agent/conversations");
    if (!conversations.length) {
      container.innerHTML = `<div class="empty-state" style="padding:2rem 1rem;"><p style="font-size:0.82rem;">No conversations yet.</p></div>`;
      return;
    }
    container.innerHTML = conversations
      .map((c) => {
        const meta = modeMeta(c.mode);
        return `
        <div class="conv-item ${c.id === activeConversationId ? "active" : ""}" data-conv-id="${c.id}">
          <div class="conv-icon"><i class="bi ${meta.icon}"></i></div>
          <div class="conv-meta">
            <div class="conv-title">${agentEscapeHtml(c.title)}</div>
            <div class="conv-sub">${meta.label}${c.project_name ? " · " + agentEscapeHtml(c.project_name) : ""} · ${relativeTime(c.updated_at)}</div>
          </div>
          <button type="button" class="conv-delete-btn" data-conv-id="${c.id}" title="Delete"><i class="bi bi-trash3"></i></button>
        </div>`;
      })
      .join("");

    container.querySelectorAll(".conv-item").forEach((el) => {
      el.addEventListener("click", (e) => {
        if (e.target.closest(".conv-delete-btn")) return;
        selectConversation(el.dataset.convId);
      });
    });
    container.querySelectorAll(".conv-delete-btn").forEach((btn) => {
      btn.addEventListener("click", async (e) => {
        e.stopPropagation();
        const confirmed = await window.AIAgentModals.confirmAction({
          title: "Delete this conversation?",
          message: "This permanently deletes the conversation and its messages.",
          confirmLabel: "Delete",
          danger: true,
        });
        if (!confirmed) return;
        await window.AIAgentApi.del(`/agent/conversations/${btn.dataset.convId}`);
        if (btn.dataset.convId === activeConversationId) {
          activeConversationId = null;
          document.getElementById("thread-active").classList.add("d-none");
          document.getElementById("thread-empty-state").classList.remove("d-none");
        }
        loadConversations();
      });
    });
  } catch (err) {
    container.innerHTML = `<div class="empty-state" style="padding:2rem 1rem;"><p>${err.message}</p></div>`;
  }
}

function renderMessageRow(role, content, { error = null, id = null, getLanguage = null } = {}) {
  const row = document.createElement("div");
  row.className = `msg-row ${role}`;
  if (id) row.dataset.messageId = id;
  const avatarIcon = role === "user" ? "bi-person" : "bi-stars";
  const showSpeaker = role === "assistant" && !error;
  row.innerHTML = `
    <div class="msg-avatar"><i class="bi ${avatarIcon}"></i></div>
    <div class="msg-bubble-wrap">
      <div class="route-badge-slot"></div>
      <div class="msg-bubble ${error ? "error-bubble" : ""}">${content}</div>
      <div class="sources-slot"></div>
      ${showSpeaker ? `<div class="msg-bubble-actions"><button type="button" class="speaker-btn" title="Read aloud" aria-label="Read message aloud"><i class="bi bi-volume-up"></i></button></div>` : ""}
    </div>`;
  if (showSpeaker) wireSpeakerButton(row, getLanguage);
  return row;
}

// getLanguage is a closure so a live (still-streaming) message picks up
// its routing language once the "route" SSE event arrives, even though
// the button itself was created before that event landed.
function wireSpeakerButton(row, getLanguage) {
  const btn = row.querySelector(".speaker-btn");
  if (!btn) return;
  btn.addEventListener("click", () => {
    const bubble = row.querySelector(".msg-bubble");
    const text = bubble.textContent.trim();
    if (!text) return;
    speakText(text, getLanguage ? getLanguage() : "english", btn);
  });
}

// --- Voice output (speaker button / Auto Speak) ---

function pickVoiceForLanguage(language) {
  const voices = window.speechSynthesis.getVoices();
  if (!voices.length) return null;
  if (language === "tamil" || language === "tanglish") {
    return voices.find((v) => v.lang && v.lang.toLowerCase().startsWith("ta")) || null;
  }
  return voices.find((v) => v.lang && v.lang.toLowerCase().startsWith("en")) || null;
}

function stopSpeaking() {
  if ("speechSynthesis" in window) window.speechSynthesis.cancel();
  if (currentSpeakerBtn) {
    currentSpeakerBtn.classList.remove("speaking");
    const icon = currentSpeakerBtn.querySelector("i");
    if (icon) icon.className = "bi bi-volume-up";
  }
  currentSpeakerBtn = null;
}

function speakText(text, language, btn) {
  if (!("speechSynthesis" in window) || typeof SpeechSynthesisUtterance === "undefined") {
    window.AIAgentToast.show("Voice playback is not supported in this browser.", "error");
    return;
  }
  const wasSpeakingThisButton = currentSpeakerBtn === btn;
  stopSpeaking();
  if (wasSpeakingThisButton) return; // clicking the active speaker again just stops it

  const utterance = new SpeechSynthesisUtterance(text);
  const voice = pickVoiceForLanguage(language);
  if (voice) utterance.voice = voice;

  utterance.onstart = () => {
    btn.classList.add("speaking");
    btn.querySelector("i").className = "bi bi-volume-up-fill";
  };
  const reset = () => {
    btn.classList.remove("speaking");
    const icon = btn.querySelector("i");
    if (icon) icon.className = "bi bi-volume-up";
    if (currentSpeakerBtn === btn) currentSpeakerBtn = null;
  };
  utterance.onend = reset;
  utterance.onerror = (e) => {
    // Chrome fires an "interrupted"/"canceled" error whenever a new
    // utterance preempts this one (e.g. the user clicked a different
    // speaker button) — that's expected, not a real playback failure,
    // so only surface a toast for genuine errors.
    if (e.error !== "interrupted" && e.error !== "canceled") {
      window.AIAgentToast.show("Could not play audio for this message.", "error");
    }
    reset();
  };

  currentSpeakerBtn = btn;
  window.speechSynthesis.speak(utterance);
}

// --- Voice input (microphone -> speech recognition) ---

function getRecognitionLang() {
  const selected = document.getElementById("voice-language-select").value;
  // The Web Speech API has no real "auto-detect language" mode (that's
  // a genuine browser limitation, not something this app can add) —
  // "Auto Detect" and "Tanglish" both fall back to the closest available
  // recognition locale; the resulting TEXT still goes through the same
  // backend language-aware routing/response logic regardless of which
  // locale recognized it.
  if (selected === "auto") return "en-US";
  if (selected === "tanglish") return "en-IN";
  return selected; // "en-US" or "ta-IN"
}

function initVoiceInput() {
  const micBtn = document.getElementById("mic-btn");
  const SpeechRecognitionCtor = window.SpeechRecognition || window.webkitSpeechRecognition;
  if (!SpeechRecognitionCtor) {
    micBtn.disabled = true;
    micBtn.title = "Voice input is not supported in this browser.";
    return;
  }

  micBtn.addEventListener("click", () => {
    if (isRecording) {
      speechRecognition.stop();
      return;
    }
    startRecording(SpeechRecognitionCtor);
  });
}

function startRecording(SpeechRecognitionCtor) {
  const micBtn = document.getElementById("mic-btn");
  const indicator = document.getElementById("listening-indicator");

  speechRecognition = new SpeechRecognitionCtor();
  speechRecognition.lang = getRecognitionLang();
  speechRecognition.interimResults = false;
  speechRecognition.maxAlternatives = 1;

  speechRecognition.onstart = () => {
    isRecording = true;
    micBtn.classList.add("recording");
    micBtn.querySelector("i").className = "bi bi-mic-fill";
    indicator.classList.remove("d-none");
  };

  speechRecognition.onresult = (event) => {
    const transcript = (event.results[0] && event.results[0][0] && event.results[0][0].transcript || "").trim();
    if (!transcript) {
      window.AIAgentToast.show("No speech was detected. Please try again.", "error");
      return;
    }
    const input = document.getElementById("composer-input");
    input.value = input.value ? `${input.value} ${transcript}` : transcript;
    autoGrowTextarea(input);
    input.focus();
  };

  speechRecognition.onerror = (event) => {
    const messages = {
      "not-allowed": "Microphone permission was denied. Allow microphone access in your browser to use voice input.",
      "service-not-allowed": "Microphone permission was denied. Allow microphone access in your browser to use voice input.",
      "no-speech": "No speech was detected. Please try again.",
      "audio-capture": "No microphone was found on this device.",
      "network": "A network error interrupted speech recognition.",
    };
    window.AIAgentToast.show(messages[event.error] || "Voice input failed. Please try again.", "error");
  };

  speechRecognition.onend = () => {
    isRecording = false;
    micBtn.classList.remove("recording");
    micBtn.querySelector("i").className = "bi bi-mic";
    indicator.classList.add("d-none");
  };

  try {
    speechRecognition.start();
  } catch (err) {
    console.error("[agent] Could not start voice input:", err);
    window.AIAgentToast.show("Could not start voice input.", "error");
  }
}

function initVoiceSettings() {
  const langSelect = document.getElementById("voice-language-select");
  const autoSpeakToggle = document.getElementById("auto-speak-toggle");

  const savedLang = localStorage.getItem(VOICE_LANG_STORAGE_KEY);
  if (savedLang) langSelect.value = savedLang;
  langSelect.addEventListener("change", () => {
    localStorage.setItem(VOICE_LANG_STORAGE_KEY, langSelect.value);
  });

  autoSpeakToggle.checked = localStorage.getItem(AUTO_SPEAK_STORAGE_KEY) === "1";
  autoSpeakToggle.addEventListener("change", () => {
    localStorage.setItem(AUTO_SPEAK_STORAGE_KEY, autoSpeakToggle.checked ? "1" : "0");
    if (!autoSpeakToggle.checked) stopSpeaking();
  });

  initVoiceInput();
}

async function selectConversation(id) {
  stopSpeaking();
  activeConversationId = id;
  document.getElementById("thread-empty-state").classList.add("d-none");
  document.getElementById("thread-active").classList.remove("d-none");
  document.querySelectorAll(".conv-item").forEach((el) => {
    el.classList.toggle("active", el.dataset.convId === id);
  });

  const thread = document.getElementById("agent-thread");
  thread.innerHTML = `<div class="skeleton" style="height:60px; border-radius:12px;"></div>`;

  try {
    const detail = await window.AIAgentApi.get(`/agent/conversations/${id}`);
    thread.innerHTML = "";
    detail.messages.forEach((m) => {
      const content = m.error
        ? `${agentEscapeHtml(m.content)}<span class="msg-error-note"><i class="bi bi-exclamation-triangle"></i> ${agentEscapeHtml(m.error)}</span>`
        : agentEscapeHtml(m.content);
      thread.appendChild(renderMessageRow(m.role, content, { error: m.error, id: m.id }));
    });
    thread.scrollTop = thread.scrollHeight;
  } catch (err) {
    window.AIAgentToast.show(err.message, "error");
  }

  document.getElementById("agent-conv-list").classList.remove("mobile-open");
}

async function sendMessage() {
  const input = document.getElementById("composer-input");
  const content = input.value.trim();
  if (!content || isStreaming || !activeConversationId) return;

  stopSpeaking();
  input.value = "";
  autoGrowTextarea(input);
  isStreaming = true;
  document.getElementById("composer-send-btn").disabled = true;

  const thread = document.getElementById("agent-thread");
  thread.appendChild(renderMessageRow("user", agentEscapeHtml(content)));

  let routingLanguage = "english";
  const assistantRow = renderMessageRow(
    "assistant",
    '<span class="typing-dot"></span><span class="typing-dot"></span><span class="typing-dot"></span>',
    { getLanguage: () => routingLanguage }
  );
  thread.appendChild(assistantRow);
  thread.scrollTop = thread.scrollHeight;
  const bubble = assistantRow.querySelector(".msg-bubble");

  try {
    const resp = await fetch(`${window.AIAgentApi.apiBase()}/agent/conversations/${activeConversationId}/messages`, {
      method: "POST",
      credentials: "include",
      headers: { "Content-Type": "application/json", "X-CSRF-Token": window.AIAgentApi.getCsrfToken() },
      body: JSON.stringify({ content }),
    });

    if (!resp.ok) {
      const errBody = await resp.json().catch(() => ({}));
      throw new Error(errBody.detail || `Request failed (${resp.status}).`);
    }

    const reader = resp.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";
    let assistantText = "";
    let sawFirstDelta = false;

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      let boundary;
      while ((boundary = buffer.indexOf("\n\n")) >= 0) {
        const rawEvent = buffer.slice(0, boundary);
        buffer = buffer.slice(boundary + 2);
        if (!rawEvent.startsWith("data: ")) continue;
        const evt = JSON.parse(rawEvent.slice(6));

        if (evt.type === "route") {
          routingLanguage = evt.language || "english";
          if (evt.intent === "technical") {
            assistantRow.querySelector(".route-badge-slot").innerHTML =
              `<span class="route-badge technical"><i class="bi bi-search"></i> From your knowledge base</span>`;
            if (evt.sources && evt.sources.length) {
              assistantRow.querySelector(".sources-slot").innerHTML = `<div class="msg-sources">Sources: ${evt.sources
                .map((s) => `<span class="source-chip"><i class="bi bi-file-earmark-text"></i> ${agentEscapeHtml(s.title)}</span>`)
                .join("")}</div>`;
            }
          }
        } else if (evt.type === "delta") {
          if (!sawFirstDelta) {
            bubble.innerHTML = "";
            sawFirstDelta = true;
          }
          assistantText += evt.text;
          bubble.textContent = assistantText;
          thread.scrollTop = thread.scrollHeight;
        } else if (evt.type === "error") {
          bubble.classList.add("error-bubble");
          bubble.innerHTML = `${agentEscapeHtml(assistantText)}<span class="msg-error-note"><i class="bi bi-exclamation-triangle"></i> ${agentEscapeHtml(evt.message)}</span>`;
        }
      }
    }
    loadConversations();

    if (assistantText && document.getElementById("auto-speak-toggle").checked) {
      const speakerBtn = assistantRow.querySelector(".speaker-btn");
      if (speakerBtn) speakText(assistantText, routingLanguage, speakerBtn);
    }
  } catch (err) {
    bubble.classList.add("error-bubble");
    bubble.textContent = err.message;
  } finally {
    isStreaming = false;
    document.getElementById("composer-send-btn").disabled = false;
  }
}

function autoGrowTextarea(el) {
  el.style.height = "auto";
  el.style.height = `${Math.min(el.scrollHeight, 160)}px`;
}

async function createConversation({ mode, projectId }) {
  const conv = await window.AIAgentApi.post("/agent/conversations", {
    mode,
    project_id: projectId || null,
  });
  await loadConversations();
  await selectConversation(conv.id);
}

function initComposer() {
  const input = document.getElementById("composer-input");
  input.addEventListener("input", () => autoGrowTextarea(input));
  input.addEventListener("keydown", (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      sendMessage();
    }
  });
  document.getElementById("composer-send-btn").addEventListener("click", sendMessage);
}

let newChatSelectedMode = "chat";

function renderNewChatModePicker(selected) {
  newChatSelectedMode = selected;
  renderModePicker(document.getElementById("new-chat-mode-picker"), {
    selected: newChatSelectedMode,
    onSelect: (m) => (newChatSelectedMode = m),
  });
}

// Opens the "new conversation" modal pre-scoped to a mode/project — used
// both by the normal "New chat" button and by a project workspace's Chat
// tab "New" link (see the ?project_id= handling in init() below).
async function openNewChatModal({ mode = defaultMode, projectId = "" } = {}) {
  await loadProjectOptions();
  renderNewChatModePicker(mode);
  document.getElementById("new-chat-project").value = projectId;
  newChatModal.show();
}

function initNewChatModal() {
  renderNewChatModePicker(defaultMode);

  document.getElementById("new-chat-btn").addEventListener("click", () => {
    openNewChatModal({ mode: defaultMode });
  });

  document.getElementById("new-chat-create-btn").addEventListener("click", async () => {
    const projectId = document.getElementById("new-chat-project").value;
    newChatModal.hide();
    try {
      await createConversation({ mode: newChatSelectedMode, projectId });
    } catch (err) {
      window.AIAgentToast.show(err.message, "error");
    }
  });

  renderModePicker(document.getElementById("empty-mode-picker"), {
    selected: defaultMode,
    onSelect: async (m) => {
      try {
        await createConversation({ mode: m, projectId: null });
      } catch (err) {
        window.AIAgentToast.show(err.message, "error");
      }
    },
  });
}

async function init() {
  const user = await window.AppShell.initAppShell("agent");
  if (!user) return;

  newChatModal = new bootstrap.Modal(document.getElementById("new-chat-modal"));

  try {
    const settings = await window.AIAgentApi.get("/users/me/settings");
    if (settings.ai_settings && settings.ai_settings.default_mode) {
      defaultMode = settings.ai_settings.default_mode;
    }
  } catch {
    // Non-fatal: falls back to "chat".
  }

  initComposer();
  initNewChatModal();
  initVoiceSettings();

  document.getElementById("mobile-conv-toggle").addEventListener("click", () => {
    document.getElementById("agent-conv-list").classList.toggle("mobile-open");
  });

  await loadStatus();
  await loadConversations();

  const params = new URLSearchParams(window.location.search);
  const prefill = params.get("prompt");
  const openConversationId = params.get("conversation");
  const linkedProjectId = params.get("project_id");

  if (prefill) {
    try {
      await createConversation({ mode: defaultMode, projectId: null });
      document.getElementById("composer-input").value = prefill;
      autoGrowTextarea(document.getElementById("composer-input"));
      sendMessage();
    } catch (err) {
      window.AIAgentToast.show(err.message, "error");
    }
  } else if (openConversationId) {
    // Deep link from a project workspace's Chat tab into an existing
    // project-scoped conversation.
    await selectConversation(openConversationId);
  } else if (linkedProjectId) {
    // Deep link from a project workspace's Chat tab "New" button —
    // pre-scope the new-chat modal to that project and Project mode
    // instead of making the user pick it again.
    await openNewChatModal({ mode: "project", projectId: linkedProjectId });
  }
}

init();
