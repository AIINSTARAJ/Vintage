let TICKER_LIST = null;

async function loadTickerList() {
  if (TICKER_LIST) return TICKER_LIST;
  const res = await fetch("/static/data/tickers.json");
  TICKER_LIST = await res.json();
  return TICKER_LIST;
}

function attachTickerAutocomplete(inputEl, onPick) {
  const wrapper = document.createElement("div");
  wrapper.className = "autocomplete-wrap";
  inputEl.parentNode.insertBefore(wrapper, inputEl);
  wrapper.appendChild(inputEl);

  const dropdown = document.createElement("div");
  dropdown.className = "autocomplete-dropdown";
  dropdown.style.display = "none";
  wrapper.appendChild(dropdown);

  inputEl.addEventListener("input", async () => {
    const q = inputEl.value.trim().toUpperCase();
    if (q.length < 1) {
      dropdown.style.display = "none";
      return;
    }
    const list = await loadTickerList();
    const matches = list.filter((t) =>
      t.symbol.toUpperCase().startsWith(q) || t.name.toUpperCase().includes(q)
    ).slice(0, 8);

    if (!matches.length) {
      dropdown.style.display = "none";
      return;
    }

    dropdown.innerHTML = matches.map((t) => `
      <div class="autocomplete-item" data-symbol="${t.symbol}">
        <span class="mono" style="font-weight:700;">${t.symbol}</span>
        <span style="color:var(--text-soft); font-size:13px;">${t.name}</span>
      </div>
    `).join("");
    dropdown.style.display = "block";
  });

  dropdown.addEventListener("mousedown", (e) => {
    const item = e.target.closest(".autocomplete-item");
    if (!item) return;
    inputEl.value = item.dataset.symbol;
    dropdown.style.display = "none";
    if (onPick) onPick(item.dataset.symbol);
  });

  document.addEventListener("click", (e) => {
    if (!wrapper.contains(e.target)) dropdown.style.display = "none";
  });
}
