let chart = null;
let candleSeries = null;
let volumeSeries = null;
let sma20Series = null;
let sma50Series = null;
let currentTicker = null;
let currentPeriod = "6mo";
let currentInterval = "1d";
let lastSnapshot = null;
let chatThread = [];

function threadKey(ticker) {
  return `vintage_stock_chat_${ticker}`;
}

document.getElementById("ticker-form").addEventListener("submit", (e) => {
  e.preventDefault();
  const t = document.getElementById("ticker-input").value.trim().toUpperCase();
  if (t) loadTicker(t);
});

document.getElementById("tf-row").addEventListener("click", (e) => {
  const btn = e.target.closest(".tf-btn");
  if (!btn || !currentTicker) return;
  document.querySelectorAll(".tf-btn").forEach((b) => b.classList.remove("active"));
  btn.classList.add("active");
  currentPeriod = btn.dataset.period;
  currentInterval = btn.dataset.interval || "1d";
  loadHistory(currentTicker, currentPeriod);
});

async function loadTicker(ticker) {
  currentTicker = ticker.toUpperCase();
  document.getElementById("ticker-input").value = currentTicker;
  document.getElementById("stock-empty").style.display = "none";
  document.getElementById("stock-panel").style.display = "block";
  document.getElementById("panel-ticker").textContent = currentTicker;
  document.getElementById("trade-panel").innerHTML =
    '<div class="empty-state">Ask a question below and take a view for an AI-sized position, or trade manually above.</div>';

  const saved = sessionStorage.getItem(threadKey(currentTicker));
  chatThread = saved ? JSON.parse(saved) : [];
  const win = document.getElementById("chat-window");
  win.innerHTML = "";
  chatThread.forEach((m) => appendMessage(m.role, m.content, m.meta, false));

  setupChart();
  await loadHistory(currentTicker, currentPeriod);
  loadHoldingSummary(currentTicker);
}

function setupChart() {
  const container = document.getElementById("price-chart");
  container.innerHTML = "";
  chart = LightweightCharts.createChart(container, {
    layout: { background: { color: "#FFFFFF" }, textColor: "#6B7080", fontFamily: "Inter, sans-serif" },
    grid: { vertLines: { color: "#F0F1F5" }, horzLines: { color: "#F0F1F5" } },
    rightPriceScale: { borderColor: "#E7E9F0" },
    timeScale: { borderColor: "#E7E9F0", timeVisible: true, secondsVisible: false },
    height: 380,
    width: container.clientWidth,
  });

  candleSeries = chart.addCandlestickSeries({
    upColor: "#16A34A", downColor: "#E5484D",
    borderVisible: false,
    wickUpColor: "#16A34A", wickDownColor: "#E5484D",
  });

  volumeSeries = chart.addHistogramSeries({
    color: "#C7CCDA",
    priceFormat: { type: "volume" },
    priceScaleId: "volume",
  });
  chart.priceScale("volume").applyOptions({ scaleMargins: { top: 0.82, bottom: 0 } });
  candleSeries.priceScale().applyOptions({ scaleMargins: { top: 0.05, bottom: 0.22 } });

  sma20Series = chart.addLineSeries({ color: "#F0A93E", lineWidth: 1.5, priceLineVisible: false, lastValueVisible: false });
  sma50Series = chart.addLineSeries({ color: "#2F6FED", lineWidth: 1.5, priceLineVisible: false, lastValueVisible: false });

  chart.subscribeClick((param) => {
    if (!param.time) return;
    const candle = param.seriesData.get(candleSeries);
    if (!candle) return;
    askAboutDay(param.time, candle);
  });

  window.addEventListener("resize", () => chart.applyOptions({ width: container.clientWidth }));
}

function computeSMA(candles, period) {
  const out = [];
  for (let i = 0; i < candles.length; i++) {
    if (i < period - 1) continue;
    let sum = 0;
    for (let j = i - period + 1; j <= i; j++) sum += candles[j].close;
    out.push({ time: candles[i].time, value: +(sum / period).toFixed(2) });
  }
  return out;
}

async function loadHistory(ticker, period) {
  const res = await fetch(`/api/stock/${ticker}/history?period=${period}&interval=${currentInterval}`);
  const data = await res.json();

  if (data.error) {
    document.getElementById("panel-price").innerHTML = `<span class="text-down" style="font-size:14px;">${data.error}</span>`;
    candleSeries.setData([]);
    volumeSeries.setData([]);
    sma20Series.setData([]);
    sma50Series.setData([]);
    return;
  }

  lastSnapshot = data.snapshot;
  renderPrice(data.snapshot);

  const candles = data.series.map((p) => ({
    time: p.time, open: p.open, high: p.high, low: p.low, close: p.close,
  }));
  candleSeries.setData(candles);

  const volumes = data.series.map((p) => ({
    time: p.time, value: p.volume,
    color: p.close >= p.open ? "rgba(22,163,74,0.35)" : "rgba(229,72,77,0.35)",
  }));
  volumeSeries.setData(volumes);

  sma20Series.setData(computeSMA(candles, 20));
  sma50Series.setData(computeSMA(candles, 50));

  chart.timeScale().fitContent();
}

