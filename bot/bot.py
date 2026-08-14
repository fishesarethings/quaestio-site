#!/usr/bin/env python3
"""Quaestio — your server's own AI companion.

Self-hosted Discord bot: AI chat (via local Ollama), XP levels, moderation,
tags, welcomes, and a handful of core utilities. One process, one SQLite file.

Requires: a Discord bot token and Ollama running locally (OLLAMA_BASE_URL).
"""

import asyncio
import datetime
import json
import os
import random
import sqlite3
import sys
import time
import urllib.request
import urllib.error

import discord
from discord import app_commands
from discord.ext import commands

# ---------------------------------------------------------------------------
# Config (env vars, .env is loaded by the launcher or install script)
# ---------------------------------------------------------------------------

BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
OLLAMA_BASE_URL = os.environ.get("OLLAMA_BASE_URL", "http://127.0.0.1:11434")
OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "llama3.2")
OLLAMA_TIMEOUT = int(os.environ.get("OLLAMA_TIMEOUT", "120"))
DB_PATH = os.environ.get("DB_PATH", "quaestio.db")
PREFIX = os.environ.get("PREFIX", "/")
WARN_LIMIT_DEFAULT = int(os.environ.get("WARN_LIMIT", "3"))
RPC_LARGE_IMAGE = os.environ.get("RPC_LARGE_IMAGE", "logo")
RPC_SMALL_IMAGE = os.environ.get("RPC_SMALL_IMAGE", "")

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
        """
    )
    conn.commit()
    conn.close()


# ---------------------------------------------------------------------------
# Ollama AI (local, no cloud)
# ---------------------------------------------------------------------------

async def ask_ollama(prompt: str) -> str:
    payload = json.dumps(
        {"model": OLLAMA_MODEL, "prompt": prompt, "stream": False}
    ).encode()

    def _request():
        req = urllib.request.Request(
            f"{OLLAMA_BASE_URL}/api/generate",
            data=payload,
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=OLLAMA_TIMEOUT) as resp:
            return json.loads(resp.read().decode())

    try:
        result = await asyncio.to_thread(_request)
    except (urllib.error.URLError, TimeoutError, OSError):
        raise ConnectionError("AI is offline — is Ollama running?")

    response = (result.get("response") or "").strip()
    if not response:
        raise ConnectionError("AI returned an empty response.")
    return response


# ---------------------------------------------------------------------------
# Leveling helpers
# ---------------------------------------------------------------------------

def xp_for_level(level: int) -> int:
    return 5 * (level ** 2) + 50 * level + 100


def add_xp(guild_id: str, user_id: str):
    conn = db()
    conn.execute(
        """INSERT INTO xp (guild_id, user_id, messages) VALUES (?, ?, 1)
           ON CONFLICT(guild_id, user_id)
           DO UPDATE SET messages = messages + 1""",
        (guild_id, user_id),
    )
    row = conn.execute(
        "SELECT messages FROM xp WHERE guild_id=? AND user_id=?",
        (guild_id, user_id),
    ).fetchone()
    conn.commit()
    conn.close()
    return row["messages"]


def level_for_messages(messages: int) -> int:
    level = 0
    required = xp_for_level(level + 1)
    while messages >= required and level < 100:
        level += 1
        required = xp_for_level(level + 1)
    return level


def get_owner_config(guild: discord.Guild, key: str, default=None):
    conn = db()
    row = conn.execute(
        "SELECT value FROM config WHERE guild_id=? AND key=?",
        (str(guild.id), key),
    ).fetchone()
    conn.close()
    return row["value"] if row else default


def set_owner_config(guild: discord.Guild, key: str, value: str):
    conn = db()
    conn.execute(
        """INSERT INTO config (guild_id, key, value) VALUES (?, ?, ?)
           ON CONFLICT(guild_id, key) DO UPDATE SET value = excluded.value""",
        (str(guild.id), key, value),
    )
    conn.commit()
    conn.close()


def is_admin(user: discord.Member) -> bool:
    return user.guild_permissions.administrator


# ---------------------------------------------------------------------------
# Event hooks
# ---------------------------------------------------------------------------

@bot.event
async def on_ready():
    db_init()
    activity = discord.Activity(
        type=discord.ActivityType.watching,
        name="/ask",
        details=f"AI · {OLLAMA_MODEL}",
        state="27 commands · free",
        assets={"large_image": RPC_LARGE_IMAGE},
    )
    if RPC_SMALL_IMAGE:
        activity.assets["small_image"] = RPC_SMALL_IMAGE
    await bot.change_presence(activity=activity)
    invited = sum(1 for g in (await bot.application_info()).guilds)
    print(f"quæstio: logged in as {bot.user} · {len(bot.guilds)} servers · {invited} invites")
    try:
        synced = await bot.tree.sync()
        print(f"quæstio: {len(synced)} slash commands synced")
    except Exception as exc:
        print(f"quæstio: sync failed: {exc}")


@bot.event
async def on_message(message: discord.Message):
    if message.author.bot or message.guild is None:
        return
    if message.content.startswith(PREFIX):
        await bot.process_commands(message)
        return
    messages = add_xp(str(message.guild.id), str(message.author.id))
    new_level = level_for_messages(messages)
    old_level = level_for_messages(messages - 1)
    if new_level > old_level and new_level > 1:
        role_id = get_owner_config(message.guild, "levelrole")
        try:
            await message.channel.send(
                f"🎉 {message.author.mention} reached **level {new_level}**!"
            )
        except discord.Forbidden:
            pass
        if role_id:
            role = message.guild.get_role(int(role_id))
            if role:
                try:
                    await message.author.add_roles(role)
                except discord.Forbidden:
                    pass
        welcome_channel_id = get_owner_config(message.guild, "levelup_channel")
        if welcome_channel_id:
            channel = message.guild.get_channel(int(welcome_channel_id))
            if channel:
                await channel.send(message.author.mention)


@bot.event
async def on_member_join(member: discord.Member):
    if member.bot:
        return
    channel_id = get_owner_config(member.guild, "welcome_channel")
    if not channel_id:
        return
    channel = member.guild.get_channel(int(channel_id))
    if not channel:
        return
    text = get_owner_config(
        member.guild, "welcome_message",
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

AI_LOCK = asyncio.Lock()


@bot.tree.command(name="ask", description="Ask Quaestio's local AI a question.")
@app_commands.describe(prompt="Your question or prompt")
async def ask(interaction: discord.Interaction, prompt: str):
    await interaction.response.defer(thinking=True)
    async with AI_LOCK:
        try:
            async with interaction.channel.typing():
                answer = await ask_ollama(prompt)
        except ConnectionError as exc:
            await interaction.followup.send(f"⚠️ {exc}")
            return
    if len(answer) > 1900:
        answer = answer[:1950] + "…"
    embed = discord.Embed(color=0xA78BFA)
    embed.add_field(name="🧠 Prompt", value=f"> {prompt[:1024]}", inline=False)
    embed.add_field(name="Quaestio", value=answer, inline=False)
    await interaction.followup.send(embed=embed)


@bot.tree.command(name="summarize", description="Summarize the last N messages in this channel.")
@app_commands.describe(limit="How many messages to summarize (default 20, max 60)")
async def summarize(interaction: discord.Interaction, limit: int = 20):
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
    async with AI_LOCK:
        try:
            async with interaction.channel.typing():
                answer = await ask_ollama(prompt)
        except ConnectionError as exc:
            await interaction.followup.send(f"⚠️ {exc}")
            return
    await interaction.followup.send(
        f"📄 **Summary of last {len(texts)} messages**\n{answer[:1900]}"
    )


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


@bot.tree.command(name="top", description="The top 10 members in this server.")
async def top(interaction: discord.Interaction):
    conn = db()
    rows = conn.execute(
        "SELECT user_id, messages FROM xp WHERE guild_id=? ORDER BY messages DESC LIMIT 10",
        (str(interaction.guild.id),),
    ).fetchall()
    conn.close()
    if not rows:
        await interaction.response.send_message("No XP yet — start chatting! 🚀")
        return
    lines = []
    for i, row in enumerate(rows, 1):
        member = interaction.guild.get_member(int(row["user_id"]))
        name = member.display_name if member else f"<@{row['user_id']}>"
        lines.append(f"**{i}.** {name} — {row['messages']} msgs (Lv{level_for_messages(row['messages'])})")
    await interaction.response.send_message("🏆 **Server leaderboard**\n" + "\n".join(lines))


@bot.tree.command(name="levelrole", description="Auto-assign a role at every level up.")
@app_commands.describe(role="Role to give on level up, or 'none' to disable")
async def levelrole(interaction: discord.Interaction, role: str):
    if not is_admin(interaction.user):
        await interaction.response.send_message("Needs Administrator.", ephemeral=True)
        return
    if role.lower() in ("none", "off", "remove"):
        set_owner_config(interaction.guild, "levelrole", "")
        await interaction.response.send_message("Level-up role disabled.")
        return
    resolved = discord.utils.get(interaction.guild.roles, name=role)
    if not resolved:
        await interaction.response.send_message(
            f"Role `{role}` not found.", ephemeral=True
        )
        return
    set_owner_config(interaction.guild, "levelrole", str(resolved.id))
    await interaction.response.send_message(f"Level-ups now grant **{resolved.name}**.")


# ---------------------------------------------------------------------------
# Moderation
# ---------------------------------------------------------------------------

def staff_only(func):
    @commands.has_permissions(manage_messages=True, kick_members=True, ban_members=True)
    async def wrapper(interaction, *args, **kwargs):
        return await func(interaction, *args, **kwargs)
    return wrapper


def _warn_db(guild_id, user_id, reason):
    conn = db()
    conn.execute(
        "INSERT INTO warned (guild_id, user_id, reason, at) VALUES (?, ?, ?, ?)",
        (guild_id, user_id, reason, datetime.datetime.now().isoformat()),
    )
    conn.commit()
    count = conn.execute(
        "SELECT COUNT(*) AS n FROM warned WHERE guild_id=? AND user_id=?",
        (guild_id, user_id),
    ).fetchone()["n"]
    conn.close()
    return count


@bot.tree.command(name="warn", description="Warn a member.")
@app_commands.describe(member="Member to warn", reason="Reason")
async def warn(interaction: discord.Interaction, member: discord.Member, reason: str = "No reason"):
    if not is_admin(interaction.user):
        await interaction.response.send_message("Needs Administrator.", ephemeral=True)
        return
    count = _warn_db(str(interaction.guild.id), str(member.id), reason)
    limit = int(get_owner_config(interaction.guild, "warnlimit") or WARN_LIMIT_DEFAULT)
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


@bot.tree.command(name="warnlimit", description="Set the auto-kick warn limit.")
@app_commands.describe(limit="Warnings before auto-kick")
async def warnlimit(interaction: discord.Interaction, limit: int):
    if not is_admin(interaction.user):
        await interaction.response.send_message("Needs Administrator.", ephemeral=True)
        return
    limit = max(1, min(limit, 20))
    set_owner_config(interaction.guild, "warnlimit", str(limit))
    await interaction.response.send_message(f"Auto-kick limit set to **{limit}** warns.")


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
@app_commands.describe(user="Name of the banned user (e.g. user#1234 or just name)")
async def unban(interaction: discord.Interaction, user: str):
    if not is_admin(interaction.user):
        await interaction.response.send_message("Needs Administrator.", ephemeral=True)
        return
    banned = [entry async for entry in interaction.guild.bans()]
    target = next((e for e in banned if user.lower() in str(e.user).lower()), None)
    if target is None:
        await interaction.response.send_message(f"No banned user matching `{user}`.", ephemeral=True)
        return
    await interaction.guild.unban(target.user, reason="Quæstio unban")
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
# Welcome
# ---------------------------------------------------------------------------

@bot.tree.command(name="welcome", description="Turn welcome messages on/off.")
@app_commands.describe(enabled="true or false")
async def welcome(interaction: discord.Interaction, enabled: bool):
    if not is_admin(interaction.user):
        await interaction.response.send_message("Needs Administrator.", ephemeral=True)
        return
    set_owner_config(interaction.guild, "welcome_enabled", "1" if enabled else "0")
    await interaction.response.send_message(f"Welcome messages {'enabled' if enabled else 'disabled'}.")


@bot.tree.command(name="welcomechannel", description="Set the welcome channel.")
@app_commands.describe(channel="Channel to send welcomes to")
async def welcomechannel(interaction: discord.Interaction, channel: discord.TextChannel):
    if not is_admin(interaction.user):
        await interaction.response.send_message("Needs Administrator.", ephemeral=True)
        return
    set_owner_config(interaction.guild, "welcome_channel", str(channel.id))
    await interaction.response.send_message(f"👋 Welcomes → {channel.mention}")


@bot.tree.command(name="welcomemessage", description="Set the welcome text.")
@app_commands.describe(text="Welcome message (use {member} for the person)")
async def welcomemessage(interaction: discord.Interaction, text: str):
    if not is_admin(interaction.user):
        await interaction.response.send_message("Needs Administrator.", ephemeral=True)
        return
    set_owner_config(interaction.guild, "welcome_message", text)
    await interaction.response.send_message("Welcome text set.")


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