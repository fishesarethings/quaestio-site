#!/usr/bin/env python3
"""Quaestio — your server's own AI companion.

Self-hosted Discord bot: AI chat (via a local/remote Ollama), XP levels,
moderation, tags, welcomes, and core utilities. One process, one SQLite file.

Design goals (for weak hosts):
  * One AI call at a time — a fair queue round-robins across servers so a busy
    server can't starve everyone else, and replies "busy" instead of stacking.
  * Per-channel conversation memory, so a small model still chats coherently
    without loading whole-server history.
  * Human-like replies: streamed in with a typing indicator and natural pauses.
  * Server admins can override model/endpoint/memory — e.g. point at their own
    Ollama box (Windows/Linux/macOS) and "host their own" if they want.

Requires: a Discord bot token and an Ollama instance (OLLAMA_BASE_URL). The
Ollama host can be a different machine on your network or the same box.
"""

import asyncio
import datetime
import json
import os
import random
import re
import sqlite3
import sys
import time
import urllib.request
import urllib.error

import discord
from discord import app_commands
from discord.ext import commands

import config as quaestio_config
from config import decrypt, encrypt, maybe_decrypt, maybe_encrypt

# ---------------------------------------------------------------------------
# Config (env vars, .env is loaded by the launcher or install script)
# ---------------------------------------------------------------------------

BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
# Where Ollama lives. This can be ANOTHER computer on your network, e.g.
#   OLLAMA_BASE_URL=http://192.168.1.50:11434   (Windows/Linux model host)
OLLAMA_BASE_URL = os.environ.get("OLLAMA_BASE_URL", "http://127.0.0.1:11434")
OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "qwen2.5:0.5b")
OLLAMA_TIMEOUT = int(os.environ.get("OLLAMA_TIMEOUT", "180"))
DB_PATH = os.environ.get("DB_PATH", "quaestio.db")
PREFIX = os.environ.get("PREFIX", "/")
WARN_LIMIT_DEFAULT = int(os.environ.get("WARN_LIMIT", "3"))
RPC_LARGE_IMAGE = os.environ.get("RPC_LARGE_IMAGE", "logo")
RPC_SMALL_IMAGE = os.environ.get("RPC_SMALL_IMAGE", "")

# "Chat like a person" persona for the small model. Keeps it short, casual,
# and natural instead of a wall of text — but grounded so a weak model stays
# honest instead of inventing dates/facts or bouncing questions back.
GROUND_RULES = (
    "- you are talking to real people on a Discord server\n"
    "- answer the question directly; don't deflect or repeat the question\n"
    "- NEVER ask the user a question back, say 'what about you', or end by\n"
    "  flinging the topic at them\n"
    "- never invent dates, years, facts, names or numbers — if you don't\n"
    "  know, say you're not sure\n"
    "- reply in 1-4 short casual sentences and never mention being an AI\n"
)

# The "Chat like a person" opening fed to the small model when no character or
# personality is picked. Keeps it short, casual and natural, with the grounding
# rules above keeping the model honest (no invented dates, no deflecting).
DEFAULT_OPENING = (
    "You are Quaestio, a friendly, dry-witted Discord buddy. Behave like a human. "
    "You share one small brain with the whole server, so keep it light."
)

# Personality = the *tone* of the replies — a titled preset picked in the panel.
# Custom personalities are stored per-guild (ai_presets, kind="personality")
# and override the built-ins listed here. "none" means no personality applies
# and Quaestio stays the default friendly buddy. Grounding rules always win.
PERSONALITIES = {
    "friendly": {"title": "Friendly", "prompt": "Keep the tone friendly, warm and upbeat."},
    "sage": {"title": "Wise sage", "prompt": "Keep the tone wise, calm, measured and to the point."},
    "sarcastic": {"title": "Sarcastic wit", "prompt": "Keep a playful, sarcastic edge — never mean."},
    "pirate": {"title": "Pirate", "prompt": "Lace your replies with nautical cheer (arr, ye, matey) but stay on topic."},
    "professional": {"title": "Professional", "prompt": "Keep it crisp, precise and to the point."},
}

# Character = *who* the bot pretends to be (a whole new persona) — a titled
# preset too. Built-ins ship with the bot and can't be edited or deleted;
# guilds create their own in the ai_presets table (kind="character").
CHARACTERS = {
    "Jeff from Mars": {
        "title": "Jeff from Mars",
        "prompt": (
            "You are Jeff, a friendly alien from Mars who is absolutely obsessed "
            "with beans. You bring beans up constantly and insist they solve everything."
        ),
    },
    "Grumpy tavern keeper": {
        "title": "Grumpy tavern keeper",
        "prompt": (
            "You are a grumpy but well-meaning tavern keeper. You complain a "
            "little, mutter under your breath, but you always help customers in "
            "the end."
        ),
    },
    "Wholesome grandma": {
        "title": "Wholesome grandma",
        "prompt": (
            "You are a sweet, supportive grandma. You are proud of everyone, "
            "worry about whether people ate, and always have time to listen."
        ),
    },
    "Cyber detective": {
        "title": "Cyber detective",
        "prompt": (
            "You are a sharp, no-nonsense cyber-sleuth. You talk calmly, spot "
            "details others miss, and punctuate breakthroughs with 'elementary'."
        ),
    },
}


def persona_from(personality="none", character_name="", custom_personas=None, custom_characters=None):
    """Build the persona prompt from a personality (tone) + character (who).

    A character wins over tone when both are set (it defines *who* you are);
    the chosen personality still tints the tone. Grounding rules are always
    appended last so a weak model stays honest. Both accept custom dicts whose
    keys shadow the built-in presets.
    """
    personality = (personality or "none").strip().lower()
    custom_personas = custom_personas or {}
    custom_characters = custom_characters or {}

    person = persona_prompt(personality, custom_personas)
    char = persona_prompt(character_name, custom_characters) if character_name else ""

    parts = []
    if char:
        parts.append(char)
        if personality not in ("none", "") and person:
            parts.append(f"Keep the {personality} tone in your replies.")
    elif person:
        parts.append(person)
    else:
        parts.append(DEFAULT_OPENING)
    parts.append(GROUND_RULES)
    return "\n".join(parts)


def persona_prompt(key, custom):
    """Resolve a preset key (personality or character) to its raw prompt."""
    key = (key or "").strip()
    if not key or key == "none":
        return ""
    p = custom.get(key)
    if p is not None:
        return (p or "").strip()
    return (PERSONALITIES.get(key) or CHARACTERS.get(key) or {}).get("prompt", "")

# How much conversation to remember per channel by default (turns).
MEMORY_DEFAULT = 4

START_TIME = time.time()

intents = discord.Intents.default()
intents.message_content = True
intents.members = True

bot = commands.Bot(command_prefix=PREFIX, intents=intents, help_command=None)


# ---------------------------------------------------------------------------
# Storage (single SQLite file, private by design)
# ---------------------------------------------------------------------------

def db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def db_init():
    conn = db()
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS xp (
            guild_id TEXT, user_id TEXT, messages INTEGER DEFAULT 0,
            PRIMARY KEY (guild_id, user_id)
        );
        CREATE TABLE IF NOT EXISTS warned (
            guild_id TEXT, user_id TEXT, reason TEXT, at TEXT
        );
        CREATE TABLE IF NOT EXISTS config (
            guild_id TEXT, key TEXT, value TEXT,
            PRIMARY KEY (guild_id, key)
        );
        CREATE TABLE IF NOT EXISTS tags (
            guild_id TEXT, name TEXT, content TEXT, author TEXT, at TEXT,
            PRIMARY KEY (guild_id, name)
        );
        CREATE TABLE IF NOT EXISTS usage (
            guild_id TEXT, bucket TEXT, calls INTEGER DEFAULT 0,
            PRIMARY KEY (guild_id, bucket)
        );
        CREATE TABLE IF NOT EXISTS memory (
            guild_id TEXT, channel_id TEXT, role TEXT, text TEXT, at TEXT
        );
        CREATE TABLE IF NOT EXISTS birthdays (
            guild_id TEXT, user_id TEXT, month TEXT, day TEXT,
            PRIMARY KEY (guild_id, user_id)
        );
        CREATE TABLE IF NOT EXISTS ai_presets (
            guild_id TEXT, kind TEXT, name TEXT, text TEXT,
            PRIMARY KEY (guild_id, kind, name)
        );
        CREATE TABLE IF NOT EXISTS profiles (
            guild_id TEXT, user_id TEXT, name TEXT, facts TEXT, at TEXT,
            PRIMARY KEY (guild_id, user_id)
        );
        """
    )
    # Migration: older databases have a memory table without attribution.
    cols = {r[1] for r in conn.execute("PRAGMA table_info(memory)").fetchall()}
    if "user_id" not in cols:
        conn.execute("ALTER TABLE memory ADD COLUMN user_id TEXT DEFAULT ''")
    if "name" not in cols:
        conn.execute("ALTER TABLE memory ADD COLUMN name TEXT DEFAULT ''")
    conn.commit()
    conn.close()


def guild_presets(guild_id, kind):
    """This guild's custom personality/character presets: {name: text}."""
    conn = db()
    rows = conn.execute(
        "SELECT name, text FROM ai_presets WHERE guild_id=? AND kind=?",
        (str(guild_id), kind),
    ).fetchall()
    conn.close()
    return {r["name"]: r["text"] for r in rows}


