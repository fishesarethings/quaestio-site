#!/usr/bin/env python3
"""Quaestio command-line manager.

After install, `quaestio` is a command on your PATH — just type it:

  quaestio               -> interactive menu
  quaestio help          -> the same guide, as text
  quaestio <action>      -> run one action directly

Actions: status, start, stop, restart, update, uninstall, contribute,
settings, localweb, about.

No admin needed: everything lives in ~/quaestio (or QUAESTIO_DIR). Uninstall
removes the directory, the systemd unit and the keyfile — nothing is left
behind except an empty ~/quaestio if it already existed before install.
"""

import argparse
import datetime
import os
import shutil
import subprocess
import sys

try:
    from textual.app import App as _TApp, ComposeResult
    from textual.binding import Binding
    from textual.containers import Horizontal, Vertical
    from textual.screen import ModalScreen
    from textual.widgets import Button, Footer, Header, Input, ListItem, ListView, Static
except Exception:
    _TApp = None
    ComposeResult = Binding = None
    Horizontal = Vertical = ModalScreen = None
    Button = Footer = Header = Input = ListItem = ListView = Static = None

HOME = os.path.expanduser("~")
INSTALL_DIR = os.environ.get("QUAESTIO_DIR", os.path.join(HOME, "quaestio"))
BOT_DIR = os.path.join(INSTALL_DIR, "bot")
VENV = os.path.join(INSTALL_DIR, ".venv")
def _default_keyfile_path() -> str:
    if sys.platform == "win32":
        return os.path.join(os.environ.get("USERPROFILE", ""), ".quaestio", "keyfile")
    if sys.platform == "darwin":
        return os.path.join(HOME, ".quaestio", "keyfile")
    return "/etc/quaestio/keyfile"


SERVICE = "/etc/systemd/system/quaestio.service"
KEYFILE_DEFAULT = _default_keyfile_path()
KEYFILE_LOCAL = os.path.join(INSTALL_DIR, "quaestio.key")

RESET = "\033[0m"
BOLD = "\033[1m"
CYAN = "\033[36m"
GREEN = "\033[32m"
YELLOW = "\033[33m"
RED = "\033[31m"
DIM = "\033[2m"


def say(msg, color=CYAN):
    print(f"{color}[quaestio]{RESET} {msg}")


def boom(msg):
    print(f"{RED}[quaestio]{RESET} {msg}")
    sys.exit(1)


def which(cmd):
    return shutil.which(cmd) is not None


def is_linux_systemd():
    return sys.platform.startswith("linux") and which("systemctl")


def is_installed():
    return os.path.isdir(BOT_DIR) and os.path.isfile(os.path.join(BOT_DIR, "bot.py"))


def venv_python():
    p = os.path.join(VENV, "bin", "python")
    return p if os.path.exists(p) else sys.executable


def systemd_active():
    try:
        p = subprocess.run(["systemctl", "is-active", "quaestio.service"],
                           capture_output=True, text=True)
        return p.stdout.strip() == "active"
    except Exception:
        return False


def read_env(k):
    env_file = os.path.join(BOT_DIR, ".env")
    if not os.path.isfile(env_file):
        cwd_env = os.path.join(os.getcwd(), ".env")
        env_file = cwd_env if os.path.isfile(cwd_env) else None
    if not env_file:
        return os.environ.get(k)
    try:
        with open(env_file) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, val = line.split("=", 1)
                    if key == k:
                        return val
    except Exception:
        return None
    return None


# ---------------------------------------------------------------------------
# Actions
# ---------------------------------------------------------------------------

def is_running():
    try:
        out = subprocess.run(["pgrep", "-f", r"python[0-9.]* .*bot\.py"],
                             capture_output=True, text=True)
        return bool(out.stdout.strip())
    except Exception:
        return False


def start():
    if systemd_active():
        say("Already running as a service.", GREEN)
        return
    if is_running():
        say("Already running.", GREEN)
        return
    if is_linux_systemd() and os.path.exists(SERVICE):
        subprocess.run(["sudo", "systemctl", "start", "quaestio.service"])
        say("Started (systemd). Status: systemctl status quaestio", GREEN)
        return
    run_sh = os.path.join(INSTALL_DIR, "run-quaestio.sh")
    if os.path.exists(run_sh):
        say("For a background service, use the installer's systemd option "
            "(Linux). A quick foreground run:")
        say(f"  {run_sh}", GREEN)
    else:
        p = venv_python()
        say("Run the bot from the bot folder:")
        say(f"  cd {BOT_DIR} && set -a && source .env && set +a && {p} bot.py")


def stop():
    if is_linux_systemd() and os.path.exists(SERVICE):
        subprocess.run(["sudo", "systemctl", "stop", "quaestio.service"])
        say("Stopped (systemd).", GREEN)
        return
    try:
        subprocess.run(["pkill", "-f", r"python[0-9.]* .*bot\.py"])
        say("Sent stop to the running bot process.", GREEN)
    except Exception:
        say("Nothing running to stop.", YELLOW)


def restart():
    stop()
    start()


def update():
    if not is_installed():
        boom("Quaestio isn't installed here. Run the installer first:\n"
             f"  curl -fsSL https://quaestio.online/bot/install.sh | bash")
    say("Updating bot code from GitHub…")
    base = os.environ.get("QUAESTIO_SRC",
                          "https://raw.githubusercontent.com/fishesarethings/quaestio-site/main/bot")
    for f in ("bot.py", "config.py", "requirements.txt", ".env.example", "quaestio.py"):
        subprocess.run(["curl", "-fsSL", f"{base}/{f}", "-o", os.path.join(BOT_DIR, f)])
    subprocess.run([venv_python(), "-m", "pip", "install", "--quiet",
                    "-r", os.path.join(BOT_DIR, "requirements.txt")])
    say("Code + dependencies updated.", GREEN)
    restart()
    say("Restarted. Check the log with `journalctl -u quaestio -f` (Linux).")


