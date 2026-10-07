/* Footprint + DOM ladder. Streams from /ws/footprint (dashboard/footprint_hub.py). */
(() => {
  const $ = (id) => document.getElementById(id);
  const css = (v) => getComputedStyle(document.documentElement).getPropertyValue(v).trim();
  const C = { bg: css("--bg"), line: css("--line"), text: css("--text"), muted: css("--muted"),
              up: css("--up"), down: css("--down"), gold: css("--gold"), accent: css("--accent") };
  const UP = "38,166,154", DN = "239,83,80", BLUE = "91,140,255";

  const qs = new URLSearchParams(location.search);
  const S = {
    sym: qs.get("sym") || "ES", mode: qs.get("mode") || "live", bar: +(qs.get("bar") || 300),
    row: +(qs.get("row") || 0), ratio: +(qs.get("ratio") || 3), view: qs.get("view") || "bidask",
    syms: [], meta: null, tick: 0.25, rowSize: 0.25, dec: 2,
    bars: [], book: { bids: [], asks: [] }, profile: [], tape: [],
    rowH: 16, colW: 120, yCenter: null, xOff: 0, follow: true, hover: null,
    domCenter: null, domFollow: true, ws: null, wsId: 0, dirty: true,
  };

  // ---------- formatting ----------
  const decimalsOf = (x) => { const s = String(x); return s.includes("e-") ? +s.split("e-")[1] : (s.split(".")[1] || "").length; };
  const fp = (p) => Number(p).toFixed(S.dec);
  const fv = (v) => {
    const a = Math.abs(v);
    if (a >= 1e6) return (v / 1e6).toFixed(1) + "M";
    if (a >= 1e4) return (v / 1e3).toFixed(0) + "k";
    if (a >= 1e3) return (v / 1e3).toFixed(1) + "k";
    if (a > 0 && a < 10 && a % 1) return v.toFixed(a < 1 ? 3 : 2);
    return String(Math.round(v));
  };
  const hhmm = (t) => new Date(t * 1000).toTimeString().slice(0, 5);
  const hhmmss = (t) => new Date(t * 1000).toTimeString().slice(0, 8);

  // ---------- canvas helpers ----------
  const fpC = $("fp"), domC = $("dom");
  const fit = (cv) => {
    const r = cv.getBoundingClientRect(), d = window.devicePixelRatio || 1;
    if (cv.width !== Math.round(r.width * d) || cv.height !== Math.round(r.height * d)) {
      cv.width = Math.round(r.width * d); cv.height = Math.round(r.height * d);
    }
    const ctx = cv.getContext("2d"); ctx.setTransform(d, 0, 0, d, 0, 0);
    return [ctx, r.width, r.height];
  };
  const rowOf = (p, size) => Math.floor(p / size + 1e-9);

  // ---------- footprint ----------
  const AXIS = 76, STATS = 54, PROF = 70;
  let geo = null; // last layout, used for hover hit-testing

  function drawFootprint() {
    const [g, W, H] = fit(fpC);
    g.fillStyle = C.bg; g.fillRect(0, 0, W, H);
    const plotW = W - AXIS, plotH = H - STATS, n = S.bars.length;
    if (!n) { g.fillStyle = C.muted; g.font = "13px system-ui"; g.fillText("waiting for prints…", 20, 30); return; }
    const last = S.bars[n - 1].c, rs = S.rowSize;
    if (S.follow) {
      S.xOff = 0;
      const y = plotH / 2 - (last - (S.yCenter ?? last)) / rs * S.rowH;
      if (S.yCenter == null || y < plotH * 0.2 || y > plotH * 0.8) S.yCenter = (rowOf(last, rs) + 0.5) * rs;
    }
    const yOf = (p) => plotH / 2 - (p - S.yCenter) / rs * S.rowH;
    const pOf = (y) => S.yCenter + (plotH / 2 - y) / S.rowH * rs;
    const right0 = plotW - PROF - 8;
    geo = { plotW, plotH, right0, yOf, pOf };

    // row grid
    if (S.rowH >= 9) {
      g.strokeStyle = "#10151c"; g.lineWidth = 1; g.beginPath();
      const r0 = rowOf(pOf(plotH), rs), r1 = rowOf(pOf(0), rs) + 1;
      for (let r = r0; r <= r1; r++) { const y = Math.round(yOf(r * rs)) + 0.5; g.moveTo(0, y); g.lineTo(plotW, y); }
      g.stroke();
    }

    // session profile (right edge of plot)
    if (S.profile.length) {
      const agg = new Map();
      for (const [p, b, a] of S.profile) { const r = rowOf(p, rs); agg.set(r, (agg.get(r) || 0) + b + a); }
      let mx = 0, poc = null; for (const [r, v] of agg) if (v > mx) { mx = v; poc = r; }
      for (const [r, v] of agg) {
        const y = yOf((r + 1) * rs), h = Math.max(1, S.rowH - 1); if (y > plotH || y + h < 0) continue;
        const w = v / mx * (PROF - 6);
        g.fillStyle = r === poc ? "rgba(245,197,66,.7)" : "rgba(107,118,134,.28)";
        g.fillRect(plotW - w, y, w, h);
      }
    }

    // visible range + scales
    const vis = [];
    for (let i = n - 1; i >= 0; i--) {
      const xR = right0 - (n - 1 - i - S.xOff) * S.colW, xL = xR - S.colW;
      if (xR < 0) break; if (xL > right0) continue;
      vis.push([i, xL, xR]);
    }
    let maxAbsD = 1; for (const [i] of vis) maxAbsD = Math.max(maxAbsD, Math.abs(S.bars[i].delta));

    g.save(); g.beginPath(); g.rect(0, 0, plotW - PROF, plotH); g.clip();
    // stacked imbalance zones extend right from the bar that printed them
    for (const [i, , xR] of vis.slice(0, 40)) {
      const b = S.bars[i];
      for (const [lo, hi] of b.stacked_buy) { g.fillStyle = `rgba(${UP},.10)`; g.fillRect(xR, yOf(hi), right0 - xR + 8, yOf(lo) - yOf(hi)); }
      for (const [lo, hi] of b.stacked_sell) { g.fillStyle = `rgba(${DN},.10)`; g.fillRect(xR, yOf(hi), right0 - xR + 8, yOf(lo) - yOf(hi)); }
    }
    for (const [i, xL, xR] of vis) drawBar(g, S.bars[i], xL, xR, yOf, plotH);
    g.restore();

    // stats strip
    g.fillStyle = "#0e1218"; g.fillRect(0, plotH, plotW, STATS);
    g.font = "11px system-ui"; g.textAlign = "center"; g.textBaseline = "middle";
    for (const [i, xL, xR] of vis) {
      const b = S.bars[i], cx = (xL + xR) / 2, w = S.colW - 4;
      g.fillStyle = C.muted; g.fillText(hhmm(b.t), cx, plotH + 9);
      const a = 0.15 + 0.6 * Math.abs(b.delta) / maxAbsD;
      g.fillStyle = `rgba(${b.delta >= 0 ? UP : DN},${a})`; g.fillRect(xL + 2, plotH + 19, w, 16);
      g.fillStyle = C.text; g.fillText((b.delta > 0 ? "+" : "") + fv(b.delta), cx, plotH + 27);
      g.fillStyle = C.muted; g.fillText(fv(b.volume), cx, plotH + 45);
    }
    g.textAlign = "left"; g.fillStyle = "#0e1218"; g.fillRect(0, plotH + 18, 22, STATS - 18);
    g.fillStyle = C.muted; g.fillText("Δ", 6, plotH + 27); g.fillText("vol", 3, plotH + 45);

    // price axis
    g.fillStyle = "#0e1218"; g.fillRect(plotW, 0, AXIS, H);
    g.font = "11px system-ui"; g.textAlign = "left"; g.textBaseline = "middle";
    const every = Math.max(1, Math.ceil(18 / S.rowH));
    const r0 = rowOf(pOf(plotH), rs), r1 = rowOf(pOf(0), rs);
    for (let r = r0; r <= r1; r++) {
      if (r % every) continue;
      g.fillStyle = C.muted; g.fillText(fp(r * rs), plotW + 8, yOf((r + 0.5) * rs));
    }
    const tag = (p, bg, fg, text) => {
      const y = yOf((rowOf(p, rs) + 0.5) * rs); if (y < 0 || y > plotH) return;
      g.fillStyle = bg; g.fillRect(plotW + 2, y - 8, AXIS - 4, 16); g.fillStyle = fg; g.fillText(text ?? fp(p), plotW + 8, y);
    };
    tag(last, C.gold, "#111");

    // crosshair + tooltip
    const tip = $("tip");
    if (S.hover && S.hover.x < plotW && S.hover.y < plotH) {
      const p = pOf(S.hover.y), r = rowOf(p, rs), y = yOf((r + 0.5) * rs);
      g.strokeStyle = "rgba(214,219,227,.25)"; g.setLineDash([3, 3]); g.beginPath();
      g.moveTo(0, y); g.lineTo(plotW, y); g.moveTo(S.hover.x, 0); g.lineTo(S.hover.x, plotH); g.stroke(); g.setLineDash([]);
      tag(r * rs, "#2a3342", C.text);
      const hit = vis.find(([, xL, xR]) => S.hover.x >= xL && S.hover.x < xR);
      const cell = hit && S.bars[hit[0]].cells.find((c) => rowOf(c[0] + rs / 2, rs) === r);
      if (cell) {
        const [px, bid, ask, imb] = cell;
        tip.innerHTML = `<b>${fp(px)}</b> · ${hhmm(S.bars[hit[0]].t)}<br>bid <span style="color:${C.down}">${fv(bid)}</span> × ask <span style="color:${C.up}">${fv(ask)}</span>` +
          `<br>Δ ${(ask - bid > 0 ? "+" : "") + fv(ask - bid)}${imb ? ` · <b style="color:${imb > 0 ? C.up : C.down}">${imb > 0 ? "buy" : "sell"} imbalance</b>` : ""}`;
        tip.hidden = false;
        tip.style.left = Math.min(S.hover.x + 14, plotW - 180) + "px"; tip.style.top = Math.max(S.hover.y - 50, 4) + "px";
      } else tip.hidden = true;
    } else tip.hidden = true;
  }

  function drawBar(g, b, xL, xR, yOf, plotH) {
    const rs = S.rowSize, h = Math.max(1, S.rowH - 1);
    let mx = 1e-12, mxD = 1e-12;
    for (const [, bid, ask] of b.cells) { mx = Math.max(mx, S.view === "volume" ? bid + ask : Math.max(bid, ask)); mxD = Math.max(mxD, Math.abs(ask - bid)); }

    // candle strip
    const cx = xL + 6, up = b.c >= b.o;
    const mid = (p) => yOf((rowOf(p, rs) + 0.5) * rs);
    g.strokeStyle = up ? C.up : C.down; g.lineWidth = 1;
    g.beginPath(); g.moveTo(cx + 0.5, mid(b.h) - S.rowH / 2); g.lineTo(cx + 0.5, mid(b.l) + S.rowH / 2); g.stroke();
    const yo = mid(b.o), yc = mid(b.c);
    g.fillStyle = up ? C.up : C.down;
    g.fillRect(cx - 2, Math.min(yo, yc) - S.rowH / 2, 5, Math.abs(yo - yc) + S.rowH);

    const x0 = xL + 14, x1 = xR - 4, w = x1 - x0, xm = x0 + w / 2;
    const showText = S.rowH >= 11 && w >= 56;
    g.font = `${Math.min(12, S.rowH - 3)}px ui-monospace, SFMono-Regular, Menlo, monospace`;
    g.textBaseline = "middle";
    for (const [px, bid, ask, imb] of b.cells) {
      const y = yOf(px + rs); if (y > plotH || y + h < 0) continue;
      const ty = y + h / 2;
      if (S.view === "bidask") {
        g.fillStyle = `rgba(${DN},${(imb < 0 ? 0.35 : 0.06) + 0.45 * bid / mx})`; g.fillRect(x0, y, w / 2 - 1, h);
        g.fillStyle = `rgba(${UP},${(imb > 0 ? 0.35 : 0.06) + 0.45 * ask / mx})`; g.fillRect(xm, y, w / 2, h);
        if (showText) {
          g.textAlign = "right"; g.fillStyle = imb < 0 ? "#ffd1d0" : "#c9ced6"; g.font = `${imb < 0 ? "bold " : ""}${Math.min(12, S.rowH - 3)}px ui-monospace, Menlo, monospace`;
          g.fillText(fv(bid), xm - 5, ty);
          g.textAlign = "left"; g.fillStyle = imb > 0 ? "#c8fff7" : "#c9ced6"; g.font = `${imb > 0 ? "bold " : ""}${Math.min(12, S.rowH - 3)}px ui-monospace, Menlo, monospace`;
          g.fillText(fv(ask), xm + 4, ty);
        }
      } else if (S.view === "delta") {
        const d = ask - bid;
        g.fillStyle = `rgba(${d >= 0 ? UP : DN},${0.08 + 0.7 * Math.abs(d) / mxD})`; g.fillRect(x0, y, w, h);
        if (showText) { g.textAlign = "center"; g.fillStyle = C.text; g.fillText((d > 0 ? "+" : "") + fv(d), xm, ty); }
      } else {
        const v = bid + ask, bw = Math.max(1, v / mx * w);
        g.fillStyle = `rgba(${BLUE},${0.2 + 0.5 * v / mx})`; g.fillRect(x0, y, bw, h);
        if (showText) { g.textAlign = "left"; g.fillStyle = C.text; g.fillText(fv(v), x0 + 3, ty); }
      }
    }
    // POC outline
    if (b.poc != null) {
      g.strokeStyle = C.gold; g.lineWidth = 1.5;
      g.strokeRect(x0 + 0.5, yOf(b.poc + rs) + 0.5, w - 1, h - 1);
    }
    // unfinished auctions (both sides traded at the extreme)
    g.fillStyle = C.gold;
    if (b.unfinished_high) { const y = yOf(rowOf(b.h, rs) * rs + rs); g.beginPath(); g.arc(x1 - 3, y - 4, 2.5, 0, 7); g.fill(); }
    if (b.unfinished_low) { const y = yOf(rowOf(b.l, rs) * rs); g.beginPath(); g.arc(x1 - 3, y + 4, 2.5, 0, 7); g.fill(); }
  }

  // ---------- DOM ladder ----------
  const DOM_ROW = 18;
  function drawDom() {
    const [g, W, H] = fit(domC);
    g.fillStyle = C.bg; g.fillRect(0, 0, W, H);
    const symDef = S.syms.find((s) => s.key === S.sym);
    const step = S.tick * Math.max(1, Math.floor((symDef ? symDef.row_ticks : 1) / 5));
    const bids = new Map(), asks = new Map();
    for (const [p, s] of S.book.bids) { const r = rowOf(p, step); bids.set(r, (bids.get(r) || 0) + s); }
    for (const [p, s] of S.book.asks) { const r = rowOf(p, step); asks.set(r, (asks.get(r) || 0) + s); }
    const bestBid = S.book.bids.length ? S.book.bids[0][0] : null, bestAsk = S.book.asks.length ? S.book.asks[0][0] : null;
    const lastPx = S.bars.length ? S.bars[S.bars.length - 1].c : bestBid;
    if (lastPx == null) { g.fillStyle = C.muted; g.font = "12px system-ui"; g.fillText("no book yet", 12, 20); return; }

    // recent aggression per row (last 15s of tape) + session traded
    const now = S.tape.length ? S.tape[S.tape.length - 1][0] : 0;
    const rb = new Map(), rsl = new Map();
    for (let i = S.tape.length - 1; i >= 0; i--) {
      const [t, p, s, isBuy] = S.tape[i]; if (now - t > 15) break;
      const m = isBuy ? rb : rsl, r = rowOf(p, step); m.set(r, (m.get(r) || 0) + s);
    }
    const traded = new Map(); let mxT = 1e-12;
    for (const [p, b, a] of S.profile) { const r = rowOf(p, step), v = (traded.get(r) || 0) + b + a; traded.set(r, v); mxT = Math.max(mxT, v); }

    const nRows = Math.floor(H / DOM_ROW);
    const midRow = bestBid != null && bestAsk != null ? rowOf((bestBid + bestAsk) / 2, step) : rowOf(lastPx, step);
    if (S.domFollow || S.domCenter == null || Math.abs(S.domCenter - midRow) > nRows / 2 - 3) { if (S.domFollow) S.domCenter = midRow; }
    const top = S.domCenter + Math.floor(nRows / 2);
    let mxS = 1e-12, sum = 0, cnt = 0;
    for (let k = 0; k < nRows; k++) { const r = top - k; const v = Math.max(bids.get(r) || 0, asks.get(r) || 0); mxS = Math.max(mxS, v); if (v) { sum += v; cnt++; } }
    const avg = cnt ? sum / cnt : 1;
    const cw = W / 5.1, cols = [0, cw, 2 * cw, 3.1 * cw, 4.1 * cw, 5.1 * cw];
    g.font = "12px ui-monospace, SFMono-Regular, Menlo, monospace"; g.textBaseline = "middle";
    const lastRow = rowOf(lastPx, step);
    for (let k = 0; k < nRows; k++) {
      const r = top - k, y = k * DOM_ROW, ty = y + DOM_ROW / 2, p = r * step;
      if (k % 2) { g.fillStyle = "#0d1117"; g.fillRect(0, y, W, DOM_ROW); }
      const tv = traded.get(r);
      if (tv) { g.fillStyle = "rgba(107,118,134,.18)"; g.fillRect(cols[2], y + 1, (cols[3] - cols[2]) * tv / mxT, DOM_ROW - 2); }
      const b = bids.get(r), a = asks.get(r);
      if (b) {
        const wall = b >= 3 * avg, w = (cols[2] - cols[1] - 2) * b / mxS;
        g.fillStyle = `rgba(${BLUE},${wall ? 0.6 : 0.3})`; g.fillRect(cols[2] - 1 - w, y + 2, w, DOM_ROW - 4);
        g.fillStyle = wall ? "#fff" : "#c9d6ff"; g.textAlign = "right"; g.font = `${wall ? "bold " : ""}12px ui-monospace, Menlo, monospace`;
        g.fillText(fv(b), cols[2] - 5, ty);
      }
      if (a) {
        const wall = a >= 3 * avg, w = (cols[4] - cols[3] - 2) * a / mxS;
        g.fillStyle = `rgba(${DN},${wall ? 0.6 : 0.3})`; g.fillRect(cols[3] + 1, y + 2, w, DOM_ROW - 4);
        g.fillStyle = wall ? "#fff" : "#ffd0cf"; g.textAlign = "left"; g.font = `${wall ? "bold " : ""}12px ui-monospace, Menlo, monospace`;
        g.fillText(fv(a), cols[3] + 5, ty);
      }
      g.font = "12px ui-monospace, Menlo, monospace";
      const s = rsl.get(r), bb = rb.get(r);
      if (s) { g.fillStyle = C.down; g.textAlign = "right"; g.fillText(fv(s), cols[1] - 6, ty); }
      if (bb) { g.fillStyle = C.up; g.textAlign = "left"; g.fillText(fv(bb), cols[4] + 6, ty); }
      g.textAlign = "center";
      if (r === lastRow) {
        g.fillStyle = "rgba(245,197,66,.18)"; g.fillRect(cols[2], y, cols[3] - cols[2], DOM_ROW);
        g.strokeStyle = C.gold; g.strokeRect(cols[2] + 0.5, y + 0.5, cols[3] - cols[2] - 1, DOM_ROW - 1);
      }
      g.fillStyle = r === lastRow ? C.gold : C.text;
      g.fillText(fp(p), (cols[2] + cols[3]) / 2, ty);
    }
    g.strokeStyle = C.line; g.beginPath();
    for (const x of cols.slice(1, 5)) { g.moveTo(Math.round(x) + 0.5, 0); g.lineTo(Math.round(x) + 0.5, H); }
    g.stroke();
  }

  // ---------- tape ----------
  function pushTape(list) {
    if (!list.length) return;
    S.tape.push(...list); if (S.tape.length > 3000) S.tape.splice(0, S.tape.length - 3000);
    const ul = $("tape"), min = +$("minSize").value || 0;
    const sizes = S.tape.slice(-300).map((t) => t[2]).sort((a, b) => a - b);
    const big = sizes.length ? sizes[Math.floor(sizes.length * 0.95)] : Infinity;
    const frag = document.createDocumentFragment();
    for (const [t, p, s, isBuy] of list) {
      if (s < min) continue;
      const li = document.createElement("li");
      li.className = (isBuy ? "b" : "s") + (s >= big ? " big" : "");
      li.innerHTML = `<span>${hhmmss(t)}</span><span>${fp(p)}</span><span>${fv(s)}</span>`;
      frag.prepend(li);
    }
    ul.prepend(frag);
    while (ul.children.length > 150) ul.lastChild.remove();
  }

  // ---------- stream ----------
  function mergeBars(list) {
    for (const b of list) {
      const n = S.bars.length;
      if (!n || b.t > S.bars[n - 1].t) S.bars.push(b);
      else if (b.t === S.bars[n - 1].t) S.bars[n - 1] = b;
      else { const i = S.bars.findIndex((x) => x.t === b.t); if (i >= 0) S.bars[i] = b; }
    }
    if (S.bars.length > 400) S.bars.splice(0, S.bars.length - 400);
  }

  function setStatus(m) {
    const el = $("status");
    if (!m) { el.className = "badge"; el.textContent = "connecting…"; return; }
    const ok = m.status === "live" || m.status === "sim";
    el.className = "badge " + (m.live ? (ok ? "live" : "bad") : "sim");
    el.textContent = m.live ? `${m.feed.toUpperCase()} · ${m.status}` : "SIM: synthetic data";
    el.title = m.error || "";
    const msg = $("msg");
    if (m.error && !S.bars.length) { msg.textContent = m.error; msg.hidden = false; } else msg.hidden = true;
  }

  function connect() {
    if (S.ws) { S.ws.onclose = null; S.ws.close(); }
    const id = ++S.wsId;
    S.bars = []; S.tape = []; S.profile = []; S.book = { bids: [], asks: [] }; S.yCenter = null; S.follow = true; S.domFollow = true;
    $("tape").innerHTML = ""; setStatus(null);
    const p = new URLSearchParams({ sym: S.sym, mode: S.mode, bar: S.bar, row: S.row, ratio: S.ratio });
    history.replaceState(null, "", "?" + new URLSearchParams({ ...Object.fromEntries(p), view: S.view }));
    const ws = new WebSocket(`${location.protocol === "https:" ? "wss" : "ws"}://${location.host}/ws/footprint?${p}`);
    S.ws = ws;
    ws.onmessage = (ev) => {
      if (id !== S.wsId) return;
      const m = JSON.parse(ev.data);
      if (m.type === "error") { $("msg").textContent = m.error; $("msg").hidden = false; return; }
      if (m.type === "snapshot") {
        S.tick = m.meta.tick; S.rowSize = m.row_size; S.dec = decimalsOf(S.tick);
        S.bars = m.bars;
      } else mergeBars(m.bars);
      S.book = m.book; if (m.profile) S.profile = m.profile;
      pushTape(m.tape || []);
      setStatus(m.meta); S.meta = m.meta; S.dirty = true;
      $("depth").textContent = m.meta.depth ? `· ${m.meta.depth}` : "";
    };
    ws.onclose = () => { if (id === S.wsId) setTimeout(() => id === S.wsId && connect(), 1500); };
  }

  // ---------- controls ----------
  function fillRows() {
    const s = S.syms.find((x) => x.key === S.sym); if (!s) return;
    const opts = [1, 2, 4, 5, 10, 20, 25, 50, 100, 250].filter((k) => k <= Math.max(20, s.row_ticks * 5));
    if (!S.row || !opts.includes(S.row)) S.row = s.row_ticks;
    $("row").innerHTML = opts.map((k) => `<option value="${k}" ${k === S.row ? "selected" : ""}>${k}t · ${+(k * s.tick).toFixed(8)}</option>`).join("");
  }
  const segs = (id, key, attr) => document.querySelectorAll(`#${id} button`).forEach((b) => {
    b.classList.toggle("on", b.dataset[attr] === S[key]);
    b.onclick = () => {
      S[key] = b.dataset[attr];
      document.querySelectorAll(`#${id} button`).forEach((x) => x.classList.toggle("on", x === b));
      key === "view" ? (S.dirty = true, history.replaceState(null, "", location.search.replace(/view=\w+/, "view=" + S.view))) : connect();
    };
  });
  segs("modeSeg", "mode", "mode"); segs("viewSeg", "view", "view");
  $("bar").value = String(S.bar); $("ratio").value = String(S.ratio);
  $("bar").onchange = (e) => { S.bar = +e.target.value; connect(); };
  $("ratio").onchange = (e) => { S.ratio = +e.target.value; connect(); };
  $("row").onchange = (e) => { S.row = +e.target.value; connect(); };
  $("sym").onchange = (e) => { S.sym = e.target.value; S.row = 0; fillRows(); connect(); };
  $("minSize").oninput = () => { $("tape").innerHTML = ""; const t = S.tape; S.tape = []; pushTape(t); };

  // pan / zoom
  let drag = null;
  fpC.addEventListener("mousedown", (e) => { drag = { x: e.clientX, y: e.clientY, xOff: S.xOff, yc: S.yCenter }; });
  window.addEventListener("mouseup", () => { drag = null; });
  fpC.addEventListener("mousemove", (e) => {
    const r = fpC.getBoundingClientRect(); S.hover = { x: e.clientX - r.left, y: e.clientY - r.top };
    if (drag) {
      S.follow = false;
      S.xOff = drag.xOff + (e.clientX - drag.x) / S.colW;
      S.yCenter = drag.yc + (e.clientY - drag.y) / S.rowH * S.rowSize;
    }
    S.dirty = true;
  });
  fpC.addEventListener("mouseleave", () => { S.hover = null; S.dirty = true; });
  fpC.addEventListener("wheel", (e) => {
    e.preventDefault();
    const f = e.deltaY < 0 ? 1.1 : 1 / 1.1;
    if (e.shiftKey || e.ctrlKey) S.colW = Math.min(260, Math.max(28, S.colW * f));
    else S.rowH = Math.min(40, Math.max(4, S.rowH * f));
    S.dirty = true;
  }, { passive: false });
  fpC.addEventListener("dblclick", () => { S.follow = true; S.yCenter = null; S.dirty = true; });
  domC.addEventListener("wheel", (e) => { e.preventDefault(); S.domFollow = false; S.domCenter += e.deltaY < 0 ? 2 : -2; S.dirty = true; }, { passive: false });
  domC.addEventListener("dblclick", () => { S.domFollow = true; S.dirty = true; });
  window.addEventListener("resize", () => { S.dirty = true; });

  (function loop() {
    if (S.dirty && !document.hidden) { S.dirty = false; drawFootprint(); drawDom(); }
    requestAnimationFrame(loop);
  })();

  fetch("/api/fp/symbols").then((r) => r.json()).then((syms) => {
    S.syms = syms;
    if (!syms.find((s) => s.key === S.sym)) S.sym = syms[0].key;
    $("sym").innerHTML = syms.map((s) => `<option value="${s.key}" ${s.key === S.sym ? "selected" : ""}>${s.key}  ${s.name}</option>`).join("");
    fillRows(); connect();
  });
})();