def get_cfg(guild_id, key, default=None):
    conn = db()
    row = conn.execute(
        "SELECT value FROM config WHERE guild_id=? AND key=?",
        (str(guild_id), key),
    ).fetchone()
    conn.close()
    if row is None:
        return default
    return maybe_decrypt(key, row["value"])


def set_cfg(guild_id, key, value):
    conn = db()
    conn.execute(
        """INSERT INTO config (guild_id, key, value) VALUES (?, ?, ?)
           ON CONFLICT(guild_id, key) DO UPDATE SET value = excluded.value""",
        (str(guild_id), key, maybe_encrypt(key, str(value))),
    )
    conn.commit()
    conn.close()


def flag_on(guild_id, key, default="1") -> bool:
    """Truthy config check that tolerates '1'/'0', 'True'/'False' and empty."""
    v = str(get_cfg(guild_id, key, default)).strip().lower()
    return v not in ("", "0", "false", "none")


# ---------------------------------------------------------------------------
# Ollama AI (local or remote — the URL decides; Windows is fine on the far end)
# ---------------------------------------------------------------------------

async def ask_ollama(endpoint: str, model: str, prompt: str, temperature: float = 0.8, max_tokens: int = 400) -> str:
    payload = json.dumps(
        {"model": model, "prompt": prompt, "stream": False,
         "options": {"temperature": float(temperature), "num_predict": int(max_tokens)}}
    ).encode()

    def _request():
        req = urllib.request.Request(
            f"{endpoint}/api/generate",
            data=payload,
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=OLLAMA_TIMEOUT) as resp:
            return json.loads(resp.read().decode())

    try:
        result = await asyncio.to_thread(_request)
    except urllib.error.URLError:
        raise ConnectionError("AI is offline — the model box isn't reachable.")
    except (TimeoutError, OSError):
        raise ConnectionError("AI timed out. Try again in a moment.")

    response = (result.get("response") or "").strip()
    if not response:
        raise ConnectionError("AI returned an empty reply.")
    return response


def guild_ai_config(guild_id):
    """Per-server AI settings (admin-overridable via web UI) merged over defaults.

    ``ai_source`` decides where the server's AI runs:

      shared  — Quaestio's trusted shared box (the host). Server admins pick a
                model from it and can lower memory/quota, never above host caps.
      self    — the server runs its own Ollama box (bring-your-own). It sets its
                own endpoint, memory and quota, and may share the box with the
                community pool (ai_contribute).
    """
    host = lambda k, d: get_cfg("host", k, d)
    managed = get_cfg("host", "host_mode", "managed") != "decentral"
    source = (get_cfg(guild_id, "ai_source", "shared") or "shared").strip().lower()

    base = {
        "model": get_cfg(guild_id, "ai_model", host("ai_model", OLLAMA_MODEL)),
        "enabled": flag_on(guild_id, "ai_enabled", "1"),
        "instructions": get_cfg(guild_id, "ai_instructions", ""),
        "persona": persona_from(
            get_cfg(guild_id, "ai_personality", "none"),
            get_cfg(guild_id, "ai_character", ""),
            guild_presets(guild_id, "personality"),
            guild_presets(guild_id, "character"),
        ),
        "ai_channels": get_cfg(guild_id, "ai_channels", ""),
        "ai_mention": flag_on(guild_id, "ai_mention", "1"),
        "temperature": float(get_cfg(guild_id, "ai_temperature", "0.7") or "0.7"),
        "max_tokens": int(get_cfg(guild_id, "ai_max_tokens", "400") or "400"),
        "window": max(1, int(get_cfg(guild_id, "ai_window", "6") or "6")),
        "source": source,
        "contribute": flag_on(guild_id, "ai_contribute", "0"),
        # Conversation mode: once the bot replies it "stays" for a few minutes,
        # so members can keep chatting without @mentioning it again. On by
        # default; only a real @mentions it wakes it back up.
        "conv": flag_on(guild_id, "ai_conv", "1"),
        "conv_minutes": max(1, int(get_cfg(guild_id, "ai_conv_minutes", "3") or 3)),
    }

    if source == "self":
        base["endpoint"] = (get_cfg(guild_id, "ai_endpoint", "") or OLLAMA_BASE_URL).strip()
        base["model"] = get_cfg(guild_id, "ai_model", OLLAMA_MODEL)
        base["memory"] = max(1, int(get_cfg(guild_id, "ai_memory", MEMORY_DEFAULT) or MEMORY_DEFAULT))
        base["quota"] = max(0, int(get_cfg(guild_id, "ai_quota", "0") or 0))
        return base

    endpoint = host("ai_endpoint", OLLAMA_BASE_URL)
    host_memory = max(1, int(host("ai_memory", MEMORY_DEFAULT) or MEMORY_DEFAULT))
    host_quota = max(0, int(host("ai_quota", "0") or 0))
    memory = max(1, int(get_cfg(guild_id, "ai_memory", host_memory) or host_memory))
    quota = max(0, int(get_cfg(guild_id, "ai_quota", host_quota) or host_quota))
    if managed:
        if host_memory:
            memory = min(memory, host_memory)
        if host_quota:
            quota = min(quota, host_quota)
    base["endpoint"] = endpoint
    base["memory"] = memory
    base["quota"] = quota
    return base


def channel_allowed(guild_id, channel_id, cfg) -> bool:
    """True if the channel is on the server's AI allowlist (empty list = all)."""
    raw = (get_cfg(guild_id, "ai_channels", "") or "").strip()
    if not raw:
        return True
    allowed = {c.strip() for c in raw.split(",") if c.strip()}
    return str(channel_id) in allowed


def list_ollama_models(endpoint: str) -> list:
    """Ask an Ollama host for the models it has (used by the selector)."""
    try:
        req = urllib.request.Request(f"{endpoint}/api/tags", method="GET")
        with urllib.request.urlopen(req, timeout=8) as resp:
            data = json.loads(resp.read().decode())
        return [m.get("name", "") for m in data.get("models", []) if m.get("name")]
    except Exception:
        return []


def usage_bucket(window: int) -> str:
    """Rolling bucket key: hour, 6-hour block, or calendar day."""
    now = datetime.datetime.now(datetime.timezone.utc)
    if window <= 1:
        return now.strftime("%Y%m%d%H")
    if window <= 6:
        return now.strftime("%Y%m%d") + str(now.hour // 6)
    return now.strftime("%Y%m%d")


def quota_ok(guild_id, quota: int, window: int = 24) -> bool:
    """True if the guild has quota left in the current window (0 = unlimited)."""
    if not quota:
        return True
    bucket = usage_bucket(window)
    conn = db()
    row = conn.execute(
        "SELECT calls FROM usage WHERE guild_id=? AND bucket=?",
        (str(guild_id), bucket),
    ).fetchone()
    calls = row["calls"] if row else 0
    conn.close()
    return calls < quota


def quota_tick(guild_id, window: int = 24):
    bucket = usage_bucket(window)
    conn = db()
    conn.execute(
        """INSERT INTO usage (guild_id, bucket, calls) VALUES (?, ?, 1)
           ON CONFLICT(guild_id, bucket) DO UPDATE SET calls = calls + 1""",
        (str(guild_id), bucket),
    )
    conn.commit()
    conn.close()


# ---------------------------------------------------------------------------
# Conversation mode — the bot "stays" a while after a reply, then goes quiet
# ---------------------------------------------------------------------------

_conv_until = {}


def conv_mark(guild_id, channel_id, minutes: int):
    """The bot is now "in conversation" in this channel for ``minutes`` more."""
    _conv_until[(guild_id, channel_id)] = time.time() + max(1, minutes) * 60.0


def conv_live(guild_id, channel_id, cfg) -> bool:
    """True if conversation mode is on for this server and the bot is still
    in an active conversation in this channel (next message needs no @)."""
    if not cfg.get("conv"):
        return False
    expiry = _conv_until.get((guild_id, channel_id))
    if expiry is None:
        return False
    if time.time() >= expiry:
        _conv_until.pop((guild_id, channel_id), None)
        return False
    return True


async def _say_goodbye(message):
    """A member told the bot to leave — end the conversation right now."""
    _conv_until.pop((message.guild.id, message.channel.id), None)
    try:
        await message.channel.send(
            "👋 okay, I'm stepping out. Just @ me or use `/ask` whenever you want to talk again."
        )
    except discord.Forbidden:
        pass


# ---------------------------------------------------------------------------
# Per-channel conversation memory (split conversations & history)
# ---------------------------------------------------------------------------

class MemoryBank:
    """Rolling memory per (guild, channel), persisted in the shared SQLite DB.

    Persisting means the web panel can inspect and clear a server's memory,
    and conversations survive bot restarts. Each channel is trimmed at
    insert time so it can never grow unbounded. Every entry records who said
    it (user_id + display name) so the bot never confuses speakers.
    """

    def push(self, guild_id, channel_id, role, text, maxlen, user_id="", name=""):
        conn = db()
        conn.execute(
            "INSERT INTO memory (guild_id, channel_id, role, text, at, user_id, name) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (str(guild_id), str(channel_id), role, (text or "")[:1000],
             datetime.datetime.now().isoformat(), str(user_id or ""), (name or "")[:60]),
        )
        cap = max(8, int(maxlen) * 2 + 4)
        rows = conn.execute(
            "SELECT rowid FROM memory WHERE guild_id=? AND channel_id=? ORDER BY rowid DESC",
            (str(guild_id), str(channel_id)),
        ).fetchall()
        if len(rows) > cap:
            conn.execute(
                "DELETE FROM memory WHERE guild_id=? AND channel_id=? AND rowid <= ?",
                (str(guild_id), str(channel_id), rows[cap - 1]["rowid"]),
            )
        conn.commit()
        conn.close()

    def context(self, guild_id, channel_id, maxlen):
        conn = db()
        rows = conn.execute(
            "SELECT role, user_id, name, text FROM memory "
            "WHERE guild_id=? AND channel_id=? ORDER BY rowid DESC LIMIT ?",
            (str(guild_id), str(channel_id), int(maxlen)),
        ).fetchall()
        conn.close()
        return [
            {"role": r["role"], "user_id": r["user_id"], "name": r["name"], "text": r["text"]}
            for r in reversed(rows)
        ]

    def clear(self, guild_id, channel_id=None):
        conn = db()
        if channel_id is None:
            conn.execute("DELETE FROM memory WHERE guild_id=?", (str(guild_id),))
        else:
            conn.execute(
                "DELETE FROM memory WHERE guild_id=? AND channel_id=?",
                (str(guild_id), str(channel_id)),
            )
        conn.commit()
        conn.close()