def uninstall():
    if not is_installed() and not os.path.exists(SERVICE):
        boom("Nothing installed here — nothing to remove.")
    say("Stopping the bot…")
    stop()
    wiped = []
    if is_linux_systemd() and os.path.exists(SERVICE):
        for cmd in (["sudo", "systemctl", "disable", "quaestio.service"],
                    ["sudo", "rm", "-f", SERVICE]):
            subprocess.run(cmd)
        subprocess.run(["sudo", "systemctl", "daemon-reload"])
        wiped.append(SERVICE)
    keyfile = os.environ.get("QUAESTIO_KEY_FILE", KEYFILE_DEFAULT)
    if os.path.exists(keyfile):
        subprocess.run(["sudo", "rm", "-f", keyfile])
        wiped.append(keyfile)
    local_key = KEYFILE_LOCAL
    if os.path.exists(local_key):
        os.remove(local_key)
        wiped.append(local_key)
    if os.path.isdir(INSTALL_DIR):
        shutil.rmtree(INSTALL_DIR, ignore_errors=True)
        wiped.append(INSTALL_DIR)
    # Remove the `quaestio` PATH command if it points at this install.
    for d in (os.path.join(HOME, ".local", "bin"), os.path.join(HOME, "bin"), "/usr/local/bin"):
        link = os.path.join(d, "quaestio")
        try:
            if os.path.islink(link) or os.path.isfile(link):
                if os.path.realpath(link) == os.path.realpath(os.path.join(INSTALL_DIR, "bin", "quaestio")) \
                        or os.path.realpath(link) == os.path.realpath(os.path.join(BOT_DIR, "quaestio.py")):
                    os.remove(link)
                    wiped.append(link)
        except Exception:
            pass
    say("Removed: " + ", ".join(wiped), GREEN)
    say("Done — Quaestio is fully gone. If you want the AI gone too: "
        "`ollama rm qwen2.5:1.5b`, and uninstall Ollama itself anytime.")


def status():
    say("Install location: " + INSTALL_DIR)
    if is_installed():
        say("Bot code: present", GREEN)
    else:
        say("Bot code: not installed yet", YELLOW)
    if is_linux_systemd() and os.path.exists(SERVICE):
        say(("Service: running" if systemd_active() else "Service: stopped"), GREEN if systemd_active() else YELLOW)
    elif is_running():
        say("Bot process: running", GREEN)
    else:
        say("Bot process: not running", YELLOW)
    model = read_env("OLLAMA_MODEL")
    endpoint = read_env("OLLAMA_BASE_URL")
    if model:
        say(f"Model: {model} · Endpoint: {endpoint}")
    token = read_env("BOT_TOKEN")
    say("Bot token configured: " + ("yes (hidden)" if token else "no — run `settings`"), GREEN if token else YELLOW)
    if read_env("POOL_NODE_SECRET"):
        d = _pool_status_data(read_env("POOL_NODE_SECRET"))
        if d and "error" not in d and "name" in d:
            say(f"Community pool: {d['name']} · {d['status']} · {d['served']} requests served",
                GREEN if d["status"] == "active" else YELLOW)


# ---------------------------------------------------------------------------
# Install / add components (full-screen wizard)
# ---------------------------------------------------------------------------

def install_menu():
    """Open the full-screen installer — it first asks WHAT you want (bot,
    web panel, pool), then the connection + model, the token, and installs.
    Falls back to the classic `install.sh` command when this terminal can't
    run a full-screen TUI."""
    import urllib.request
    if not which("curl") and not which("python3"):
        boom("Can't install without curl or python3 on this machine.")
    wizard = os.path.join(BOT_DIR, "install_wizard.py")
    os.makedirs(BOT_DIR, exist_ok=True)
    say("Fetching the latest installer wizard…")
    base = os.environ.get("QUAESTIO_SRC",
                          "https://raw.githubusercontent.com/fishesarethings/quaestio-site/main/bot")
    try:
        urllib.request.urlretrieve(f"{base}/install_wizard.py", wizard)
    except Exception:
        boom("Couldn't fetch the wizard. Run it directly instead:\n"
             "  curl -fsSL https://quaestio.online/bot/install.sh | bash")
    try:
        import textual  # noqa: F401
    except Exception:
        boom("Full-screen installer needs the `textual` UI library, which isn't "
             "installed in this Python. Run the text installer instead:\n"
             "  curl -fsSL https://quaestio.online/bot/install.sh | bash")
    say("Opening the installer — tick what you'd like to install, then Next…")
    env = dict(os.environ)
    env.setdefault("QUAESTIO_DIR", INSTALL_DIR)
    env.setdefault("BOT_TOKEN", read_env("BOT_TOKEN") or "")
    env.setdefault("QUAESTIO_SRC", "https://raw.githubusercontent.com/fishesarethings/quaestio-site/main/bot")
    if os.path.exists(KEYFILE_LOCAL) and not os.environ.get("QUAESTIO_KEY_FILE"):
        env["QUAESTIO_KEY_FILE"] = KEYFILE_LOCAL
    subprocess.call([sys.executable, wizard], env=env)
    say("Done. Pick 'Status' to check, or 'Settings' to adjust anything.", GREEN)


