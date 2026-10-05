/* Orderflow Desk — chart + auction panel. Talks to /api/* (dashboard/app.py). */
(() => {
  const LWC = window.LightweightCharts;
  const css = (v) => getComputedStyle(document.documentElement).getPropertyValue(v).trim();
  const C = {
    bg: css("--bg"), text: css("--muted"), line: css("--line"), up: css("--up"), down: css("--down"),
    accent: css("--accent"), gold: css("--gold"), violet: css("--violet"),
  };
  const EMA_COLORS = { 9: "#7dd3fc", 21: "#f59e0b", 50: "#a78bfa", 200: "#e5e7eb" };

  const qs = new URLSearchParams(location.search);
  const state = {
    sym: qs.get("sym") || "ES", tf: qs.get("tf") || "1h", days: +(qs.get("days") || 60),
    show: Object.fromEntries([...document.querySelectorAll("#toggles input")].map((i) => [i.dataset.k, true])),
    data: null, gamma: null, symbols: [],
  };
  try { Object.assign(state.show, JSON.parse(localStorage.getItem("of.show") || "{}")); } catch {}

  const $ = (id) => document.getElementById(id);
  const mainEl = $("main"), flowEl = $("flow"), overlay = $("overlay");

  // ---------- charts ----------
  const base = {
    layout: { background: { type: "solid", color: C.bg }, textColor: C.text, fontSize: 11 },
    grid: { vertLines: { color: "#12171f" }, horzLines: { color: "#12171f" } },
    rightPriceScale: { borderVisible: false },
    timeScale: { borderVisible: false, timeVisible: true, secondsVisible: false, rightOffset: 8 },
    crosshair: { mode: LWC.CrosshairMode.Normal },
    autoSize: true,
  };
  const chart = LWC.createChart(mainEl, base);
  const flow = LWC.createChart(flowEl, { ...base, timeScale: { ...base.timeScale, visible: false } });

  const candles = chart.addCandlestickSeries({
    upColor: C.up, downColor: C.down, wickUpColor: C.up, wickDownColor: C.down, borderVisible: false,
  });
  const vol = chart.addHistogramSeries({ priceScaleId: "vol", priceFormat: { type: "volume" }, lastValueVisible: false, priceLineVisible: false });
  chart.priceScale("vol").applyOptions({ scaleMargins: { top: 0.85, bottom: 0 } });

  const line = (color, width = 1, style = 0) => chart.addLineSeries({
    color, lineWidth: width, lineStyle: style, priceLineVisible: false, lastValueVisible: false, crosshairMarkerVisible: false,
  });
  const emas = Object.fromEntries(Object.entries(EMA_COLORS).map(([n, c]) => [n, line(c, n === "200" ? 2 : 1)]));
  const vw = {
    vwap: line(C.gold, 2), u1: line("rgba(245,197,66,.45)", 1, 2), l1: line("rgba(245,197,66,.45)", 1, 2),
    u2: line("rgba(245,197,66,.25)", 1, 1), l2: line("rgba(245,197,66,.25)", 1, 1),
  };
  const vwm = line(C.violet, 2, 0);

  const deltaS = flow.addHistogramSeries({ priceScaleId: "left", lastValueVisible: false, priceLineVisible: false });
  flow.priceScale("left").applyOptions({ visible: false, scaleMargins: { top: 0.55, bottom: 0 } });
  const cvdS = flow.addLineSeries({ color: C.accent, lineWidth: 2, priceLineVisible: false, priceFormat: { type: "volume" } });
  flow.priceScale("right").applyOptions({ scaleMargins: { top: 0.08, bottom: 0.1 } });

  // keep the two panes scrolled together
  let syncing = false;
  const sync = (src, dst) => src.timeScale().subscribeVisibleLogicalRangeChange((r) => {
    if (syncing || !r) return; syncing = true; dst.timeScale().setVisibleLogicalRange(r); syncing = false;
  });
  sync(chart, flow); sync(flow, chart);

  let priceLines = [];
  const clearLines = () => { priceLines.forEach((pl) => candles.removePriceLine(pl)); priceLines = []; };
  const addLine = (price, color, title, style = 2, width = 1) => {
    if (price == null || !isFinite(price)) return;
    priceLines.push(candles.createPriceLine({ price, color, title, lineStyle: style, lineWidth: width, axisLabelVisible: true }));
  };

  // ---------- formatting ----------
  let prec = 2;
  const fmt = (x) => (x == null ? "—" : Number(x).toLocaleString(undefined, { minimumFractionDigits: prec, maximumFractionDigits: prec }));
  const precFor = (tick) => Math.min(7, Math.max(0, Math.ceil(-Math.log10(tick) - 1e-9)));

  // ---------- data ----------
  async function api(path) {
    const r = await fetch(path);
    if (!r.ok) throw new Error((await r.json().catch(() => ({}))).detail || r.statusText);
    return r.json();
  }

  async function load() {
    $("err").hidden = true;
    const url = new URL(location); url.searchParams.set("sym", state.sym); url.searchParams.set("tf", state.tf);
    url.searchParams.set("days", state.days); history.replaceState(null, "", url);
    const s = state.symbols.find((x) => x.key === state.sym);
    $("symKey").textContent = state.sym; $("symName").textContent = s ? s.name : "";
    document.querySelectorAll("#watch li").forEach((li) => li.classList.toggle("on", li.dataset.k === state.sym));
    try {
      state.data = await api(`/api/chart?sym=${state.sym}&tf=${state.tf}&days=${state.days}`);
    } catch (e) {
      $("err").textContent = e.message; $("err").hidden = false; return;
    }
    render();
    state.gamma = null; renderGamma();
    if (s && s.gamma) {
      api(`/api/gamma?sym=${state.sym}`).then((g) => { state.gamma = g; renderGamma(); render(false); })
        .catch((e) => { state.gamma = { error: e.message }; renderGamma(); });
    }
  }

  function render(fit = true) {
    const d = state.data; if (!d) return;
    prec = precFor(d.tick);
    candles.applyOptions({ priceFormat: { type: "price", precision: prec, minMove: d.tick } });
    candles.setData(d.bars);
    vol.setData(d.bars.map((b) => ({ time: b.time, value: b.volume, color: b.close >= b.open ? "rgba(38,166,154,.28)" : "rgba(239,83,80,.28)" })));
    for (const [n, s] of Object.entries(emas)) s.setData(state.show.ema ? d.ema[n] : []);
    for (const [k, s] of Object.entries(vw)) s.setData(state.show.vwap ? d.vwap_w[k] : []);
    vwm.setData(state.show.vwap ? d.vwap_m.vwap : []);
    deltaS.setData(d.delta.map((p) => ({ ...p, color: p.value >= 0 ? "rgba(38,166,154,.6)" : "rgba(239,83,80,.6)" })));
    cvdS.setData(d.cvd);

    const a = d.auction, last = d.bars[d.bars.length - 1];
    $("symLast").textContent = fmt(last.close);
    clearLines();
    if (state.show.levels) {
      addLine(a.composite.poc, C.accent, "cPOC", 0, 2);
      addLine(a.composite.vah, "rgba(91,140,255,.7)", "cVAH");
      addLine(a.composite.val, "rgba(91,140,255,.7)", "cVAL");
      addLine(a.balance.vah, "#9aa4b2", "bVAH", 1);
      addLine(a.balance.val, "#9aa4b2", "bVAL", 1);
    }
    if (state.show.npoc) a.naked_pocs.slice(-6).forEach((p) => addLine(p.price, "#e879f9", "nPOC", 1));
    const g = state.gamma;
    if (state.show.gamma && g && !g.unavailable && !g.error) {
      addLine(g.zero_gamma, C.gold, "0γ", 0, 2);
      addLine(g.call_wall, C.up, "Call wall", 0, 2);
      addLine(g.put_wall, C.down, "Put wall", 0, 2);
    }
    renderLegend(); renderPanel();
    if (fit) { chart.timeScale().fitContent(); }
  }

  function renderLegend() {
    const items = [];
    if (state.show.ema) for (const [n, c] of Object.entries(EMA_COLORS)) items.push(`<span><i style="background:${c}"></i>EMA ${n}</span>`);
    if (state.show.vwap) items.push(`<span><i style="background:${C.gold}"></i>wVWAP ±1/2σ</span>`, `<span><i style="background:${C.violet}"></i>mVWAP</span>`);
    $("legend").innerHTML = items.join("");
  }

  // ---------- side panel ----------
  function renderPanel() {
    const a = state.data.auction;
    const biasCls = a.bias;
    $("chips").innerHTML = [
      `<span class="chip ${biasCls}">${a.bias.toUpperCase()}</span>`,
      `<span class="chip">${a.state}</span>`,
      `<span class="chip">${a.read}</span>`,
      a.divergence ? `<span class="chip ${a.divergence === "bullish" ? "long" : "short"}">${a.divergence} CVD div</span>` : "",
    ].join("");
    const kv = [
      ["Location", a.location], ["Value vs prior", a.value_relationship], ["Trend (21/50)", a.trend],
      ["RVOL", a.rvol ? a.rvol.toFixed(2) + "x" : "—"], ["ATR", fmt(a.atr)],
      ["Next up", a.next_up ? `${a.next_up.name} ${fmt(a.next_up.price)}` : "—"],
      ["Next down", a.next_down ? `${a.next_down.name} ${fmt(a.next_down.price)}` : "—"],
    ];
    $("kv").innerHTML = kv.map(([k, v]) => `<dt>${k}</dt><dd>${v}</dd>`).join("");
    $("notes").innerHTML = a.notes.map((n) => `<li>${n}</li>`).join("");

    const rows = [];
    let placed = false;
    for (const l of a.levels) {
      if (!placed && l.price < a.last) { rows.push(`<tr class="price"><td>Last</td><td>${fmt(a.last)}</td><td></td></tr>`); placed = true; }
      const cls = l.dist >= 0 ? "up" : "down";
      rows.push(`<tr><td>${l.name}</td><td>${fmt(l.price)}</td><td class="${cls}">${l.dist_atr > 0 ? "+" : ""}${l.dist_atr}</td></tr>`);
    }
    if (!placed) rows.push(`<tr class="price"><td>Last</td><td>${fmt(a.last)}</td><td></td></tr>`);
    $("levels").innerHTML = rows.join("");
  }

  function renderGamma() {
    const g = state.gamma, el = $("gamma");
    const s = state.symbols.find((x) => x.key === state.sym);
    $("gProxy").textContent = g && g.proxy ? `via ${g.proxy}` : "";
    if (s && !s.gamma) { el.innerHTML = `<span class="muted">No liquid options proxy for ${state.sym}.</span>`; return; }
    if (!g) { el.innerHTML = `<span class="muted">loading options…</span>`; return; }
    if (g.error || g.unavailable) { el.innerHTML = `<span class="muted">${g.error || "unavailable"}</span>`; return; }
    const reg = `<span class="chip">${g.regime_text || (g.regime === "positive" ? "Positive gamma regime (est.)" : "Negative gamma regime (est.)")}</span>`;
    const stale = g.stale ? `<span class="chip short" title="Older than the freshness limit: levels may have moved">STALE</span>` : "";
    const age = g.age_minutes == null ? "age unknown" : `${Math.round(g.age_minutes)} min old`;
    el.innerHTML = `<div class="chips">${reg}${stale}</div>
      <div class="muted" style="margin:-4px 0 8px">Proxy ${g.proxy} · calculated ${g.calculated_et || "?"} · ${age}</div>
      <dl class="gk">
        <dt>Zero gamma</dt><dd>${fmt(g.zero_gamma)}</dd>
        <dt>Call wall</dt><dd class="up">${fmt(g.call_wall)}</dd>
        <dt>Put wall</dt><dd class="down">${fmt(g.put_wall)}</dd>
        <dt>Majors</dt><dd>${g.major_strikes.map(fmt).join(" · ")}</dd>
      </dl>
      <div class="pine"><code id="pineStr">${g.pine}</code><button class="ghost" id="copyPine" title="Paste into gamma_levels.pine">Copy</button></div>`;
    $("copyPine").onclick = () => navigator.clipboard.writeText(g.pine).then(() => ($("copyPine").textContent = "✓"));
  }

  // ---------- overlay: volume profile + session POC/VA ----------
  const ctx = overlay.getContext("2d");
  function drawOverlay() {
    const d = state.data;
    const dpr = window.devicePixelRatio || 1;
    const W = mainEl.clientWidth, H = mainEl.clientHeight;
    if (overlay.width !== W * dpr || overlay.height !== H * dpr) { overlay.width = W * dpr; overlay.height = H * dpr; }
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.clearRect(0, 0, W, H);
    if (!d) return;
    const plotW = W - chart.priceScale("right").width();
    const plotH = H - chart.timeScale().height();
    ctx.save(); ctx.beginPath(); ctx.rect(0, 0, plotW, plotH); ctx.clip();
    const a = d.auction;

    if (state.show.sessions) {
      const ts = chart.timeScale();
      for (const s of a.sessions) {
        const x1 = ts.timeToCoordinate(s.start), x2 = ts.timeToCoordinate(s.end);
        if (x1 == null || x2 == null) continue;
        const yH = candles.priceToCoordinate(s.vah), yL = candles.priceToCoordinate(s.val), yP = candles.priceToCoordinate(s.poc);
        if (yH == null || yL == null) continue;
        ctx.fillStyle = "rgba(91,140,255,.06)"; ctx.fillRect(x1, yH, x2 - x1, yL - yH);
        ctx.strokeStyle = "rgba(91,140,255,.75)"; ctx.lineWidth = 1.5;
        ctx.beginPath(); ctx.moveTo(x1, yP); ctx.lineTo(x2, yP); ctx.stroke();
      }
    }

    if (state.show.profile) {
      const p = a.composite, bins = p.bins;
      let maxV = 0; for (const b of bins) maxV = Math.max(maxV, b[1]);
      const maxW = plotW * 0.22;
      for (const [price, v] of bins) {
        const y1 = candles.priceToCoordinate(price + p.bin_size), y2 = candles.priceToCoordinate(price);
        if (y1 == null || y2 == null) continue;
        const w = (v / maxV) * maxW, h = Math.max(1, y2 - y1 - 1);
        const isPoc = p.poc >= price && p.poc < price + p.bin_size;
        const inVa = price >= p.val - 1e-9 && price < p.vah - 1e-9;
        ctx.fillStyle = isPoc ? "rgba(245,197,66,.85)" : inVa ? "rgba(91,140,255,.38)" : "rgba(107,118,134,.22)";
        ctx.fillRect(plotW - w, y1, w, h);
      }
      const lv = (price, color) => {
        const y = candles.priceToCoordinate(price); if (y == null) return;
        ctx.strokeStyle = color; ctx.setLineDash([2, 3]); ctx.beginPath(); ctx.moveTo(plotW - maxW, y); ctx.lineTo(plotW, y); ctx.stroke(); ctx.setLineDash([]);
      };
      p.lvns.forEach((x) => lv(x, "rgba(232,121,249,.6)"));
    }
    ctx.restore();
  }
  (function loop() { if (!document.hidden) drawOverlay(); requestAnimationFrame(loop); })();

  // ---------- watchlist ----------
  async function loadWatch() {
    const ul = $("watch");
    try {
      const rows = await api(`/api/watchlist?tf=1h&days=30`);
      ul.innerHTML = rows.map((r) => r.error
        ? `<li data-k="${r.key}"><span class="k">${r.key}</span><span class="p muted">err</span><span class="s" title="${r.error}">no data</span><span></span></li>`
        : `<li data-k="${r.key}"><span class="k">${r.key}</span><span class="p">${r.last.toPrecision(6)}</span>
             <span class="s">${r.state.replace("imbalance-", "imb ")} · ${r.read}</span>
             <span class="c ${r.chg >= 0 ? "up" : "down"}">${r.chg >= 0 ? "+" : ""}${r.chg.toFixed(2)}%</span></li>`).join("");
      ul.querySelectorAll("li").forEach((li) => {
        li.classList.toggle("on", li.dataset.k === state.sym);
        li.onclick = () => { state.sym = li.dataset.k; load(); };
      });
    } catch (e) { ul.innerHTML = `<li class="muted">${e.message}</li>`; }
  }

  // ---------- controls ----------
  document.querySelectorAll("#tfSeg button").forEach((b) => {
    b.classList.toggle("on", b.dataset.tf === state.tf);
    b.onclick = () => { state.tf = b.dataset.tf; document.querySelectorAll("#tfSeg button").forEach((x) => x.classList.toggle("on", x === b)); load(); };
  });
  $("days").value = String(state.days);
  $("days").onchange = (e) => { state.days = +e.target.value; load(); };
  document.querySelectorAll("#toggles input").forEach((i) => {
    i.checked = !!state.show[i.dataset.k];
    i.onchange = () => {
      state.show[i.dataset.k] = i.checked;
      try { localStorage.setItem("of.show", JSON.stringify(state.show)); } catch {}
      render(false);
    };
  });
  $("refresh").onclick = () => { load(); loadWatch(); };
  window.addEventListener("keydown", (e) => {
    if (e.target.tagName === "INPUT" || e.target.tagName === "SELECT") return;
    if (e.key === "r") { load(); loadWatch(); }
    const tfs = { 1: "1h", 4: "4h", d: "1d" }; if (tfs[e.key]) document.querySelector(`#tfSeg [data-tf="${tfs[e.key]}"]`).click();
  });

  api("/api/symbols").then((s) => { state.symbols = s; load(); loadWatch(); });
})();