memory = MemoryBank()


# ---------------------------------------------------------------------------
# Member profiles — "who is who". We learn a short profile per member from
# what they actually say ("i like fish"), keep who sent what in memory, and
# feed both back into the AI prompt so the bot talks to the right person.
# ---------------------------------------------------------------------------

# Light heuristics to pull "self facts" out of casual chat. Kept deliberately
# narrow so we don't invent things — only "I/me/my" statements become facts.
_PROFILE_RE = [
    re.compile(r"(?:^|\s)i(?:'?m| am) ([a-z][a-z ]{1,40})", re.I),       # "i'm a baker"
    re.compile(r"(?:^|\s)i (?:really )?(?:like|love|enjoy) ([a-z][a-z ]{1,40})", re.I),
    re.compile(r"(?:^|\s)i (?:hate|dislike) ([a-z][a-z ]{1,40})", re.I),
    re.compile(r"(?:^|\s)my favourite? (?:is|are) ([a-z][a-z ]{1,40})", re.I),
    re.compile(r"(?:^|\s)i (?:play|watch|read|program(?: in| with)?) ([a-z][a-z ]{1,40})", re.I),
    re.compile(r"(?:^|\s)i (?:work|work as|work with) ([a-z][a-z ]{1,40})", re.I),
    re.compile(r"(?:^|\s)i (?:use|listen to|collect) ([a-z][a-z ]{1,40})", re.I),
]

_PROFILE_STOP = re.compile(r"\b(?:u|ur|you|your|my|and|to|the|for|with|that|this|what|how|why|when|where|who|do|you|me|it|is|are|was|be|so|just|like)\b", re.I)


def extract_facts(text: str) -> list:
    """Pull a few short "facts" a member stated about themselves. Returns
    lowercased fragments like ['a baker', 'fish', 'minecraft'] — capped and
    cleaned so the profile stays tiny and honest."""
    out = []
    t = (text or "")[:400]
    for rx in _PROFILE_RE:
        for m in rx.finditer(t):
            frag = m.group(1).strip().strip(".,!?")
            if not frag or len(frag) > 40:
                continue
            if _PROFILE_STOP.fullmatch(frag):
                continue
            if frag not in out:
                out.append(frag)
        if len(out) >= 4:
            break
    return out


def learn_profile_message(message):
    """Record the author's self-facts + keep the speaker attribution."""
    if message.author.bot or message.guild is None:
        return
    facts = extract_facts(message.content)
    if not facts:
        return
    conn = db()
    row = conn.execute(
        "SELECT facts FROM profiles WHERE guild_id=? AND user_id=?",
        (str(message.guild.id), str(message.author.id)),
    ).fetchone()
    known = (row["facts"].split("\n") if row else [])
    for f in facts:
        if f not in known:
            known.append(f)
    known = known[-8:]
    conn.execute(
        """INSERT INTO profiles (guild_id, user_id, name, facts, at) VALUES (?, ?, ?, ?, ?)
           ON CONFLICT(guild_id, user_id)
           DO UPDATE SET name=excluded.name, facts=excluded.facts, at=excluded.at""",
        (str(message.guild.id), str(message.author.id),
         message.author.display_name[:60], "\n".join(known),
         datetime.datetime.now().isoformat()),
    )
    conn.commit()
    conn.close()


def _facts_text(parts) -> str:
    """Turn raw fact fragments into a readable list like 'likes fish, plays guitar'."""
    nice = []
    for p in parts:
        low = p.lower()
        if low.startswith(("a ", "an ", "the ")):
            nice.append(f"is {p}")
        else:
            nice.append(f"likes {p}")
    return ", ".join(nice)


def profile_facts(guild_id, user_id) -> str:
    """This member's learned profile as a sentence, or ''."""
    conn = db()
    row = conn.execute(
        "SELECT facts FROM profiles WHERE guild_id=? AND user_id=?",
        (str(guild_id), str(user_id)),
    ).fetchone()
    conn.close()
    if not row or not row["facts"]:
        return ""
    return _facts_text(row["facts"].split("\n"))


def profile_lines(guild_id, user_ids) -> list:
    """["name — likes fish", ...] for the given members (deduped, capped)."""
    ids = []

    def _seen(u):
        s = str(u)
        if s and s not in ids:
            ids.append(s)

    for u in user_ids:
        _seen(u)
    if not ids:
        return []
    q = ",".join("?" * len(ids))
    conn = db()
    rows = conn.execute(
        f"SELECT name, facts FROM profiles WHERE guild_id=? AND user_id IN ({q})",
        [str(guild_id), *ids],
    ).fetchall()
    conn.close()
    out = []
    for r in rows:
        if not r["facts"]:
            continue
        out.append(f"{r['name']} — {_facts_text(r['facts'].split('\n'))}")
    return out[:8]


def build_prompt(persona, context, question, instructions="", member_profiles=None):
    """Build the final LLM prompt.

    ``context`` is a list of dicts {"role","user_id","name","text"} from
    MemoryBank. ``member_profiles`` is a list of "name — likes X" strings from
    profile_lines(), shown so the model knows who's who without being told to
    guess facts.
    """
    today = datetime.datetime.now(datetime.timezone.utc).strftime("%B %d, %Y")
    lines = [
        persona,
        "",
        f"Today is {today} (UTC). Use it for anything time-related; never guess dates.",
        "The messages below are from real members of a Discord server.",
    ]
    if member_profiles:
        lines += ["", "What we know about some of these members (use it, don't repeat it):"]
        for line in member_profiles:
            lines.append(f"- {line}")
    if instructions:
        lines += ["", "SERVER INSTRUCTIONS (follow these, they override the above):", instructions]
    lines += ["", "Recent conversation:"]
    for m in context[-6:]:
        speaker = "you" if m["role"] == "bot" else (m["name"] or "member")
        lines.append(f"{speaker}: {m['text']}")
    lines += ["", f"the member just asked: {question}", "You reply:"]
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Fair AI queue — one model call at a time, spread fairly across servers
# ---------------------------------------------------------------------------

class BusyError(Exception):
    pass


class FairAIQueue:
    """Round-robin across guilds so one server can't hog the weak box.

    A single worker runs model calls one at a time. Each guild gets at most
    one slot per round; if a guild has too many waiting, it's told "busy".
    """

    def __init__(self, max_waiting=2, busy_reply="Quaestio's head is busy — one chat at a time. Ask again in a moment."):
        self._queues = {}
        self._worker = None
        self._max_waiting = max_waiting
        self.busy_reply = busy_reply

    def submit(self, guild_id, factory):
        fut = asyncio.get_running_loop().create_future()
        q = self._queues.setdefault(str(guild_id), [])
        if len(q) >= self._max_waiting:
            fut.set_exception(BusyError(self.busy_reply))
            return fut
        q.append((fut, factory))
        if self._worker is None or self._worker.done():
            self._worker = asyncio.create_task(self._run())
        return fut

    async def _run(self):
        try:
            pending = True
            while pending:
                pending = False
                for guild_id in list(self._queues):
                    q = self._queues[guild_id]
                    if not q:
                        continue
                    pending = True
                    fut, factory = q.pop(0)
                    if fut.cancelled():
                        continue
                    try:
                        result = await factory()
                        if not fut.done():
                            fut.set_result(result)
                    except Exception as exc:
                        if not fut.done():
                            fut.set_exception(exc)
                await asyncio.sleep(0)
        finally:
            self._worker = None


