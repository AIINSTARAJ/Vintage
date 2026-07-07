window.addEventListener("DOMContentLoaded", loadBriefing);

async function loadBriefing() {
  const el = document.getElementById("briefing-text");
  try {
    const res = await fetch("/api/feed/briefing");
    const data = await res.json();
    if (data.error) {
      el.textContent = "Briefing needs a connected runtime key, headlines below still work without it.";
      return;
    }
    el.textContent = data.text;

    if (data.pipeline) {
      const toggle = document.getElementById("toggle-pipeline");
      const detail = document.getElementById("pipeline-detail");
      toggle.style.display = "inline-block";
      detail.innerHTML = `
        <div style="margin-bottom:8px;"><strong style="color:var(--text);">Stage 1, significance filter:</strong> ${escapeHtml(data.pipeline.movers)}</div>
        <div><strong style="color:var(--text);">Stage 2, relevance to your holdings:</strong> ${escapeHtml(data.pipeline.relevance)}</div>
      `;
      toggle.addEventListener("click", () => {
        const showing = detail.style.display === "block";
        detail.style.display = showing ? "none" : "block";
        toggle.textContent = showing ? "Show how this was put together" : "Hide";
      });
    }
  } catch (err) {
    el.textContent = "Couldn't put a briefing together right now.";
  }
}

const popup = document.getElementById("highlight-popup");
const askBtn = document.getElementById("ask-about-selection");
let selectedText = "";
let selectedWrap = null;

document.getElementById("article-list").addEventListener("mouseup", (e) => {
  const selection = window.getSelection();
  const text = selection.toString().trim();

  if (text.length < 3) {
    popup.style.display = "none";
    return;
  }

  selectedWrap = e.target.closest(".article-row-wrap");
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

askBtn.addEventListener("click", async () => {
  if (!selectedWrap) return;
  popup.style.display = "none";

  const ticker = selectedWrap.dataset.ticker;
  const query = ticker ? `${ticker}: ${selectedText}` : selectedText;

  // remove any existing answer box under this row first
  const existing = selectedWrap.querySelector(".inline-answer");
  if (existing) existing.remove();

  const box = document.createElement("div");
  box.className = "inline-answer";
  box.innerHTML = `<div class="answer-label">Desk take</div><div class="answer-body">Reading into it...</div>`;
  selectedWrap.appendChild(box);
  box.scrollIntoView({ behavior: "smooth", block: "nearest" });

  try {
    const res = await fetch("/api/research/ask", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ query, brief: true }),
    });
    const data = await res.json();

    if (data.error) {
      box.innerHTML = `<button class="close-answer" onclick="this.closest('.inline-answer').remove()">&times;</button>
        <div class="answer-label">Desk take</div><div class="answer-body">${escapeHtml(data.error)}</div>`;
      return;
    }

    box.innerHTML = `<button class="close-answer" onclick="this.closest('.inline-answer').remove()">&times;</button>
      <div class="answer-label">Desk take</div><div class="answer-body">${escapeHtml(data.text)}</div>`;
  } catch (err) {
    box.innerHTML = `<button class="close-answer" onclick="this.closest('.inline-answer').remove()">&times;</button>
      <div class="answer-label">Desk take</div><div class="answer-body">Something broke reaching the desk.</div>`;
  }
});

function escapeHtml(str) {
  const div = document.createElement("div");
  div.textContent = str;
  return div.innerHTML;
}
