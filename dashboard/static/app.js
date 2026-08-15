/* ============================= Quaestio admin UI ============================= */
const $ = (sel) => document.querySelector(sel);
const $$ = (sel) => [...document.querySelectorAll(sel)];

let me = null;
let guilds = [];
let activeGuild = null;
let currentTab = "ai";
let modelState = null;

const TOKEN_KEY = "qa_token";
const getToken = () => sessionStorage.getItem(TOKEN_KEY) || "";

const ESCAPED = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const OFF = (v) => v === "0" || String(v).toLowerCase() === "false" || v === false;
const ON = (v) => !OFF(v); // defaults on when empty

/* ---------- helpers ---------- */
async function api(path, opts = {}) {
  const res = await fetch(path, {
    headers: {
      "Content-Type": "application/json",
      ...(getToken() ? { Authorization: `Bearer ${getToken()}` } : {}),
    },
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

function grabTokenFromHash() {
  const m = location.hash.match(/token=([^&]+)/);
  if (m) {
    sessionStorage.setItem(TOKEN_KEY, m[1]);
    history.replaceState(null, "", location.pathname + location.search);
  }
}

function handleLogout(e) {
  e.preventDefault();
  const t = getToken();
  sessionStorage.removeItem(TOKEN_KEY);
  if (t) fetch(`/auth/logout?token=${encodeURIComponent(t)}`).catch(() => {});
  location.href = "/";
}

function showLoginError() {
  const p = new URLSearchParams(location.search);
  if (p.get("error") === "login") $("#login-error").textContent = "Login failed — please try again.";
  else if (p.get("error") === "needadmin") $("#login-error").textContent = "You need to be in at least one Discord server to use the panel.";
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
  const u = me.user || {};
  const avatar = u.avatar
    ? `https://cdn.discordapp.com/avatars/${u.id}/${u.avatar}.png`
    : "";
  const initial = (u.username || "?").slice(0, 1).toUpperCase();
  box.innerHTML = `
    <div class="avatar">
      ${avatar ? `<img src="${ESCAPED(avatar)}" alt="">` : `<span>${ESCAPED(initial)}</span>`}
    </div>
    <span class="name">${ESCAPED(u.username || "Guest")}</span>
    <button class="btn btn-ghost" id="logout-btn">Sign out</button>`;
  const lb = $("#logout-btn");
  if (lb) lb.addEventListener("click", handleLogout);
}

function renderNav() {
  $("#nav-links").innerHTML = `
    ${me && guilds.length ? '<a data-view="picker-view" class="active">Servers</a>' : ""}
    ${me && me.is_host_admin ? '<a data-view="host-view">Host</a>' : ""}`;
  $$("#nav-links a").forEach((a) =>
    a.addEventListener("click", () => { if (a.dataset.view === "picker-view") renderPicker(); show(a.dataset.view); })
  );
}

/* ---------- picker ---------- */
function guildIcon(g) {
  return g.icon
    ? `<img class="guild-icon" src="https://cdn.discordapp.com/icons/${g.id}/${g.icon}.png" alt="">`
    : `<div class="guild-icon placeholder">${ESCAPED((g.name || "?").slice(0, 1).toUpperCase())}</div>`;
}

function manageCard(g) {
  return `<button class="guild-card" data-id="${ESCAPED(g.id)}">
    ${guildIcon(g)}
    <div class="guild-meta"><span class="guild-name">${ESCAPED(g.name)}</span><span class="guild-sub">Configure AI, welcomes &amp; more</span></div>
    <span class="badge-tag ok">Managed</span>
  </button>`;
}

function inviteCard(g) {
  return `<button class="guild-card invite" data-invite="${ESCAPED(g.invite_url)}">
    ${guildIcon(g)}
    <div class="guild-meta"><span class="guild-name">${ESCAPED(g.name)}</span><span class="guild-sub">Quaestio isn't here yet</span></div>
    <span class="badge-tag accent">+ Invite</span>
  </button>`;
}

function lockedCard(g) {
  return `<button class="guild-card locked" disabled>
    ${guildIcon(g)}
    <div class="guild-meta"><span class="guild-name">${ESCAPED(g.name)}</span><span class="guild-sub">Need admin permissions to manage</span></div>
    <span class="badge-tag dim">Locked</span>
  </button>`;
}

function pickerGroup(title, sub, cards) {
  return `<div class="picker-group">
    <h3>${ESCAPED(title)}</h3>
    ${sub ? `<p>${ESCAPED(sub)}</p>` : ""}
    <div class="guild-grid">${cards}</div>
  </div>`;
}

async function renderPicker() {
  guilds = (me && me.guilds) || [];
  renderNav();
  drawPicker();
}

function drawPicker() {
  const list = $("#guild-list");
  const q = ($("#guild-search").value || "").trim().toLowerCase();
  const all = q ? guilds.filter((g) => (g.name || "").toLowerCase().includes(q)) : guilds;
  if (!guilds.length) {
    list.innerHTML = '<div class="card"><p class="muted">No servers found. You need to be in at least one Discord server to use the panel.</p></div>';
    return;
  }
  if (q && !all.length) {
    list.innerHTML = '<div class="card"><p class="muted">No servers match “' + ESCAPED($("#guild-search").value) + '”.</p></div>';
    return;
  }
  const manage = all.filter((g) => g.can_manage && g.bot_present);
  const invite = all.filter((g) => !g.bot_present);
  const locked = all.filter((g) => g.bot_present && !g.can_manage);
  const sections = [];
  if (manage.length) sections.push(pickerGroup("Manage", "Configure AI, welcomes, levels and moderation.", manage.map(manageCard).join("")));
  if (invite.length) sections.push(pickerGroup("Add Quaestio", "Servers the bot hasn't joined yet — click to invite it.", invite.map(inviteCard).join("")));
  if (locked.length) sections.push(pickerGroup("View only", "Quaestio is here but you need admin permissions to change settings.", locked.map(lockedCard).join("")));
  list.innerHTML = sections.join("");
  $$(".guild-card[data-id]").forEach((el) =>
    el.addEventListener("click", () => openGuild(el.dataset.id))
  );
  $$(".guild-card.invite").forEach((el) =>
    el.addEventListener("click", () => {
      const url = el.dataset.invite;
      if (url) window.open(url, "_blank");
    })
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
  const [s, refs] = await Promise.all([
    api(`/api/guilds/${id}/settings`),
    loadRefs(id),
  ]);
  const set = (el, v) => { if ($(el)) $(el).value = v ?? ""; };
  const source = (s.ai_source || "shared").toLowerCase();
  set("#ai_source", source);
  set("#ai_endpoint", source === "self" ? (s.ai_endpoint || "") : "");
  set("#ai_memory", s.ai_memory);
  set("#ai_quota", s.ai_quota || "");
  set("#ai_window", String(s.ai_window || "6"));
  set("#ai_personality", s.ai_personality || "friendly");
  set("#ai_instructions", s.ai_instructions);
  set("#ai_max_tokens", s.ai_max_tokens);
  set("#welcome_message", s.welcome_message);
  set("#warnlimit", s.warnlimit);
  $("#ai_enabled").checked = ON(s.ai_enabled);
  $("#ai_mention").checked = ON(s.ai_mention);
  $("#ai_conv").checked = ON(s.ai_conv);
  $("#ai_conv_minutes").value = s.ai_conv_minutes || "3";
  $("#ai-conv-minutes-wrap").hidden = !ON(s.ai_conv);
  $("#ai_contribute").checked = ON(s.ai_contribute);
  $("#welcome_enabled").checked = ON(s.welcome_enabled);
  $("#xp_enabled").checked = ON(s.xp_enabled);
  $("#level_announce").checked = ON(s.level_announce);
  $("#birthday_enabled").checked = ON(s.birthday_enabled);

  setTemperature(s.ai_temperature);
  populateRefPicker("welcome_channel", "channels", refs, s.welcome_channel);
  populateRefPicker("welcome_role", "roles", refs, s.welcome_role);
  populateRefPicker("levelrole", "roles", refs, s.levelrole);
  populateRefPicker("birthday_channel", "channels", refs, s.birthday_channel);
  renderAiChannels(refs, s.ai_channels);

  const pill = $("#guild-status");
  pill.className = "pill" + (ON(s.ai_enabled) ? " green" : "");
  pill.textContent = ON(s.ai_enabled) ? "AI on" : "AI off";

  applySourceUI(source, s);

  await populateModels("#ai_model", id, "ai_model", s.ai_model);
  buildSummary(s);
  renderQuota(s);
  renderMemory(s, refs);
  renderBirthdays(s);
  renderLeaderboard(id);
  renderWelcomePreview();
}

function applySourceUI(source, s) {
  const self = source === "self";
  const ep = $("#ai_endpoint");
  const epBadge = $("#endpoint-badge");
  const epHint = $("#endpoint-hint");
  const memHint = $("#memory-hint");
  const quotaHint = $("#quota-hint");
  const contribute = $("#contribute-wrap");
  ep.disabled = !self;
  if (contribute) contribute.hidden = !self;
  if (self) {
    epBadge.textContent = "my own box";
    epBadge.classList.remove("green");
    epHint.textContent = "Where this server's AI runs. Point at your own Ollama box, or leave blank to use http://127.0.0.1:11434.";
    memHint.textContent = "Past messages your box keeps in mind per channel. Its own replies count too — more = better but slower.";
    quotaHint.textContent = "AI calls allowed in each window (0 = unlimited). You run the box, so you set the rules.";
  } else {
    epBadge.textContent = "shared box";
    epBadge.classList.add("green");
    epHint.textContent = "Locked — the shared Quaestio box is owned by the host and kept private. Pick a model from it below.";
    memHint.textContent = s.host_memory
      ? `Past messages the AI keeps in mind per channel (top ${s.host_memory}, set by the host).`
      : "Past messages the AI keeps in mind per channel.";
    quotaHint.textContent = s.host_quota
      ? `AI calls per window (capped at ${s.host_quota} by the host). 0 = unlimited.`
      : "AI calls allowed in each window. 0 = unlimited.";
  }
}

function buildSummary(s) {
  const source = (s.ai_source || "shared").toLowerCase();
  const mem = Number(s.memory_effective) || 4;
  const q = Number(s.quota_effective) || 0;
  const win = Number(s.ai_window) || 6;
  const used = Number(s.usage_now) || 0;
  const box = modelState;
  const allowedCount = (s.ai_channels || "").split(",").filter((c) => c.trim()).length;
  const caps = Number(s.host_quota) || Number(s.host_memory);
  const rows = [
    ["AI chat", ON(s.ai_enabled) ? "On" : "Off"],
    ["AI box", source === "self" ? "My own (self-hosted)" : "Shared Quaestio box"],
    ["Community pool", ON(s.ai_contribute) ? "Yes — sharing my box" : "No"],
    ["AI box status", box ? (box.online ? "Online" : "Offline") : "Checking…"],
    ["Models on box", box && box.models.length ? `${box.models.length}` : "—"],
    ["Model in use", s.ai_model || s.host_model || "Host default"],
    ["Personality", PERSONALITY_LABELS[s.ai_personality] || "Friendly"],
    ["Memory", `${mem} messages / channel`],
    ["Rate limit", q ? `${q} calls / ${win}h` : "Unlimited"],
    ["Used this window", `${used} call${used === 1 ? "" : "s"}`],
    ["Host caps", caps ? `≤${s.host_memory || "—"} mem · ${s.host_quota || "∞"} calls` : "none"],
    ["Allowed channels", allowedCount ? `${allowedCount} picked` : "Everywhere"],
    ["Replies on mention", ON(s.ai_mention) ? "Yes" : "No"],
    ["Conversation mode", ON(s.ai_conv) ? `On — stays ${s.ai_conv_minutes || 3} min after a reply` : "Off (needs @ each time)"],
    ["Creativity", Number(s.ai_temperature) || "0.8"],
    ["Max reply length", `${Number(s.ai_max_tokens) || 400} tokens`],
  ];
  $("#ai-summary").innerHTML = rows
    .map(([k, v]) => `<div><dt>${ESCAPED(k)}</dt><dd>${ESCAPED(String(v))}</dd></div>`)
    .join("");
}

function renderQuota(s) {
  const m = $("#quota-meter");
  if (!m) return;
  m.hidden = false;
  const win = Number(s.ai_window) || 6;
  const winLabel = win <= 1 ? "hour" : win <= 6 ? "6h window" : "day";
  const used = Number(s.usage_now) || 0;
  const limit = Number(s.quota_effective) || 0;
  const fill = $("#quota-fill");
  const label = $("#quota-label");
  const reset = $("#quota-reset");
  if (!limit) {
    label.textContent = used ? `${used} call${used === 1 ? "" : "s"} used — no cap this ${winLabel}` : `Unlimited calls this ${winLabel}`;
    reset.textContent = "no cap";
    fill.style.width = "0%";
    fill.classList.remove("warn");
    return;
  }
  const pct = Math.min(100, Math.round((used / limit) * 100));
  label.textContent = `${used} of ${limit} calls used this ${winLabel}`;
  reset.textContent = `resets in ${Number(s.reset_minutes) || "—"}m`;
  fill.style.width = pct + "%";
  fill.classList.toggle("warn", used >= limit);
}

const MODEL_SPEED = {
  "tinyllama": "⚡ fast",
  "qwen2.5:0.5b": "⚡ fast",
  "qwen2.5:1.5b": "balanced (a bit slower)",
  "qwen2.5:3b": "🐢 powerful but slow",
};
const modelSpeedLabel = (m) => MODEL_SPEED[m] ? ` — ${MODEL_SPEED[m]}` : "";

const PERSONALITY_LABELS = {
  friendly: "Friendly", sage: "Wise sage", sarcastic: "Sarcastic wit",
  pirate: "Pirate", professional: "Professional",
};

async function populateModels(sel, guildId, field, selected) {
  const el = $(sel);
  el.innerHTML = '<option value="">Loading models…</option>';
  const status = $(sel + "-status") || $("#model-scan-status");
  if (status) status.textContent = "";
  try {
    const data = await api(`/api/guilds/${guildId}/models`);
    const models = data && data.models ? data.models : [];
    modelState = { online: true, models };
    if (!models.length) {
      el.innerHTML = '<option value="">(no models found — check the AI host)</option>';
      return;
    }
    el.innerHTML = models.map((m) => `<option value="${ESCAPED(m)}" ${m === selected ? "selected" : ""}>${ESCAPED(m)}${modelSpeedLabel(m)}</option>`).join("");
    if (selected && !models.includes(selected)) el.innerHTML += `<option value="${ESCAPED(selected)}" selected>${ESCAPED(selected)}</option>`;
  } catch {
    modelState = { online: false, models: [] };
    el.innerHTML = `<option value="${ESCAPED(selected || "")}" ${selected ? "selected" : ""}>${ESCAPED(selected || "(unreachable — save endpoint first)")}</option>`;
  }
}

/* ---------- memory viewer ---------- */
function renderMemory(s, refs) {
  const view = $("#memory-view");
  if (!view) return;
  const mem = s.memory || [];
  if (!mem.length) {
    view.innerHTML = '<p class="muted">No memory yet — conversations appear here as you talk to the bot.</p>';
    return;
  }
  const name = (id) => {
    const ch = (refs.channels || []).find((c) => String(c.id) === String(id));
    return ch ? `#${ch.name}` : id;
  };
  view.innerHTML = mem.slice(0, 18).map((r) => `
    <div class="mem-row ${r.role === "bot" ? "bot" : "user"}">
      <div class="mem-who"><span>${r.role === "bot" ? "🤖 Quaestio" : "👤 Member"} · ${ESCAPED(name(r.channel_id))}</span><span class="who">${r.role === "bot" ? "bot" : "member"}</span></div>
      <div class="mem-text">${ESCAPED(r.text)}</div>
    </div>`).join("");
}

function renderBirthdays(s) {
  const list = $("#birthday-list");
  if (!list) return;
  const bd = s.birthdays || [];
  if (!bd.length) {
    list.innerHTML = '<p class="muted">No birthdays saved yet. Members add theirs in Discord with <code>/birthday set 3 14</code>.</p>';
    return;
  }
  list.innerHTML = '<p class="hint">Saved birthdays:</p>' + bd.map((b) => `
    <div class="bday-row"><span class="bday-date">${ESCAPED(b.month)}/${ESCAPED(b.day)}</span><span><@${ESCAPED(b.user_id)}></span></div>`).join("");
}

async function renderLeaderboard(id) {
  const el = $("#leaderboard");
  if (!el) return;
  try {
    const data = await api(`/api/guilds/${id}/leaderboard`);
    const members = (data && data.members) || [];
    if (!members.length) {
      el.innerHTML = '<p class="muted">No XP yet — get people chatting!</p>';
      return;
    }
    const medals = ["🥇", "🥈", "🥉"];
    el.innerHTML = members.map((m, i) => `
      <div class="lb-row"><span class="lb-rank">${medals[i] || (i + 1) + "."}</span>
      <span class="lb-name">${ESCAPED(m.name)}</span><span class="lb-msgs">${m.messages} msgs</span></div>`).join("");
  } catch {
    el.innerHTML = '<p class="muted">Could not load the leaderboard.</p>';
  }
}

/* ---------- channel / role pickers by name ---------- */
const refsCache = {};

async function loadRefs(guildId) {
  if (refsCache[guildId]) return refsCache[guildId];
  try {
    const r = await api(`/api/guilds/${guildId}/refs`);
    refsCache[guildId] = { channels: r.channels || [], roles: r.roles || [] };
  } catch {
    refsCache[guildId] = { channels: [], roles: [] };
  }
  return refsCache[guildId];
}

function refLabel(item, type) {
  return (type === "channels" ? "#" : "@") + item.name;
}

/* Picks a channel/role by name, or falls back to a "Custom ID…" input. */
function populateRefPicker(prefix, type, refs, current) {
  const sel = $("#" + prefix + "_ref");
  const custom = $("#" + prefix + "_custom");
  if (!sel) return;
  const list = type === "channels" ? refs.channels : refs.roles;
  const selected = String(current || "");
  let opts = `<option value="">None</option>`;
  if (!list.length) opts += `<option value="" disabled>Couldn't load list — use Custom ID…</option>`;
  list.forEach((it) => {
    opts += `<option value="${ESCAPED(it.id)}" ${String(it.id) === selected ? "selected" : ""}>${ESCAPED(refLabel(it, type))}</option>`;
  });
  opts += `<option value="__custom__">Custom ID…</option>`;
  sel.innerHTML = opts;

  const known = list.some((it) => String(it.id) === selected);
  if (selected && !known) {
    sel.value = "__custom__";
    custom.value = selected;
    custom.hidden = false;
  } else {
    custom.value = "";
    custom.hidden = true;
  }
}

function refValue(prefix) {
  const sel = $("#" + prefix + "_ref");
  const custom = $("#" + prefix + "_custom");
  if (!sel) return "";
  if (sel.value === "__custom__") return (custom.value || "").trim();
  return sel.value || "";
}

/* AI channel allowlist as toggle chips. Empty selection = allow everywhere. */
function renderAiChannels(refs, current) {
  const box = $("#ai-channels-chips");
  const note = $("#ai-channels-note");
  if (!refs.channels.length) {
    box.innerHTML = '<span class="muted">Chat everywhere — channel list unavailable for this server.</span>';
    if (note) note.innerHTML = "Channel names aren't available right now — the AI still runs in every channel unless restricted.";
    return;
  }
  const selected = new Set(
    (current || "").split(",").map((x) => x.trim()).filter(Boolean).map(String)
  );
  box.innerHTML = refs.channels.map((c) => {
    const on = selected.has(String(c.id));
    return `<button type="button" class="chip${on ? " on" : ""}" data-channel="${ESCAPED(c.id)}"><span class="hash">#</span>${ESCAPED(c.name)}</button>`;
  }).join("");
  const sync = () => {
    const onCount = box.querySelectorAll(".chip.on").length;
    if (note) note.innerHTML = onCount
      ? `Allowed in <b>${onCount} of ${refs.channels.length}</b> channels — silent everywhere else.`
      : "No channels selected — the AI is allowed <b>everywhere</b>. Tap a channel to restrict it.";
  };
  box.querySelectorAll(".chip").forEach((el) =>
    el.addEventListener("click", () => { el.classList.toggle("on"); sync(); })
  );
  sync();
}

function readAiChannels() {
  return $$("#ai-channels-chips .chip.on").map((el) => el.dataset.channel).join(",");
}

function setTemperature(v) {
  const val = (v === "" || v == null) ? 0.8 : Number(v);
  $("#ai_temperature").value = val;
  $("#ai_temperature_val").textContent = val;
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

async function saving(btn, fn) {
  if (!btn) return fn();
  const original = btn.innerHTML;
  btn.disabled = true;
  btn.classList.add("loading");
  btn.innerHTML = '<span class="spinner"></span>Saving…';
  try { await fn(); }
  finally {
    btn.disabled = false;
    btn.classList.remove("loading");
    btn.innerHTML = original;
  }
}

function readSettings() {
  const endpointLocked = $("#ai_endpoint").disabled;
  const b = (el) => ($(el).checked ? "1" : "0");
  return {
    ai_enabled: b("#ai_enabled"),
    ai_source: $("#ai_source").value,
    ai_endpoint: endpointLocked ? "" : $("#ai_endpoint").value.trim(),
    ai_model: $("#ai_model").value,
    ai_memory: $("#ai_memory").value,
    ai_quota: $("#ai_quota").value,
    ai_window: $("#ai_window").value,
    ai_personality: $("#ai_personality").value,
    ai_contribute: b("#ai_contribute"),
    ai_instructions: $("#ai_instructions").value,
    ai_channels: readAiChannels(),
    ai_mention: b("#ai_mention"),
    ai_conv: b("#ai_conv"),
    ai_conv_minutes: $("#ai_conv_minutes").value,
    ai_temperature: $("#ai_temperature").value,
    ai_max_tokens: $("#ai_max_tokens").value,
    welcome_enabled: b("#welcome_enabled"),
    welcome_channel: refValue("welcome_channel"),
    welcome_message: $("#welcome_message").value,
    welcome_role: refValue("welcome_role"),
    levelrole: refValue("levelrole"),
    xp_enabled: b("#xp_enabled"),
    level_announce: b("#level_announce"),
    warnlimit: $("#warnlimit").value,
    birthday_enabled: b("#birthday_enabled"),
    birthday_channel: refValue("birthday_channel"),
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
const OS_CMDS = {
  macos: { cmd: "curl -fsSL https://quaestio.online/bot/install.sh | bash", note: "Requires Python 3.10+ · creates ~/quaestio · asks for your bot token once. Start with ~/quaestio/run-quaestio.sh" },
  linux: { cmd: "curl -fsSL https://quaestio.online/bot/install.sh | bash", note: "Installs a systemd service that auto-starts on boot. Status: systemctl status quaestio" },
  windows: { cmd: 'powershell -ExecutionPolicy Bypass -Command "irm https://quaestio.online/bot/install.ps1 | iex"', note: "Installs to %USERPROFILE%\\quaestio · asks for your bot token once. Start with run-quaestio.bat" },
};

function applyHostModeUI(mode) {
  const managed = mode !== "decentral";
  $$("#host-mode-seg .seg-btn").forEach((b) => b.classList.toggle("active", b.dataset.mode === mode));
  const badge = $("#host-endpoint-badge");
  badge.textContent = managed ? "hard-capped" : "defaults";
  badge.classList.toggle("green", managed);
  const note = $("#host-mode-note");
  note.innerHTML = managed
    ? "<b>Managed:</b> the endpoint is fixed by the host for every server; servers can only pick a model from it and lower memory/quota — never above the host's caps."
    : "<b>Server-owned:</b> servers each run their own AI and set their own memory &amp; quota. These host values are only used as fallback defaults.";
  $("#host-memory-label").textContent = managed ? "Max memory per server" : "Default memory";
  $("#host-quota-label").textContent = managed ? "Max calls / hour per server" : "Default calls / hour";
}

async function renderHost() {
  const s = (await api("/api/host/settings")) || {};
  const mode = s.host_mode || "managed";
  applyHostModeUI(mode);
  $("#host_endpoint").value = s.ai_endpoint || "";
  $("#host_memory").value = s.ai_memory ?? "";
  $("#host_quota").value = s.ai_quota ?? "";
  $("#host_ai_dm").checked = ON(s.ai_dm);
  const stats = (await api("/api/host/stats")) || {};
  $("#host-stats").innerHTML = [
    { n: fmtBytes(stats.mem_total), l: "RAM" },
    { n: `${stats.mem_pct ?? "—"}%`, l: "In use" },
    { n: fmtBytes(stats.disk_total), l: "Disk" },
    { n: stats.cpu_pct ?? "—", l: "CPU %" },
    { n: stats.model_count ?? "—", l: "Models" },
    { n: stats.ollama ? "Online" : "Offline", l: "Ollama" },
  ].map((c) => `<div class="stat-chip"><span class="num">${c.n}</span><span class="lbl">${c.l}</span></div>`).join("");

  const poolEl = $("#pool-list");
  try {
    const pool = (await api("/api/host/pool")) || { contributors: [] };
    const list = pool.contributors || [];
    poolEl.innerHTML = list.length
      ? list.map((c) => `
        <div class="pool-row">
          <span class="pool-name">@<abbr title="${ESCAPED(c.guild_id)}">${ESCAPED(c.guild_id)}</abbr></span>
          <span class="pool-model">${ESCAPED(c.model || "default model")}</span>
          <span class="pool-window">${ESCAPED(c.endpoint.split("//")[1] || c.endpoint)} · ${c.window}h windows</span>
        </div>`).join("")
      : '<p class="muted">No servers in the pool yet. Any server that self-hosts can opt in from its AI settings.</p>';
  } catch {
    poolEl.innerHTML = '<p class="muted">Could not load the pool.</p>';
  }

  const el = $("#host_model");
  el.innerHTML = '<option value="">(none set)</option>';
  if (stats.models && stats.models.length) {
    const cur = s.ai_model || "";
    el.innerHTML += stats.models.map((m) => `<option value="${ESCAPED(m)}" ${m === cur ? "selected" : ""}>${ESCAPED(m)}</option>`).join("");
    if (cur && !stats.models.includes(cur)) el.innerHTML += `<option value="${ESCAPED(cur)}" selected>${ESCAPED(cur)}</option>`;
  }
}

function applyOsTab(os) {
  $$("#os-seg .seg-btn").forEach((b) => b.classList.toggle("active", b.dataset.os === os));
  const c = OS_CMDS[os];
  if (!c) return;
  const block = $("#os-cmd");
  block.querySelector("pre code").textContent = c.cmd;
  block.querySelector(".code-bar").textContent = c.note;
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

  $("#guild-search").addEventListener("input", drawPicker);

  $$("#os-seg .seg-btn").forEach((b) =>
    b.addEventListener("click", () => applyOsTab(b.dataset.os))
  );

  $$("#host-mode-seg .seg-btn").forEach((b) =>
    b.addEventListener("click", () => {
      applyHostModeUI(b.dataset.mode);
      const btns = $$("#host-mode-seg .seg-btn");
      btns.forEach((x) => x.classList.toggle("active", x === b));
    })
  );

  $$(".tab").forEach((t) =>
    t.addEventListener("click", () => {
      currentTab = t.dataset.tab;
      $$(".tab").forEach((x) => x.classList.toggle("active", x === t));
      $$(".tab-panel").forEach((p) => p.classList.toggle("active", p.id === "panel-" + t.dataset.tab));
    })
  );

  $("#refresh-models").addEventListener("click", () => populateModels("#ai_model", activeGuild.id, "ai_model", $("#ai_model").value));
  $("#welcome_message").addEventListener("input", renderWelcomePreview);

  /* Name pickers: "Custom ID…" reveals the raw input */
  $$("select[id$='_ref']").forEach((sel) =>
    sel.addEventListener("change", () => {
      const custom = $("#" + sel.id.replace("_ref", "_custom"));
      if (custom) custom.hidden = sel.value !== "__custom__";
    })
  );

  /* Creativity slider → value readout */
  $("#ai_temperature").addEventListener("input", () => {
    $("#ai_temperature_val").textContent = $("#ai_temperature").value;
  });

  /* AI box source toggles the endpoint + pool contribution */
  $("#ai_source").addEventListener("change", () => applySourceUI($("#ai_source").value, {}));

  $("#ai_conv").addEventListener("change", () => {
    $("#ai-conv-minutes-wrap").hidden = !$("#ai_conv").checked;
  });

  $("#clear-memory").addEventListener("click", async () => {
    await saving($("#clear-memory"), async () => {
      try {
        await api(`/api/guilds/${activeGuild.id}/memory/clear`, { method: "POST", body: "{}" });
        const st = $("#memory-clear-status");
        st.textContent = "Cleared ✓";
        setTimeout(() => (st.textContent = ""), 2200);
        await loadSettings(activeGuild.id);
      } catch { /* toast already shown */ }
    });
  });

  $("#save-ai").addEventListener("click", async () => {
    await saving($("#save-ai"), async () => {
      try {
        await saveSettings(activeGuild.id, readSettings(), $("#save-status-ai"));
        await loadSettings(activeGuild.id);
      } catch { /* toast already shown */ }
    });
  });
  $("#save-welcome").addEventListener("click", async () => {
    await saving($("#save-welcome"), async () => {
      try { await saveSettings(activeGuild.id, readSettings(), $("#save-status-welcome")); }
      catch { /* toast already shown */ }
    });
  });
  $("#save-levels").addEventListener("click", async () => {
    await saving($("#save-levels"), async () => {
      try { await saveSettings(activeGuild.id, readSettings(), $("#save-status-levels")); }
      catch { /* toast already shown */ }
    });
  });
  $("#save-moderation").addEventListener("click", async () => {
    await saving($("#save-moderation"), async () => {
      try { await saveSettings(activeGuild.id, readSettings(), $("#save-status-moderation")); }
      catch { /* toast already shown */ }
    });
  });

  $("#save-host").addEventListener("click", async () => {
    await saving($("#save-host"), async () => {
      try {
        const mode = ($("#host-mode-seg .seg-btn.active") || {}).dataset?.mode || "managed";
        await api("/api/host/settings", {
          method: "POST",
          body: JSON.stringify({
            host_mode: mode,
            ai_endpoint: $("#host_endpoint").value.trim(),
            ai_model: $("#host_model").value,
            ai_memory: $("#host_memory").value,
            ai_quota: $("#host_quota").value,
            ai_dm: $("#host_ai_dm").checked ? "1" : "0",
          }),
        });
        toast("Host settings saved");
        const el = $("#save-status-host");
        el.textContent = "Saved ✓";
        setTimeout(() => (el.textContent = ""), 2200);
      } catch { /* toast already shown */ }
    });
  });
}

/* ---------- init ---------- */
async function init() {
  wireEvents();
  grabTokenFromHash();
  try {
    me = await api("/api/me");
  } catch { me = null; }
  if (!me) { renderUser(); showLoginError(); show("login-view"); return; }
  renderUser();
  await renderPicker();
  show("picker-view");
}

init();