# ---------------------------------------------------------------------------
# Contribution to the resource pool
# ---------------------------------------------------------------------------

def _anon_name() -> str:
    import secrets
    return "node-" + secrets.token_hex(2)


def _broker_url():
    return (read_env("POOL_BROKER_URL") or "").strip() or "https://admin.quaestio.online"


def _pool_json(url, payload):
    import json
    import urllib.error
    import urllib.request
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        return {"error": f"broker {e.code}: {e.read().decode(errors='replace')[:140]}"}
    except Exception as e:
        return {"error": f"broker unreachable ({e})"}


def _env_file_path():
    if os.path.isdir(BOT_DIR):
        return os.path.join(BOT_DIR, ".env")
    return os.path.join(os.getcwd(), ".env")


def _write_pool_creds(data):
    env_path = _env_file_path()
    os.makedirs(os.path.dirname(env_path) or ".", exist_ok=True)
    lines = []
    if os.path.exists(env_path):
        with open(env_path) as f:
            lines = f.readlines()
    kept = [ln for ln in lines if not ln.strip().startswith(("POOL_NODE_ID=", "POOL_NODE_SECRET="))]
    kept.append(f"POOL_NODE_ID={data.get('name', '')}\n")
    kept.append(f"POOL_NODE_SECRET={data.get('node_secret', '')}\n")
    with open(env_path, "w") as f:
        f.writelines(kept)


def _pool_status_data(node_secret):
    d = _pool_json(_broker_url().rstrip("/") + "/api/pool/me", {"node_secret": node_secret})
    return None if d.get("error", "").startswith("broker 404") else d


def pool_status():
    """Show this box's contribution to the community pool."""
    node_secret = read_env("POOL_NODE_SECRET") or ""
    node_id = read_env("POOL_NODE_ID") or ""
    if not node_secret:
        say("This box isn't in the community pool yet.", YELLOW)
        say("Join with:  quaestio contribute", GREEN)
        return
    say(f"Community pool node: {node_id or 'node-?'}\n")
    d = _pool_status_data(node_secret)
    if not d:
        say("This node no longer exists in the pool (removed by the host?).", YELLOW)
        say("Re-join with:  quaestio contribute", GREEN)
        return
    if "error" in d:
        say(f"Couldn't reach the pool broker ({d['error']}).", YELLOW)
        say(f"Broker: {_broker_url()}")
        return
    say(f"  Node:      {d['name']}", GREEN)
    if d["status"] == "active":
        say("  Status:    active — requests route to your box", GREEN)
    else:
        say("  Status:    pending host approval (see the panel Host → Community pool)", YELLOW)
    say(f"  Share:     {d['share']}% of your box")
    say(f"  Model:     {d.get('model') or '?'}")
    say(f"  Requests served:  {d['served']}", GREEN)
    if d.get("last_ok"):
        say(f"  Last ok:   {d['last_ok'][:19]} UTC")
    if not d.get("last_ok") and d.get("last_fail"):
        say(f"  Last fail: {d['last_fail'][:19]} UTC (your box looks unreachable — "
            "make sure Ollama is open to the internet)", RED)
    say("\nChange details:  quaestio contribute   ·   Leave the pool:  quaestio contribute")


pool = pool_status


def contribute():
    say("COMMUNITY POOL — lend part of your AI box, borrow from others when busy.\n")
    node_secret = read_env("POOL_NODE_SECRET") or ""
    if node_secret:
        d = _pool_status_data(node_secret)
        if d and "error" not in d and "name" in d:
            say(f"You're node {d['name']} — {d['status']}, {d['share']}% share, "
                f"{d['served']} requests served.")
            choice = input("\nWhat do you want to do?\n"
                           "  [u] update endpoint / model / share\n"
                           "  [l] leave the pool\n"
                           "  [c] cancel\n"
                           "> ").strip().lower()
            if choice == "l":
                let = _pool_json(_broker_url().rstrip("/") + "/api/pool/unregister",
                                 {"node_secret": node_secret})
                if "error" not in let:
                    say("You left the pool — your box is no longer shared.", GREEN)
                else:
                    say(f"Couldn't reach the broker to leave ({let['error']}).", YELLOW)
                _write_pool_creds({"name": "", "node_secret": ""})
                return
            if choice != "u":
                return
        elif d is None:
            say("This node's gone from the pool — re-registering as a fresh one.")
            node_secret = ""
        else:
            say(f"Pool broker unreachable ({d['error']}). Showing stored registration.")
    endpoint = input("Your Ollama URL [default http://127.0.0.1:11434]: ").strip() or "http://127.0.0.1:11434"
    model = input("Model you're sharing [default qwen2.5:1.5b]: ").strip() or "qwen2.5:1.5b"
    share = input("How much of your box to share, percent [10-100, default 50]: ").strip() or "50"
    try:
        share = max(10, min(100, int(share)))
    except ValueError:
        share = 50
    say("Connecting to the community pool…", DIM)
    reg = _pool_json(_broker_url().rstrip("/") + "/api/pool/register",
                     {"endpoint": endpoint, "model": model, "share": share,
                      **({"node_secret": node_secret} if node_secret else {})})
    if "error" not in reg and reg.get("name"):
        _write_pool_creds(reg)
        if reg.get("status") == "pending":
            say(f"Connected to the community pool as {reg['name']} ({share}%) — "
                "pending host approval.", GREEN)
        else:
            say(f"Connected to the community pool as {reg['name']} ({share}%) — "
                "requests now route to you.", GREEN)
        say("See your contributions anytime:  quaestio pool", GREEN)
        return
    # Broker unreachable → fall back to the local pool so a self-hosted bot works.
    say(f"The pool broker isn't reachable ({reg.get('error', '?')}). "
        "Registering in the local pool instead.", YELLOW)
    sys.path.insert(0, BOT_DIR)
    try:
        import config as quaestio_cfg
        enc_endpoint = quaestio_cfg.maybe_encrypt("pool_endpoint", endpoint)
        enc_model = quaestio_cfg.maybe_encrypt("pool_model", model)
    except Exception:
        enc_endpoint, enc_model = endpoint, model
    db_path = read_env("DB_PATH")
    if not db_path:
        cand = os.path.join(BOT_DIR, "quaestio.db")
        db_path = cand if os.path.isdir(BOT_DIR) else os.path.join(os.getcwd(), "quaestio.db")
    import sqlite3
    conn = sqlite3.connect(db_path)
    conn.execute(
        "INSERT INTO hosters (name, endpoint, model, share, enabled, added_by, at) "
        "VALUES (?, ?, ?, ?, 1, 'cli', ?)",
        (_anon_name(), enc_endpoint, enc_model, share, datetime.datetime.now().isoformat()),
    )
    conn.commit()
    conn.close()
    say(f"Done. You're contributing {share}% of your box to the local pool.", GREEN)


