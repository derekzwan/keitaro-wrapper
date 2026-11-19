"use strict";

/* ================= утилиты ================= */

const $ = (sel, root = document) => root.querySelector(sel);
const $$ = (sel, root = document) => [...root.querySelectorAll(sel)];
const view = $("#view");

const esc = (v) => String(v ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const fmtInt = (n) => Math.round(n || 0).toLocaleString("ru-RU");
const fmtMoney = (n) => (n || 0).toLocaleString("ru-RU", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
const fmtPct = (a, b) => (b ? ((a / b) * 100).toFixed(2) + "%" : "—");

let regionNames = null;
try { regionNames = new Intl.DisplayNames(["ru"], { type: "region" }); } catch (_) { /* старый браузер */ }
const countryName = (code) => { try { return regionNames?.of(code) || code; } catch (_) { return code; } };

function timeAgo(iso) {
  if (!iso) return "никогда";
  const s = Math.max(0, (Date.now() - new Date(iso).getTime()) / 1000);
  if (s < 45) return "только что";
  if (s < 3600) return `${Math.round(s / 60)} мин назад`;
  if (s < 86400) return `${Math.round(s / 3600)} ч назад`;
  return new Date(iso).toLocaleString("ru-RU");
}

const svg = (body, cls = "i") => `<svg class="${cls}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">${body}</svg>`;
const ICONS = {
  pin: svg('<path d="M12 17v5"/><path d="M9 10.76a2 2 0 0 1-1.11 1.79l-1.78.9A2 2 0 0 0 5 15.24V16a1 1 0 0 0 1 1h12a1 1 0 0 0 1-1v-.76a2 2 0 0 0-1.11-1.79l-1.78-.9A2 2 0 0 1 15 10.76V7a1 1 0 0 1 1-1 2 2 0 0 0 0-4H8a2 2 0 0 0 0 4 1 1 0 0 1 1 1z"/>'),
  upload: svg('<path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><path d="m17 8-5-5-5 5"/><path d="M12 3v12"/>'),
  download: svg('<path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><path d="m7 10 5 5 5-5"/><path d="M12 15V3"/>'),
  x: svg('<path d="M18 6 6 18M6 6l12 12"/>'),
  trash: svg('<path d="M3 6h18"/><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6"/><path d="M8 6V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/>'),
  undo: svg('<path d="M3 7v6h6"/><path d="M21 17a9 9 0 0 0-9-9 9 9 0 0 0-6 2.3L3 13"/>'),
  ext: svg('<path d="M15 3h6v6"/><path d="M10 14 21 3"/><path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"/>'),
  copy: svg('<rect x="9" y="9" width="13" height="13" rx="2"/><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/>'),
  plus: svg('<path d="M12 5v14M5 12h14"/>'),
  search: svg('<circle cx="11" cy="11" r="7"/><path d="m20 20-3.5-3.5"/>'),
  eye: svg('<path d="M2 12s3.5-7 10-7 10 7 10 7-3.5 7-10 7S2 12 2 12z"/><circle cx="12" cy="12" r="3"/>'),
  globe: svg('<circle cx="12" cy="12" r="9"/><path d="M3 12h18M12 3a14 14 0 0 1 0 18M12 3a14 14 0 0 0 0 18"/>'),
  users: svg('<path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M22 21v-2a4 4 0 0 0-3-3.87M16 3.13a4 4 0 0 1 0 7.75"/>'),
  target: svg('<circle cx="12" cy="12" r="9"/><circle cx="12" cy="12" r="5"/><circle cx="12" cy="12" r="1"/>'),
  check: svg('<path d="M20 6 9 17l-5-5"/>'),
  chev: svg('<path d="m9 18 6-6-6-6"/>', "i chev"),
  layers: svg('<path d="m12 2 10 5-10 5L2 7z"/><path d="m2 17 10 5 10-5M2 12l10 5 10-5"/>'),
  arrowR: svg('<path d="M5 12h14M13 5l7 7-7 7"/>'),
  filter: svg('<path d="M3 4h18l-7 8v6l-4 2v-8z"/>', "i fi"),
};

function toast(msg, kind = "") {
  const el = document.createElement("div");
  el.className = `toast ${kind}`;
  el.innerHTML = `<i></i><span>${esc(msg)}</span>`;
  $("#toasts").append(el);
  setTimeout(() => { el.classList.add("out"); setTimeout(() => el.remove(), 220); }, kind === "err" ? 7000 : 3000);
}

async function api(method, path, body) {
  let res;
  try {
    res = await fetch(path, {
      method,
      headers: body ? { "Content-Type": "application/json" } : {},
      body: body ? JSON.stringify(body) : undefined,
    });
  } catch (_) {
    throw new Error("Сервер недоступен");
  }
  const text = await res.text();
  let data = null;
  try { data = text ? JSON.parse(text) : null; } catch (_) { data = text; }
  if (!res.ok) {
    const d = data && data.detail;
    throw new Error(typeof d === "string" ? d : (d ? JSON.stringify(d) : `HTTP ${res.status}`));
  }
  return data;
}

async function busy(btn, fn) {
  if (!btn) return fn();
  const html = btn.innerHTML;
  btn.disabled = true;
  btn.innerHTML = `<span class="spin"></span>${html}`;
  try { return await fn(); } finally { if (btn.isConnected) { btn.disabled = false; btn.innerHTML = html; } }
}

async function copy(text) {
  try { await navigator.clipboard.writeText(text); toast("Скопировано", "ok"); }
  catch (_) { toast("Не удалось скопировать", "err"); }
}

function localGet(k) { try { return localStorage.getItem(`ktw.${k}`); } catch (_) { return null; } }
function localSet(k, v) { try { localStorage.setItem(`ktw.${k}`, v); } catch (_) { /* приватный режим */ } }

const PALETTE = ["--s1", "--s2", "--s3", "--s4", "--s5", "--s6", "--s7", "--s8"];
const segColor = (i) => `var(${PALETTE[i % PALETTE.length]})`;
const geoTags = (csv) => (csv ? csv.split(",").filter(Boolean).map((c) => `<span class="tag blue" title="${esc(countryName(c))}">${esc(c)}</span>`).join("") : "");
const avatarColor = (s) => segColor([...String(s)].reduce((a, ch) => a + ch.charCodeAt(0), 0));
const initials = (s) => esc((s || "?").replace(/[^\p{L}\p{N}]/gu, "").slice(0, 2).toUpperCase() || "?");

/* ================= графики ================= */

/** Спарклайн: столбики — клики по дням, точки сверху — дни с конверсиями. */
function sparkline(series, { cls = "trend", color = "var(--s2)" } = {}) {
  const clicks = series?.clicks || [];
  const conv = series?.conversions || [];
  const n = clicks.length;
  if (!n) return `<span class="trend-empty">—</span>`;
  const W = 120, H = 30, gap = n > 14 ? 1 : 2;
  const max = Math.max(1, ...clicks);
  const bw = Math.max(1, (W - gap * (n - 1)) / n);
  const bars = clicks.map((v, i) => {
    const h = v ? Math.max(2, (v / max) * (H - 6)) : 1.5;
    const x = i * (bw + gap);
    return `<rect x="${x.toFixed(1)}" y="${(H - h).toFixed(1)}" width="${bw.toFixed(1)}" height="${h.toFixed(1)}" rx="1.2" fill="${color}" opacity="${v ? (i === n - 1 ? 1 : 0.55) : 0.18}"><title>${esc(series.days?.[i] || "")}: ${v} кл. / ${conv[i] || 0} конв.</title></rect>`;
  }).join("");
  const dots = conv.map((v, i) => (v ? `<circle cx="${(i * (bw + gap) + bw / 2).toFixed(1)}" cy="2.5" r="2" fill="var(--s1)"/>` : "")).join("");
  return `<svg class="${cls}" viewBox="0 0 ${W} ${H}" preserveAspectRatio="none">${bars}${dots}</svg>`;
}

function donut(parts, total, label) {
  const R = 46, C = 2 * Math.PI * R;
  let offset = 0;
  const arcs = parts.filter((p) => p.value > 0).map((p) => {
    const len = (p.value / 100) * C;
    const gapLen = parts.length > 1 ? 2 : 0;
    const a = `<circle cx="56" cy="56" r="${R}" fill="none" stroke="${p.color}" stroke-width="14" stroke-dasharray="${Math.max(0, len - gapLen).toFixed(2)} ${C.toFixed(2)}" stroke-dashoffset="${(-offset).toFixed(2)}"/>`;
    offset += len;
    return a;
  }).join("");
  return `
    <div class="donut">
      <svg viewBox="0 0 112 112"><circle cx="56" cy="56" r="${R}" fill="none" stroke="var(--panel-3)" stroke-width="14"/>${arcs}</svg>
      <div class="center"><div><b class="${total === 100 ? "" : "bad"}">${total}%</b><small>${esc(label)}</small></div></div>
    </div>`;
}

const zeroSeries = (days) => ({ clicks: days.map(() => 0), conversions: days.map(() => 0), days });

/* ================= автокомплит офферов ================= */

function offerAutocomplete(root, { onPick, placeholder = "Поиск оффера по ID или названию", exclude = () => new Set() }) {
  root.classList.add("ac");
  root.innerHTML = `<input class="input" type="text" autocomplete="off" placeholder="${esc(placeholder)}"><div class="ac-list hidden"></div>`;
  const input = $("input", root);
  const list = $(".ac-list", root);
  let items = [], active = -1, timer = null, seq = 0;

  const visible = () => { const ex = exclude(); return items.filter((o) => !ex.has(o.id)); };
  const close = () => { list.classList.add("hidden"); active = -1; };
  const render = () => {
    const shown = visible();
    list.innerHTML = shown.length
      ? shown.map((o, i) => `<div class="ac-item ${i === active ? "active" : ""}" data-i="${i}"><span class="id">${esc(o.id)}</span><span class="nm" title="${esc(o.name)}">${esc(o.name)}</span><span class="geo">${geoTags(o.country)}</span></div>`).join("")
      : `<div class="ac-empty">Ничего не найдено</div>`;
    list.classList.remove("hidden");
  };
  const pick = (o) => { close(); input.value = ""; onPick(o); };
  const search = async () => {
    const my = ++seq;
    try {
      const data = await api("GET", `/api/offers?q=${encodeURIComponent(input.value.trim())}&limit=30`);
      if (my !== seq) return;
      items = data; active = items.length ? 0 : -1; render();
    } catch (e) {
      if (my === seq) { list.innerHTML = `<div class="ac-empty">${esc(e.message)}</div>`; list.classList.remove("hidden"); }
    }
  };

  input.addEventListener("input", () => { clearTimeout(timer); timer = setTimeout(search, 160); });
  input.addEventListener("focus", () => { if (!items.length) search(); else render(); });
  input.addEventListener("keydown", (e) => {
    const shown = visible();
    if (e.key === "ArrowDown") { e.preventDefault(); active = Math.min(shown.length - 1, active + 1); render(); }
    else if (e.key === "ArrowUp") { e.preventDefault(); active = Math.max(0, active - 1); render(); }
    else if (e.key === "Enter") { e.preventDefault(); if (shown[active]) pick(shown[active]); }
    else if (e.key === "Escape") close();
  });
  list.addEventListener("mousedown", (e) => {
    const el = e.target.closest(".ac-item");
    if (!el) return;
    e.preventDefault();
    pick(visible()[+el.dataset.i]);
  });
  input.addEventListener("blur", () => setTimeout(close, 120));
  return { focus: () => input.focus() };
}

function pickedOffer(o) {
  return `<div class="ac-picked"><span class="id">${esc(o.id)}</span><span class="nm" title="${esc(o.name)}">${esc(o.name)}</span>${geoTags(o.country)}<button class="iconbtn" type="button" title="Сбросить">${ICONS.x}</button></div>`;
}

/* ================= выпадающий список ================= */

/** Свой select: кнопка + список, поиск при длинном списке, клавиатура. Значение — в el.dataset.value. */
function customSelect(el, { items, value, onChange = () => {}, placeholder = "Выбери…" }) {
  const searchable = items.length > 7;
  el.classList.add("csel");
  el.innerHTML = `
    <button type="button" class="csel-btn" aria-haspopup="listbox" aria-expanded="false">
      <span class="csel-label"></span>${svg('<path d="m6 9 6 6 6-6"/>', "i csel-chev")}
    </button>
    <div class="csel-pop hidden" role="listbox">
      ${searchable ? `<div class="csel-search">${ICONS.search}<input type="text" placeholder="Поиск" autocomplete="off"></div>` : ""}
      <div class="csel-list"></div>
    </div>`;
  const btn = $(".csel-btn", el), pop = $(".csel-pop", el), listEl = $(".csel-list", el), search = $(".csel-search input", el);
  let active = -1;

  const current = () => items.find((i) => String(i.id) === String(el.dataset.value));
  const setValue = (id, fire = true) => {
    const it = items.find((i) => String(i.id) === String(id));
    el.dataset.value = it ? it.id : "";
    el.dataset.text = it ? it.name : "";
    $(".csel-label", el).innerHTML = it ? esc(it.name) : `<span class="faint">${esc(placeholder)}</span>`;
    if (fire) onChange(it);
  };
  const filtered = () => {
    const q = (search?.value || "").trim().toLowerCase();
    return items.filter((i) => !q || i.name.toLowerCase().includes(q) || String(i.id).startsWith(q));
  };
  const render = () => {
    const shown = filtered();
    listEl.innerHTML = shown.length ? shown.map((i, n) => `
      <div class="csel-opt ${n === active ? "active" : ""} ${String(i.id) === String(el.dataset.value) ? "sel" : ""}" data-n="${n}" role="option">
        <span>${esc(i.name)}</span><span class="csel-id">${esc(i.id)}</span>${String(i.id) === String(el.dataset.value) ? ICONS.check : ""}
      </div>`).join("") : `<div class="ac-empty">Ничего не найдено</div>`;
    listEl.querySelector(".active")?.scrollIntoView({ block: "nearest" });
  };
  const open = () => {
    $$(".csel.open").forEach((x) => x !== el && x.dispatchEvent(new Event("csel-close")));
    el.classList.add("open"); pop.classList.remove("hidden"); btn.setAttribute("aria-expanded", "true");
    if (search) search.value = "";
    active = Math.max(0, filtered().findIndex((i) => String(i.id) === String(el.dataset.value)));
    render();
    (search || btn).focus();
    document.addEventListener("mousedown", outside);
  };
  const close = (focusBtn = false) => {
    el.classList.remove("open"); pop.classList.add("hidden"); btn.setAttribute("aria-expanded", "false");
    document.removeEventListener("mousedown", outside);
    if (focusBtn) btn.focus();
  };
  const outside = (e) => { if (!el.contains(e.target)) close(); };
  const choose = (n) => { const it = filtered()[n]; if (it) { setValue(it.id); close(true); } };
  const keys = (e) => {
    const n = filtered().length;
    if (e.key === "ArrowDown") { e.preventDefault(); if (pop.classList.contains("hidden")) return open(); active = Math.min(n - 1, active + 1); render(); }
    else if (e.key === "ArrowUp") { e.preventDefault(); active = Math.max(0, active - 1); render(); }
    else if (e.key === "Enter") { e.preventDefault(); if (pop.classList.contains("hidden")) open(); else choose(active); }
    else if (e.key === "Escape") { if (!pop.classList.contains("hidden")) { e.stopPropagation(); close(true); } }
    else if (e.key === "Tab") close();
  };

  btn.addEventListener("click", () => (pop.classList.contains("hidden") ? open() : close()));
  btn.addEventListener("keydown", keys);
  search?.addEventListener("keydown", keys);
  search?.addEventListener("input", () => { active = 0; render(); });
  listEl.addEventListener("mousedown", (e) => { const o = e.target.closest(".csel-opt"); if (o) { e.preventDefault(); choose(+o.dataset.n); } });
  listEl.addEventListener("mousemove", (e) => { const o = e.target.closest(".csel-opt"); if (o && +o.dataset.n !== active) { active = +o.dataset.n; render(); } });
  el.addEventListener("csel-close", () => close());
  setValue(value ?? items[0]?.id, false);
  return { get value() { return el.dataset.value; }, get item() { return current(); }, setValue };
}

/* ================= окно подтверждения ================= */

/** Своё модальное окно вместо confirm(). Возвращает Promise<boolean>. */
function confirmDialog({ title, text, ok = "Продолжить", cancel = "Отмена", tone = "warn" }) {
  return new Promise((resolve) => {
    const root = document.createElement("div");
    root.className = "modal-root";
    root.innerHTML = `
      <div class="scrim"></div>
      <div class="modal ${tone}" role="alertdialog" aria-modal="true" aria-labelledby="mdl-t">
        <div class="modal-ico">${tone === "danger" ? ICONS.trash : svg('<path d="M12 9v4M12 17h.01"/><path d="M10.3 3.9 1.8 18a2 2 0 0 0 1.7 3h17a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0z"/>')}</div>
        <h2 id="mdl-t">${esc(title)}</h2>
        <p>${esc(text)}</p>
        <div class="modal-actions">
          <button class="btn" data-r="0">${esc(cancel)}</button>
          <button class="btn ${tone === "danger" ? "danger" : "primary"}" data-r="1">${esc(ok)}</button>
        </div>
      </div>`;
    const prev = document.activeElement;
    const done = (r) => {
      document.removeEventListener("keydown", onKey, true);
      root.classList.add("out");
      setTimeout(() => root.remove(), 160);
      prev?.focus?.();
      resolve(r);
    };
    const onKey = (e) => {
      if (e.key === "Escape") { e.preventDefault(); e.stopPropagation(); done(false); }
      else if (e.key === "Tab") { // фокус не уходит за пределы окна
        const b = $$("button", root); const i = b.indexOf(document.activeElement);
        e.preventDefault(); b[(i + (e.shiftKey ? -1 : 1) + b.length) % b.length].focus();
      }
    };
    root.addEventListener("click", (e) => {
      const b = e.target.closest("button[data-r]");
      if (b) done(b.dataset.r === "1");
      else if (e.target.classList.contains("scrim")) done(false);
    });
    document.addEventListener("keydown", onKey, true);
    document.body.append(root);
    $('button[data-r="1"]', root).focus();
  });
}

/* ================= подключение ================= */

let META = null;
async function loadMeta(force = false) {
  if (META && !force) return META;
  const conn = $("#conn");
  try {
    META = await api("GET", "/api/meta");
    conn.className = "conn ok";
    $(".conn-text", conn).textContent = (META.keitaro_url || "").replace(/^https?:\/\//, "").replace(/\/$/, "") || "подключено";
  } catch (e) {
    conn.className = "conn bad";
    $(".conn-text", conn).textContent = e.message;
    throw e;
  }
  return META;
}

/* ================= экран: создаватор ================= */

async function renderCreate() {
  view.innerHTML = `
    <div class="page-head"><div class="grow">
      <div class="eyebrow">Создаватор</div>
      <h1>Новая кампания</h1>
      <p class="lead">Трафик из выбранных стран уходит на Google, остальной — на оффер. Домен, группа и источник подставляются автоматически.</p>
    </div></div>
    <div class="grid-create">
      <div class="stack">
        <form class="card" id="create-form" novalidate>
          <div class="card-body stack">
            <div class="field" id="fl-name">
              <label for="f-name"><span class="step">1</span>Название кампании</label>
              <input class="input" id="f-name" maxlength="255" placeholder="например, PE Flexacil test" autocomplete="off">
            </div>
            <div class="field" id="fl-geo">
              <label><span class="step">2</span>Гео для Google</label>
              <div class="chips" id="f-geo"><input placeholder="AU, MX, RO… — Enter или запятая"></div>
              <div class="hint">ISO-коды стран. Пользователей из этих стран поток 1 отправит на Google.</div>
            </div>
            <div class="field" id="fl-offer">
              <label><span class="step">3</span>Оффер</label>
              <div id="f-offer"></div>
              <div class="hint">Поиск по ID или названию в базе офферов Keitaro.</div>
            </div>
            <details class="more" id="f-more">
              <summary>${ICONS.chev}Домен, группа, источник<span class="sum" id="f-more-sum"></span></summary>
              <div class="row-3">
                <div class="field"><label>Домен</label><div id="f-domain"></div></div>
                <div class="field"><label>Группа</label><div id="f-group"></div></div>
                <div class="field"><label>Источник</label><div id="f-source"></div></div>
              </div>
            </details>
            <button class="btn primary lg block" id="f-submit" type="submit">${ICONS.plus} Создать кампанию</button>
          </div>
        </form>
        <div id="create-result"></div>
      </div>
      <div class="preview stack">
        <div class="card">
          <div class="card-head"><h2>Схема кампании</h2><span class="tag" style="margin-left:auto">предпросмотр</span></div>
          <div class="diagram" id="pv"></div>
        </div>
        <div class="card">
          <div class="card-head"><h2>Недавно созданные</h2></div>
          <ul class="list" id="recent"><li class="muted">…</li></ul>
        </div>
      </div>
    </div>`;

  const state = { geo: [], offer: null };
  const name = $("#f-name");
  const geoBox = $("#f-geo");
  const geoInput = $("input", geoBox);
  const offerBox = $("#f-offer");

  const renderGeo = () => {
    $$(".chip", geoBox).forEach((c) => c.remove());
    state.geo.forEach((code) => {
      const chip = document.createElement("span");
      chip.className = "chip";
      chip.innerHTML = `<span class="cc">${esc(code)}</span><small>${esc(countryName(code))}</small><button type="button" aria-label="Убрать">×</button>`;
      $("button", chip).onclick = (e) => { e.stopPropagation(); state.geo = state.geo.filter((c) => c !== code); renderGeo(); };
      geoBox.insertBefore(chip, geoInput);
    });
    geoBox.classList.remove("invalid");
    renderPreview();
  };
  const commitGeo = () => {
    const bad = [];
    geoInput.value.split(/[\s,;]+/).map((s) => s.trim().toUpperCase()).filter(Boolean).forEach((raw) => {
      const p = raw === "UK" ? "GB" : raw;
      if (!/^[A-Z]{2}$/.test(p) || countryName(p) === p) bad.push(raw);
      else if (!state.geo.includes(p)) state.geo.push(p);
    });
    geoInput.value = bad.join(", ");
    if (bad.length) { geoBox.classList.add("invalid"); toast(`Неизвестные коды: ${bad.join(", ")}`, "err"); }
    renderGeo();
  };
  geoBox.addEventListener("click", () => geoInput.focus());
  geoInput.addEventListener("keydown", (e) => {
    if (e.key === "Enter" || e.key === "," || e.key === " ") { e.preventDefault(); commitGeo(); }
    else if (e.key === "Backspace" && !geoInput.value && state.geo.length) { state.geo.pop(); renderGeo(); }
  });
  geoInput.addEventListener("blur", () => { if (geoInput.value.trim()) commitGeo(); });
  geoInput.addEventListener("paste", () => setTimeout(commitGeo, 0));

  const renderOffer = () => {
    if (state.offer) {
      offerBox.className = "";
      offerBox.innerHTML = pickedOffer(state.offer);
      $("button", offerBox).onclick = () => { state.offer = null; renderOffer(); $("input", offerBox)?.focus(); };
    } else {
      offerAutocomplete(offerBox, { onPick: (o) => { state.offer = o; renderOffer(); } });
    }
    renderPreview();
  };

  const selText = (id) => $(id)?.dataset.text || "—";
  function renderPreview() {
    const domain = META ? selText("#f-domain").replace(/^https?:\/\//, "").replace(/\/$/, "") : "домен";
    const hasGeo = state.geo.length > 0;
    $("#fl-name").classList.toggle("done", !!name.value.trim());
    $("#fl-geo").classList.toggle("done", hasGeo);
    $("#fl-offer").classList.toggle("done", !!state.offer);
    $("#pv").innerHTML = `
      <div class="node src">
        <div class="ico">${ICONS.users}</div>
        <div style="min-width:0"><div class="t">${esc(name.value.trim() || "Новая кампания")}</div><div class="d mono">${esc(domain)}/<span class="faint">alias</span></div></div>
      </div>
      <div class="connector"></div>
      <div class="branches">
        <span class="branch-label l">поток 1</span><span class="branch-label r">поток 2</span>
        <div class="node g ${hasGeo ? "" : "empty"}">
          <div class="ico">${ICONS.globe}</div>
          <div style="min-width:0">
            <div class="t">${hasGeo ? "Страна = " + esc(state.geo.join(", ")) : "Страны не выбраны"}</div>
            <div class="d">→ ${esc(META?.google_url || "https://google.com")}</div>
            <div style="display:flex;gap:4px;flex-wrap:wrap;margin-top:6px">${geoTags(state.geo.join(","))}</div>
          </div>
        </div>
        <div class="node o ${state.offer ? "" : "empty"}">
          <div class="ico">${ICONS.target}</div>
          <div style="min-width:0">
            <div class="t">Остальные → оффер</div>
            <div class="d">${state.offer ? `<span class="mono">${esc(state.offer.id)}</span> ${esc(state.offer.name)}` : "оффер не выбран"}</div>
            ${state.offer ? '<div style="margin-top:6px"><span class="tag green">100%</span></div>' : ""}
          </div>
        </div>
      </div>
      <div class="pv-meta">
        <div><small>Домен</small><b>${esc(domain)}</b></div>
        <div><small>Группа</small><b>${esc(selText("#f-group"))}</b></div>
        <div><small>Источник</small><b>${esc(selText("#f-source"))}</b></div>
      </div>`;
    if (META) $("#f-more-sum").textContent = `${domain} · ${selText("#f-group")} · ${selText("#f-source")}`;
  }
  name.addEventListener("input", renderPreview);

  renderOffer();
  renderGeo();

  try {
    const meta = await loadMeta();
    const fill = (id, items, def) => customSelect($(id), { items, value: def, onChange: renderPreview, placeholder: "нет вариантов" });
    fill("#f-domain", meta.domains, meta.defaults.domain_id);
    fill("#f-group", meta.groups, meta.defaults.group_id);
    fill("#f-source", meta.sources, meta.defaults.traffic_source_id);
    if (!meta.domains.length || !meta.groups.length || !meta.sources.length) $("#f-more").open = true;
    renderPreview();
  } catch (e) { toast(e.message, "err"); }
  loadRecent();

  $("#create-form").addEventListener("submit", async (e) => {
    e.preventDefault();
    if (geoInput.value.trim()) commitGeo();
    const errs = [];
    name.classList.toggle("invalid", !name.value.trim());
    if (!name.value.trim()) errs.push("название");
    if (!state.geo.length) { errs.push("гео"); geoBox.classList.add("invalid"); }
    if (!state.offer) errs.push("оффер");
    if (!META) errs.push("справочники Keitaro не загружены");
    if (errs.length) { toast(`Заполни: ${errs.join(", ")}`, "err"); return; }

    await busy($("#f-submit"), async () => {
      try {
        const c = await api("POST", "/api/campaigns", {
          name: name.value.trim(),
          geo: state.geo,
          offer_id: state.offer.id,
          domain_id: +$("#f-domain").dataset.value,
          group_id: +$("#f-group").dataset.value,
          traffic_source_id: +$("#f-source").dataset.value,
        });
        showCreated(c);
        toast(`Кампания «${c.name}» создана в Keitaro`, "ok");
        name.value = ""; state.geo = []; state.offer = null;
        renderGeo(); renderOffer(); loadRecent();
      } catch (err) { toast(err.message, "err"); }
    });
  });
}

function showCreated(c) {
  const box = $("#create-result");
  if (!box) return;
  box.innerHTML = `
    <div class="card success">
      <div class="banner">
        <div class="check">${ICONS.check}</div>
        <div style="flex:1;min-width:0"><h2>${esc(c.name)}</h2><div class="muted" style="font-size:12.5px">Кампания и 2 потока созданы в Keitaro</div></div>
        <span class="tag green">KT #${esc(c.keitaro_id)}</span>
      </div>
      <div class="card-body stack">
        ${c.url ? `<div class="urlbox"><span class="grow">${esc(c.url)}</span><button class="btn xs" id="cp-url">${ICONS.copy} Копировать</button></div>` : ""}
        <div style="display:flex;gap:8px;flex-wrap:wrap">
          <a class="btn blue" href="#/campaigns/${esc(c.keitaro_id)}">${ICONS.layers} Открыть в редакторе</a>
          ${c.keitaro_link ? `<a class="btn" href="${esc(c.keitaro_link)}" target="_blank" rel="noopener">${ICONS.ext} В Keitaro</a>` : ""}
        </div>
      </div>
    </div>`;
  $("#cp-url")?.addEventListener("click", () => copy(c.url));
  box.scrollIntoView({ behavior: "smooth", block: "nearest" });
}

async function loadRecent() {
  const ul = $("#recent");
  if (!ul) return;
  try {
    const rows = await api("GET", "/api/campaigns/recent");
    ul.innerHTML = rows.length ? rows.map((c) => `
      <li>
        <div class="avatar" style="background:${avatarColor(c.name)}">${initials(c.name)}</div>
        <div class="grow">
          <div class="nm">${esc(c.name)}</div>
          <div class="sub">${esc(c.geo || "")} · оффер ${esc(c.offer_id)} · ${esc(timeAgo(c.created_at))}</div>
        </div>
        <a class="btn xs" href="#/campaigns/${esc(c.keitaro_id)}">Редактор</a>
      </li>`).join("") : `<li class="muted" style="justify-content:center;padding:18px">Пока пусто — создай первую кампанию</li>`;
  } catch (e) { ul.innerHTML = `<li class="muted">${esc(e.message)}</li>`; }
}

/* ================= экран: список кампаний ================= */

async function renderCampaigns() {
  const mode = localGet("cfilter") || "all";
  view.innerHTML = `
    <div class="page-head"><div class="grow">
      <div class="eyebrow">Редактор</div>
      <h1>Кампании</h1>
      <p class="lead">Выбери кампанию — потоки и офферы подтянутся из Keitaro.</p>
    </div></div>
    <div class="toolbar">
      <div class="search-wrap">${ICONS.search}<input class="input" id="c-search" placeholder="Название, alias или ID"></div>
      <div class="filters" id="c-filter">
        <button data-f="all" class="${mode === "all" ? "on" : ""}">Все</button>
        <button data-f="mine" class="${mode === "mine" ? "on" : ""}">Созданные здесь</button>
        <button data-f="wrap" class="${mode === "wrap" ? "on" : ""}">В обёртке</button>
      </div>
      <div class="grow"></div>
      <form id="c-open" style="display:flex;gap:8px"><input class="input" id="c-id" style="width:150px" inputmode="numeric" placeholder="ID кампании"><button class="btn">Открыть</button></form>
    </div>
    <div class="card" id="c-table"><div class="skeleton" style="margin:16px"></div><div class="skeleton" style="margin:16px"></div></div>`;

  $("#c-open").addEventListener("submit", (e) => {
    e.preventDefault();
    const id = parseInt($("#c-id").value, 10);
    if (id > 0) location.hash = `#/campaigns/${id}`;
  });

  let rows = [];
  let filter = mode;
  const draw = () => {
    const q = $("#c-search").value.trim().toLowerCase();
    const shown = rows.filter((c) =>
      (filter === "all" || (filter === "mine" && c.created_by_wrapper) || (filter === "wrap" && c.in_wrapper)) &&
      (!q || String(c.keitaro_id).startsWith(q) || c.name.toLowerCase().includes(q) || (c.alias || "").toLowerCase().includes(q)));
    $("#c-table").innerHTML = shown.length ? `
      <table class="tbl">
        <thead><tr><th style="width:52px"></th><th>Кампания</th><th class="hide-sm">Alias</th><th class="hide-sm"></th><th style="width:40px"></th></tr></thead>
        <tbody>${shown.map((c) => `
          <tr class="link" data-id="${esc(c.keitaro_id)}">
            <td><div class="avatar" style="background:${avatarColor(c.name)}">${initials(c.name)}</div></td>
            <td><div style="font-weight:600">${esc(c.name)}</div><div class="mono muted">#${esc(c.keitaro_id)}</div></td>
            <td class="hide-sm"><span class="code-chip">${esc(c.alias || "—")}</span></td>
            <td class="num hide-sm">${c.created_by_wrapper ? '<span class="tag green">создана здесь</span>' : c.in_wrapper ? '<span class="tag blue">в обёртке</span>' : ""}${c.state === "disabled" ? ' <span class="tag">выключена</span>' : ""}</td>
            <td class="go">${ICONS.chev}</td>
          </tr>`).join("")}</tbody>
      </table>` : `<div class="empty"><div class="big">${rows.length ? "Ничего не найдено" : "В Keitaro нет кампаний"}</div>Попробуй другой запрос или фильтр</div>`;
  };
  $("#c-search").addEventListener("input", draw);
  $("#c-filter").addEventListener("click", (e) => {
    const b = e.target.closest("button[data-f]");
    if (!b) return;
    filter = b.dataset.f; localSet("cfilter", filter);
    $$("#c-filter button").forEach((x) => x.classList.toggle("on", x === b));
    draw();
  });
  $("#c-table").addEventListener("click", (e) => {
    const tr = e.target.closest("tr[data-id]");
    if (tr) location.hash = `#/campaigns/${tr.dataset.id}`;
  });

  try {
    loadMeta().catch(() => {});
    rows = await api("GET", "/api/campaigns");
    draw();
  } catch (e) {
    $("#c-table").innerHTML = `<div class="empty"><div class="big">Не удалось загрузить</div>${esc(e.message)}</div>`;
  }
}

/* ================= экран: редактор ================= */

const PERIODS = [["today", "Сегодня"], ["yesterday", "Вчера"], ["7d", "7 дней"], ["30d", "30 дней"]];
const TREND_DAYS = { today: 7, yesterday: 7, "7d": 7, "30d": 30 };

async function renderEditor(ktId) {
  const ed = { campaign: null, stats: null, trends: null, period: localGet("period") || "today", seq: 0, flash: null };
  view.innerHTML = `<div class="skeleton" style="height:150px"></div><div class="skeleton" style="height:90px"></div><div class="skeleton" style="height:260px"></div>`;

  try {
    ed.campaign = await api("GET", `/api/campaigns/${ktId}`);
  } catch (e) {
    view.innerHTML = `<div class="card empty"><div class="big">${esc(e.message)}</div><p><a class="btn" href="#/campaigns">К списку кампаний</a></p></div>`;
    return;
  }
  loadMeta().catch(() => {});

  const offerStreams = () => ed.campaign.streams.filter((s) => s.has_offers);
  const trendDays = () => TREND_DAYS[ed.period] || 7;

  const replaceStream = (s, flashOfferId = null) => {
    ed.campaign.streams = ed.campaign.streams.map((x) => (x.id === s.id ? s : x));
    ed.flash = flashOfferId;
    drawStream(s);
    ed.flash = null;
    drawHeadState();
    if (drawer.isOpen()) drawer.refresh();
  };

  async function loadStats() {
    const my = ++ed.seq;
    const [st, tr] = await Promise.allSettled([
      api("GET", `/api/campaigns/${ktId}/stats?period=${ed.period}`),
      api("GET", `/api/campaigns/${ktId}/trends?days=${trendDays()}`),
    ]);
    if (my !== ed.seq) return;
    ed.stats = st.status === "fulfilled" ? st.value : null;
    ed.trends = tr.status === "fulfilled" ? tr.value : null;
    if (st.status === "rejected") toast(`Статистика: ${st.reason.message}`, "err");
    drawKpis();
    ed.campaign.streams.forEach(drawStream);
  }

  function drawHeadState() {
    const dirty = ed.campaign.streams.filter((s) => s.is_dirty).length;
    $("#dirty-note").innerHTML = dirty
      ? `<span class="tag warn"><span class="pulse"></span>не опубликовано: ${dirty}</span>`
      : `<span class="tag green">синхронно с Keitaro</span>`;
    $("#synced").textContent = `обновлено ${timeAgo(ed.campaign.synced_at)}`;
  }

  function drawKpis() {
    const t = ed.stats?.total;
    const tr = ed.trends ? { ...ed.trends.total, days: ed.trends.days } : null;
    const k = (label, v, color, series) => `
      <div class="card kpi">
        <div class="k"><i style="background:${color}"></i>${label}</div>
        <div class="v">${v}</div>
        ${series ? sparkline(series, { cls: "spark", color }) : ""}
      </div>`;
    $("#kpis").innerHTML =
      k("Клики", t ? fmtInt(t.clicks) : "—", "var(--s2)", tr) +
      k("Конверсии", t ? fmtInt(t.conversions) : "—", "var(--s1)", tr ? { clicks: tr.conversions, conversions: [], days: tr.days } : null) +
      k("CR", t ? fmtPct(t.conversions, t.clicks) : "—", "var(--s3)", null) +
      k("Доход", t ? fmtMoney(t.revenue) : "—", "var(--s4)", null);
  }

  function head() {
    const c = ed.campaign;
    view.innerHTML = `
      <div class="card hero">
        <div style="min-width:0">
          <div class="crumbs"><a href="#/campaigns">Кампании</a>${ICONS.chev}<span>KT #${esc(c.keitaro_id)}</span></div>
          <h1>${esc(c.name)}</h1>
          <div class="meta-row">
            ${c.alias ? `<span class="code-chip">/${esc(c.alias)}</span>` : ""}
            ${geoTags(c.geo)}
            <span id="dirty-note"></span>
            <span class="muted" style="font-size:12.5px" id="synced"></span>
          </div>
          ${c.url ? `<div class="urlbox"><span class="grow">${esc(c.url)}</span><button class="btn xs" id="cp-url">${ICONS.copy}</button></div>` : ""}
        </div>
        <div class="hero-actions">
          <div class="seg" id="period">${PERIODS.map(([v, l]) => `<button data-p="${v}" class="${v === ed.period ? "on" : ""}">${l}</button>`).join("")}</div>
          <div class="row">
            <button class="btn" id="fetch">${ICONS.download} Fetch streams from KT</button>
            <button class="btn" id="all-offers">${ICONS.layers} Все офферы</button>
            ${c.keitaro_link ? `<a class="btn ghost" href="${esc(c.keitaro_link)}" target="_blank" rel="noopener">${ICONS.ext} View in KT</a>` : ""}
          </div>
        </div>
      </div>
      <div class="kpis" id="kpis"></div>
      <div class="section-title"><h2>Потоки · ${c.streams.length}</h2><div class="line"></div></div>
      <div id="streams">${c.streams.map((s) => `<div id="st-${s.id}"></div>`).join("") || '<div class="card empty"><div class="big">В кампании нет потоков</div>Создай их в Keitaro и нажми Fetch</div>'}</div>`;

    $("#cp-url")?.addEventListener("click", () => copy(c.url));
    $("#all-offers").addEventListener("click", () => drawer.open());
    $("#period").addEventListener("click", (e) => {
      const b = e.target.closest("button[data-p]");
      if (!b || b.dataset.p === ed.period) return;
      ed.period = b.dataset.p; localSet("period", ed.period);
      $$("#period button").forEach((x) => x.classList.toggle("on", x === b));
      loadStats();
    });
    $("#fetch").addEventListener("click", async (e) => {
      const dirty = ed.campaign.streams.filter((s) => s.is_dirty).length;
      if (dirty && !(await confirmDialog({
        title: "Перезаписать черновик?",
        text: `В ${dirty} потоке(ах) есть неопубликованные изменения. Fetch заменит их тем, что сейчас в Keitaro.`,
        ok: "Загрузить из Keitaro",
      }))) return;
      await busy(e.currentTarget, async () => {
        try {
          ed.campaign = await api("POST", `/api/campaigns/${ktId}/fetch`);
          head(); drawKpis(); ed.campaign.streams.forEach(drawStream); drawHeadState();
          toast("Потоки загружены из Keitaro", "ok");
          loadStats();
        } catch (err) { toast(err.message, "err"); }
      });
    });
  }

  function statCells(s, o) {
    const key = `${s.keitaro_id}:${o.offer_id}`;
    const v = ed.stats?.by_offer?.[key];
    const z = ed.stats ? "0" : "—";
    const nums = v
      ? `<td class="num hide-sm">${fmtInt(v.clicks)}</td><td class="num hide-sm">${fmtInt(v.conversions)}</td><td class="num hide-sm">${fmtPct(v.conversions, v.clicks)}</td><td class="num hide-sm">${fmtMoney(v.revenue)}</td>`
      : `<td class="num hide-sm faint">${z}</td><td class="num hide-sm faint">${z}</td><td class="num hide-sm faint">—</td><td class="num hide-sm faint">${ed.stats ? fmtMoney(0) : "—"}</td>`;
    const series = ed.trends ? { ...(ed.trends.by_offer[key] || zeroSeries(ed.trends.days)), days: ed.trends.days } : null;
    return nums + `<td class="hide-sm">${series ? sparkline(series, { color: o.status === "active" ? "var(--s2)" : "var(--faint)" }) : '<span class="trend-empty">—</span>'}</td>`;
  }

  function streamMeta(s) {
    const sstat = ed.stats?.by_stream?.[String(s.keitaro_id)];
    return `
      <span class="mono">stream_id ${esc(s.keitaro_id)}</span><span>·</span>
      <span>${ICONS.filter} ${s.filters_summary ? `<span class="code-chip">${esc(s.filters_summary)}</span>` : "без фильтров"}</span><span>·</span>
      <span>клики за период: <b class="tnum">${sstat ? fmtInt(sstat.clicks) : "—"}</b></span>`;
  }

  function drawStream(s) {
    const box = $(`#st-${s.id}`);
    if (!box) return;

    if (!s.has_offers) {
      const series = ed.trends ? { ...(ed.trends.by_stream[String(s.keitaro_id)] || zeroSeries(ed.trends.days)), days: ed.trends.days } : null;
      box.innerHTML = `
        <div class="card stream">
          <div class="card-head">
            <div class="stream-pos">${esc(s.position)}</div>
            <div class="stream-title">
              <div class="r1"><h2>${esc(s.name)}</h2><span class="tag">${esc(s.type)}</span></div>
              <div class="r2">${streamMeta(s)}</div>
            </div>
            ${series ? `<div class="hide-sm">${sparkline(series, { color: "var(--faint)" })}</div>` : ""}
          </div>
          <div class="plain">${ICONS.arrowR}<span>Поток без офферов — содержимое не разбирается, правится в Keitaro.</span></div>
        </div>`;
      return;
    }

    const active = s.offers.filter((o) => o.status === "active");
    const removedCount = s.offers.length - active.length;
    const colorOf = new Map(active.map((o, i) => [o.id, segColor(i)]));
    const totalOk = s.share_total === 100;

    box.innerHTML = `
      <div class="card stream ${s.is_dirty ? "dirty" : ""}">
        <div class="card-head">
          <div class="stream-pos">${esc(s.position)}</div>
          <div class="stream-title">
            <div class="r1">
              <h2>${esc(s.name)}</h2>
              <span class="tag">${esc(s.type)}</span>
              ${s.is_dirty ? '<span class="tag warn"><span class="pulse"></span>не опубликовано</span>' : '<span class="tag green">синхронно</span>'}
            </div>
            <div class="r2">${streamMeta(s)}</div>
          </div>
          <div class="stream-actions">
            <button class="btn ghost sm" data-act="cancel" ${s.is_dirty ? "" : "disabled"}>${ICONS.x} Cancel</button>
            <button class="btn blue sm" data-act="push" ${s.is_dirty && totalOk && active.length ? "" : "disabled"}>${ICONS.upload} Push to KT</button>
          </div>
        </div>
        <div class="mix">
          ${donut(active.map((o) => ({ value: o.share, color: colorOf.get(o.id) })), s.share_total, `${active.length} офф.`)}
          <div class="legend">
            ${active.map((o) => `<div class="li"><i style="background:${colorOf.get(o.id)}"></i><span title="${esc(o.offer_name)}">${esc(o.offer_name || "Оффер " + o.offer_id)}</span><b>${o.share}%</b></div>`).join("") || '<div class="muted">Нет активных офферов</div>'}
            <div class="bar">${active.map((o) => `<span style="width:${o.share}%;background:${colorOf.get(o.id)}"></span>`).join("")}</div>
            ${removedCount ? `<div class="muted" style="font-size:12px">в архиве: ${removedCount}</div>` : ""}
          </div>
        </div>
        <div style="overflow-x:auto">
        <table class="otbl">
          <thead><tr><th>Оффер</th><th>Доля</th><th class="num hide-sm">Клики</th><th class="num hide-sm">Конв.</th><th class="num hide-sm">CR</th><th class="num hide-sm">Доход</th><th class="hide-sm">Тренд · ${trendDays()} дн.</th><th></th></tr></thead>
          <tbody>${s.offers.map((o) => {
            const removed = o.status !== "active";
            const changed = o.is_published && o.published_share !== o.share && !removed;
            return `
            <tr class="${removed ? "removed" : ""} ${ed.flash === o.offer_id ? "flash" : ""}" data-oid="${o.id}">
              <td style="min-width:240px"><div class="offer">
                <span class="swatch" style="background:${colorOf.get(o.id) || "var(--line)"}"></span>
                <div style="min-width:0">
                  <div class="oname" title="${esc(o.offer_name)}">${esc(o.offer_name || "Оффер")}</div>
                  <div class="osub">
                    <span class="mono">${esc(o.offer_id)}</span>
                    ${geoTags(o.offer_country)}
                    ${!o.is_published ? '<span class="tag warn">new</span>' : ""}
                    ${removed ? '<span class="tag">removed</span>' : ""}
                    ${o.preview_url ? `<a href="${esc(o.preview_url)}" target="_blank" rel="noopener" title="Открыть оффер">${ICONS.eye} preview</a>` : ""}
                  </div>
                </div>
              </div></td>
              <td style="white-space:nowrap"><div class="share">
                <button class="share-val" data-act="share" ${removed ? "disabled" : ""} title="Задать долю вручную — она закрепится">${o.share}%</button>
                <button class="pin ${o.pinned ? "on" : ""}" data-act="pin" ${removed ? "disabled" : ""} title="${o.pinned ? "Открепить долю" : "Закрепить долю"}">${ICONS.pin}</button>
                ${changed ? `<span class="was">было ${o.published_share}%</span>` : ""}
              </div></td>
              ${statCells(s, o)}
              <td class="num">${removed
                ? `<button class="btn xs" data-act="restore">${ICONS.undo} Bring back</button>`
                : `<button class="btn danger-ghost xs" data-act="remove">${ICONS.trash} Remove</button>`}</td>
            </tr>`;
          }).join("")}</tbody>
        </table>
        </div>
        <div class="addrow"><div class="ac-host"></div><button class="btn sm" data-act="add" disabled>${ICONS.plus} Add</button></div>
      </div>`;

    let picked = null;
    const addBtn = $('[data-act="add"]', box);
    const host = $(".ac-host", box);
    const mountAc = () => offerAutocomplete(host, {
      placeholder: "Добавить оффер: ID или название",
      exclude: () => new Set(s.offers.filter((o) => o.status === "active").map((o) => o.offer_id)),
      onPick: (o) => {
        picked = o;
        host.className = "ac-host";
        host.innerHTML = pickedOffer(o);
        $("button", host).onclick = () => { picked = null; addBtn.disabled = true; mountAc().focus(); };
        addBtn.disabled = false;
        addBtn.focus();
      },
    });
    mountAc();
    addBtn.addEventListener("click", () => busy(addBtn, async () => {
      if (!picked) return;
      try { replaceStream(await api("POST", `/api/streams/${s.id}/offers`, { offer_id: picked.id }), picked.id); }
      catch (e) { toast(e.message, "err"); }
    }));

    $(".stream-actions", box).addEventListener("click", async (e) => {
      const b = e.target.closest("button[data-act]");
      if (!b) return;
      const act = b.dataset.act;
      await busy(b, async () => {
        try {
          replaceStream(await api("POST", `/api/streams/${s.id}/${act}`));
          toast(act === "push" ? "Изменения опубликованы в Keitaro" : "Изменения отменены", "ok");
          if (act === "push") loadStats();
        } catch (err) { toast(err.message, "err"); }
      });
    });

    $("tbody", box).addEventListener("click", async (e) => {
      const b = e.target.closest("button[data-act]");
      if (!b) return;
      const id = b.closest("tr").dataset.oid;
      const o = s.offers.find((x) => String(x.id) === id);
      const act = b.dataset.act;
      if (act === "share") return editShare(b, o);
      await busy(b, async () => {
        try {
          if (act === "remove") replaceStream(await api("POST", `/api/stream-offers/${id}/remove`));
          else if (act === "restore") replaceStream(await api("POST", `/api/stream-offers/${id}/restore`), o.offer_id);
          else if (act === "pin") replaceStream(await api("PUT", `/api/stream-offers/${id}/pin`, { pinned: !o.pinned }));
        } catch (err) { toast(err.message, "err"); }
      });
    });

    function editShare(btn, o) {
      const input = document.createElement("input");
      input.className = "share-input";
      input.type = "number"; input.min = "0"; input.max = "100"; input.value = o.share;
      btn.replaceWith(input);
      input.focus(); input.select();
      let done = false;
      const finish = async (save) => {
        if (done) return; done = true;
        const v = parseInt(input.value, 10);
        if (!save || Number.isNaN(v) || v === o.share) { drawStream(s); return; }
        if (v < 0 || v > 100) { toast("Доля должна быть от 0 до 100", "err"); drawStream(s); return; }
        try { replaceStream(await api("PUT", `/api/stream-offers/${o.id}/share`, { share: v })); }
        catch (err) { toast(err.message, "err"); drawStream(s); }
      };
      input.addEventListener("keydown", (e) => { if (e.key === "Enter") finish(true); else if (e.key === "Escape") finish(false); });
      input.addEventListener("blur", () => finish(true));
    }
  }

  /* ---- панель «Все офферы» ---- */
  const drawer = (() => {
    const root = $("#drawer-root");
    let offers = null;
    const isOpen = () => !!root.firstChild;
    const onKey = (e) => { if (e.key === "Escape") close(); };
    function close() { root.innerHTML = ""; document.removeEventListener("keydown", onKey); }

    const usage = (offerId) => offerStreams()
      .map((s) => ({ s, o: s.offers.find((x) => x.offer_id === offerId) }))
      .filter((x) => x.o);

    function list() {
      const body = $(".drawer-body", root);
      if (!body) return;
      if (!offers) { body.innerHTML = `<div class="skeleton" style="height:80px"></div><div class="skeleton" style="height:80px"></div>`; return; }
      const q = $("#d-search").value.trim().toLowerCase();
      const shown = offers.filter((o) => !q || String(o.id).startsWith(q) || o.name.toLowerCase().includes(q));
      $("#d-count").textContent = `${shown.length} из ${offers.length}`;
      body.innerHTML = shown.length ? shown.map((o) => {
        const used = usage(o.id);
        const chips = used.map(({ s, o: b }) => `<span class="tag ${b.status === "active" ? "green" : ""}">${esc(s.name)} · ${b.status === "active" ? b.share + "%" : "removed"}</span>`).join("");
        const addTo = offerStreams().filter((s) => !used.some((u) => u.s.id === s.id && u.o.status === "active"));
        return `
          <div class="ocard">
            <div class="top"><span class="code-chip">${esc(o.id)}</span><div class="nm">${esc(o.name)}</div></div>
            <div class="info">${geoTags(o.country)}${o.group ? `<span class="tag">${esc(o.group)}</span>` : ""}${chips}</div>
            <div class="acts">
              ${addTo.map((s) => `<button class="btn xs" data-add="${o.id}" data-stream="${s.id}">${ICONS.plus} в «${esc(s.name)}»</button>`).join("")}
              ${o.preview_url ? `<a class="btn ghost xs" href="${esc(o.preview_url)}" target="_blank" rel="noopener">${ICONS.eye} preview</a>` : ""}
            </div>
          </div>`;
      }).join("") : `<div class="empty"><div class="big">Ничего не найдено</div></div>`;
    }

    async function open() {
      root.innerHTML = `
        <div class="scrim"></div>
        <aside class="drawer" role="dialog" aria-label="Все офферы">
          <div class="drawer-head">
            <div class="row"><h2 style="font-size:17px">Все офферы Keitaro</h2><span class="tag" id="d-count"></span><span style="flex:1"></span><button class="iconbtn" id="d-close">${ICONS.x}</button></div>
            <div class="search-wrap" style="max-width:none;margin-top:12px">${ICONS.search}<input class="input" id="d-search" placeholder="ID или название"></div>
          </div>
          <div class="drawer-body"></div>
        </aside>`;
      $(".scrim", root).onclick = close;
      $("#d-close").onclick = close;
      document.addEventListener("keydown", onKey);
      $("#d-search").addEventListener("input", list);
      $(".drawer-body", root).addEventListener("click", async (e) => {
        const b = e.target.closest("button[data-add]");
        if (!b) return;
        await busy(b, async () => {
          try {
            replaceStream(await api("POST", `/api/streams/${b.dataset.stream}/offers`, { offer_id: +b.dataset.add }), +b.dataset.add);
            toast("Оффер добавлен — не забудь Push to KT", "ok");
          } catch (err) { toast(err.message, "err"); }
        });
      });
      list();
      $("#d-search").focus();
      try { offers = await api("GET", "/api/offers?limit=500"); }
      catch (err) { offers = []; toast(err.message, "err"); }
      if (isOpen()) list();
    }
    return { open, close, isOpen, refresh: list };
  })();

  head();
  drawKpis();
  ed.campaign.streams.forEach(drawStream);
  drawHeadState();
  loadStats();
}

/* ================= роутер ================= */

function route() {
  $("#drawer-root").innerHTML = "";
  const hash = location.hash || "#/create";
  const m = hash.match(/^#\/campaigns\/(\d+)/);
  const tab = hash.startsWith("#/campaigns") ? "campaigns" : "create";
  $$(".nav a").forEach((a) => a.classList.toggle("active", a.dataset.tab === tab));
  window.scrollTo(0, 0);
  if (m) return renderEditor(+m[1]);
  if (tab === "campaigns") return renderCampaigns();
  return renderCreate();
}

window.addEventListener("hashchange", route);
route();
