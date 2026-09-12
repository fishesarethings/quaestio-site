# Quaestio agent auth guide (auth.md)

How automated systems and AI agents access Quaestio surfaces. No site login
exists — access is per-surface below.

## Admin panel (server owners, humans + agents acting for them)

- URL: https://admin.quaestio.online
- Auth: Discord OAuth2 (`identify` + `guilds`). Flow: GET /auth/login →
  Discord authorize → callback sets a bearer session token.
- Agents acting for a server admin: have the human complete Discord login
  once, then reuse their session token as `Authorization: Bearer <token>`.
- APIs: same-origin `/api/guilds/{id}/settings`, `/api/host/*` (host admins),
  documented in `api-catalog.json`. Rate: human-scale; no key needed beyond
  the session.

## Pool broker (compute contributors, fully machine-usable)

- Base: https://pool.quaestio.online (fallback https://admin.quaestio.online)
- Join: POST /api/pool/register `{pull, model, share, endpoint?}` →
  `{name, node_secret, status}`. No approval step; reputation is automatic.
- Work loop: POST /api/pool/jobs/claim `{node_secret, models[]}` →
  `{job|null}`; POST /api/pool/jobs/complete `{node_secret, job_id,
  response|error}`.
- Public, no auth: GET /api/pool/public, GET /api/pool/leaderboard
  (anonymous node IDs only — safe to display anywhere).
- Bot-only: GET /api/pool/nodes (Discord bot token), POST /api/pool/report.
- Rename (weekly): POST /api/pool/rename `{node_secret}`. Leave:
  POST /api/pool/unregister `{node_secret}`.
- Client rules: custom `User-Agent` (Cloudflare challenges default
  library UAs), HTTPS only, 30 req/min/IP on write endpoints.

## Discord bot (end users)

- No token needed: invite the shared bot, use slash commands in-server.
  Hosting your own bot app is not a thing here — contribute compute instead.

## What agents must NOT do

- Never publish node endpoints, models tied to people, or session tokens.
- Pool names (`node-xxxx`) are safe to quote; they resolve to nothing.