ai_queue = FairAIQueue()


# ---------------------------------------------------------------------------
# Human-like streaming (typing indicator + natural pauses)
# ---------------------------------------------------------------------------

async def human_type(channel, text, mention=""):
    """Stream a reply into the channel like a person typing.

    Shows the typing indicator, reveals the message in chunks via edit +
    small random pauses, so a fast local model still feels natural. An
    optional ``mention`` (e.g. a user ping) is glued to the first chunk.
    """
    chunks = []
    current = ""
    for token in text.split():
        if len(current) + len(token) + 1 > 350:
            chunks.append(current + " " if not current.endswith("\n") else current)
            current = token
        else:
            current = (current + " " + token).lstrip()
    if current:
        chunks.append(current)
    if not chunks:
        chunks = [text]
    if mention and chunks:
        chunks[0] = f"{mention} {chunks[0]}"

    async with channel.typing():
        await asyncio.sleep(0.35 + random.random() * 0.4)
        msg = await channel.send(chunks[0])
        for chunk in chunks[1:]:
            await asyncio.sleep(0.45 + random.random() * 0.5)
            new_text = (msg.content + " " + chunk).lstrip()
            if len(new_text) > 1990:
                break
            await msg.edit(content=new_text)
    return msg


_GOODBYE = (
    "go away", "goodbye", "bye bye", " bye", "shoo", "get lost",
    "leave me alone", "stop talking", "stop replying", "done talking",
    "that's all", "thats all", "never mind", "nevermind", "go to sleep",
)


def is_goodbye(text: str) -> bool:
    low = re.sub(r"<@!?[0-9]+>", "", text).lower().strip()
    return any(phrase in low or low == phrase.strip() for phrase in _GOODBYE)


async def ai_reply(message: discord.Message, *, ping: bool = True):
    """Passive AI chat: reply to an @-mention, or (ping=False) to a plain
    follow-up while conversation mode is active.

    Honors the same per-server rules as /ask: enabled, channel allowlist,
    quota, memory, instructions. Does not ping the author for follow-ups so
    a back-and-forth stays conversational.
    """
    guild_id = message.guild.id
    cfg = guild_ai_config(guild_id)
    if not cfg["enabled"] or not cfg["ai_mention"]:
        return False
    if not channel_allowed(guild_id, message.channel.id, cfg):
        return False
    if not quota_ok(guild_id, cfg["quota"], cfg["window"]):
        await _quota_notice(message)
        return False

    question = message.content[:400].replace(f"<@{message.guild.me.id}>", "").strip() or "…"
    context = memory.context(guild_id, message.channel.id, cfg["memory"])
    profiles = profile_lines(guild_id, [m.get("user_id") for m in context] + [message.author.id])
    full_prompt = build_prompt(cfg["persona"], context, question, cfg["instructions"], profiles)

    async def factory():
        return await ask_ollama(
            cfg["endpoint"], cfg["model"], full_prompt,
            cfg.get("temperature", 0.8), cfg.get("max_tokens", 400),
        )

    fut = ai_queue.submit(guild_id, factory)
    try:
        answer = await asyncio.wait_for(fut, timeout=OLLAMA_TIMEOUT + 30)
        await asyncio.sleep(0)
    except (BusyError, asyncio.TimeoutError, ConnectionError):
        return False
    except asyncio.CancelledError:
        raise

    quota_tick(guild_id, cfg["window"])
    memory.push(guild_id, message.channel.id, "user", question, cfg["memory"],
                user_id=message.author.id, name=message.author.display_name)
    memory.push(guild_id, message.channel.id, "bot", answer[:400], cfg["memory"],
                user_id=message.guild.me.id, name=message.guild.me.display_name)
    await human_type(message.channel, answer, mention=message.author.mention if ping else "")
    return True


# ---------------------------------------------------------------------------
# DMs — the bot chats with anyone who messages it directly
# ---------------------------------------------------------------------------

_quota_notice_at = {}


async def _quota_notice(message):
    """Tell a channel once per 30 min that the AI quota blocked a reply."""
    key = (message.guild.id, message.channel.id)
    now = time.time()
    if now - _quota_notice_at.get(key, 0) < 1800:
        return
    _quota_notice_at[key] = now
    try:
        await message.channel.send(
            "⏳ This server hit its AI quota for this hour, so I went quiet. "
            "It resets on the hour — the number is in the web panel under AI → Quota."
        )
    except discord.Forbidden:
        pass


def host_cfg():
    """The host operator's own AI box (used for DMs and as managed-mode source)."""
    h = lambda k, d: get_cfg("host", k, d)
    return {
        "endpoint": h("ai_endpoint", OLLAMA_BASE_URL),
        "model": h("ai_model", OLLAMA_MODEL),
        "memory": max(1, int(h("ai_memory", MEMORY_DEFAULT) or MEMORY_DEFAULT)),
        "instructions": h("ai_instructions", ""),
        "persona": persona_from(
            h("ai_personality", "none"), h("ai_character", ""),
            guild_presets("host", "personality"), guild_presets("host", "character"),
        ),
        "quota": max(0, int(h("ai_quota", "0") or 0)),
        "temperature": float(h("ai_temperature", "0.7") or 0.7),
        "max_tokens": int(h("ai_max_tokens", "400") or 400),
        "window": max(1, int(h("ai_window", "6") or 6)),
        "enabled": flag_on("host", "ai_enabled", "1"),
        "dm_enabled": flag_on("host", "ai_dm", "1"),
    }


async def dm_chat(channel, question, cfg, mention="", user_id="", name=""):
    """Run one AI turn in a DM (or a /ask inside a DM)."""
    if not cfg["enabled"]:
        await channel.send("AI chat is disabled right now.")
        return
    if not cfg["dm_enabled"]:
        await channel.send("DM chat is switched off — try mentioning the bot in a server instead.")
        return
    if not quota_ok("dm", cfg["quota"], cfg["window"]):
        await channel.send(
            "⏳ This hour's AI quota is used up — it resets on the hour. "
            "Keep chatting after that, or raise the limit in the web panel."
        )
        return

    context = memory.context("dm", channel.id, cfg["memory"])
    who = [m.get("user_id") for m in context]
    full_prompt = build_prompt(cfg["persona"], context, question, cfg["instructions"], profile_lines("dm", who))

    async def factory():
        return await ask_ollama(
            cfg["endpoint"], cfg["model"], full_prompt,
            cfg["temperature"], cfg["max_tokens"],
        )

    fut = ai_queue.submit("dm", factory)
    try:
        answer = await asyncio.wait_for(fut, timeout=OLLAMA_TIMEOUT + 30)
        await asyncio.sleep(0)
    except BusyError as exc:
        await channel.send(str(exc))
        return
    except asyncio.TimeoutError:
        await channel.send("The AI took too long. Try again in a moment.")
        return
    except ConnectionError as exc:
        await channel.send(f"⚠️ {exc}")
        return
    except asyncio.CancelledError:
        raise

    quota_tick("dm", cfg["window"])
    memory.push("dm", channel.id, "user", question, cfg["memory"], user_id=user_id, name=name)
    memory.push("dm", channel.id, "bot", answer[:400], cfg["memory"])
    await human_type(channel, answer, mention=mention)


async def dm_reply(message: discord.Message):
    """Mention-style chat in DMs: any message to the bot gets an answer."""
    question = message.content[:400].strip() or "…"
    await dm_chat(message.channel, question, host_cfg(), mention=message.author.mention,
                  user_id=message.author.id, name=message.author.display_name)


# ---------------------------------------------------------------------------
# Leveling helpers
# ---------------------------------------------------------------------------

def xp_for_level(level: int) -> int:
    return 5 * (level ** 2) + 50 * level + 100


def add_xp(guild_id, user_id):
    conn = db()
    conn.execute(
        """INSERT INTO xp (guild_id, user_id, messages) VALUES (?, ?, 1)
           ON CONFLICT(guild_id, user_id)
           DO UPDATE SET messages = messages + 1""",
        (str(guild_id), str(user_id)),
    )
    row = conn.execute(
        "SELECT messages FROM xp WHERE guild_id=? AND user_id=?",
        (str(guild_id), str(user_id)),
    ).fetchone()
    conn.commit()
    conn.close()
    return row["messages"]


def level_for_messages(messages: int) -> int:
    level = 0
    while messages >= xp_for_level(level + 1) and level < 100:
        level += 1
    return level


def is_admin(user: discord.Member) -> bool:
    return user.guild_permissions.administrator


# ---------------------------------------------------------------------------
# Event hooks
# ---------------------------------------------------------------------------

