"""Quaestio admin dashboard — web UI for server settings.

Companion to the bot. Shares the same SQLite DB and encryption key, so settings
changed here are respected by the bot immediately (no bot restart needed).

Run:
  uvicorn app:app --host 127.0.0.1 --port 8900
Env:
  DISCORD_CLIENT_ID / DISCORD_CLIENT_SECRET  Discord OAuth2 app
  DISCORD_REDIRECT_URI                        e.g. https://admin.quaestio.online/auth/callback
  SECRET_KEY                                   session signing key
  DB_PATH                                     same DB as the bot
  QUAESTIO_KEY_FILE                           same keyfile as the bot
"""

import datetime
import json
import os
import secrets
import shutil
import sqlite3
import sys
import time
import urllib.parse
import urllib.request

import httpx
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, RedirectResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))) + "/bot")
import config as qconfig  # noqa: E402

BASE = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.environ.get("DB_PATH", os.path.join(BASE, "..", "bot", "quaestio.db"))
OLLAMA_BASE_URL = os.environ.get("OLLAMA_BASE_URL", "http://127.0.0.1:11434")

# Only these models show up in the AI model picker. Everything else on a box
# (phi, gemma, future pulls, …) stays hidden so members see a curated menu.
ALLOWED_MODELS = [
    "qwen2.5:0.5b", "qwen2.5:1.5b", "qwen2.5:3b",
    "tinyllama:latest", "llama3.2:3b",
]

CLIENT_ID = os.environ.get("DISCORD_CLIENT_ID", "")
CLIENT_SECRET = os.environ.get("DISCORD_CLIENT_SECRET", "")
REDIRECT_URI = os.environ.get(
    "DISCORD_REDIRECT_URI", "https://admin.quaestio.online/auth/callback"
)
BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
SCOPES = "identify guilds"

API = "https://discord.com/api/v10"
OAUTH_AUTH = "https://discord.com/oauth2/authorize"
ADMIN_BITS = 1 << 3  # ADMINISTRATOR
INVITE_PERMS = "1101994781766"  # same permission set the bot uses everywhere

HOST_ADMIN_IDS = {i.strip() for i in os.environ.get("HOST_ADMIN_IDS", "").split(",") if i.strip()}

app = FastAPI(title="Quaestio admin")
app.mount("/static", StaticFiles(directory=os.path.join(BASE, "static")), name="static")

# Login sessions keyed by a random bearer token (no cookies — Safari-safe OAuth).
# In-memory: a dashboard restart signs everyone out, which is fine for a panel.
SESSIONS = {}


# ---------------------------------------------------------------------------
# DB (shared with the bot)
# ---------------------------------------------------------------------------

def db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def db_init():
    conn = db()
    conn.executescript(
        """CREATE TABLE IF NOT EXISTS config (
            guild_id TEXT, key TEXT, value TEXT,
            PRIMARY KEY (guild_id, key)
        );
        CREATE TABLE IF NOT EXISTS ai_presets (
            guild_id TEXT, kind TEXT, name TEXT, text TEXT, emoji TEXT DEFAULT '✨',
            PRIMARY KEY (guild_id, kind, name)
        );
        CREATE TABLE IF NOT EXISTS profiles (
            guild_id TEXT, user_id TEXT, name TEXT, facts TEXT, at TEXT,
            PRIMARY KEY (guild_id, user_id)
        );
        CREATE TABLE IF NOT EXISTS warned (
            guild_id TEXT, user_id TEXT, reason TEXT, at TEXT
        );
        CREATE TABLE IF NOT EXISTS hosters (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT, endpoint TEXT, model TEXT,
            share INTEGER DEFAULT 50, enabled INTEGER DEFAULT 1,
            added_by TEXT, at TEXT
        );"""
    )
    _migrate_pool_health(conn)
    cols = {r[1] for r in conn.execute("PRAGMA table_info(memory)").fetchall()}
    if "user_id" not in cols:
        conn.execute("ALTER TABLE memory ADD COLUMN user_id TEXT DEFAULT ''")
    if "name" not in cols:
        conn.execute("ALTER TABLE memory ADD COLUMN name TEXT DEFAULT ''")
    pcols = {r[1] for r in conn.execute("PRAGMA table_info(ai_presets)").fetchall()}
    if "emoji" not in pcols:
        conn.execute("ALTER TABLE ai_presets ADD COLUMN emoji TEXT DEFAULT '✨'")
    conn.commit()
    _migrate_pool_anonymize(conn)
    conn.close()


