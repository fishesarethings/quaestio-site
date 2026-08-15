/* ============================= Quaestio admin UI ============================= */
const $ = (sel) => document.querySelector(sel);
const $$ = (sel) => [...document.querySelectorAll(sel)];

let me = null;
let guilds = [];
let activeGuild = null;
let currentTab = "ai";

const ESCAPED = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

/* ---------- helpers ---------- */
async function api(path, opts = {}) {
  const res = await fetch(path, {
    headers: { "Content-Type": "application/json" },
    credentials: "same-origin",
    ...opts,
  });
  if (res.status === 401) { show("login"); return null; }
  const data = await res.json().catch(() => null);
  if (!res.ok) {
    const msg = data && data.error ? data.error : `Request failed (${res.status})`;
    toast(msg, true);
    throw new Error(msg);
  }
  return data;
}

function toast(msg, isErr = false) {
  const t = $("#toast");
  t.textContent = msg;
  t.style.color = isErr ? "var(--danger)" : "var(--text)";
  t.classList.add("show");
  clearTimeout(t._timer);
  t._timer = setTimeout(() => t.classList.remove("show"), 3200);
}

function show(view) {
  ["login-view", "picker-view", "settings-view", "host-view"].forEach((id) => $("#" + id).classList.toggle("hidden", id !== view));
  $$("#nav-links a").forEach((a) => a.classList.toggle("active", a.dataset.view === view));
}

/* ---------- login ---------- */
function renderUser() {
  const box = $("#nav-user");
  if (!me) {
    box.innerHTML = '<a class="btn btn-primary" href="/auth/login">Sign in</a>';
    return;
  }
  box.innerHTML = `
    ${me.avatar ? `<img src="${ESCAPED(me.avatar)}" alt="">` : ""}
    <span class="name">${ESCAPED(me.username)}</span>
    <a class="btn btn-ghost" href="/auth/logout">Sign out</a>`;
}

function renderNav() {
  $("#nav-links").innerHTML = `
    ${me && guilds.length ? '<a data-view="picker-view" class="active">Servers</a>' : ""}
    ${me ? '<a data-view="host-view">Host</a>' : ""}`;
  $$("#nav-links a").forEach((a) =>
    a.addEventListener("click", () => { if (a.dataset.view === "picker-view") renderPicker(); show(a.dataset.view); })
  );
}

/* ---------- picker ---------- */
async function renderPicker() {
  guilds = (await api("/api/guilds")) || [];
  renderNav();
  const list = $("#guild-list");
  if (!guilds.length) {
    list.innerHTML = '<div class="card"><p class="muted">No servers to manage yet. Invite the bot and make sure you have an admin role (or own the server).</p></div>';
    return;
  }
  list.innerHTML = guilds.map((g) => {
    const icon = g.icon ? `<img class="guild-icon" src="${ESCAPED(g.icon)}" alt="">`
      : `<div class="guild-icon placeholder">${ESCAPED((g.name || "?").slice(0, 1).toUpperCase())}</div>`;
    return `<button class="guild-card" data-id="${ESCAPED(g.id)}">${icon}<span>${ESCAPED(g.name)}</span></button>`;
  }).join("");
  $$(".guild-card").forEach((el) =>
    el.addEventListener("click", () => openGuild(el.dataset.id))
  );
}

/* ---------- settings view ---------- */
async function openGuild(id) {
  activeGuild = guilds.find((g) => g.id === id) || { id, name: "Server" };
  $("#settings-guild-name").textContent = activeGuild.name;
  currentTab = "ai";
  $$(".tab").forEach((t) => t.classList.toggle("active", t.dataset.tab === "ai"));
  $$(".tab-panel").forEach((p) => p.classList.toggle("active", p.id === "panel-ai"));
  await loadSettings(id);
  show("settings-view");
}

async function loadSettings(id) {
  const s = (await api(`/api/guilds/${id}/settings`)) || {};
  const set = (el, v) => { if ($(el)) $(el).value = v ?? ""; };
  set("#ai_endpoint", s.ai_endpoint);
  set("#ai_memory", s.ai_memory);
  set("#ai_quota", s.ai_quota);
  set("#ai_instructions", s.ai_instructions);
  set("#welcome_channel", s.welcome_channel);
  set("#welcome_message", s.welcome_message);
  set("#levelrole", s.levelrole);
  set("#warnlimit", s.warnlimit);
  $("#ai_enabled").checked = s.ai_enabled !== false;
  $("#welcome_enabled").checked = s.welcome_enabled === true;

  await populateModels("#ai_model", id, "ai_model", s.ai_model);
  renderWelcomePreview();
}

async function populateModels(sel, guildId, field, selected) {
  const el = $(sel);
  el.innerHTML = '<option value="">Loading models…</option>';
  const status = $(sel + "-status") || $("#model-scan-status");
  if (status) status.textContent = "";
  try {
    const data = await api(`/api/guilds/${guildId}/models`);
    const models = data && data.models ? data.models : [];
    if (!models.length) {
      el.innerHTML = '<option value="">(no models found — check the AI host)</option>';
      return;
    }
    el.innerHTML = models.map((m) => `<option value="${ESCAPED(m)}" ${m === selected ? "selected" : ""}>${ESCAPED(m)}</option>`).join("");
    if (selected && !models.includes(selected)) el.innerHTML += `<option value="${ESCAPED(selected)}" selected>${ESCAPED(selected)}</option>`;
  } catch {
    el.innerHTML = `<option value="${ESCAPED(selected || "")}" ${selected ? "selected" : ""}>${ESCAPED(selected || "(unreachable — save endpoint first)")}</option>`;
  }
}