@bot.event
async def on_ready():
    db_init()
    command_count = len(bot.tree.get_commands()) + sum(
        len(g.commands) for g in bot.tree.get_commands() if isinstance(g, app_commands.Group)
    )
    activity = discord.Activity(
        type=discord.ActivityType.watching,
        name="/ask",
        details=f"AI · {OLLAMA_MODEL}",
        state=f"{command_count} commands · free",
        assets={"large_image": RPC_LARGE_IMAGE},
    )
    if RPC_SMALL_IMAGE:
        activity.assets["small_image"] = RPC_SMALL_IMAGE
    await bot.change_presence(activity=activity)
    print(f"quaestio: logged in as {bot.user} · {len(bot.guilds)} servers")
    try:
        synced = await bot.tree.sync()
        print(f"quaestio: {len(synced)} slash commands synced")
    except Exception as exc:
        print(f"quaestio: sync failed: {exc}")
    if not getattr(bot, "_bday_task", None) or bot._bday_task.done():
        bot._bday_task = bot.loop.create_task(birthday_loop())


@bot.event
async def on_message(message: discord.Message):
    if message.author.bot:
        return
    learn_profile_message(message)
    if message.content.startswith(PREFIX):
        await bot.process_commands(message)
        return
    if message.guild is None:
        await dm_reply(message)
        return
    # Passive AI: only a direct @Quaestio wakes it. With conversation mode on, a
    # plain message also replies while the bot is "still here" (conv_live) — no
    # @ needed — but messages aimed at *other people* (a random @mention) never
    # wake it, and neither does /ask (see the ask command). Saying "go away"
    # ends the conversation immediately.
    _ai_cfg = guild_ai_config(message.guild.id)
    mentions_me = message.guild.me in message.mentions
    aimed_at_others = any(m != message.guild.me for m in message.mentions)
    if conv_live(message.guild.id, message.channel.id, _ai_cfg) and is_goodbye(message.content):
        await _say_goodbye(message)
    elif mentions_me:
        if await ai_reply(message) and _ai_cfg.get("conv"):
            conv_mark(message.guild.id, message.channel.id, _ai_cfg["conv_minutes"])
    elif conv_live(message.guild.id, message.channel.id, _ai_cfg) and not aimed_at_others:
        if await ai_reply(message, ping=False):
            conv_mark(message.guild.id, message.channel.id, _ai_cfg["conv_minutes"])

    if not flag_on(message.guild.id, "xp_enabled", "1"):
        return
    messages = add_xp(message.guild.id, message.author.id)
    new_level = level_for_messages(messages)
    old_level = level_for_messages(messages - 1)
    if new_level > old_level and new_level > 1:
        if flag_on(message.guild.id, "level_announce", "1"):
            try:
                await message.channel.send(
                    f"🎉 {message.author.mention} reached **level {new_level}**!"
                )
            except discord.Forbidden:
                pass
        role_id = get_cfg(message.guild.id, "levelrole")
        if role_id:
            role = message.guild.get_role(int(role_id))
            if role:
                try:
                    await message.author.add_roles(role)
                except discord.Forbidden:
                    pass


@bot.event
async def on_member_join(member: discord.Member):
    if member.bot or not flag_on(member.guild.id, "welcome_enabled", "1"):
        return
    role_id = get_cfg(member.guild.id, "welcome_role")
    if role_id:
        role = member.guild.get_role(int(role_id))
        if role:
            try:
                await member.add_roles(role)
            except discord.Forbidden:
                pass
    channel_id = get_cfg(member.guild.id, "welcome_channel")
    if not channel_id:
        return
    channel = member.guild.get_channel(int(channel_id))
    if not channel:
        return
    text = get_cfg(
        member.guild.id, "welcome_message",
        f"Welcome to {member.guild.name}, {member.mention}! 👋",
    )
    try:
        await channel.send(f"{text}")
    except discord.Forbidden:
        pass


# ---------------------------------------------------------------------------
# Core
# ---------------------------------------------------------------------------

@bot.tree.command(name="ping", description="Check the bot's latency.")
async def ping(interaction: discord.Interaction):
    await interaction.response.send_message(
        f"🏓 Pong! `{round(bot.latency * 1000)}ms`", ephemeral=True
    )


@bot.tree.command(name="uptime", description="How long has the bot been running?")
async def uptime(interaction: discord.Interaction):
    secs = int(time.time() - START_TIME)
    days, rem = divmod(secs, 86400)
    hours, rem = divmod(rem, 3600)
    mins, secs = divmod(rem, 60)
    await interaction.response.send_message(
        f"⏱️ Up for {days}d {hours}h {mins}m {secs}s", ephemeral=True
    )


@bot.tree.command(name="about", description="What is Quaestio?")
async def about(interaction: discord.Interaction):
    embed = discord.Embed(
        title="Quaestio",
        description=(
            "Your server's own AI companion. Free, self-hosted, private.\n"
            "AI chat · XP levels · moderation · tags · welcomes.\n"
            "More: https://quaestio.online"
        ),
        color=0xA78BFA,
    )
    await interaction.response.send_message(embed=embed, ephemeral=True)


@bot.tree.command(name="invite", description="Invite Quaestio to another server.")
async def invite(interaction: discord.Interaction):
    app = await bot.application_info()
    await interaction.response.send_message(
        f"📨 Invite me here: https://discord.com/oauth2/authorize?client_id={app.id}&permissions=1101994781766&scope=bot",
        ephemeral=True,
    )


@bot.tree.command(name="8ball", description="Ask the magic 8-ball a question.")
@app_commands.describe(question="Your question")
async def eightball(interaction: discord.Interaction, question: str):
    answers = [
        "🎱 It is certain.", "🎱 It is decidedly so.", "🎱 Without a doubt.",
        "🎱 Yes — definitely.", "🎱 You may rely on it.", "🎱 As I see it, yes.",
        "🎱 Most likely.", "🎱 Outlook good.", "🎱 Signs point to yes.",
        "🎱 Reply hazy, try again.", "🎱 Ask again later.", "🎱 Better not tell you now.",
        "🎱 Cannot predict now.", "🎱 Concentrate and ask again.",
        "🎱 Don't count on it.", "🎱 My reply is no.", "🎱 My sources say no.",
        "🎱 Outlook not so good.", "🎱 Very doubtful.",
    ]
    await interaction.response.send_message(
        f"> {question}\n{random.choice(answers)}"
    )


# ---------------------------------------------------------------------------
# AI
# ---------------------------------------------------------------------------

AI_GROUP = app_commands.Group(name="ai", description="AI settings (admins only)")


async def ai_model_autocomplete(interaction: discord.Interaction, current: str):
    endpoint = guild_ai_config(interaction.guild.id)["endpoint"]
    models = await asyncio.to_thread(list_ollama_models, endpoint)
    models = [m for m in models if current.lower() in m.lower()][:20]
    if not models:
        return [app_commands.Choice(name=f"default ({OLLAMA_MODEL})", value="default")]
    return [app_commands.Choice(name=m, value=m) for m in models]


@AI_GROUP.command(name="model", description="Choose an AI model (default = host's model).")
@app_commands.describe(model="Pick from models on your configured AI host, or 'default'")
@app_commands.autocomplete(model=ai_model_autocomplete)
async def ai_model_selector(interaction: discord.Interaction, model: str):
    if interaction.guild is None:
        await interaction.response.send_message("Use `/ai model` inside a server.", ephemeral=True)
        return
    if not is_admin(interaction.user):
        await interaction.response.send_message("Needs Administrator.", ephemeral=True)
        return
    if model.lower() in ("default", "reset", "off"):
        set_cfg(interaction.guild.id, "ai_model", "")
        await interaction.response.send_message("AI model reset to the host default.")
        return
    set_cfg(interaction.guild.id, "ai_model", model)
    await interaction.response.send_message(f"AI model → **{model}** on this server.")


@AI_GROUP.command(name="toggle", description="Enable or disable AI chat on this server.")
@app_commands.describe(enabled="true to enable, false to disable")
async def ai_toggle(interaction: discord.Interaction, enabled: bool):
    if interaction.guild is None:
        await interaction.response.send_message("Use `/ai toggle` inside a server.", ephemeral=True)
        return
    if not is_admin(interaction.user):
        await interaction.response.send_message("Needs Administrator.", ephemeral=True)
        return
    set_cfg(interaction.guild.id, "ai_enabled", "1" if enabled else "0")
    await interaction.response.send_message(f"AI chat {'enabled' if enabled else 'disabled'}.")


def preset_choice_items(guild_id, kind):
    """Autocomplete choices: 'none' + built-in + custom preset names."""
    found = {"none"}
    for name in PERSONALITIES if kind == "personality" else CHARACTERS:
        found.add(name)
    for name in guild_presets(guild_id, kind):
        found.add(name)
    return [app_commands.Choice(name=n, value=n) for n in sorted(found)]