# ---------------------------------------------------------------------------
# Settings — .env editor with a guided menu
# ---------------------------------------------------------------------------

def _pool_db_path():
    db_path = read_env("DB_PATH")
    if not db_path:
        cand = os.path.join(BOT_DIR, "quaestio.db")
        db_path = cand if os.path.isdir(BOT_DIR) else os.path.join(os.getcwd(), "quaestio.db")
    return db_path


def _pool_rows():
    """This box's pool rows, endpoint/model decrypted, for the settings TUI."""
    import sqlite3
    db_path = _pool_db_path()
    if not os.path.isfile(db_path):
        return []
    try:
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        rows = [dict(r) for r in conn.execute(
            "SELECT id, name, endpoint, model, share, enabled FROM hosters ORDER BY id").fetchall()]
        conn.close()
    except Exception:
        return []
    sys.path.insert(0, BOT_DIR)
    try:
        import config as q_cfg
        dec = q_cfg.maybe_decrypt
        enc = q_cfg.maybe_encrypt
    except Exception:
        dec = lambda _k, v: v
        enc = lambda _k, v: v
    for r in rows:
        r["endpoint"] = (dec("pool_endpoint", r["endpoint"]) or "").strip()
        r["model"] = (dec("pool_model", r["model"]) or "").strip()
    return rows


def _pool_apply(endpoint, model, share):
    """Create/update this box's pool node (the settings TUI's resources tab).
    share 0 enables the row and keeps it; set None to leave share unchanged."""
    import sqlite3
    import secrets
    db_path = _pool_db_path()
    conn = sqlite3.connect(db_path)
    my_id = None
    local_ep = (read_env("OLLAMA_BASE_URL") or "http://127.0.0.1:11434").strip().rstrip("/")
    try:
        rows = conn.execute("SELECT id, endpoint FROM hosters WHERE enabled=1").fetchall()
        for r in rows:
            if r[1] and r[1].startswith("enc:"):
                ep = (config_dec_pool(r[1]) or "").rstrip("/")
            else:
                ep = (r[1] or "").rstrip("/")
            if ep == local_ep:
                my_id = r[0]
                break
        if my_id is None:
            rows = conn.execute("SELECT id, added_by FROM hosters WHERE added_by IN ('cli','installer') ORDER BY id DESC LIMIT 1").fetchall()
            if rows:
                my_id = rows[0][0]
        if my_id is None:
            rows = conn.execute("SELECT id FROM hosters ORDER BY id DESC LIMIT 1").fetchall()
            if rows:
                my_id = rows[0][0]
    except Exception:
        pass

    sys.path.insert(0, BOT_DIR)
    try:
        import config as q_cfg
        enc_ep = q_cfg.maybe_encrypt("pool_endpoint", endpoint)
        enc_m = q_cfg.maybe_encrypt("pool_model", model)
    except Exception:
        enc_ep, enc_m = endpoint, model

    if my_id is not None:
        conn.execute("UPDATE hosters SET endpoint=?, model=?, share=?, enabled=1 WHERE id=?",
                     (enc_ep, enc_m, max(0, min(100, int(share or 50))), my_id))
    else:
        conn.execute(
            "INSERT INTO hosters (name, endpoint, model, share, enabled, added_by, at) "
            "VALUES (?, ?, ?, ?, 1, 'cli', ?)",
            (_anon_name(), enc_ep, enc_m, max(0, min(100, int(share or 50))),
             datetime.datetime.now().isoformat()))
    conn.commit()
    conn.close()


def config_dec_pool(v):
    """Best-effort decrypt of a pool endpoint/model for display."""
    try:
        import config as q_cfg
        return q_cfg.maybe_decrypt("pool_endpoint", v)
    except Exception:
        return v


def write_env_value(key, value):
    """Set/clear a .env value directly (used by the settings TUI). 'CLEAR' wipes it."""
    env_file = os.path.join(BOT_DIR, ".env")
    val = (value or "").strip()
    if val.upper() == "CLEAR":
        val = ""
    lines = []
    if os.path.isfile(env_file):
        with open(env_file) as f:
            lines = f.readlines()
    out = [ln for ln in lines if not ln.startswith(key + "=")]
    if val:
        out.append(f"{key}={val}\n")
    with open(env_file, "w") as f:
        f.writelines(out)
    os.chmod(env_file, 0o600)


