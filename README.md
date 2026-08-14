# Quaestio

**Your server's own AI companion** — a free, self-hosted Discord bot with a real on-prem AI brain, XP levels, moderation, tags and welcome messages.

🌐 **Live site:** https://fishesarethings.github.io/quaestio-site/ · 🔒 [Privacy](https://fishesarethings.github.io/quaestio-site/privacy.html) · 📜 [Terms](https://fishesarethings.github.io/quaestio-site/terms.html)

🤖 **Add to Discord:** [discord.com/oauth2/authorize?client_id=1537428372802506802](https://discord.com/oauth2/authorize?client_id=1537428372802506802&permissions=1101994781766&scope=bot)

> Custom domain **quaestio.online** is the eventual home — DNS records pending (see below).

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

This repo is the marketing / legal site for the bot. Pure HTML + CSS + vanilla JS — no build step, no framework, no dependencies.

```
index.html      Landing page (hero, features, commands, install, FAQ)
privacy.html    Privacy policy (operator-based, since the bot is self-hosted)
terms.html      Terms of service
style.css       Design system (dark theme, gradients, animations)
script.js       Animations, copy-to-clipboard, counters, scroll reveal
assets/         Circular transparent-background logos (256 / 512 / 1024)
```

### Editing & publishing
Everything lives on `main`; GitHub Pages rebuilds automatically ~1 min after each push:

```bash
git add -A
git commit -m "what changed"
git push
```

Live at https://fishesarethings.github.io/quaestio-site/

### Invite link
Used in the hero + CTA buttons. Permission integer `1101994781766` = kick, ban, moderate members (timeouts), manage roles, purge messages, send messages/embeds, read history, add reactions, use slash commands. If you change the portal permissions, regenerate the integer and update the 3 links in `index.html`.

## Deploying to quaestio.online (in progress)

The domain is registered and on Cloudflare nameservers. To finish:

1. In Cloudflare → **quaestio.online** → DNS, add (proxy on, orange cloud):
   - `A` `@` → `185.199.108.153`
   - `A` `@` → `185.199.109.153`
   - `A` `@` → `185.199.110.153`
   - `A` `@` → `185.199.111.153`
   - `CNAME` `www` → `fishesarethings.github.io`
2. The `CNAME` file in this repo tells GitHub Pages to serve `quaestio.online`.
3. In Pages settings, enforce HTTPS once DNS propagates.

## Legal

Quaestio is an independent project, not affiliated with, endorsed by, or connected to Discord Inc. The bot and its site are provided as-is; see the Terms for the full warranty/liability text.