async def _personality_ac(interaction: discord.Interaction, current: str):
    """Autocomplete callback (must be a coroutine function)."""
    return preset_choice_items(interaction.guild_id or 0, "personality")


async def _character_ac(interaction: discord.Interaction, current: str):
    """Autocomplete callback (must be a coroutine function)."""
    return preset_choice_items(interaction.guild_id or 0, "character")


@AI_GROUP.command(name="personality", description="Set the bot's personality tone (or 'none').")
@app_commands.describe(name="Personality name, or 'none'")
@app_commands.autocomplete(name=_personality_ac)
async def ai_personality(interaction: discord.Interaction, name: str):
    if interaction.guild is None:
        await interaction.response.send_message("Use `/ai personality` inside a server.", ephemeral=True)
        return
    if not is_admin(interaction.user):
        await interaction.response.send_message("Needs Administrator.", ephemeral=True)
        return
    key = name.strip()
    if key == "none":
        set_cfg(interaction.guild.id, "ai_personality", "none")
        await interaction.response.send_message("Personality → **none** (default buddy).")
        return
    if key not in PERSONALITIES and key not in guild_presets(interaction.guild.id, "personality"):
        await interaction.response.send_message(f"Unknown personality `{key}`.", ephemeral=True)
        return
    set_cfg(interaction.guild.id, "ai_personality", key)
    await interaction.response.send_message(f"Personality → **{key}**.")


@AI_GROUP.command(name="character", description="Set how the bot pretends to be (or 'none').")
@app_commands.describe(name="Character name, or 'none'")
@app_commands.autocomplete(name=_character_ac)
async def ai_character(interaction: discord.Interaction, name: str):
    if interaction.guild is None:
        await interaction.response.send_message("Use `/ai character` inside a server.", ephemeral=True)
        return
    if not is_admin(interaction.user):
        await interaction.response.send_message("Needs Administrator.", ephemeral=True)
        return
    key = name.strip()
    if key == "none":
        set_cfg(interaction.guild.id, "ai_character", "")
        await interaction.response.send_message("Character → **none**.")
        return
    if key not in CHARACTERS and key not in guild_presets(interaction.guild.id, "character"):
        await interaction.response.send_message(f"Unknown character `{key}`.", ephemeral=True)
        return
    set_cfg(interaction.guild.id, "ai_character", key)
    await interaction.response.send_message(f"Character → **{key}**.")


@AI_GROUP.command(name="status", description="Show this server's AI settings.")
async def ai_status(interaction: discord.Interaction):
    if interaction.guild is None:
        await interaction.response.send_message("Use `/ai status` inside a server.", ephemeral=True)
        return
    cfg = guild_ai_config(interaction.guild.id)
    allowed_note = "everywhere" if not (cfg["ai_channels"] or "").strip() else "picked channels only"
    source_note = "shared Quaestio box" if cfg["source"] == "shared" else (f"your own box{f' (in community pool)' if cfg['contribute'] else ''}")
    persona_note = ""
    if cfg.get("ai_character"):
        persona_note = f"\nCharacter: `{cfg['ai_character']}`"
    personality = get_cfg(interaction.guild.id, "ai_personality", "none")
    await interaction.response.send_message(
        f"**AI settings**\n"
        f"Enabled: {'✅' if cfg['enabled'] else '❌'}\n"
        f"Source: {source_note}\n"
        f"Model: `{cfg['model']}`\n"
        f"Endpoint: `{cfg['endpoint']}`\n"
        f"Personality: `{personality or 'none'}` · Memory: {cfg['memory']} turns/channel\n"
        f"Quota: {cfg['quota']} calls/{cfg['window']}h {'(unlimited)' if not cfg['quota'] else ''}\n{persona_note}"
        f"\nReplies on mention: {'✅' if cfg['ai_mention'] else '❌'}\n"
        f"Conversation mode: {'✅ stays ' + str(cfg['conv_minutes']) + ' min after a reply' if cfg['conv'] else '❌ (needs @ each time)'}\n"
        f"Allowed channels: {allowed_note}\n"
        f"Creativity: {cfg['temperature']} · Max reply: {cfg['max_tokens']} tokens",
        ephemeral=True,
    )


@AI_GROUP.command(name="clear", description="Forget this channel's conversation memory.")
async def ai_clear(interaction: discord.Interaction):
    if interaction.guild is None:
        await interaction.response.send_message("Use `/ai clear` inside a server channel.", ephemeral=True)
        return
    memory.clear(interaction.guild.id, interaction.channel.id)
    await interaction.response.send_message("🧹 Memory cleared for this channel.", ephemeral=True)


def _remember_reply(interaction, answer, prompt):
    cfg = guild_ai_config(interaction.guild.id)
    question = (prompt or "")[:400]
    memory.push(interaction.guild.id, interaction.channel.id, "user", question, cfg["memory"],
                user_id=interaction.user.id, name=interaction.user.display_name)
    memory.push(interaction.guild.id, interaction.channel.id, "bot", answer[:400], cfg["memory"],
                user_id=interaction.guild.me.id, name=interaction.guild.me.display_name)


@bot.tree.command(name="ask", description="Chat with Quaestio's local AI.")
@app_commands.describe(prompt="What you want to say or ask")
async def ask(interaction: discord.Interaction, prompt: str):
    if interaction.guild is None:
        await interaction.response.defer(thinking=True)
        await dm_chat(interaction.channel, prompt[:400], host_cfg(),
                      mention=interaction.user.mention,
                      user_id=interaction.user.id, name=interaction.user.display_name)
        await interaction.followup.send("▸ sent", ephemeral=True)
        return
    cfg = guild_ai_config(interaction.guild.id)
    # /ask is an explicit, one-shot question: it never wakes conversation mode
    # (only @Quaestio does).
    _conv_until.pop((interaction.guild.id, interaction.channel.id), None)
    if not cfg["enabled"]:
        await interaction.response.send_message("AI chat is disabled here.", ephemeral=True)
        return
    if not quota_ok(interaction.guild.id, cfg["quota"], cfg["window"]):
        await interaction.response.send_message(
            "⚠️ This server has hit its AI quota for this hour (set in the dashboard).",
            ephemeral=True,
        )
        return
    if not channel_allowed(interaction.guild.id, interaction.channel.id, cfg):
        await interaction.response.send_message(
            "AI chat is switched off in this channel — it's only allowed in the channels picked in the dashboard.",
            ephemeral=True,
        )
        return
    await interaction.response.defer(thinking=True)

    context = memory.context(interaction.guild.id, interaction.channel.id, cfg["memory"])
    profiles = profile_lines(interaction.guild.id, [m.get("user_id") for m in context] + [interaction.user.id])
    full_prompt = build_prompt(cfg["persona"], context, prompt, cfg["instructions"], profiles)

    async def factory():
        return await ask_ollama(
            cfg["endpoint"], cfg["model"], full_prompt,
            cfg["temperature"], cfg["max_tokens"],
        )

    fut = ai_queue.submit(interaction.guild.id, factory)
    try:
        async with interaction.channel.typing():
            answer = await asyncio.wait_for(fut, timeout=OLLAMA_TIMEOUT + 30)
            await asyncio.sleep(0)
    except BusyError as exc:
        await interaction.followup.send(str(exc))
        return
    except asyncio.TimeoutError:
        await interaction.followup.send("The AI took too long. Try again in a moment.")
        return
    except ConnectionError as exc:
        await interaction.followup.send(f"⚠️ {exc}")
        return
    except asyncio.CancelledError:
        raise

    quota_tick(interaction.guild.id, cfg["window"])
    _remember_reply(interaction, answer, prompt)
    await human_type(interaction.channel, answer, mention=interaction.user.mention)


PANEL_URL = os.environ.get("PANEL_URL", "https://admin.quaestio.online")


@bot.tree.command(name="panel", description="Open this server's web settings panel.")
async def panel(interaction: discord.Interaction):
    await interaction.response.send_message(
        "🛠️ **Quaestio web panel**\n"
        f"⚙️ Settings: {PANEL_URL}\n"
        "Sign in with Discord **as an admin of this server** to change AI settings, "
        "custom instructions, welcomes, and more.\n"
        "Settings you see in Discord stay here too — the panel is just easier.",
        ephemeral=True,
    )