ENV_QUESTIONS = [
    ("BOT_TOKEN", "Discord bot token (optional, add later)", None, True),
    ("OLLAMA_BASE_URL", "Where Ollama lives (e.g. http://127.0.0.1:11434)", "http://127.0.0.1:11434", False),
    ("OLLAMA_MODEL", "Default model to use", "qwen2.5:1.5b", False),
    ("OLLAMA_TIMEOUT", "AI timeout in seconds", "180", False),
    ("PREFIX", "Command prefix for text commands", "/", False),
    ("WARN_LIMIT", "Auto-kick after this many warns", "3", False),
    ("DB_PATH", "SQLite database path", "quaestio.db", False),
]


def edit_env(key, label, default, secret):
    env_file = os.path.join(BOT_DIR, ".env")
    current = read_env(key) or ""
    current_label = "(hidden)" if secret and current else (current or "(not set)")
    print(f"  {BOLD}{label}{RESET}  {DIM}current: {current_label}{RESET}")
    val = input(f"  New value{(' (leave blank to keep, ' + DIM + 'type CLEAR to wipe' + RESET + ')' if current else '')}: ").strip()
    if val == "CLEAR":
        val = ""
    elif not val:
        if not current:
            val = default or ""
        else:
            return None
    lines = []
    if os.path.isfile(env_file):
        with open(env_file) as f:
            lines = f.readlines()
    kept = False
    out = []
    for line in lines:
        if line.startswith(key + "="):
            if val:
                out.append(f"{key}={val}\n")
            kept = True
        else:
            out.append(line)
    if not kept and val:
        out.append(f"{key}={val}\n")
    with open(env_file, "w") as f:
        f.writelines(out)
    os.chmod(env_file, 0o600)
    return val


def settings():
    env_file = os.path.join(BOT_DIR, ".env")
    if not os.path.isdir(BOT_DIR):
        boom("No install at " + INSTALL_DIR + ". Install first, then configure.")
    if not os.path.isfile(env_file):
        say("No .env yet — creating one from the example.")
        shutil.copy(os.path.join(BOT_DIR, ".env.example"), env_file)
    if _tui():
        try:
            if settings_tui():
                if which("ollama"):
                    m = read_env("OLLAMA_MODEL") or "qwen2.5:1.5b"
                    if input(f"\nPull the AI model '{m}' now if missing? [y/N] ").strip().lower() in ("y", "yes"):
                        subprocess.run(["ollama", "pull", m])
                if input("\nRestart the bot to apply changes? [Y/n] ").strip().lower() in ("", "y", "yes"):
                    restart()
                return
        except Exception as exc:
            say(f"Settings TUI fell back to the text flow ({exc}).", DIM)
    say("Change Quaestio settings. Leave a field blank to keep it, type CLEAR to reset.\n")
    for key, label, default, secret in ENV_QUESTIONS:
        edit_env(key, label, default, secret)
    say("\nSettings saved to " + env_file + " (permissions 600).")
    if which("ollama"):
        m = read_env("OLLAMA_MODEL") or "qwen2.5:1.5b"
        if input(f"\nPull the AI model '{m}' now if missing? [y/N] ").strip().lower() in ("y", "yes"):
            subprocess.run(["ollama", "pull", m])
    if input("\nRestart the bot to apply changes? [Y/n] ").strip().lower() in ("", "y", "yes"):
        restart()


# ---------------------------------------------------------------------------
# Settings as a real full-screen TUI (Textual) — neatly laid out, no overlap.
# Sections: Bot, AI engine, Community pool (the resources you lend the pool).
# ---------------------------------------------------------------------------

SETTINGS_ROWS = [
    # (section, key, label, secret, kind)
    ("Bot", "BOT_TOKEN", "Discord bot token (optional)", True, "env"),
    ("Bot", "PREFIX", "Command prefix", False, "env"),
    ("Bot", "WARN_LIMIT", "Warn limit before kick", False, "env"),
    ("AI engine", "OLLAMA_BASE_URL", "Ollama endpoint", False, "env"),
    ("AI engine", "OLLAMA_MODEL", "Default model", False, "env"),
    ("AI engine", "OLLAMA_TIMEOUT", "AI timeout (seconds)", False, "env"),
    ("Community pool", "POOL_SHARE", "Share you lend the pool (%)", False, "pool"),
    ("Community pool", "POOL_ENDPOINT", "Endpoint you share", False, "pool"),
    ("Community pool", "POOL_MODEL", "Model you share", False, "pool"),
]


def _settings_pool_row():
    rows = _pool_rows()
    return rows[0] if rows else None


def _settings_current(kind, key):
    if kind == "pool":
        r = _settings_pool_row()
        if r is None:
            return "not contributing"
        if key == "POOL_SHARE":
            return f"{r['share']}%"
        if key == "POOL_ENDPOINT":
            return r["endpoint"] or "(not set)"
        return r["model"] or "(not set)"
    v = read_env(key) or ""
    if key == "BOT_TOKEN":
        if v:
            return "(hidden — is set)"
        return "(not set — optional)"
    return v or "(not set)"


