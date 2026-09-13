# Quaestio skills index (skills.md) — what the Discord agent can do

Machine-readable skill list for AI assistants helping server admins.
Full command reference: https://quaestio.online/ (Commands section).

## ai — local AI chat (Ollama, no cloud)
/ask <prompt> — one-shot question; @Quaestio mention for chat; conversation
mode keeps answering follow-ups for a few minutes; `go away` ends it.
/summarize [limit] — bullets over recent channel history.
/ai status — embed: source, model, personality, memory, quota, contributor badge.
/ai model <name> — per-server model (autocomplete from host box).
/ai toggle <bool> — enable/disable. /ai personality|character <name|none>.
/ai clear — wipe channel memory.

## levels — XP and ranks
/rank [member], /profile [member] (learned facts), /leaderboard [top].

## moderation — Administrator only
/warn <member> [reason] (auto-kick at warn limit), /warns, /delwarns,
/kick, /ban, /unban <name>, /purge <count≤100>, /mute <member> <minutes>, /unmute.

## tags — reusable answers
/tag <name>, /tagcreate (admin), /tagdelete (admin), /tags.

## birthdays
/birthday set <month> <day>, /birthday list, /birthday remove.

## core
/ping, /uptime, /about, /invite, /panel (opens https://admin.quaestio.online).

## games
/8ball, /dice [XdY], /coin, /rps <rock|paper|scissors>, /slot,
/trivia + /answer (DMs work too), /tictactoe @friend + /move <1-9>.

## core extras
/help, /userinfo, /serverinfo, /avatar, /poll, /remind, /site, /contribute.

## games
/hangman (solo/together/race) + /hm_guess, /wouldyou, /truthordare (/tod alias), /majority, /scramble + /unscramble.

## pool (community compute)
/pool — anonymous nodes online, capacity, top contributors.
Contribute: install + `quaestio pool-serve` (outbound only, NAT-proof).
Perks: priority routing, 2–4x request limits by share, gold badge.
Docs: https://pool.quaestio.online and auth.md (same folder).
