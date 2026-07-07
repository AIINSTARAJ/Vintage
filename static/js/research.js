const STORAGE_KEY = "vintage_research_thread";
let thread = [];
let tickerList = null;

window.addEventListener("DOMContentLoaded", async () => {
  const saved = sessionStorage.getItem(STORAGE_KEY);
  if (saved) {
    thread = JSON.parse(saved);
    renderThread();
  }

  const prefill = sessionStorage.getItem("vintage_prefill_query");
  if (prefill) {
    sessionStorage.removeItem("vintage_prefill_query");
    document.getElementById("research-input").value = prefill;
    sendMessage();
  }
});

document.getElementById("research-send").addEventListener("click", sendMessage);
document.getElementById("research-input").addEventListener("keydown", (e) => {
  if (e.key === "Enter") sendMessage();
});

// ---------- voice input, native browser speech recognition, no API key ----------
const SpeechRecognitionImpl = window.SpeechRecognition || window.webkitSpeechRecognition;
const micBtn = document.getElementById("mic-btn");
if (!SpeechRecognitionImpl) {
  micBtn.style.display = "none";
} else {
  let recognizing = false;
  const recognizer = new SpeechRecognitionImpl();
  recognizer.continuous = false;
  recognizer.interimResults = false;
  recognizer.lang = "en-US";

  micBtn.addEventListener("click", () => {
    if (recognizing) { recognizer.stop(); return; }
    recognizer.start();
  });
  recognizer.addEventListener("start", () => {
    recognizing = true;
    micBtn.textContent = "Listening...";
    micBtn.classList.add("btn-primary");
  });
  recognizer.addEventListener("end", () => {
    recognizing = false;
    micBtn.textContent = "Mic";
    micBtn.classList.remove("btn-primary");
  });
  recognizer.addEventListener("result", (event) => {
    const transcript = event.results[0][0].transcript;
    document.getElementById("research-input").value = transcript;
    sendMessage();
  });
  recognizer.addEventListener("error", () => {
    recognizing = false;
    micBtn.textContent = "Mic";
    micBtn.classList.remove("btn-primary");
  });
}

// ---------- read aloud, native browser speech synthesis, no API key ----------
function speakText(text) {
  if (!("speechSynthesis" in window)) return;
  window.speechSynthesis.cancel();
  const utterance = new SpeechSynthesisUtterance(text);
  utterance.rate = 1.02;
  window.speechSynthesis.speak(utterance);
}
document.getElementById("clear-research").addEventListener("click", () => {
  thread = [];
  sessionStorage.removeItem(STORAGE_KEY);
  renderThread();
});

async function sendMessage() {
  const input = document.getElementById("research-input");
  const query = input.value.trim();
  if (!query) return;
  input.value = "";

  thread.push({ role: "user", content: query });
  renderThread();

  const win = document.getElementById("research-window");
  const thinking = document.createElement("div");
  thinking.className = "msg assistant";
  thinking.id = "thinking-msg";
  thinking.innerHTML = `<div class="bubble">Pulling what's out there and reading through it...</div>`;
  win.appendChild(thinking);
  win.scrollTop = win.scrollHeight;

  try {
    const res = await fetch("/api/research/ask", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ query, history: thread.slice(0, -1) }),
    });
    const data = await res.json();
    document.getElementById("thinking-msg")?.remove();

    if (data.error) {
      thread.push({ role: "assistant", content: data.error, isError: true });
    } else {
      thread.push({ role: "assistant", content: data.text, articles: data.articles || [] });
    }
    sessionStorage.setItem(STORAGE_KEY, JSON.stringify(thread));
    renderThread();
  } catch (err) {
    document.getElementById("thinking-msg")?.remove();
    thread.push({ role: "assistant", content: "Something broke reaching the desk.", isError: true });
    renderThread();
  }
}

async function loadTickerList() {
  if (tickerList) return tickerList;
  const res = await fetch("/static/data/tickers.json");
  tickerList = await res.json();
  return tickerList;
}

async function renderThread() {
  const win = document.getElementById("research-window");
  const empty = document.getElementById("research-empty");
  win.innerHTML = "";

  if (thread.length === 0) {
    win.appendChild(empty);
    return;
  }

  const tickers = await loadTickerList();

  for (let i = 0; i < thread.length; i++) {
    const msg = thread[i];
    const div = document.createElement("div");
    div.className = `msg ${msg.role}`;
    div.dataset.idx = i;

    if (msg.role === "user") {
      div.innerHTML = `<div class="bubble">${escapeHtml(msg.content)}</div>`;
    } else {
      const mentioned = msg.isError ? [] : tickers.filter((t) => new RegExp(`\\b${t.symbol}\\b`).test(msg.content)).slice(0, 5);
      const linksHtml = mentioned.length ? `
        <div style="display:flex; flex-wrap:wrap; gap:6px; margin-top:8px;">
          ${mentioned.map((t) => `<a href="/stock?ticker=${t.symbol}" class="btn btn-outline btn-sm" style="padding:5px 12px; font-size:12px;">Open ${t.symbol}</a>`).join("")}
        </div>` : "";
      const sourceCount = msg.articles ? msg.articles.length : 0;
      const sourcesNote = sourceCount ? `<div class="meta">${sourceCount} source${sourceCount > 1 ? "s" : ""} pulled</div>` : "";

      const speakBtn = `<button class="speak-btn" data-msg-idx="${i}" title="Read aloud" style="background:none; border:none; cursor:pointer; color:var(--text-faint); font-size:12px; padding:0; margin-top:6px;">Read aloud</button>`;
      div.innerHTML = `<div class="bubble research-answer" data-idx="${i}">${escapeHtml(msg.content).replace(/\n/g, "<br>")}${linksHtml}</div>${msg.isError ? "" : speakBtn}${sourcesNote}`;
    }
    win.appendChild(div);
  }

  win.scrollTop = win.scrollHeight;
}

document.getElementById("research-window").addEventListener("click", (e) => {
  const btn = e.target.closest(".speak-btn");
  if (!btn) return;
  const idx = parseInt(btn.dataset.msgIdx, 10);
  const msg = thread[idx];
  if (msg) speakText(msg.content);
});

// ---------- highlight to ask, works on any assistant bubble ----------
const popup = document.getElementById("highlight-popup");
const askBtn = document.getElementById("ask-about-selection");
let selectedText = "";
let selectedBubble = null;

document.getElementById("research-window").addEventListener("mouseup", (e) => {
  const selection = window.getSelection();
  const text = selection.toString().trim();

  if (text.length < 3) {
    popup.style.display = "none";
    return;
  }

  selectedBubble = e.target.closest(".research-answer");
  if (!selectedBubble) {
    popup.style.display = "none";
    return;
  }
  selectedText = text;

  const range = selection.getRangeAt(0);
  const rect = range.getBoundingClientRect();
  popup.style.left = `${window.scrollX + rect.left}px`;
  popup.style.top = `${window.scrollY + rect.bottom + 8}px`;
  popup.style.display = "block";
});

document.addEventListener("mousedown", (e) => {
  if (!popup.contains(e.target)) popup.style.display = "none";
});

askBtn.addEventListener("click", () => {
  if (!selectedBubble) return;
  popup.style.display = "none";
  document.getElementById("research-input").value = selectedText;
  sendMessage();
});

function escapeHtml(str) {
  const div = document.createElement("div");
  div.textContent = str;
  return div.innerHTML;
}