if _TApp is not None and ModalScreen is not None:
    class SettingsEdit(ModalScreen):
        def __init__(self, label, initial, secret):
            super().__init__()
            self._label = label
            self._initial = initial
            self._secret = secret
    
        def compose(self) -> ComposeResult:
            with Vertical(classes="modal"):
                yield Static(f"[b]  {self._label}[/b]", classes="mtitle")
                yield Input(
                    value=self._initial,
                    password=self._secret,
                    placeholder="Leave as-is · type CLEAR to empty",
                    id="sval",
                )
                yield Static("  ⏎ enter: save   ·   esc: cancel", classes="mhelp")
                with Horizontal(id="mnav"):
                    yield Button("Cancel", variant="default", id="mcancel")
                    yield Button("Save", variant="primary", id="msave")
    
        def on_button_pressed(self, event: Button.Pressed) -> None:
            if event.button.id == "msave":
                self.dismiss(self.query_one("#sval", Input).value)
            else:
                self.dismiss(None)
    
    
    if _TApp is not None and ModalScreen is not None:
        class SettingsApp(_TApp):
            TITLE = "Quaestio — settings"
            CSS = """
            Screen { background: #0d1117; }
            #body { padding: 0 3; }
            #list { border: round #30363d; height: 1fr; }
            #list:focus-within { border: round #58a6ff; }
            ListView { height: 1fr; }
            ListItem { height: 3; padding: 0 1; }
            ListItem.--highlight { background: #1f6feb; }
            #bottom { height: 4; align-horizontal: right; }
            #bottom Button { margin: 0 1; }
            .modal { width: 60; height: auto; background: #161b22; border: round #58a6ff; padding: 1 2; }
            #mnav { height: auto; align-horizontal: right; }
            #mnav Button { margin: 0 1; }
            """
            BINDINGS = [
                Binding("q", "quit", "Quit", priority=True),
                Binding("escape", "quit", "Quit", priority=True),
                Binding("up,k", "cursor_up", "Up", show=False),
                Binding("down,j", "cursor_down", "Down", show=False),
            ]
    
            def compose(self) -> ComposeResult:
                yield Header(show_clock=True)
                with Vertical(id="body"):
                    yield Static("[b]Settings[/b] — pick a row, ⏎ to edit. Everything stays on this machine.",
                                 classes="pvhint")
                    yield ListView(id="list")
                    yield Static("  ↑↓/j/k move · ⏎ edit · [b]q[/b]/esc quit · [b]Restart & done[/b] to apply", id="keys")
                    with Horizontal(id="bottom"):
                        yield Button("Pull AI model", id="pull")
                        yield Button("Restart & done", variant="success", id="done")
                yield Footer()
    
            def _build_items(self):
                from textual.widgets import ListItem, ListView, Static
                lv = self.query_one("#list", ListView)
                lv.remove_children(list(lv.children))
                first_pool = True
                for section, key, label, secret, kind in SETTINGS_ROWS:
                    if kind == "pool" and first_pool:
                        first_pool = False
                        r = _settings_pool_row()
                        share = r["share"] if r else 0
                        lv.append(ListItem(
                            Static(f"[b]● Community pool[/b]  [dim]lending {share}% of your box to other servers[/dim]",
                                   classes="sechead"),
                            id="poolhdr"))
                    lv.append(ListItem(
                        Static(f"[b]{label}[/b]" + ("  [dim](secret)[/dim]" if secret else ""), classes="slbl"),
                        Static(f"[dim]    {_settings_current(kind, key)}[/dim]", classes="sval", id="v_" + key),
                        id="row_" + key,
                    ))
    
            def on_mount(self) -> None:
                self._build_items()
                self.query_one("#list", ListView).focus()
    
            def on_list_view_selected(self, ev) -> None:
                row_id = getattr(ev.item, "id", "") or ""
                if not row_id.startswith("row_"):
                    return
                key = row_id[len("row_"):]
                kind = next(_kk for _k, rk, _l, _s, _kk in SETTINGS_ROWS if rk == key)
                secret = next(s for _k, rk, _l, s, _kk in SETTINGS_ROWS if rk == key)
                if kind == "pool":
                    r = _settings_pool_row()
                    if r is None:
                        init = "http://127.0.0.1:11434" if key == "POOL_ENDPOINT" else ("qwen2.5:1.5b" if key == "POOL_MODEL" else "50")
                    elif key == "POOL_SHARE":
                        init = str(r["share"])
                    elif key == "POOL_ENDPOINT":
                        init = r["endpoint"] or ""
                    else:
                        init = r["model"] or ""
                else:
                    init = read_env(key) or ""
                label = next(l for _k, rk, l, _s, _kk in SETTINGS_ROWS if rk == key)
                self.push_screen(SettingsEdit(label, init, secret),
                                 callback=lambda result: self._apply_row(key, kind, result))
    
            def _apply_row(self, key, kind, result) -> None:
                if result is None:
                    return
                if kind == "env":
                    write_env_value(key, result)
                else:
                    r = _settings_pool_row()
                    endpoint = result if key == "POOL_ENDPOINT" else (
                        r["endpoint"] if r else (read_env("OLLAMA_BASE_URL") or "http://127.0.0.1:11434"))
                    model = result if key == "POOL_MODEL" else (
                        r["model"] if r else (read_env("OLLAMA_MODEL") or "qwen2.5:1.5b"))
                    share = int(result) if key == "POOL_SHARE" else (r["share"] if r else 50)
                    _pool_apply(endpoint or "http://127.0.0.1:11434", model or "qwen2.5:1.5b", share)
                self.query_one("#v_" + key, Static).update(f"[dim]    {_settings_current(kind, key)}[/dim]")
                if kind == "pool":
                    r = _settings_pool_row()
                    share = r["share"] if r else 0
                    self.query_one("#poolhdr").query_one(Static).update(
                        f"[b]● Community pool[/b]  [dim]lending {share}% of your box to other servers[/dim]")
                self.query_one("#list", ListView).focus()
    
            def on_button_pressed(self, event: Button.Pressed) -> None:
                if event.button.id == "pull":
                    event.button.label = "Pulling…"
                    subprocess.run(["ollama", "pull", read_env("OLLAMA_MODEL") or "qwen2.5:1.5b"],
                                   check=False)
                    event.button.label = "Pull AI model"
                elif event.button.id == "done":
                    self.exit(True)
    
    