@bot.tree.command(name="summarize", description="Summarize the last N messages in this channel.")
@app_commands.describe(limit="How many messages to summarize (default 20, max 60)")
async def summarize(interaction: discord.Interaction, limit: int = 20):
    if interaction.guild is None:
        await interaction.response.send_message("Summarize works in a server's channel, not DMs.", ephemeral=True)
        return
    cfg = guild_ai_config(interaction.guild.id)
    if not cfg["enabled"]:
        await interaction.response.send_message("AI chat is disabled here.", ephemeral=True)
        return
    if not channel_allowed(interaction.guild.id, interaction.channel.id, cfg):
        await interaction.response.send_message(
            "AI chat is switched off in this channel — it's only allowed in the channels picked in the dashboard.",
            ephemeral=True,
        )
        return
    limit = max(1, min(limit, 60))
    await interaction.response.defer(thinking=True)
    texts = []
    async for msg in interaction.channel.history(limit=limit):
        if msg.author.bot:
            continue
        texts.append(f"{msg.author.display_name}: {msg.content[:200]}")
        if len(texts) >= 60:
            break
    if not texts:
        await interaction.followup.send("Nothing to summarize.")
        return
    prompt = (
        "Summarize these Discord messages in a few short bullets. Keep it neutral "
        "and concise.\n\n" + "\n".join(reversed(texts))
    )
    if cfg["instructions"]:
        prompt += "\n\nFollow these server instructions where relevant:\n" + cfg["instructions"]

    async def factory():
        return await ask_ollama(
            cfg["endpoint"], cfg["model"], prompt, cfg["temperature"], cfg["max_tokens"]
        )

    fut = ai_queue.submit(interaction.guild.id, factory)
    try:
        async with interaction.channel.typing():
            answer = await asyncio.wait_for(fut, timeout=OLLAMA_TIMEOUT + 30)
    except BusyError as exc:
        await interaction.followup.send(str(exc))
        return
    except asyncio.TimeoutError:
        await interaction.followup.send("The AI took too long. Try again in a moment.")
        return
    except ConnectionError as exc:
        await interaction.followup.send(f"⚠️ {exc}")
        return

    await interaction.followup.send(
        f"📄 **Summary of last {len(texts)} messages**\n{answer[:1900]}"
    )


bot.tree.add_command(AI_GROUP)


# ---------------------------------------------------------------------------
# Levels
# ---------------------------------------------------------------------------

@bot.tree.command(name="rank", description="Check your XP and level.")
@app_commands.describe(member="Member to check (defaults to you)")
async def rank(interaction: discord.Interaction, member: discord.Member = None):
    member = member or interaction.user
    conn = db()
    row = conn.execute(
        "SELECT messages FROM xp WHERE guild_id=? AND user_id=?",
        (str(interaction.guild.id), str(member.id)),
    ).fetchone()
    conn.close()
    messages = row["messages"] if row else 0
    level = level_for_messages(messages)
    await interaction.response.send_message(
        f"{member.mention} — **Level {level}** · {messages} messages "
        f"(next level at {xp_for_level(level + 1)})",
        ephemeral=True,
    )


@bot.tree.command(name="profile", description="What Quaestio has learned about a member.")
@app_commands.describe(member="Member to check (defaults to you)")
async def profile(interaction: discord.Interaction, member: discord.Member = None):
    if interaction.guild is None:
        await interaction.response.send_message("Use `/profile` inside a server.", ephemeral=True)
        return
    member = member or interaction.user
    facts = profile_facts(interaction.guild.id, member.id)
    if not facts:
        await interaction.response.send_message(
            f"{member.display_name} — I haven't learned anything about them yet. "
            "Say things like *'I like fish'* and I'll start remembering.",
            ephemeral=True,
        )
        return
    await interaction.response.send_message(
        f"🧠 **What I know about {member.display_name}**\n{facts}",
        ephemeral=True,
    )


@bot.tree.command(name="leaderboard", description="Top chatters by XP in this server.")
@app_commands.describe(top="How many to show (default 10, max 25)")
async def leaderboard(interaction: discord.Interaction, top: int = 10):
    if interaction.guild is None:
        await interaction.response.send_message("Leaderboard works inside a server.", ephemeral=True)
        return
    top = max(3, min(top, 25))
    conn = db()
    rows = conn.execute(
        "SELECT user_id, messages FROM xp WHERE guild_id=? ORDER BY messages DESC LIMIT ?",
        (str(interaction.guild.id), top),
    ).fetchall()
    conn.close()
    if not rows:
        await interaction.response.send_message("No XP yet — get people chatting first!", ephemeral=True)
        return
    medals = ["🥇", "🥈", "🥉"]
    lines = ["**🏆 Top chatters**"]
    for i, r in enumerate(rows):
        member = interaction.guild.get_member(int(r["user_id"]))
        name = member.display_name if member else f"<@{r['user_id']}>"
        lines.append(f"{medals[i] if i < 3 else f'{i + 1}.'} **{name}** — Lv {level_for_messages(r['messages'])} · {r['messages']} msgs")
    await interaction.response.send_message("\n".join(lines))


# ---------------------------------------------------------------------------
# Moderation
# ---------------------------------------------------------------------------

def _warn_db(guild_id, user_id, reason):
    conn = db()
    conn.execute(
        "INSERT INTO warned (guild_id, user_id, reason, at) VALUES (?, ?, ?, ?)",
        (str(guild_id), str(user_id), reason, datetime.datetime.now().isoformat()),
    )
    conn.commit()
    count = conn.execute(
        "SELECT COUNT(*) AS n FROM warned WHERE guild_id=? AND user_id=?",
        (str(guild_id), str(user_id)),
    ).fetchone()["n"]
    conn.close()
    return count


@bot.tree.command(name="warn", description="Warn a member.")
@app_commands.describe(member="Member to warn", reason="Reason")
async def warn(interaction: discord.Interaction, member: discord.Member, reason: str = "No reason"):
    if not is_admin(interaction.user):
        await interaction.response.send_message("Needs Administrator.", ephemeral=True)
        return
    count = _warn_db(interaction.guild.id, member.id, reason)
    limit = int(get_cfg(interaction.guild.id, "warnlimit") or WARN_LIMIT_DEFAULT)
    msg = f"⚠️ {member.mention} warned — **{count}/{limit}**\n> {reason}"
    await interaction.response.send_message(msg)
    if count >= limit:
        try:
            await member.kick(reason=f"Reached warn limit ({count}).")
        except discord.Forbidden:
            pass
        await interaction.followup.send(f"{member.display_name} auto-kicked (warn limit).")


@bot.tree.command(name="warns", description="List a member's warnings.")
@app_commands.describe(member="Member to check")
async def warns(interaction: discord.Interaction, member: discord.Member):
    conn = db()
    rows = conn.execute(
        "SELECT reason, at FROM warned WHERE guild_id=? AND user_id=?",
        (str(interaction.guild.id), str(member.id)),
    ).fetchall()
    conn.close()
    if not rows:
        await interaction.response.send_message(f"{member.mention} has no warnings. ✅")
        return
    lines = [f"**{member.display_name}** — {len(rows)} warning(s):"]
    for r in rows:
        lines.append(f"- {r['at'][:10]}: {r['reason']}")
    await interaction.response.send_message("\n".join(lines))


@bot.tree.command(name="delwarns", description="Clear all warnings for a member.")
@app_commands.describe(member="Member to clear")
async def delwarns(interaction: discord.Interaction, member: discord.Member):
    if not is_admin(interaction.user):
        await interaction.response.send_message("Needs Administrator.", ephemeral=True)
        return
    conn = db()
    conn.execute(
        "DELETE FROM warned WHERE guild_id=? AND user_id=?",
        (str(interaction.guild.id), str(member.id)),
    )
    conn.commit()
    conn.close()
    await interaction.response.send_message(f"Cleared warnings for {member.mention}.")


@bot.tree.command(name="kick", description="Kick a member.")
@app_commands.describe(member="Member to kick", reason="Reason")
async def kick(interaction: discord.Interaction, member: discord.Member, reason: str = "No reason"):
    if not is_admin(interaction.user):
        await interaction.response.send_message("Needs Administrator.", ephemeral=True)
        return
    try:
        await member.kick(reason=reason)
    except discord.Forbidden:
        await interaction.response.send_message("I can't kick that member.", ephemeral=True)
        return
    await interaction.response.send_message(f"👢 Kicked {member.display_name} — {reason}")


@bot.tree.command(name="ban", description="Ban a member.")
@app_commands.describe(member="Member to ban", reason="Reason")
async def ban(interaction: discord.Interaction, member: discord.Member, reason: str = "No reason"):
    if not is_admin(interaction.user):
        await interaction.response.send_message("Needs Administrator.", ephemeral=True)
        return
    try:
        await member.ban(reason=reason)
    except discord.Forbidden:
        await interaction.response.send_message("I can't ban that member.", ephemeral=True)
        return
    await interaction.response.send_message(f"🔨 Banned {member.display_name} — {reason}")


@bot.tree.command(name="unban", description="Unban a user by name.")
@app_commands.describe(user="Name of the banned user")
async def unban(interaction: discord.Interaction, user: str):
    if not is_admin(interaction.user):
        await interaction.response.send_message("Needs Administrator.", ephemeral=True)
        return
    banned = [entry async for entry in interaction.guild.bans()]
    target = next((e for e in banned if user.lower() in str(e.user).lower()), None)
    if target is None:
        await interaction.response.send_message(f"No banned user matching `{user}`.", ephemeral=True)
        return
    await interaction.guild.unban(target.user, reason="Quaestio unban")
    await interaction.response.send_message(f"🔓 Unbanned {target.user}.")