function renderPrice(snapshot) {
  const el = document.getElementById("panel-price");
  if (!snapshot || snapshot.price == null) {
    el.textContent = "no data";
    return;
  }
  const change = snapshot.previous_close ? snapshot.price - snapshot.previous_close : null;
  const pct = change !== null ? (change / snapshot.previous_close) * 100 : null;
  const cls = change >= 0 ? "text-up" : "text-down";
  const arrow = change >= 0 ? "+" : "";
  el.innerHTML = `${snapshot.price.toFixed(2)} <span class="${cls}">${arrow}${pct !== null ? pct.toFixed(2) + "%" : ""}</span>`;
}

// ---------- click a candle to ask about that day ----------
async function askAboutDay(time, candle) {
  const d = new Date(time * 1000);
  const label = d.toISOString().slice(0, 16).replace("T", " ");
  const question = `What happened around ${label} UTC for ${currentTicker} that moved the price from ${candle.open} to ${candle.close}?`;
  document.getElementById("chat-input").value = question;
  sendQuestion();
}

// ---------- manual trading, independent of the AI draft flow ----------
document.getElementById("manual-buy").addEventListener("click", () => manualTrade("buy"));
document.getElementById("manual-sell").addEventListener("click", () => manualTrade("sell"));

async function manualTrade(side) {
  const amountInput = document.getElementById("manual-amount");
  const amount = parseFloat(amountInput.value);
  if (!currentTicker || !lastSnapshot || !lastSnapshot.price) {
    alert("Load a ticker with a valid price first.");
    return;
  }
  if (!amount || amount <= 0) {
    alert("Enter an amount first.");
    return;
  }

  const res = await fetch("/api/trade/execute", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      ticker: currentTicker, side, amount_usd: amount, price: lastSnapshot.price,
    }),
  });
  const trade = await res.json();
  if (trade.error) {
    alert(trade.error);
    return;
  }

  amountInput.value = "";
  const panel = document.getElementById("trade-panel");
  panel.innerHTML = `<div class="flag-box flag-verified">Filled, ${trade.side} ${trade.quantity} ${trade.ticker} at ${trade.price}. Cash balance now $${trade.new_cash_balance.toLocaleString()}.</div>`;
  loadHoldingSummary(currentTicker);
  document.querySelector(".balance-chip").textContent = `$${trade.new_cash_balance.toLocaleString()}`;
}

async function loadHoldingSummary(ticker) {
  const box = document.getElementById("holding-summary");
  try {
    const res = await fetch("/api/portfolio");
    const data = await res.json();
    const holding = data.holdings.find((h) => h.ticker === ticker);
    if (!holding) {
      box.innerHTML = `<div style="font-size:13px; color:var(--text-soft);">No position in ${ticker} yet.</div>`;
      return;
    }
    const plClass = holding.unrealized_pl >= 0 ? "text-up" : "text-down";
    const plLine = holding.price_stale
      ? `<div style="font-size:12.5px; color:var(--text-faint);">price unavailable right now</div>`
      : `<div class="${plClass}" style="font-size:13px; font-weight:700;">${holding.unrealized_pl >= 0 ? "+" : ""}${holding.unrealized_pl} (${holding.unrealized_pl_pct}%)</div>`;
    box.innerHTML = `
      <div style="font-size:13px; color:var(--text-soft);">Holding</div>
      <div style="font-weight:700;">${holding.shares} shares, avg cost ${holding.avg_cost}</div>
      ${plLine}
    `;
  } catch (err) {
    box.innerHTML = "";
  }
}

// ---------- chat ----------
document.getElementById("chat-send").addEventListener("click", sendQuestion);
document.getElementById("chat-input").addEventListener("keydown", (e) => {
  if (e.key === "Enter") sendQuestion();
});

async function sendQuestion() {
  const input = document.getElementById("chat-input");
  const question = input.value.trim();
  if (!question || !currentTicker) return;
  input.value = "";

  appendMessage("user", question);
  const thinkingId = appendMessage("assistant", "Working through it...", null, false);

  try {
    const res = await fetch(`/api/stock/${currentTicker}/ask`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ question, history: chatThread.slice(0, -1).map(m => ({ role: m.role, content: m.content })) }),
    });
    const data = await res.json();
    document.getElementById(thinkingId)?.remove();

    if (data.error) {
      appendMessage("assistant", `Couldn't reach the runtime: ${data.error}`);
      return;
    }

    appendMessage("assistant", data.text, data);
    if (data.snapshot) { lastSnapshot = data.snapshot; renderPrice(data.snapshot); }
    maybeShowTradeDraft(data);
  } catch (err) {
    document.getElementById(thinkingId)?.remove();
    appendMessage("assistant", "Something broke reaching the desk. Try again.");
  }
}