def settings_tui():
    """Open the full-screen settings form. Returns True when the user saves."""
    if _TApp is None:
        raise RuntimeError("Textual isn't installed — using the text flow.")
    return SettingsApp().run()


# Local web server for the same settings (optional, toggled from the CLI)
# ---------------------------------------------------------------------------

LOCAL_PORT = "8123"


def localweb():
    say("LOCALHOST WEB PANEL — view and change the same settings in a browser.")
    say("Uses only the bot's own data; you can turn it on or off from this menu.")
    mode = input(f"Enable on http://127.0.0.1:{LOCAL_PORT} ? [y/N] ").strip().lower()
    if mode not in ("y", "yes"):
        say("Local web panel stays off.")
        return
    env_file = os.path.join(BOT_DIR, ".env")
    with open(env_file, "a") as f:
        f.write(f"LOCAL_WEB=1\nLOCAL_WEB_PORT={LOCAL_PORT}\n")
    say(f"Enabled. Point your browser at http://127.0.0.1:{LOCAL_PORT} (or "
        "http://localhost:{LOCAL_PORT}). A page is served that lets you edit "
        "the same settings the CLI does.", GREEN)
    if input("Restart the bot so it serves the panel? [Y/n] ").strip().lower() in ("", "y", "yes"):
        restart()
    say("Disable anytime by re-running `quaestio localweb` and choosing N, "
        "or deleting LOCAL_WEB=1 from bot/.env.")


# ---------------------------------------------------------------------------
# About
# ---------------------------------------------------------------------------

ABOUT = f"""
{BOLD}Quaestio{RESET} — your server's own AI companion.

A self-contained Discord bot (AI chat, XP levels, moderation, tags, welcomes,
birthdays, games) with an optional web admin panel. Everything lives in your
folder — nothing is cloud-hosted unless you choose to share.

  {BOLD}Install:{RESET}
    curl -fsSL https://quaestio.online/bot/install.sh | bash

  {BOLD}Manage (this tool):{RESET}
    quaestio                        interactive menu
    quaestio help                   this help as text
    quaestio status                 what's here / running
    quaestio settings               change any setting
    quaestio contribute             join the community pool
    quaestio pool                   see your contributions
    quaestio update                 pull the latest bot
    quaestio uninstall              remove everything

  (Before the installer has put `quaestio` on your PATH, run it directly:
   python3 {os.path.join(BOT_DIR, 'quaestio.py')})

  {BOLD}Resources:{RESET}
    Web:  https://quaestio.online
    Admin panel:  https://admin.quaestio.online
    Docs: README.md in this folder

  {BOLD}Leaves nothing behind:{RESET} uninstall clears {INSTALL_DIR}, the
  systemd unit and the encryption keyfile.
"""


def help_text():
    print(ABOUT)
    print(f"  {BOLD}One-liners you can type directly:{RESET}")
    print("    quaestio status")
    print("    quaestio settings")
    print("    quaestio contribute")
    print("    quaestio pool")
    print("    quaestio update")
    print("    quaestio uninstall")
    print(f"  (no `quaestio` command yet? Run: python3 {os.path.join(BOT_DIR, 'quaestio.py')})")


def _tui():
    try:
        import textual  # noqa: F401
        return True
    except Exception:
        return False


def _pick(title, choices, default=None):
    import questionary
    return questionary.select(
        title,
        choices=choices,
        default=default,
        use_indicator=True,
        use_arrow_keys=True,
    ).ask()


def _menu_actions():
    return [
        ("Install / Add components", install_menu, "full-screen wizard: bot + web panel + pool"),
        ("Status", status, "what's installed / running"),
        ("Start / Stop / Restart", restart, "control the bot"),
        ("Settings", settings, "change tokens, model, timeout…"),
        ("Contribute to the pool", contribute, "join / update / leave the community pool"),
        ("Pool status", pool_status, "your contributions: requests served, share, health"),
        ("Local web panel", localweb, "turn the localhost settings page on/off"),
        ("Update", update, "pull the latest bot code"),
        ("Uninstall", uninstall, "remove everything, nothing left behind"),
        ("About / help", help_text, "how everything works"),
    ]


def _status_text() -> str:
    parts = []
    if is_installed():
        parts.append(f"Installed at {INSTALL_DIR}")
    else:
        parts.append("Not installed yet — pick 'Install / Add components'")
    if is_linux_systemd() and os.path.exists(SERVICE):
        parts.append("service " + ("running" if systemd_active() else "stopped"))
    elif is_running():
        parts.append("process running")
    else:
        parts.append("process stopped")
    model = read_env("OLLAMA_MODEL") or "?"
    parts.append(f"model {model}")
    return "  ·  ".join(parts)


