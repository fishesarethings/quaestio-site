const state = {
  user: null,
  guilds: [],
  currentGuild: null,
  models: [],
};

const $ = (id) => document.getElementById(id);

async function api(path, opts = {}) {
  const r = await fetch(path, {
    headers: { "Content-Type": "application/json" },
    ...opts,
  });
  if (r.status === 401) {
    location.href = "/";
    throw new Error("unauthorized");
  }
  if (!r.ok) throw new Error(await r.text());
  return r.json();
}

function show(view) {
  for (const v of ["login-view", "picker-view", "settings-view"]) {
    $(v).classList.toggle("hidden", v !== view);
  }
}

function renderTopbar() {
  const el = $("topbar-user");
  if (!state.user) { el.innerHTML = ""; return; }
  el.innerHTML = `
    <img class="avatar" src="${state.user.user.avatar
      ? `https://cdn.discordapp.com/avatars/${state.user.user.id}/${state.user.user.avatar}.png`
      : "/static/discord.png"}" alt="">
    <span>${escapeHtml(state.user.user.global_name || state.user.user.username)}</span>
    <a href="/auth/logout" class="btn-ghost small">Sign out</a>`;
}

function renderGuilds() {
  const list = $("guild-list");
  list.innerHTML = "";
  if (!state.guilds.length) {
    list.innerHTML = '<p class="muted">No servers found where you are an admin.</p>';
    return;
  }
  for (const g of state.guilds) {
    const icon = g.icon
      ? `<img class="guild-icon" src="https://cdn.discordapp.com/icons/${g.id}/${g.icon}.png" alt="">`
      : `<div class="guild-icon placeholder">${escapeHtml((g.name || "?").charAt(0))}</div>`;
    const card = document.createElement("button");
    card.className = "guild-card";
    card.innerHTML = `${icon}<span>${escapeHtml(g.name)}</span>`;
    card.onclick = () => openSettings(g);
    list.appendChild(card);
  }
}

async function openSettings(guild) {
  state.currentGuild = guild;
  $("settings-guild-name").textContent = guild.name;
  show("settings-view");
  const s = await api(`/api/guilds/${guild.id}/settings`);
  $("ai_enabled").checked = s.ai_enabled === "1";
  $("ai_endpoint").value = s.ai_endpoint || "";
  $("ai_memory").value = s.ai_memory || 4;
  $("ai_quota").value = s.ai_quota || 0;
  $("ai_instructions").value = s.ai_instructions || "";
  $("welcome_enabled").checked = s.welcome_enabled === "1";
  $("welcome_channel").value = s.welcome_channel || "";
  $("welcome_message").value = s.welcome_message || "";
  $("welcome_message").oninput = renderWelcomePreview;
  $("levelrole").value = s.levelrole || "";
  $("warnlimit").value = s.warnlimit || 5;
  state.savedAiModel = s.ai_model || "";
  renderWelcomePreview();
  await refreshModels();
}

async function refreshModels() {
  if (!state.currentGuild) return;
  const sel = $("ai_model");
  const status = $("model-scan-status");
  status.textContent = "Scanning models…";
  const data = await api(`/api/guilds/${state.currentGuild.id}/models`);
  state.models = data.models;
  status.textContent = data.error
    ? `⚠️ Couldn't reach ${data.endpoint} — showing saved value.`
    : `${data.models.length} models on ${data.endpoint}`;
  sel.innerHTML = "";
  if (data.models.length) {
    for (const m of data.models) {
      const opt = document.createElement("option");
      opt.value = m;
      opt.textContent = m;
      sel.appendChild(opt);
    }
  }
  const opt = document.createElement("option");
  opt.value = "";
  opt.textContent = "default (host's model)";
  sel.prepend(opt);
  sel.value = state.savedAiModel || "";
}

function renderWelcomePreview() {
  const text = $("welcome_message").value || "";
  const member = "NewMember";
  const guild = state.currentGuild ? state.currentGuild.name : "Server";
  $("welcome-preview").textContent = text
    .replace(/\{member\}/g, member)
    .replace(/\{guild\}/g, guild);
}

function bindSave(btnId, statusId, payloadFn, successText) {
  $(btnId).onclick = async () => {
    const status = $(statusId);
    status.textContent = "Saving…";
    try {
      await api(`/api/guilds/${state.currentGuild.id}/settings`, {
        method: "POST",
        body: JSON.stringify(payloadFn()),
      });
      status.textContent = successText;
      setTimeout(() => (status.textContent = ""), 2500);
    } catch (e) {
      status.textContent = "Save failed.";
    }
  };
}

function escapeHtml(s) {
  return String(s).replace(/[&<>"']/g, (c) =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c])
  );
}

document.addEventListener("DOMContentLoaded", async () => {
  const params = new URLSearchParams(location.search);
  if (params.get("error") === "login") {
    $("login-error").textContent = "Sign-in failed. Try again.";
    $("login-error").classList.remove("hidden");
  } else if (params.get("error") === "needadmin") {
    $("login-error").textContent = "You need to be an admin of at least one server.";
    $("login-error").classList.remove("hidden");
  }

  try {
    state.user = await api("/api/me");
  } catch (e) {
    show("login-view");
    renderTopbar();
    return;
  }

  state.guilds = state.user.guilds;
  renderTopbar();
  show("picker-view");
  renderGuilds();

  for (const t of document.querySelectorAll(".tab")) {
    t.onclick = () => {
      document.querySelectorAll(".tab").forEach((x) => x.classList.remove("active"));
      document.querySelectorAll(".tab-panel").forEach((x) => x.classList.remove("active"));
      t.classList.add("active");
      $(`panel-${t.dataset.tab}`).classList.add("active");
    };
  }

  $("back-btn").onclick = () => { show("picker-view"); state.currentGuild = null; };
  $("refresh-models").onclick = refreshModels;

  bindSave("save-ai", "save-status-ai", () => ({
    ai_enabled: $("ai_enabled").checked ? "1" : "0",
    ai_endpoint: $("ai_endpoint").value.trim(),
    ai_model: $("ai_model").value || "",
    ai_memory: $("ai_memory").value || 4,
    ai_quota: $("ai_quota").value || 0,
    ai_instructions: $("ai_instructions").value,
  }), "✅ Saved (encrypted).");

  bindSave("save-welcome", "save-status-welcome", () => ({
    welcome_enabled: $("welcome_enabled").checked ? "1" : "0",
    welcome_channel: $("welcome_channel").value.trim(),
    welcome_message: $("welcome_message").value,
  }), "✅ Saved (encrypted).");

  bindSave("save-levels", "save-status-levels", () => ({
    levelrole: $("levelrole").value.trim(),
  }), "✅ Saved.");

  bindSave("save-moderation", "save-status-moderation", () => ({
    warnlimit: $("warnlimit").value || 5,
  }), "✅ Saved.");
});