/* ---------- save helpers ---------- */
async function saveSettings(id, body, statusEl) {
  await api(`/api/guilds/${id}/settings`, { method: "POST", body: JSON.stringify(body) });
  if (statusEl) {
    statusEl.textContent = "Saved ✓";
    setTimeout(() => (statusEl.textContent = ""), 2200);
  }
  toast("Saved");
}

function readSettings() {
  return {
    ai_enabled: $("#ai_enabled").checked,
    ai_endpoint: $("#ai_endpoint").value.trim(),
    ai_model: $("#ai_model").value,
    ai_memory: $("#ai_memory").value,
    ai_quota: $("#ai_quota").value,
    ai_instructions: $("#ai_instructions").value,
    welcome_enabled: $("#welcome_enabled").checked,
    welcome_channel: $("#welcome_channel").value.trim(),
    welcome_message: $("#welcome_message").value,
    levelrole: $("#levelrole").value.trim(),
    warnlimit: $("#warnlimit").value,
  };
}

function renderWelcomePreview() {
  const msg = $("#welcome_message").value;
  const preview = $("#welcome-preview");
  if (!msg) { preview.innerHTML = '<span class="muted">No message yet.</span>'; return; }
  const server = activeGuild ? activeGuild.name : "My Server";
  const rendered = msg
    .replace(/\{member\}/g, "<b>NewMember</b>")
    .replace(/\{guild\}/g, `<b>${ESCAPED(server)}</b>`);
  preview.innerHTML = ESCAPED(rendered).replace(/&lt;b&gt;/g, "<b>").replace(/&lt;\/b&gt;/g, "</b>");
}

/* ---------- host view ---------- */
async function renderHost() {
  const s = (await api("/api/host/settings")) || {};
  $("#host_endpoint").value = s.ai_endpoint || "";
  $("#host_memory").value = s.ai_memory ?? "";
  $("#host_quota").value = s.ai_quota ?? "";
  const stats = (await api("/api/host/stats")) || {};
  $("#host-stats").innerHTML = [
    { n: fmtBytes(stats.mem_total), l: "RAM" },
    { n: `${stats.mem_pct ?? "—"}%`, l: "In use" },
    { n: fmtBytes(stats.disk_total), l: "Disk" },
    { n: stats.cpu_pct ?? "—", l: "CPU %" },
    { n: stats.model_count ?? "—", l: "Models" },
    { n: stats.ollama ? "Online" : "Offline", l: "Ollama" },
  ].map((c) => `<div class="stat-chip"><span class="num">${c.n}</span><span class="lbl">${c.l}</span></div>`).join("");

  const el = $("#host_model");
  el.innerHTML = '<option value="">(none set)</option>';
  if (stats.models && stats.models.length) {
    const cur = s.ai_model || "";
    el.innerHTML += stats.models.map((m) => `<option value="${ESCAPED(m)}" ${m === cur ? "selected" : ""}>${ESCAPED(m)}</option>`).join("");
    if (cur && !stats.models.includes(cur)) el.innerHTML += `<option value="${ESCAPED(cur)}" selected>${ESCAPED(cur)}</option>`;
  }
}

function fmtBytes(n) {
  if (!n && n !== 0) return "—";
  const u = ["B", "KB", "MB", "GB", "TB"];
  let i = 0;
  while (n >= 1024 && i < u.length - 1) { n /= 1024; i++; }
  return `${n.toFixed(n >= 100 ? 0 : 1)}${u[i]}`;
}

/* ---------- events ---------- */
function wireEvents() {
  $("#back-btn").addEventListener("click", (e) => { e.preventDefault(); renderPicker(); show("picker-view"); });

  $$(".tab").forEach((t) =>
    t.addEventListener("click", () => {
      currentTab = t.dataset.tab;
      $$(".tab").forEach((x) => x.classList.toggle("active", x === t));
      $$(".tab-panel").forEach((p) => p.classList.toggle("active", p.id === "panel-" + t.dataset.tab));
    })
  );

  $("#refresh-models").addEventListener("click", () => populateModels("#ai_model", activeGuild.id, "ai_model", $("#ai_model").value));
  $("#welcome_message").addEventListener("input", renderWelcomePreview);

  $("#save-ai").addEventListener("click", async () => {
    try { await saveSettings(activeGuild.id, readSettings(), $("#save-status-ai")); }
    catch { /* toast already shown */ }
  });
  $("#save-welcome").addEventListener("click", async () => {
    try { await saveSettings(activeGuild.id, readSettings(), $("#save-status-welcome")); }
    catch { /* toast already shown */ }
  });
  $("#save-levels").addEventListener("click", async () => {
    try { await saveSettings(activeGuild.id, readSettings(), $("#save-status-levels")); }
    catch { /* toast already shown */ }
  });
  $("#save-moderation").addEventListener("click", async () => {
    try { await saveSettings(activeGuild.id, readSettings(), $("#save-status-moderation")); }
    catch { /* toast already shown */ }
  });

  $("#save-host").addEventListener("click", async () => {
    try {
      await api("/api/host/settings", {
        method: "POST",
        body: JSON.stringify({
          ai_endpoint: $("#host_endpoint").value.trim(),
          ai_model: $("#host_model").value,
          ai_memory: $("#host_memory").value,
          ai_quota: $("#host_quota").value,
        }),
      });
      toast("Host defaults saved");
      const el = $("#save-status-host");
      el.textContent = "Saved ✓";
      setTimeout(() => (el.textContent = ""), 2200);
    } catch { /* toast already shown */ }
  });
}

/* ---------- init ---------- */
async function init() {
  wireEvents();
  try {
    me = await api("/api/me");
  } catch { me = null; }
  if (!me) { renderUser(); show("login-view"); return; }
  renderUser();
  await renderPicker();
  show("picker-view");
}

init();