def menu_tui():
    """A real full-screen TUI built on Textual — live status panel on the
    right, arrow keys to move, Enter to run, q to quit. Falls back to the
    numbered menu if Textual isn't installed."""
    try:
        from textual.app import App, ComposeResult
        from textual.containers import Horizontal, Vertical
        from textual.widgets import Footer, Header, ListItem, ListView, Static
        from textual.binding import Binding
    except Exception:
        menu_plain()
        return

    ACTIONS = _menu_actions()

    class Quaestio(App):
        TITLE = "Quaestio — server manager"
        CSS = """
        Screen { background: #0d1117; }
        #logo { height: 3; background: #161b22; color: #58a6ff; }
        #right { width: 38; height: 1fr; padding: 0 1; }
        #right Static { margin: 1 0; }
        #actions { border: round #30363d; height: 1fr; }
        #actions:focus-within { border: round #58a6ff; }
        ListView { height: 1fr; }
        ListItem { padding: 0 1; height: 2; }
        ListItem > Static { width: 1fr; }
        ListView:focus ListItem.--highlight { background: #1f6feb; color: white; }
        #desc { color: #8b949e; height: 1; padding: 0 1; }
        .lbl { color: #58a6ff; }
        """

        BINDINGS = [
            Binding("q", "quit", "Quit", priority=True),
            Binding("escape", "quit", "Quit", priority=True),
            Binding("up,k", "cursor_up", "Up", show=False),
            Binding("down,j", "cursor_down", "Down", show=False),
        ]

        def compose(self) -> ComposeResult:
            yield Header(show_clock=True)
            yield Static("  ██████╗ ██╗   ██╗ █████╗ ███████╗████████╗██╗ ██████╗ "
                         "██╗██████╗ \n  ██╔═══██╗██║   ██║██╔══██╗██╔════╝╚══██╔══╝██║██╔═══██╗"
                         "██║██╔═══██╗\n  ██║   ██║██║   ██║███████║█████╗     ██║   ██║██║   ██║██║██║   ██║",
                         id="logo")
            with Horizontal():
                with Vertical():
                    lv = ListView()
                    yield lv
                    yield Static("", id="desc")
                yield Static(f"[b]● status[/b]\n\n{_status_text()}\n\n[b]● keys[/b]\n↑ ↓  move  ·  Enter  run\nq   quit", id="right")
            yield Footer()

        def on_mount(self) -> None:
            lv = self.query_one(ListView)
            for name, _fn, desc in ACTIONS:
                lv.append(ListItem(Static(f"[b]{name}[/b]"), Static(f"[dim]  {desc}[/dim]")))
            lv.focus()

        def on_list_view_selected(self, event) -> None:
            self.exit((event.index, None))

    lv = Quaestio()
    res = lv.run()
    if res is None:
        # Quit (q / Esc) — exit the whole tool.
        print(f"\n  {CYAN}[quaestio]{RESET} Bye!")
        return
    try:
        idx = int(res[0])
    except Exception:
        menu_plain()
        return
    fn = ACTIONS[idx][1]
    print()
    fn()
    input(f"\n  {DIM}Press Enter to go back to the menu…{RESET} ")
    menu()


def menu_plain():
    os.system("clear" if os.name != "nt" else "cls")
    print(f"{BOLD}{CYAN}┌─────────────────────────────────────────────┐{RESET}")
    print(f"{BOLD}{CYAN}│  Quaestio — server manager                  │{RESET}")
    print(f"{BOLD}{CYAN}└─────────────────────────────────────────────┘{RESET}")
    print()
    if is_installed():
        print(f"  {GREEN}● Installed{RESET}  at {INSTALL_DIR}")
    else:
        print(f"  {YELLOW}○ Not installed yet{RESET}  (pick 1 — Install / Add components)")
    print()
    menu_actions = [
        ("1", "Install / Add components", install_menu, "full-screen wizard: bot + web panel + pool"),
        ("2", "Status", status, "what's installed / running"),
        ("3", "Start / Stop / Restart", restart, "control the bot"),
        ("4", "Settings", settings, "change tokens, model, timeout…"),
        ("5", "Contribute to the pool", contribute, "join / update / leave the community pool"),
        ("6", "Pool status", pool_status, "your contributions: requests served, share, health"),
        ("7", "Local web panel", localweb, "turn the localhost settings page on/off"),
        ("8", "Update", update, "pull the latest bot code"),
        ("9", "Uninstall", uninstall, "remove everything, nothing left behind"),
        ("10", "About / help", help_text, "how everything works"),
        ("0", "Quit", None, "close this menu"),
    ]
    for num, name, _fn, desc in menu_actions:
        print(f"  {BOLD}{num}.{RESET} {name:<26}{DIM}{desc}{RESET}")
    print()
    choice = input("  Pick a number: ").strip()
    for num, _name, fn, _desc in menu_actions:
        if choice == num:
            if fn is None:
                print("Bye!")
                return
            print()
            fn()
            input("\n  Press Enter to continue… ")
            return menu()
    print("Unknown choice.")
    input("\n  Press Enter to continue… ")
    return menu()


def menu():
    if _tui():
        menu_tui()
        return
    menu_plain()


def main():
    parser = argparse.ArgumentParser(description="Quaestio command-line manager",
                                     add_help=False)
    parser.add_argument("action", nargs="?", default=None,
                        help="status | start | stop | restart | update | uninstall | "
                             "contribute | pool | settings | localweb | help | about")
    parser.add_argument("-h", "--help", action="store_true")
    args = parser.parse_args()
    if args.help or args.action in ("help", "about"):
        help_text()
        return
    if not args.action:
        menu()
        return
    fn = globals().get(args.action)
    if fn is None or not callable(fn):
        boom(f"Unknown action '{args.action}'. Type `quaestio help` (or `{os.path.join(BOT_DIR, 'quaestio.py')} help` before install).")
    fn()


if __name__ == "__main__":
    main()