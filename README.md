# Quaestio

**Your server's own AI companion** — a free, self-hosted Discord bot with a real on-prem AI brain, XP levels, moderation, tags and welcome messages.

🌐 **Live site:** https://quaestio.online · 🔒 [Privacy](https://quaestio.online/privacy.html) · 📜 [Terms](https://quaestio.online/terms.html)

🤖 **Add to Discord:** [discord.com/oauth2/authorize?client_id=1537428372802506802](https://discord.com/oauth2/authorize?client_id=1537428372802506802&permissions=1101994781766&scope=bot)

The custom domain **quaestio.online** is live, served through Cloudflare → GitHub Pages.

---

## What is Quaestio?

Quaestio is a small Discord bot that runs a tiny local AI model on the server owner's own hardware. It answers one conversation at a time, typed out like a person — with no cloud, no API bills, and no subscriptions. Ever.

Alongside the AI it ships 27 slash commands:

| Area | Commands |
|---|---|
| 🤖 AI | `/ask` `/summarize` |
| 🏆 Levels | `/rank` `/top` `/levelrole` |
| 🛡️ Moderation | `/warn` `/warns` `/delwarns` `/warnlimit` `/kick` `/ban` `/unban` `/purge` `/mute` `/unmute` |
| 🏷️ Tags | `/tag` `/tagcreate` `/tagdelete` `/tags` |
| 👋 Welcome | `/welcome` `/welcomechannel` `/welcomemessage` |
| 🧭 Core | `/ping` `/uptime` `/about` `/invite` `/8ball` |

## Site

This repo is the marketing / legal site for the bot **and** the bot's code (in `bot/`). Pure HTML + CSS + vanilla JS — no build step, no framework.

```
index.html      Landing page (hero, features, commands, install, FAQ)
privacy.html    Privacy policy (operator-based, since the bot is self-hosted)
terms.html      Terms of service
style.css       Design system (dark theme, gradients, animations)
script.js       Animations, copy-to-clipboard, counters, scroll reveal
assets/         Circular transparent-background logos (256 / 512 / 1024)
bot/bot.py      The bot itself (27 slash commands, one process, one SQLite file)
bot/install.sh  Single-command installer (macOS + Linux)
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

```bash
curl -fsSL https://quaestio.online/bot/install.sh | bash
```

The installer checks/installs Python, creates an isolated virtualenv, installs
`discord.py`, detects the local AI engine (Ollama), pulls a small model, prompts
once for your bot token, and sets up a service (systemd on Linux). The AI runs
entirely on your machine — nothing goes to the cloud.

- Config: `bot/.env` (copy from `.env.example`)
- Model: `ollama pull llama3.2` for a bigger brain, `ollama pull tinyllama` for speed
- The bot process type-runs replies; only one AI conversation at a time (by design)

## Legal

Quaestio is an independent project, not affiliated with, endorsed by, or connected to Discord Inc. The bot and its site are provided as-is; see the Terms for the full warranty/liability text.
