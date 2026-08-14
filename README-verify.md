# Quaestio — Website, Publishing & Verification Guide

Domain: **quaestio.online** (Cloudflare in progress)

## 1. Where the site lives
Everything is in this folder (`quaestio-site/`):
- `index.html` — animated landing page (hero, features, commands, install, FAQ)
- `privacy.html` + `terms.html` — legal pages, restyled to match
- `style.css` + `script.js` — design system + animations
- `assets/logo-512.png` (app icon) + `assets/logo-1024.png` (art asset)

All three pages share one stylesheet. Edit text in the HTML files directly.

## 2. Final placeholder
- `terms.html` → section 9 still has `[YOUR COUNTRY / STATE]` — replace with the
  country/state you operate from. (Privacy/contact fields were intentionally removed —
  docs point to "the server operator" since the bot is self-hosted.)

## 3. Deploying to quaestio.online (once the server is reachable)
1. Copy this folder to the server: `scp -r quaestio-site/ ca@100.76.239.124:/opt/quaestio/www/`
2. Cloudflare Tunnel maps `quaestio.online` → `http://localhost:80` serving `/opt/quaestio/www`
   (config written when the tunnel is set up; no open ports needed).
3. HTTPS is automatic via Cloudflare.

### Until the server is back (temporary, for verification now)
Drag this folder onto https://app.netlify.com/drop → instant URLs:
- Privacy: `https://<name>.netlify.app/privacy.html`
- Terms:  `https://<name>.netlify.app/terms.html`

## 4. Invite link (used in the buttons)
`https://discord.com/oauth2/authorize?client_id=1537428372802506802&permissions=1101994781766&scope=bot`
- Permissions included: kick, ban, moderate members (timeouts), manage roles, purge,
  send messages/embeds, read history, reactions, nickname, use slash commands.
- If you change permissions in the portal, regenerate this integer at
  https://discord.com/api/oauth2/authorize?client_id=1537428372802506802&scope=bot and update
  every link in `index.html` (3 places).

## 5. Discord Verification checklist (Blue Badge)
- [x] Bot in 75+ unique servers
- [x] Privacy Policy URL (temporarily Netlify, final quaestio.online)
- [x] Terms of Service URL
- [x] App name/username = Quaestio (no emoji / "Discord" / brand impersonation)
- [x] App icon uploaded (`assets/logo-512.png`) — no trademarks/copyrighted art
- [x] Description + tags set (General Information)
- [x] Developer Terms complied with
- [ ] Personal/team info in Verification tab
- [ ] Apply for Verification (Blue Badge → Yes)
- [ ] Verified account + payment method if asked

## 6. Rich Presence asset key
Large image uploaded to the portal must be named **`logo`**.
On the server: `RPC_LARGE_IMAGE=logo` in `/etc/quaestio/quaestio.env`.
Optional small image: upload a second asset named e.g. `wrench`, then `RPC_SMALL_IMAGE=wrench`.
