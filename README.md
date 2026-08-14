# Quaestio

**Your server's own AI companion** — a free, self-hosted Discord bot with a real on-prem AI brain, XP levels, moderation, tags and welcome messages.

🌐 **Live site:** https://quaestio.online · 🔒 [Privacy](https://quaestio.online/privacy.html) · 📜 [Terms](https://quaestio.online/terms.html)

🤖 **Add to Discord:** [discord.com/oauth2/authorize?client_id=1537428372802506802](https://discord.com/oauth2/authorize?client_id=1537428372802506802&permissions=1101994781766&scope=bot)

The custom domain **quaestio.online** is live, served through Cloudflare → GitHub Pages.

---

## What is Quaestio?

Quaestio is a small Discord bot that runs a tiny local AI model on the server owner's own hardware. It answers one conversation at a time, typed out like a person — with no cloud, no API bills, and no subscriptions. Ever.

Alongside the AI it ships 32 slash commands:

| Area | Commands |
|---|---|
| 🤖 AI | `/ask` `/summarize` `/ai model` `/ai endpoint` `/ai memory` `/ai toggle` `/ai status` |
| 🏆 Levels | `/rank` `/top` `/levelrole` |
| 🛡️ Moderation | `/warn` `/warns` `/delwarns` `/warnlimit` `/kick` `/ban` `/unban` `/purge` `/mute` `/unmute` |
| 🏷️ Tags | `/tag` `/tagcreate` `/tagdelete` `/tags` |
| 👋 Welcome | `/welcome` `/welcomechannel` `/welcomemessage` |
| 🧭 Core | `/ping` `/uptime` `/about` `/invite` `/8ball` |

The `/ai` settings are **admin-only** — a server admin can point this server at
their own Ollama box (any OS, including Windows) to host their own model, or
revert to the shared one with `default`.

## Site

This repo is the marketing / legal site for the bot **and** the bot's code (in `bot/`). Pure HTML + CSS + vanilla JS — no build step, no framework.

```
index.html      Landing page (hero, features, commands, install, FAQ)
privacy.html    Privacy policy (operator-based, since the bot is self-hosted)
terms.html      Terms of service
style.css       Design system (dark theme, gradients, animations)
script.js       Animations, copy-to-clipboard, counters, scroll reveal
assets/         Circular transparent-background logos (256 / 512 / 1024)
bot/bot.py      The bot itself (32 slash commands, one process, one SQLite file)
bot/install.sh  Single-command installer (macOS + Linux)
bot/install.ps1 Windows installer (PowerShell)
bot/            requirements.txt + .env.example
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

## Running the bot yourself (one command)

**macOS / Linux:**
```bash
curl -fsSL https://quaestio.online/bot/install.sh | bash
```

**Windows (PowerShell):**
```powershell
powershell -ExecutionPolicy Bypass -Command "irm https://quaestio.online/bot/install.ps1 | iex"
```

The installer checks/installs Python, creates an isolated virtualenv, installs
`discord.py`, detects the local AI engine (Ollama), pulls a small model, prompts
once for your bot token, and sets up a service (systemd on Linux, startup task
on Windows). The AI runs on your machine — nothing goes to the cloud.

### Hosting the AI on a different computer
Quaestio and the model don't have to share a machine. Run Ollama on any spare
PC (Windows, Linux, macOS), then either:
- set `OLLAMA_BASE_URL` before installing (e.g. `OLLAMA_BASE_URL=http://192.168.1.50:11434 curl -fsSL … | bash`), or
- change it later in `bot/.env`.

On the model host, make Ollama listen on the network:
`OLLAMA_HOST=0.0.0.0:11434 ollama serve` (set `OLLAMA_HOST` env var on Windows).

Server admins can also point their own server at their own box with
`/ai endpoint` + `/ai model` (no restart needed).

### Weak-host friendliness
- One AI call at a time — a fair queue round-robins across servers, and says
  "busy" instead of stacking up requests.
- Per-channel memory (default 4 turns, `/ai memory` to tune) so a small model
  chats coherently without loading whole-server history.
- Replies are streamed with a typing indicator, so it feels human.

- Config: `bot/.env` (copy from `.env.example`)
- Model: `ollama pull llama3.2` for a bigger brain, `ollama pull tinyllama` for speed

## Legal

Quaestio is an independent project, not affiliated with, endorsed by, or connected to Discord Inc. The bot and its site are provided as-is; see the Terms for the full warranty/liability text.

### Model licensing (self-hosted AI)
Quaestio itself is open source and contains no model weights. Models come from
Ollama and each carries its own permissive license — all fine to self-host:
- `tinyllama` — **Apache 2.0** (unrestricted, commercial OK)
- `llama3.2` — **Llama Community License** (free commercial use; only restricted
  above ~700M monthly active users)
- `gemma2` — **Gemma Terms of Use** (free commercial use up to a large-user
  threshold)

Because the model runs on your own hardware and no weights are redistributed as
services, none of these require a paid license at normal scale. Which model a
server uses is set by that server's admin (see `/ai model`).
