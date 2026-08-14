# Quaestio — Website, Publishing & Verification Guide

Domain: **quaestio.online** (live, served via Cloudflare → GitHub Pages)

## 1. Where the site lives
Everything is in this folder (`quaestio-site/`):
- `index.html` — animated landing page (hero, features, commands, install, FAQ)
- `privacy.html` + `terms.html` — legal pages, restyled to match
- `style.css` + `script.js` — design system + animations
- `assets/logo-512.png` (app icon) + `assets/logo-1024.png` (art asset)

All three pages share one stylesheet. Edit text in the HTML files directly.

## 2. Legal pages
- `terms.html` + `privacy.html` are intentionally generic — no personal name, country,
  or contact details. They point to "the server operator" since the bot is self-hosted,
  so nothing links back to the owner personally.

## 3. Deploying the site
The site is served via GitHub Pages with `quaestio.online` as a custom domain,
proxied through Cloudflare for HTTPS. To publish updates, just push to `main`:

```bash
git add -A
git commit -m "change"
git push
```

Cloudflare proxies `quaestio.online` and `www` (CNAME → GitHub Pages).
No server, no open ports, nothing exposed.

## 4. Invite link (used in the buttons)
`https://discord.com/oauth2/authorize?client_id=1537428372802506802&permissions=1101994781766&scope=bot`
- Permissions included: kick, ban, moderate members (timeouts), manage roles, purge,
  send messages/embeds, read history, reactions, nickname, use slash commands.
- If you change permissions in the portal, regenerate this integer at
  https://discord.com/api/oauth2/authorize?client_id=1537428372802506802&scope=bot and update
  every link in `index.html` (3 places).

## 5. Discord Verification checklist (Blue Badge)
- [x] Bot in 75+ unique servers
- [x] Privacy Policy URL → `https://quaestio.online/privacy.html`
- [x] Terms of Service URL → `https://quaestio.online/terms.html`
- [x] App name/username = Quaestio (no emoji / "Discord" / brand impersonation)
- [x] App icon uploaded (`assets/logo-512.png`) — no trademarks/copyrighted art
- [x] Description + tags set (General Information)
- [x] Developer Terms complied with
- [ ] Personal/team info in Verification tab
- [ ] Apply for Verification (Blue Badge → Yes)
- [ ] Verified account + payment method if asked

## 6. Rich Presence asset key
Large image uploaded to the portal must be named **`logo`**.
On the server: `RPC_LARGE_IMAGE=logo` in `.env` (see `bot/`).
Optional small image: upload a second asset named e.g. `wrench`, then `RPC_SMALL_IMAGE=wrench`.
