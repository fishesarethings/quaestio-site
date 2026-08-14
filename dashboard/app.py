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

import json
import os
import sys
import sqlite3
import urllib.request

import httpx
from cryptography.fernet import Fernet
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, RedirectResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))) + "/bot")
import config as qconfig  # noqa: E402

BASE = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.environ.get("DB_PATH", os.path.join(BASE, "..", "bot", "quaestio.db"))
OLLAMA_BASE_URL = os.environ.get("OLLAMA_BASE_URL", "http://127.0.0.1:11434")

CLIENT_ID = os.environ.get("DISCORD_CLIENT_ID", "")
CLIENT_SECRET = os.environ.get("DISCORD_CLIENT_SECRET", "")
REDIRECT_URI = os.environ.get(
    "DISCORD_REDIRECT_URI", "https://admin.quaestio.online/auth/callback"
)
SCOPES = "identify guilds"

API = "https://discord.com/api/v10"
OAUTH_AUTH = "https://discord.com/oauth2/authorize"
ADMIN_BITS = 1 << 3  # ADMINISTRATOR

app = FastAPI(title="Quaestio admin")
_secret = os.environ.get("SECRET_KEY", "")
if not _secret:
    _secret = Fernet.generate_key().decode()
app.add_middleware(
    SessionMiddleware,
    secret_key=_secret,
    same_site="lax",
    https_only=True,
)
app.mount("/static", StaticFiles(directory=os.path.join(BASE, "static")), name="static")


# ---------------------------------------------------------------------------
# DB (shared with the bot)
# ---------------------------------------------------------------------------

def db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def db_init():
    conn = db()
    conn.execute(
        """CREATE TABLE IF NOT EXISTS config (
            guild_id TEXT, key TEXT, value TEXT,
            PRIMARY KEY (guild_id, key)
        )"""
    )
    conn.commit()
    conn.close()


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
    u = request.session.get("user")
    if not u:
        raise HTTPException(401, "Not signed in")
    return u


def admin_guilds(user: dict) -> list:
    return [
        g
        for g in user.get("guilds", [])
        if g.get("owner") or (int(g.get("permissions", 0)) & ADMIN_BITS)
    ]


@app.get("/auth/login")
async def auth_login():
    return RedirectResponse(
        f"{OAUTH_AUTH}?client_id={CLIENT_ID}&redirect_uri={REDIRECT_URI}"
        f"&response_type=code&scope={SCOPES}"
    )


@app.get("/auth/callback")
async def auth_callback(request: Request, code: str):
    try:
        data = await exchange_code(code)
    except HTTPException:
        return RedirectResponse("/?error=login")
    if not admin_guilds(data["user"]):
        request.session.clear()
        return RedirectResponse("/?error=needadmin")
    request.session["user"] = data
    return RedirectResponse("/")


@app.get("/auth/logout")
async def auth_logout(request: Request):
    request.session.clear()
    return RedirectResponse("/")


# ---------------------------------------------------------------------------
# API
# ---------------------------------------------------------------------------

@app.get("/api/me")
async def api_me(request: Request):
    user = session_user(request)
    return {"user": user["user"], "guilds": admin_guilds(user)}


def _model_default():
    return get_cfg("default", "ai_model", "")


@app.get("/api/guilds/{guild_id}/models")
async def api_models(request: Request, guild_id: int):
    session_user(request)
    endpoint = get_cfg(guild_id, "ai_endpoint", OLLAMA_BASE_URL)
    try:
        with urllib.request.urlopen(f"{endpoint}/api/tags", timeout=6) as resp:
            data = json.loads(resp.read().decode())
        names = [m["name"] for m in data.get("models", []) if m.get("name")]
        return {"endpoint": endpoint, "models": names}
    except Exception as exc:
        return JSONResponse({"endpoint": endpoint, "models": [], "error": str(exc)})


@app.get("/api/guilds/{guild_id}/settings")
async def api_get_settings(request: Request, guild_id: int):
    session_user(request)
    keys = [
        "ai_enabled", "ai_model", "ai_endpoint", "ai_memory", "ai_instructions",
        "ai_quota", "welcome_enabled", "welcome_channel", "welcome_message",
        "levelrole", "warnlimit",
    ]
    return {k: get_cfg(guild_id, k, "") for k in keys}


SENSITIVE = {"ai_instructions", "ai_endpoint", "welcome_message", "tag_editor"}


@app.post("/api/guilds/{guild_id}/settings")
async def api_set_settings(request: Request, guild_id: int):
    session_user(request)
    body = await request.json()
    allowed = {
        "ai_enabled", "ai_model", "ai_endpoint", "ai_memory", "ai_instructions",
        "ai_quota", "welcome_enabled", "welcome_channel", "welcome_message",
        "levelrole", "warnlimit",
    }
    for key, value in body.items():
        if key in allowed and value is not None:
            set_cfg(guild_id, key, value)
    return {"ok": True}


# ---------------------------------------------------------------------------
# Pages
# ---------------------------------------------------------------------------

@app.get("/")
async def index(request: Request):
    return FileResponse(os.path.join(BASE, "static", "index.html"))