@bot.tree.command(name="purge", description="Bulk-delete recent messages.")
@app_commands.describe(count="How many to delete (max 100)")
async def purge(interaction: discord.Interaction, count: int = 20):
    if not is_admin(interaction.user):
        await interaction.response.send_message("Needs Administrator.", ephemeral=True)
        return
    count = max(1, min(count, 100))
    deleted = await interaction.channel.purge(limit=count)
    await interaction.response.send_message(
        f"🧹 Purged {len(deleted)} messages.", delete_after=5
    )


@bot.tree.command(name="mute", description="Timeout a member.")
@app_commands.describe(member="Member to mute", minutes="How many minutes", reason="Reason")
async def mute(interaction: discord.Interaction, member: discord.Member, minutes: int = 10, reason: str = "No reason"):
    if not is_admin(interaction.user):
        await interaction.response.send_message("Needs Administrator.", ephemeral=True)
        return
    duration = datetime.timedelta(minutes=max(1, min(minutes, 10080)))
    until = discord.utils.utcnow() + duration
    try:
        await member.timeout(until, reason=reason)
    except discord.Forbidden:
        await interaction.response.send_message("I can't mute that member.", ephemeral=True)
        return
    await interaction.response.send_message(
        f"🔇 Timed out {member.display_name} for {duration.days * 24 + duration.seconds // 3600}h ({reason})"
    )


@bot.tree.command(name="unmute", description="Remove a timeout.")
@app_commands.describe(member="Member to unmute")
async def unmute(interaction: discord.Interaction, member: discord.Member):
    if not is_admin(interaction.user):
        await interaction.response.send_message("Needs Administrator.", ephemeral=True)
        return
    await member.timeout(None)
    await interaction.response.send_message(f"🔊 Unmuted {member.display_name}.")


# ---------------------------------------------------------------------------
# Tags
# ---------------------------------------------------------------------------

@bot.tree.command(name="tag", description="Show a saved tag.")
@app_commands.describe(name="Tag name")
async def tag(interaction: discord.Interaction, name: str):
    conn = db()
    row = conn.execute(
        "SELECT content FROM tags WHERE guild_id=? AND name=lower(?)",
        (str(interaction.guild.id), name),
    ).fetchone()
    conn.close()
    if not row:
        await interaction.response.send_message(f"Tag `{name}` not found.", ephemeral=True)
        return
    await interaction.response.send_message(row["content"])


@bot.tree.command(name="tagcreate", description="Create a tag.")
@app_commands.describe(name="Tag name", content="Tag content")
async def tagcreate(interaction: discord.Interaction, name: str, content: str):
    if not is_admin(interaction.user):
        await interaction.response.send_message("Needs Administrator.", ephemeral=True)
        return
    conn = db()
    try:
        conn.execute(
            """INSERT INTO tags (guild_id, name, content, author, at) VALUES (?, lower(?), ?, ?, ?)""",
            (str(interaction.guild.id), name, content, str(interaction.user.id),
             datetime.datetime.now().isoformat()),
        )
        conn.commit()
    except sqlite3.IntegrityError:
        conn.close()
        await interaction.response.send_message(f"Tag `{name}` already exists.", ephemeral=True)
        return
    conn.close()
    await interaction.response.send_message(f"📌 Tag `{name}` created.")


@bot.tree.command(name="tagdelete", description="Delete a tag.")
@app_commands.describe(name="Tag name")
async def tagdelete(interaction: discord.Interaction, name: str):
    if not is_admin(interaction.user):
        await interaction.response.send_message("Needs Administrator.", ephemeral=True)
        return
    conn = db()
    cur = conn.execute(
        "DELETE FROM tags WHERE guild_id=? AND name=lower(?)",
        (str(interaction.guild.id), name),
    )
    conn.commit()
    conn.close()
    if cur.rowcount:
        await interaction.response.send_message(f"🗑️ Tag `{name}` deleted.")
    else:
        await interaction.response.send_message(f"Tag `{name}` not found.", ephemeral=True)


@bot.tree.command(name="tags", description="List all tags in this server.")
async def tags(interaction: discord.Interaction):
    conn = db()
    rows = conn.execute(
        "SELECT name FROM tags WHERE guild_id=? ORDER BY name", (str(interaction.guild.id),)
    ).fetchall()
    conn.close()
    if not rows:
        await interaction.response.send_message("No tags yet. Create one with /tagcreate.")
    else:
        names = ", ".join(r["name"] for r in rows)
        await interaction.response.send_message(f"📚 **Tags:** {names}")


# ---------------------------------------------------------------------------
# Birthdays
# ---------------------------------------------------------------------------

BDAY_GROUP = app_commands.Group(name="birthday", description="Birthday reminders")


@BDAY_GROUP.command(name="set", description="Save your birthday (month/day).")
@app_commands.describe(month="Birth month (1-12)", day="Birth day (1-31)")
async def bday_set(interaction: discord.Interaction, month: int, day: int):
    if interaction.guild is None:
        await interaction.response.send_message("Use `/birthday set` inside a server.", ephemeral=True)
        return
    if not (1 <= month <= 12 and 1 <= day <= 31):
        await interaction.response.send_message("Pick a valid month (1-12) and day (1-31).", ephemeral=True)
        return
    conn = db()
    conn.execute(
        """INSERT INTO birthdays (guild_id, user_id, month, day) VALUES (?, ?, ?, ?)
           ON CONFLICT(guild_id, user_id)
           DO UPDATE SET month=excluded.month, day=excluded.day""",
        (str(interaction.guild.id), str(interaction.user.id), str(month), str(day)),
    )
    conn.commit()
    conn.close()
    await interaction.response.send_message(
        f"🎂 Birthday saved as **{month}/{day}**. I'll wish you a note in the server's birthday channel.",
        ephemeral=True,
    )


@BDAY_GROUP.command(name="remove", description="Remove your birthday.")
async def bday_remove(interaction: discord.Interaction):
    if interaction.guild is None:
        await interaction.response.send_message("Use `/birthday remove` inside a server.", ephemeral=True)
        return
    conn = db()
    conn.execute(
        "DELETE FROM birthdays WHERE guild_id=? AND user_id=?",
        (str(interaction.guild.id), str(interaction.user.id)),
    )
    conn.commit()
    conn.close()
    await interaction.response.send_message("Birthday removed.", ephemeral=True)


@BDAY_GROUP.command(name="list", description="Everyone's saved birthdays.")
async def bday_list(interaction: discord.Interaction):
    if interaction.guild is None:
        await interaction.response.send_message("Use `/birthday list` inside a server.", ephemeral=True)
        return
    conn = db()
    rows = conn.execute(
        "SELECT user_id, month, day FROM birthdays WHERE guild_id=? ORDER BY month, day",
        (str(interaction.guild.id),),
    ).fetchall()
    conn.close()
    if not rows:
        await interaction.response.send_message("No birthdays saved yet. Members can save theirs with /birthday set.", ephemeral=True)
        return
    lines = ["**🎂 Birthdays**"]
    for r in rows:
        lines.append(f"**{r['month']}/{r['day']}** — <@{r['user_id']}>")
    await interaction.response.send_message("\n".join(lines), ephemeral=True)


async def announce_birthdays(month_day: str):
    """Post in every guild's birthday channel for the people with a birthday today."""
    month, day = month_day.split("-")
    conn = db()
    rows = conn.execute(
        "SELECT guild_id, user_id FROM birthdays WHERE month=? AND day=?",
        (month, day),
    ).fetchall()
    conn.close()
    for r in rows:
        gid = r["guild_id"]
        if not flag_on(gid, "birthday_enabled", "0"):
            continue
        channel_id = get_cfg(gid, "birthday_channel", "")
        if not channel_id:
            continue
        guild = bot.get_guild(int(gid))
        channel = guild.get_channel(int(channel_id)) if guild else None
        if not channel:
            continue
        member = guild.get_member(int(r["user_id"])) if guild else None
        try:
            await channel.send(
                f"🎂🎉 Happy birthday <@{r['user_id']}>!"
                + (f" Have an amazing day, **{member.display_name}**! 🎈" if member else "")
            )
        except discord.Forbidden:
            pass


async def birthday_loop():
    await bot.wait_until_ready()
    last = None
    while not bot.is_closed():
        today = datetime.datetime.now(datetime.timezone.utc).strftime("%m-%d")
        if today != last:
            last = today
            try:
                await announce_birthdays(today)
            except Exception:
                pass
        await asyncio.sleep(60)


# ---------------------------------------------------------------------------
# Run
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    if not BOT_TOKEN:
        print("ERROR: BOT_TOKEN is not set. Copy bot/.env.example to .env and fill it in.")
        sys.exit(1)
    MIN_PY = (3, 10)
    if sys.version_info < MIN_PY:
        print(f"ERROR: Python {'.'.join(map(str, MIN_PY))}+ required (got {sys.version_info[0]}.{sys.version_info[1]}).")
        sys.exit(1)
    try:
        bot.run(BOT_TOKEN)
    except discord.LoginFailure:
        print("ERROR: Invalid BOT_TOKEN.")
        sys.exit(1)