def _migrate_pool_health(conn):
    """Pool-host health tracking (shared schema with the bot)."""
    cols = {r[1] for r in conn.execute("PRAGMA table_info(hosters)").fetchall()}
    for col, ddl in (("failed", "ALTER TABLE hosters ADD COLUMN failed INTEGER DEFAULT 0"),
                     ("down_until", "ALTER TABLE hosters ADD COLUMN down_until TEXT DEFAULT ''"),
                     ("last_ok", "ALTER TABLE hosters ADD COLUMN last_ok TEXT DEFAULT ''"),
                     ("last_fail", "ALTER TABLE hosters ADD COLUMN last_fail TEXT DEFAULT ''")):
        if col not in cols:
            conn.execute(ddl)


def _migrate_pool_anonymize(conn):
    """One-time privacy migration: encrypt leftover plaintext endpoints/models
    and replace any real-name labels with anonymous node IDs so identities
    can't leak from old rows."""
    import secrets as _secrets
    rows = conn.execute("SELECT id, name, endpoint, model FROM hosters").fetchall()
    for r in rows:
        cur_name = (r["name"] or "").strip()
        if not cur_name.startswith("node-"):
            conn.execute("UPDATE hosters SET name=? WHERE id=?",
                         ("node-" + _secrets.token_hex(2), r["id"]))
        ep = r["endpoint"] or ""
        if ep and not ep.startswith("enc:"):
            conn.execute("UPDATE hosters SET endpoint=? WHERE id=?",
                         (qconfig.maybe_encrypt("pool_endpoint", ep), r["id"]))
        m = r["model"] or ""
        if m and not m.startswith("enc:"):
            conn.execute("UPDATE hosters SET model=? WHERE id=?",
                         (qconfig.maybe_encrypt("pool_model", m), r["id"]))
    conn.commit()


db_init()


def get_cfg(guild_id, key, default=None):
    conn = db()
    row = conn.execute(
        "SELECT value FROM config WHERE guild_id=? AND key=?",
        (str(guild_id), key),
    ).fetchone()
    conn.close()
    if row is None:
        return default
    return qconfig.maybe_decrypt(key, row["value"])


def set_cfg(guild_id, key, value):
    conn = db()
    conn.execute(
        """INSERT INTO config (guild_id, key, value) VALUES (?, ?, ?)
           ON CONFLICT(guild_id, key) DO UPDATE SET value = excluded.value""",
        (str(guild_id), key, qconfig.maybe_encrypt(key, str(value))),
    )
    conn.commit()
    conn.close()


# ---------------------------------------------------------------------------
# Discord OAuth
# ---------------------------------------------------------------------------

