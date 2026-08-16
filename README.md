# Quaestio

**Your server's AI companion** — add the shared Quaestio bot to any Discord server in one click, then configure it in your web panel. No app creation, no tokens, no self-hosting required. Community hardware powers the AI; endpoints and prompts are encrypted end-to-end.

🌐 **Live site:** https://quaestio.online · 🔒 [Privacy](https://quaestio.online/privacy.html) · 📜 [Terms](https://quaestio.online/terms.html)

🤖 **Add to Discord:** [discord.com/oauth2/authorize?client_id=1537428372802506802](https://discord.com/oauth2/authorize?client_id=1537428372802506802&permissions=1101994781766&scope=bot)

The custom domain **quaestio.online** is live, served through Cloudflare → GitHub Pages.

---

## What is Quaestio?

Quaestio is a Discord bot with a real AI brain, plus the essentials your community actually wants: AI chat, XP levels, moderation, tags, birthdays and welcome messages. You use **Quaestio's shared bot** — there is nothing to install and no token to create to use it. If you'd like, you can also run your own box and lend it to the **community pool**, where AI requests fan out randomly (and encrypted end-to-end) across participant devices.

Alongside the AI it ships 41 slash commands:

| Area | Commands |
|---|---|
| 🤖 AI | `/ask` `/summarize` `/ai model` `/ai toggle` `/ai status` `/ai clear` `/ai personality` `/ai character` `/panel` |
| 🎮 Games | `/8ball` `/dice` `/coin` `/rps` `/trivia` `/answer` `/slot` `/tictactoe` `/move` |
| 🏆 Levels | `/rank` `/profile` `/leaderboard` |
| 🛡️ Moderation | `/warn` `/warns` `/delwarns` `/kick` `/ban` `/unban` `/purge` `/mute` `/unmute` |
| 🏷️ Tags | `/tag` `/tagcreate` `/tagdelete` `/tags` |
| 🎂 Birthdays | `/birthday set` `/birthday list` `/birthday remove` |
| 🧭 Core | `/ping` `/uptime` `/about` `/invite` |

The `/ai` settings are **admin-only** — a server admin can pick from the models
on their configured AI host (`/ai model` autocompletes from a live scan), or
revert to the shared default with `default`.

Server admins can manage everything from the **web panel** at
`/panel` (or the dashboard link in the site header): AI model, custom
instructions, memory, per-server AI quota, welcome messages, level role and the
warn-kick limit — with live previews and saved **encrypted at rest**.

The dashboard also has a **Host** tab for self-hosters: set the default AI host,
model, memory and per-server quota that apply to every server that doesn't
override them, plus live host stats (RAM, disk, CPU, Ollama status).

## Site

This repo is the marketing / legal site for the bot **and** the bot's code (in `bot/`). Pure HTML + CSS + vanilla JS — no build step, no framework.

```
index.html      Landing page (hero, features, commands, install, FAQ)
privacy.html    Privacy policy (operator-based, since the bot is self-hosted)
terms.html      Terms of service
style.css       Design system (dark theme, gradients, animations)
script.js       Animations, copy-to-clipboard, counters, scroll reveal
assets/         Circular transparent-background logos (256 / 512 / 1024)
bot/bot.py      The bot itself (29 slash commands, one process, one SQLite file)
bot/config.py   Shared encrypted-at-rest storage (Fernet) — bot + dashboard
bot/install.sh  Single-command installer (macOS + Linux)
bot/install.ps1 Windows installer (PowerShell)
bot/            requirements.txt + .env.example
dashboard/      Admin web panel (FastAPI + Discord OAuth + static UI)
```

### Editing & publishing
Everything lives on `main`; GitHub Pages rebuilds automatically ~1 min after each push:

```bash
git add -A
git commit -m "what changed"
git push
```

Live at https://quaestio.online

### Invite link
Used in the hero + CTA buttons. Permission integer `1101994781766` = kick, ban, moderate members (timeouts), manage roles, purge messages, send messages/embeds, read history, add reactions, use slash commands. If you change the portal permissions, regenerate the integer and update the 3 links in `index.html`.

## Using Quaestio (no install, no token)

1. **Add to Discord** — one click, no app to create:
   [discord.com/oauth2/authorize?client_id=1537428372802506802](https://discord.com/oauth2/authorize?client_id=1537428372802506802&permissions=1101994781766&scope=bot)
2. Say hi with `/about`, chat with `/ask` or `@Quaestio`.
3. Run `/panel`, sign in, and configure everything in the web panel.

You use Quaestio's shared bot — you never create your own bot or paste a token.

## Optional: run your own box (community host)

Want to lend compute to the community pool (or fully self-host)? One command sets
up Ollama + a model and registers your box as an anonymous, encrypted node.

**macOS / Linux:**
```bash
curl -fsSL https://quaestio.online/bot/install.sh | bash
```

**Windows (PowerShell):**
```powershell
powershell -ExecutionPolicy Bypass -Command "irm https://quaestio.online/bot/install.ps1 | iex"
```

The installer checks/installs Python, creates an isolated virtualenv, installs
`discord.py`, detects the local AI engine (Ollama), pulls a small model, and
sets up a service (systemd on Linux, startup task on Windows). It never asks
for a Discord bot token — that's only an advanced option for running your own
separate bot.

### Manage your host with the `quaestio` command
The installer also adds a `quaestio` command to your PATH. Type it from any
folder:

```
quaestio               opens a full-screen interactive TUI
quaestio help          lists every command
quaestio status        what's here / running
quaestio settings      change any setting
quaestio contribute    join the anonymous community pool
quaestio update        pull the latest code
quaestio uninstall     remove everything (including the command itself)
```

`uninstall` stops the bot, removes the service/keyfile/install folder, and
takes the `quaestio` command off your PATH.

### Hosting the AI on a different computer
Quaestio and the model don't have to share a machine. Run Ollama on any spare
PC (Windows, Linux, macOS), then either:
- set `OLLAMA_BASE_URL` before installing (e.g. `OLLAMA_BASE_URL=http://192.168.1.50:11434 curl -fsSL … | bash`), or
- change it later in `bot/.env`.

On the model host, make Ollama listen on the network:
`OLLAMA_HOST=0.0.0.0:11434 ollama serve` (set `OLLAMA_HOST` env var on Windows).

Server admins can also point their own server at their own box with
`/ai model` + the web panel (no restart needed).

### Admin web panel (dashboard)
A small FastAPI app in `dashboard/` that shares the bot's SQLite DB and
encryption key. Sign in with Discord (server **admins** only see their own
servers) and edit AI model / instructions / memory / quota, welcomes, level
role and warn limits with live previews. Deploy with:

```bash
python3 -m venv dashboard/.venv
dashboard/.venv/bin/pip install -r dashboard/requirements.txt
cp bot/config.py dashboard/          # shares the same crypto module
DISCORD_CLIENT_ID=... DISCORD_CLIENT_SECRET=... \
DISCORD_REDIRECT_URI=https://admin.quaestio.online/auth/callback \
SECRET_KEY=$(python3 -c "import secrets; print(secrets.token_urlsafe(32))") \
DB_PATH=bot/quaestio.db \
dashboard/.venv/bin/uvicorn app:app --host 127.0.0.1 --port 8900
```

Register `https://admin.quaestio.online/auth/callback` (or your tunnel URL) as
a Redirect in the Discord Developer Portal → OAuth2, scopes `identify guilds`.

### Self-hosting on Windows (full — bot + AI + web panel)

Three machines can each run a piece (bot, model, panel) — they don't have to be
the same one. The easy single-command path installs the **bot** and the **AI**:

```powershell
powershell -ExecutionPolicy Bypass -Command "irm https://quaestio.online/bot/install.ps1 | iex"
```

That downloads Python + the bot, creates `%USERPROFILE%\.quaestio\keyfile`
for encrypted storage, pulls a small model into Ollama, and registers a startup
task (`run-quaestio.bat` in the install folder to start it manually). It also
puts a `quaestio` command on your PATH. It does
**not** install the web panel by default — the dashboard is optional.

To also run the **admin web panel** on Windows:

```powershell
cd bot
pip install -r dashboard/requirements.txt      # or: cd dashboard; pip install -r requirements.txt
set DISCORD_CLIENT_ID=YOUR_APP_ID
set DISCORD_CLIENT_SECRET=YOUR_CLIENT_SECRET
set DISCORD_REDIRECT_URI=http://127.0.0.1:8900/auth/callback
set SECRET_KEY=generate-a-random-string
set DB_PATH=%CD%\..\bot\quaestio.db
cd dashboard
python -m uvicorn app:app --host 127.0.0.1 --port 8900
```

Open `http://127.0.0.1:8900` and sign in. Register
`http://127.0.0.1:8900/auth/callback` as a Redirect in the Discord portal
(OAuth2 → General). Everything — bot, models, panel, DB, key — lives on your
Windows machine; nothing goes to the cloud. For a public URL instead of
`localhost`, run `cloudflared tunnel --url http://127.0.0.1:8900` and register
that URL as the redirect instead.

### Host defaults (self-host quota etc.)
Open the dashboard's **Host** tab to set machine-wide defaults: the default
Ollama URL, default model, default memory and a default AI calls/hour quota.
The bot reads these whenever a server hasn't set its own value, so one chatty
server can't hog a shared model box. Host values are stored encrypted like
everything else.

### Weak-host friendliness
- One AI call at a time — a fair queue round-robins across servers, and says
  "busy" instead of stacking up requests.
- Per-channel memory (default 4 turns) so a small model chats coherently
  without loading whole-server history. Tune it in the web panel.
- Per-server AI quota (calls/hour) so one chatty server can't hog a shared host.
- Replies are streamed with a typing indicator, so it feels human.

- Config: `bot/.env` (copy from `.env.example`)
- Model: `ollama pull qwen3:1.7b` for the smartest small brain, `qwen2.5:1.5b` is the default (Apache 2.0), `qwen2.5:0.5b` for ultra-light

## Legal

Quaestio is an independent project, not affiliated with, endorsed by, or connected to Discord Inc. The bot and its site are provided as-is; see the Terms for the full warranty/liability text.

### Model licensing (self-hosted AI)
Quaestio itself is open source and contains no model weights. Models come from
Ollama and each carries its own permissive license — all fine to self-host:
- `qwen2.5` (0.5b / 1.5b) — **Apache 2.0** (unrestricted, commercial OK)
- `qwen3` (1.7b) — **Apache 2.0**
- `llama3.2` — **Llama Community License** (free commercial use; only restricted
  above ~700M monthly active users)
- `gemma2` — **Gemma Terms of Use** (free commercial use up to a large-user
  threshold)

Because the model runs on your own hardware and no weights are redistributed as
services, none of these require a paid license at normal scale. Which model a
server uses is set by that server's admin (see `/ai model`).