function appendMessage(role, text, meta, persist = true) {
  const win = document.getElementById("chat-window");
  const id = "msg-" + Math.random().toString(36).slice(2);
  const div = document.createElement("div");
  div.id = id;
  div.className = `msg ${role}`;

  if (persist) {
    chatThread.push({ role, content: text, meta: meta || null });
    if (currentTicker) sessionStorage.setItem(threadKey(currentTicker), JSON.stringify(chatThread));
  }

  let extra = "";
  if (meta && meta.contradiction) {
    extra += `<div class="flag-box flag-warn">Contradicts a prior call: ${escapeHtml(meta.contradiction)}</div>`;
  }
  if (meta && meta.verified) {
    if (meta.verified.unavailable) {
      extra += `<div class="flag-box flag-warn">Couldn't verify this calculation after checking, treat the number as unconfirmed.</div>`;
    } else {
      extra += `<div class="flag-box flag-verified">Verified, ${meta.verified.calc_type}: ${escapeHtml(String(meta.verified.result))}</div>`;
    }
  }

  div.innerHTML = `${extra}<div class="bubble">${escapeHtml(text).replace(/\n/g, "<br>")}</div>
    <div class="meta">${role === "user" ? "you" : "desk"}</div>`;
  win.appendChild(div);
  win.scrollTop = win.scrollHeight;
  return id;
}

function maybeShowTradeDraft(data) {
  const panel = document.getElementById("trade-panel");
  const direction = data.stance === "long" || data.stance === "short" ? data.stance : null;
  if (!direction) return;

  panel.innerHTML = `
    <p style="font-size:13.5px; color:var(--text-soft);">The desk leaned <strong style="color:var(--text);">${direction}</strong> on this.</p>
    <button class="btn btn-outline btn-block" id="draft-btn">Draft ${direction} position</button>
  `;
  document.getElementById("draft-btn").addEventListener("click", () => draftTrade(direction, data));
}

async function draftTrade(direction, chatData) {
  const panel = document.getElementById("trade-panel");
  panel.innerHTML = `<div class="empty-state">Sizing the position...</div>`;

  const res = await fetch("/api/trade/draft", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      ticker: currentTicker,
      direction,
      reasoning: chatData.text,
      verified_numbers: chatData.verified ? JSON.stringify(chatData.verified) : "",
    }),
  });
  const draft = await res.json();
  if (draft.error) {
    panel.innerHTML = `<div class="empty-state">${escapeHtml(draft.error)}</div>`;
    return;
  }

  const sideClass = direction === "long" ? "btn-buy" : "btn-sell";
  const sideLabel = direction === "long" ? "Buy" : "Sell";
  const reviewNote = draft.needs_review
    ? `<div class="flag-box flag-warn">Above 10% of the account, confirm before this fills.</div>`
    : "";

  panel.innerHTML = `
    <div style="display:flex; gap:16px; margin-bottom:14px;">
      <div class="stat-block"><span class="stat-label">Size</span><span class="stat-value" style="font-size:22px;">${draft.quantity_pct}%</span></div>
      <div class="stat-block"><span class="stat-label">Stop loss</span><span class="stat-value" style="font-size:22px; color:var(--red);">${draft.stop_loss_pct}%</span></div>
    </div>
    <p style="font-size:13.5px; color:var(--text-soft); margin:0 0 12px;">${escapeHtml(draft.note || "")}</p>
    ${reviewNote}
    <button class="btn ${sideClass} btn-block" id="confirm-trade">${sideLabel} at ${draft.price}</button>
  `;

  document.getElementById("confirm-trade").addEventListener("click", async () => {
    const execRes = await fetch("/api/trade/execute", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        ticker: currentTicker,
        side: direction === "long" ? "buy" : "sell",
        quantity_pct: draft.quantity_pct,
        price: draft.price,
        stop_loss_pct: draft.stop_loss_pct,
        note: draft.note,
      }),
    });
    const trade = await execRes.json();
    if (trade.error) {
      panel.innerHTML = `<div class="empty-state">${escapeHtml(trade.error)}</div>`;
      return;
    }
    panel.innerHTML = `<div class="flag-box flag-verified">Filled, ${trade.side} ${trade.quantity} ${trade.ticker} at ${trade.price}.</div>`;
    loadHoldingSummary(currentTicker);
  });
}

function escapeHtml(str) {
  const div = document.createElement("div");
  div.textContent = str;
  return div.innerHTML;
}