async def exchange_code(code: str) -> dict:
    async with httpx.AsyncClient(timeout=15) as client:
        r = await client.post(
            f"{API}/oauth2/token",
            data={
                "client_id": CLIENT_ID,
                "client_secret": CLIENT_SECRET,
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": REDIRECT_URI,
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        if r.status_code != 200:
            raise HTTPException(400, "OAuth exchange failed")
        data = r.json()
        me = await client.get(
            f"{API}/users/@me",
            headers={"Authorization": f"Bearer {data['access_token']}"},
        )
        guilds = await client.get(
            f"{API}/users/@me/guilds",
            headers={"Authorization": f"Bearer {data['access_token']}"},
        )
    return {
        "user": me.json(),
        "guilds": guilds.json() if guilds.status_code == 200 else [],
    }


def session_user(request: Request) -> dict:
    auth = request.headers.get("Authorization", "")
    if auth.startswith("Bearer "):
        data = SESSIONS.get(auth[7:].strip())
        if data:
            return data
    raise HTTPException(401, "Not signed in")


def admin_guilds(user: dict) -> list:
    return [
        g
        for g in user.get("guilds", [])
        if g.get("owner") or (int(g.get("permissions", 0)) & ADMIN_BITS)
    ]


def require_admin_guild(request: Request, guild_id: int) -> dict:
    """The caller must be an admin of the given Discord server."""
    data = session_user(request)
    g = next(
        (x for x in data.get("guilds", []) if str(x.get("id")) == str(guild_id)),
        None,
    )
    if not g or not (g.get("owner") or int(g.get("permissions", 0)) & ADMIN_BITS):
        raise HTTPException(403, "Admin of this server required")
    return data


_bot_guild_ids: set | None = None
_bot_guilds_at = 0.0


async def bot_guild_ids() -> set:
    """IDs of guilds the bot is currently in (cached 60s)."""
    global _bot_guild_ids, _bot_guilds_at
    now = time.time()
    if _bot_guild_ids is not None and now - _bot_guilds_at < 60:
        return _bot_guild_ids
    ids = set()
    if BOT_TOKEN:
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                r = await client.get(
                    f"{API}/users/@me/guilds",
                    headers={"Authorization": f"Bot {BOT_TOKEN}"},
                )
            if r.status_code == 200:
                ids = {str(g["id"]) for g in r.json()}
        except Exception:
            pass
    _bot_guild_ids = ids
    _bot_guilds_at = now
    return ids


def invite_url(guild_id) -> str:
    return (
        f"{OAUTH_AUTH}?client_id={CLIENT_ID}&permissions={INVITE_PERMS}"
        f"&scope=bot%20applications.commands&guild_id={guild_id}"
    )


_app_owner_id = None
_app_owner_at = 0.0


async def _application_owner_id() -> str:
    """Discord app owner (usually the host operator). Cached 1h."""
    global _app_owner_id, _app_owner_at
    now = time.time()
    if _app_owner_id is not None and now - _app_owner_at < 3600:
        return _app_owner_id
    owner = ""
    if BOT_TOKEN:
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                r = await client.get(
                    f"{API}/oauth2/applications/@me",
                    headers={"Authorization": f"Bot {BOT_TOKEN}"},
                )
            if r.status_code == 200:
                owner = str((r.json().get("owner") or {}).get("id", ""))
        except Exception:
            pass
    _app_owner_id = owner
    _app_owner_at = now
    return owner


async def host_admin_ids() -> set:
    """Who may see the Host tab / host settings. Explicit list, else app owner."""
    if HOST_ADMIN_IDS:
        return HOST_ADMIN_IDS
    owner = await _application_owner_id()
    return {owner} if owner else set()


@app.get("/auth/login")
async def auth_login():
    return RedirectResponse(
        f"{OAUTH_AUTH}?client_id={CLIENT_ID}"
        f"&redirect_uri={urllib.parse.quote(REDIRECT_URI, safe='')}"
        f"&response_type=code&scope={SCOPES}"
    )


@app.get("/auth/callback")
async def auth_callback(request: Request, code: str):
    try:
        data = await exchange_code(code)
    except HTTPException:
        return RedirectResponse("/?error=login")
    if not data.get("guilds"):
        return RedirectResponse("/?error=needadmin")
    token = secrets.token_urlsafe(32)
    SESSIONS[token] = data
    return RedirectResponse(f"/#token={token}")


@app.get("/auth/logout")
async def auth_logout(request: Request, token: str = ""):
    SESSIONS.pop(token, None)
    return RedirectResponse("/")


# ---------------------------------------------------------------------------
# API
# ---------------------------------------------------------------------------

@app.get("/api/me")
async def api_me(request: Request):
    data = session_user(request)
    user = data["user"]
    admins = await host_admin_ids()
    is_host_admin = str(user.get("id")) in admins
    bots = await bot_guild_ids()
    guilds = []
    for g in data.get("guilds", []):
        gid = str(g.get("id"))
        can_manage = bool(g.get("owner")) or bool(int(g.get("permissions", 0)) & ADMIN_BITS)
        present = gid in bots
        guilds.append({
            "id": gid,
            "name": g.get("name"),
            "icon": g.get("icon"),
            "owner": bool(g.get("owner")),
            "can_manage": can_manage,
            "bot_present": present,
            "invite_url": invite_url(gid) if not present else "",
        })
    return {"user": user, "guilds": guilds, "is_host_admin": is_host_admin}


HOST_ID = "host"


def host_default(key, default=None):
    return get_cfg(HOST_ID, key, default)


def model_fallback(guild_id):
    """Endpoint used to scan models: always the host's in managed mode."""
    managed = get_cfg("host", "host_mode", "managed") != "decentral"
    if managed:
        return get_cfg("host", "ai_endpoint", OLLAMA_BASE_URL)
    return get_cfg(guild_id, "ai_endpoint", OLLAMA_BASE_URL)


# ---------------------------------------------------------------------------
# Channel / role references (so the panel shows names, not bare IDs)
# ---------------------------------------------------------------------------

REF_CACHE = {}
REF_CACHE_AT = {}


async def guild_refs(guild_id: str) -> dict:
    """Text channels + assignable roles for the name pickers (bot token, cached)."""
    now = time.time()
    cached = REF_CACHE.get(guild_id)
    if cached and now - REF_CACHE_AT.get(guild_id, 0) < 90:
        return cached
    out = {"channels": [], "roles": []}
    if BOT_TOKEN:
        async with httpx.AsyncClient(timeout=10) as client:
            headers = {"Authorization": f"Bot {BOT_TOKEN}"}
            try:
                r = await client.get(f"{API}/guilds/{guild_id}/channels", headers=headers)
                if r.status_code == 200:
                    chans = sorted(
                        (
                            c for c in r.json()
                            if c.get("type") in (0, 5, 15) and c.get("name")
                        ),
                        key=lambda c: (c.get("position", 0), c.get("name", "")),
                    )
                    out["channels"] = [
                        {"id": str(c["id"]), "name": c["name"]} for c in chans
                    ]
            except Exception:
                pass
            try:
                r = await client.get(f"{API}/guilds/{guild_id}/roles", headers=headers)
                if r.status_code == 200:
                    roles = [
                        rt for rt in r.json()
                        if str(rt.get("id")) != str(guild_id) and not rt.get("managed")
                    ]
                    roles.sort(key=lambda rt: rt.get("position", 0), reverse=True)
                    out["roles"] = [
                        {"id": str(rt["id"]), "name": rt["name"]} for rt in roles
                    ]
            except Exception:
                pass
    REF_CACHE[guild_id] = out
    REF_CACHE_AT[guild_id] = now
    return out


@app.get("/api/guilds/{guild_id}/refs")
async def api_refs(request: Request, guild_id: int):
    require_admin_guild(request, guild_id)
    return await guild_refs(str(guild_id))


@app.get("/api/guilds/{guild_id}/models")
async def api_models(request: Request, guild_id: int):
    require_admin_guild(request, guild_id)
    managed = get_cfg("host", "host_mode", "managed") != "decentral"
    endpoint = model_fallback(guild_id)
    try:
        with urllib.request.urlopen(f"{endpoint}/api/tags", timeout=6) as resp:
            data = json.loads(resp.read().decode())
        names = [m["name"] for m in data.get("models", []) if m.get("name") and m["name"] in ALLOWED_MODELS]
        return {"endpoint": "" if managed else endpoint, "models": names}
    except Exception as exc:
        return JSONResponse({"endpoint": "" if managed else endpoint, "models": [], "error": str(exc)})


SETTING_KEYS = [
    "ai_enabled", "ai_model", "ai_endpoint", "ai_memory", "ai_instructions",
    "ai_quota", "ai_channels", "ai_mention", "ai_temperature", "ai_max_tokens",
    "ai_source", "ai_contribute", "ai_window", "ai_personality", "ai_character",
    "ai_conv", "ai_conv_minutes",
    "welcome_enabled", "welcome_channel", "welcome_message",
    "welcome_role", "levelrole", "level_announce", "xp_enabled", "warnlimit",
    "xp_spam", "xp_min_words", "xp_max_words", "xp_cooldown",
    "birthday_enabled", "birthday_channel",
]


def usage_bucket(window: int) -> str:
    now = datetime.datetime.now(datetime.timezone.utc)
    if window <= 1:
        return now.strftime("%Y%m%d%H")
    if window <= 6:
        return now.strftime("%Y%m%d") + str(now.hour // 6)
    return now.strftime("%Y%m%d")


def usage_calls(guild_id, window: int = 6) -> int:
    """AI calls already used in the current quota window (0 if none)."""
    bucket = usage_bucket(window)
    conn = db()
    try:
        row = conn.execute(
            "SELECT calls FROM usage WHERE guild_id=? AND bucket=?",
            (str(guild_id), bucket),
        ).fetchone()
        return row["calls"] if row else 0
    finally:
        conn.close()


def effective_ai_limits(guild_id):
    """Effective quota/memory/endpoint after host caps — mirrors the bot's merge."""
    managed = get_cfg("host", "host_mode", "managed") != "decentral"
    source = (get_cfg(guild_id, "ai_source", "shared") or "shared").strip().lower()
    window = max(1, int(get_cfg(guild_id, "ai_window", "6") or 6))
    host_mem_raw = get_cfg("host", "ai_memory", "")
    host_quota_raw = get_cfg("host", "ai_quota", "")
    host_mem = int(host_mem_raw) if str(host_mem_raw).strip() else 0
    host_quota = int(host_quota_raw) if str(host_quota_raw).strip() else 0
    mem_raw = get_cfg(guild_id, "ai_memory", "")
    quota_raw = get_cfg(guild_id, "ai_quota", "")
    memory = int(mem_raw) if str(mem_raw).strip() else (host_mem or 4)
    quota = int(quota_raw) if str(quota_raw).strip() else host_quota
    if source == "self":
        endpoint = (get_cfg(guild_id, "ai_endpoint", "") or "http://127.0.0.1:11434").strip()
    else:
        endpoint = ""  # shared host box is hidden from server admins
        if managed:
            if host_mem:
                memory = min(memory, host_mem)
            if host_quota:
                quota = min(quota, host_quota)
    return {"memory": memory, "quota": quota, "managed": managed, "window": window,
            "source": source, "endpoint": endpoint,
            "host_memory": host_mem, "host_quota": host_quota}


@app.get("/api/guilds/{guild_id}/settings")
async def api_get_settings(request: Request, guild_id: int):
    require_admin_guild(request, guild_id)
    settings = {k: get_cfg(guild_id, k, "") for k in SETTING_KEYS}
    managed = get_cfg("host", "host_mode", "managed") != "decentral"
    settings["host_mode"] = "managed" if managed else "decentral"
    settings["host_memory"] = get_cfg("host", "ai_memory", "")
    settings["host_quota"] = get_cfg("host", "ai_quota", "")
    settings["host_model"] = get_cfg("host", "ai_model", "")
    # Never reveal the host's private AI box URL to server admins.
    settings["host_endpoint"] = ""
    limits = effective_ai_limits(guild_id)
    settings["ai_source"] = limits["source"]
    settings["ai_window"] = str(limits["window"])
    settings["quota_effective"] = limits["quota"]
    settings["memory_effective"] = limits["memory"]
    settings["usage_now"] = usage_calls(guild_id, limits["window"])
    now = datetime.datetime.now(datetime.timezone.utc)
    w = limits["window"]
    if w <= 1:
        mins = 60 - now.minute
    elif w <= 6:
        mins = (6 - now.hour % 6) * 60 - now.minute
    else:
        mins = (24 - now.hour) * 60 - now.minute
    settings["reset_minutes"] = mins
    conn = db()
    rows = conn.execute(
        "SELECT channel_id, role, user_id, name, text, at FROM memory WHERE guild_id=? ORDER BY rowid DESC LIMIT 30",
        (str(guild_id),),
    ).fetchall()
    conn.close()
    settings["memory"] = [
        {"channel_id": r["channel_id"], "role": r["role"], "user_id": r["user_id"],
         "name": r["name"], "text": r["text"], "at": r["at"]}
        for r in rows
    ]
    conn = db()
    bdays = conn.execute(
        "SELECT user_id, month, day FROM birthdays WHERE guild_id=? ORDER BY month, day",
        (str(guild_id),),
    ).fetchall()
    conn.close()
    settings["birthdays"] = [
        {"user_id": r["user_id"], "month": r["month"], "day": r["day"]} for r in bdays
    ]
    settings["preset_personalities"] = preset_bundle(guild_id, "personality")
    settings["preset_characters"] = preset_bundle(guild_id, "character")
    return settings


@app.post("/api/guilds/{guild_id}/memory/clear")
async def api_clear_memory(request: Request, guild_id: int):
    require_admin_guild(request, guild_id)
    conn = db()
    conn.execute("DELETE FROM memory WHERE guild_id=?", (str(guild_id),))
    conn.commit()
    conn.close()
    return {"ok": True}


@app.get("/api/guilds/{guild_id}/leaderboard")
async def api_leaderboard(request: Request, guild_id: int):
    require_admin_guild(request, guild_id)
    conn = db()
    rows = conn.execute(
        "SELECT user_id, messages FROM xp WHERE guild_id=? ORDER BY messages DESC LIMIT 5",
        (str(guild_id),),
    ).fetchall()
    conn.close()
    names = {}
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.get(
                f"{API}/guilds/{guild_id}/members?limit=1000",
                headers={"Authorization": f"Bot {BOT_TOKEN}"},
            )
            if r.status_code == 200:
                for m in r.json():
                    uid = str(m.get("user", {}).get("id"))
                    nick = m.get("nick")
                    user = m.get("user", {})
                    names[uid] = nick or user.get("global_name") or user.get("username") or uid
    except Exception:
        pass
    return {
        "members": [
            {"id": r["user_id"], "messages": r["messages"],
             "name": names.get(str(r["user_id"]), f"<@{r['user_id']}>")}
            for r in rows
        ]
    }


@app.get("/api/guilds/{guild_id}/warns")
async def api_warns(request: Request, guild_id: int):
    require_admin_guild(request, guild_id)
    conn = db()
    rows = conn.execute(
        "SELECT user_id, reason, at FROM warned WHERE guild_id=? ORDER BY at DESC LIMIT 20",
        (str(guild_id),),
    ).fetchall()
    conn.close()
    return {"warns": [{"user_id": r["user_id"], "reason": r["reason"], "at": r["at"]} for r in rows]}


@app.get("/api/pool")
async def api_pool(request: Request):
    """Anonymous pool stats for any signed-in admin. Identities are never
    included — only totals, so nobody can piece together who contributes."""
    session_user(request)
    conn = db()
    row = conn.execute(
        "SELECT COUNT(*) c, COALESCE(SUM(share),0) s FROM hosters WHERE enabled=1"
    ).fetchone()
    conn.close()
    return {"nodes": int(row["c"] or 0), "total_share": int(row["s"] or 0)}


@app.get("/api/host/pool")
async def api_host_pool(request: Request):
    await require_host_admin(request)
    conn = db()
    rows = conn.execute(
        "SELECT id, name, endpoint, model, share, enabled FROM hosters ORDER BY name"
    ).fetchall()
    conn.close()
    # Privacy: never export raw endpoints or models. The management UI only
    # needs the anonymous node ID, its share and whether it's enabled.
    contributors = []
    for r in rows:
        d = dict(r)
        d["name"] = d.get("name")
        d.pop("endpoint", None)
        d.pop("model", None)
        contributors.append(d)
    return {"contributors": contributors,
            "total_share": sum(int(r["share"]) for r in rows if r["enabled"])}


@app.post("/api/host/pool")
async def api_host_pool_add(request: Request):
    await require_host_admin(request)
    import secrets as _secrets
    body = await request.json()
    endpoint = (body.get("endpoint") or "").strip()
    if not endpoint:
        raise HTTPException(400, "Endpoint is required")
    model = (body.get("model") or "").strip() or "default"
    share = max(0, min(100, int(body.get("share", 50) or 50)))
    name = (body.get("name") or "").strip()[:80] or "node-" + _secrets.token_hex(2)
    conn = db()
    conn.execute(
        "INSERT INTO hosters (name, endpoint, model, share, enabled, added_by, at) VALUES (?, ?, ?, ?, 1, 'dash', ?)",
        (name, qconfig.maybe_encrypt("pool_endpoint", endpoint),
         qconfig.maybe_encrypt("pool_model", model), share,
         datetime.datetime.now(datetime.timezone.utc).isoformat()),
    )
    conn.commit()
    conn.close()
    return {"ok": True, "name": name}


@app.post("/api/host/pool/{hoster_id}")
async def api_host_pool_update(request: Request, hoster_id: int):
    await require_host_admin(request)
    body = await request.json()
    conn = db()
    if "enabled" in body:
        conn.execute("UPDATE hosters SET enabled=? WHERE id=?", (1 if body.get("enabled") else 0, hoster_id))
    if "share" in body and "share_delta" not in body:
        conn.execute("UPDATE hosters SET share=? WHERE id=?", (max(0, min(100, int(body.get("share", 0) or 0))), hoster_id))
    conn.commit()
    conn.close()
    return {"ok": True}


@app.delete("/api/host/pool/{hoster_id}")
async def api_host_pool_delete(request: Request, hoster_id: int):
    await require_host_admin(request)
    conn = db()
    conn.execute("DELETE FROM hosters WHERE id=?", (hoster_id,))
    conn.commit()
    conn.close()
    return {"ok": True}


@app.post("/api/guilds/{guild_id}/settings")
async def api_set_settings(request: Request, guild_id: int):
    require_admin_guild(request, guild_id)
    body = await request.json()
    for key, value in body.items():
        if key in SETTING_KEYS and value is not None:
            set_cfg(guild_id, key, value)
    return {"ok": True}


# ---------------------------------------------------------------------------
# AI personality / character presets (custom entries per guild)
# ---------------------------------------------------------------------------

# Mirrored titles + emoji so the panel can render tiles without importing the bot.
PRESET_BUILTINS = {
    "personality": {
        "friendly": "Friendly",
        "sage": "Wise sage",
        "sarcastic": "Sarcastic wit",
        "pirate": "Pirate",
        "professional": "Professional",
    },
    "character": {
        "Jeff from Mars": "Jeff from Mars",
        "Grumpy tavern keeper": "Grumpy tavern keeper",
        "Wholesome grandma": "Wholesome grandma",
        "Cyber detective": "Cyber detective",
    },
}

PRESET_EMOJI = {
    "personality": {
        "friendly": "🙂", "sage": "🧘", "sarcastic": "😏",
        "pirate": "🏴‍☠️", "professional": "💼",
    },
    "character": {
        "Jeff from Mars": "🫘", "Grumpy tavern keeper": "🍺",
        "Wholesome grandma": "👵", "Cyber detective": "🕵️",
    },
}

PRESET_DESCRIPTIONS = {
    "personality": {
        "friendly": "Warm, upbeat and casual.",
        "sage": "Calm, wise and measured.",
        "sarcastic": "Playful dry wit, never mean.",
        "pirate": "Nautical cheer — arr, matey.",
        "professional": "Crisp and to the point.",
    },
    "character": {
        "Jeff from Mars": "A friendly alien obsessed with beans.",
        "Grumpy tavern keeper": "Grumpy but always helpful.",
        "Wholesome grandma": "Sweet, proud and always listening.",
        "Cyber detective": "Sharp sleuth who spots everything.",
    },
}

PRESET_PROMPTS = {
    "personality": {
        "friendly": "Keep the tone friendly, warm and upbeat.",
        "sage": "Keep the tone wise, calm, measured and to the point.",
        "sarcastic": "Keep a playful, sarcastic edge — never mean.",
        "pirate": "Lace your replies with nautical cheer (arr, ye, matey) but stay on topic.",
        "professional": "Keep it crisp, precise and to the point.",
    },
    "character": {
        "Jeff from Mars": (
            "You are Jeff, a friendly alien from Mars who is absolutely obsessed "
            "with beans. You bring beans up constantly and insist they solve everything."
        ),
        "Grumpy tavern keeper": (
            "You are a grumpy but well-meaning tavern keeper. You complain a "
            "little, mutter under your breath, but you always help customers in "
            "the end."
        ),
        "Wholesome grandma": (
            "You are a sweet, supportive grandma. You are proud of everyone, "
            "worry about whether people ate, and always have time to listen."
        ),
        "Cyber detective": (
            "You are a sharp, no-nonsense cyber-sleuth. You talk calmly, spot "
            "details others miss, and punctuate breakthroughs with 'elementary'."
        ),
    },
}


def guild_presets(guild_id, kind):
    conn = db()
    rows = conn.execute(
        "SELECT name, text, emoji FROM ai_presets WHERE guild_id=? AND kind=?",
        (str(guild_id), kind),
    ).fetchall()
    conn.close()
    return {r["name"]: {"text": r["text"], "emoji": r["emoji"] or "✨"} for r in rows}


def preset_bundle(guild_id, kind):
    """[{key,title,desc,emoji,text,custom}] tiles: "none" + built-ins + custom."""
    custom = guild_presets(guild_id, kind)
    items = [{"key": "none", "title": "None", "desc": "Default friendly buddy.", "emoji": "🚫", "text": "", "custom": False}]
    for key, title in PRESET_BUILTINS[kind].items():
        items.append({
            "key": key, "title": title,
            "desc": PRESET_DESCRIPTIONS[kind].get(key, ""),
            "emoji": PRESET_EMOJI[kind].get(key, "✨"),
            "text": PRESET_PROMPTS[kind].get(key, ""), "custom": False,
        })
    for name, meta in custom.items():
        items.append({"key": name, "title": name, "desc": "Your custom preset.",
                      "emoji": meta["emoji"], "text": meta["text"], "custom": True})
    return items


@app.get("/api/guilds/{guild_id}/presets/{kind}")
async def api_get_presets(request: Request, guild_id: int, kind: str):
    require_admin_guild(request, guild_id)
    if kind not in ("personality", "character"):
        raise HTTPException(400, "kind must be personality or character")
    return {
        "bundle": preset_bundle(guild_id, kind),
        "custom": [{"name": n, "text": m["text"], "emoji": m["emoji"]} for n, m in guild_presets(guild_id, kind).items()],
    }


@app.post("/api/guilds/{guild_id}/presets/{kind}")
async def api_save_preset(request: Request, guild_id: int, kind: str):
    require_admin_guild(request, guild_id)
    if kind not in ("personality", "character"):
        raise HTTPException(400, "kind must be personality or character")
    body = await request.json()
    name = str(body.get("name", "")).strip()
    text = str(body.get("text", "")).strip()
    emoji = str(body.get("emoji", "")).strip()
    if not name:
        raise HTTPException(400, "Preset needs a title")
    if not emoji:
        raise HTTPException(400, "Preset needs an emoji")
    if name in ("none",) or name in PRESET_BUILTINS[kind]:
        raise HTTPException(400, "That name is already in use by a built-in preset")
    if len(name) > 60 or len(text) > 2000:
        raise HTTPException(400, "Title too long (max 60) or instructions too long (max 2000)")
    if len(emoji) > 16:
        raise HTTPException(400, "Emoji too long")
    conn = db()
    conn.execute(
        """INSERT INTO ai_presets (guild_id, kind, name, text, emoji) VALUES (?, ?, ?, ?, ?)
           ON CONFLICT(guild_id, kind, name) DO UPDATE SET text = excluded.text, emoji = excluded.emoji""",
        (str(guild_id), kind, name, text, emoji),
    )
    conn.commit()
    conn.close()
    return {"ok": True, "bundle": preset_bundle(guild_id, kind)}


@app.delete("/api/guilds/{guild_id}/presets/{kind}")
async def api_delete_preset(request: Request, guild_id: int, kind: str):
    require_admin_guild(request, guild_id)
    if kind not in ("personality", "character"):
        raise HTTPException(400, "kind must be personality or character")
    body = await request.json()
    name = str(body.get("name", "")).strip()
    if not name or name in PRESET_BUILTINS[kind]:
        raise HTTPException(400, "Built-in presets can't be deleted")
    conn = db()
    conn.execute(
        "DELETE FROM ai_presets WHERE guild_id=? AND kind=? AND name=?",
        (str(guild_id), kind, name),
    )
    conn.commit()
    conn.close()
    return {"ok": True, "bundle": preset_bundle(guild_id, kind)}


# ---------------------------------------------------------------------------
# Host / self-host settings (applied as defaults by the bot)
# ---------------------------------------------------------------------------

HOST_KEYS = ["host_mode", "ai_endpoint", "ai_model", "ai_memory", "ai_quota", "ai_dm"]


async def require_host_admin(request: Request) -> dict:
    data = session_user(request)
    if str(data["user"].get("id")) not in await host_admin_ids():
        raise HTTPException(403, "Host settings are only for the host operator")
    return data


@app.get("/api/host/settings")
async def api_get_host(request: Request):
    await require_host_admin(request)
    return {k: get_cfg(HOST_ID, k, "") for k in HOST_KEYS}


@app.post("/api/host/settings")
async def api_set_host(request: Request):
    await require_host_admin(request)
    body = await request.json()
    for key, value in body.items():
        if key in HOST_KEYS and value is not None:
            set_cfg(HOST_ID, key, value)
    return {"ok": True}


@app.get("/api/host/stats")
async def api_host_stats(request: Request):
    await require_host_admin(request)
    stats = {"ollama": False, "models": []}
    try:
        with urllib.request.urlopen(f"{OLLAMA_BASE_URL}/api/tags", timeout=6) as resp:
            data = json.loads(resp.read().decode())
        stats["ollama"] = True
        stats["models"] = [m["name"] for m in data.get("models", []) if m.get("name")]
    except Exception:
        pass
    try:
        with open("/proc/meminfo") as f:
            meminfo = dict(line.split(":", 1) for line in f)
        stats["mem_total"] = int(meminfo["MemTotal"].split()[0]) * 1024
        stats["mem_avail"] = int(meminfo["MemAvailable"].split()[0]) * 1024
        stats["mem_pct"] = round(100 * (1 - stats["mem_avail"] / stats["mem_total"]))
        with open("/proc/loadavg") as f:
            stats["cpu_pct"] = round(float(f.read().split()[0]) * 100 / os.cpu_count())
    except Exception:
        pass
    try:
        total, _, _ = shutil.disk_usage("/")
        stats["disk_total"] = total
    except Exception:
        pass
    stats["model_count"] = len(stats["models"])
    return stats


# ---------------------------------------------------------------------------
# Pages
# ---------------------------------------------------------------------------

@app.get("/")
async def index(request: Request):
    return FileResponse(os.path.join(BASE, "static", "index.html"))