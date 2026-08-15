#!/usr/bin/env python3
"""Quaestio command-line manager.

One command opens a friendly menu that walks you through everything:

  python3 quaestio.py          -> interactive menu
  python3 quaestio.py help     -> the same guide, as text
  python3 quaestio.py <action> -> run one action directly

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

HOME = os.path.expanduser("~")
INSTALL_DIR = os.environ.get("QUAESTIO_DIR", os.path.join(HOME, "quaestio"))
BOT_DIR = os.path.join(INSTALL_DIR, "bot")
VENV = os.path.join(INSTALL_DIR, ".venv")
SERVICE = "/etc/systemd/system/quaestio.service"
KEYFILE_DEFAULT = "/etc/quaestio/keyfile"
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
        return None
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


# ---------------------------------------------------------------------------
# Contribution to the resource pool
# ---------------------------------------------------------------------------

def contribute():
    say("SELF-HOST & CONTRIBUTE — lend part of your AI box to the community pool.")
    say("The pool lets Quaestio route shared-AI servers across many Ollama boxes.\n")
    endpoint = input("Your Ollama URL [default http://127.0.0.1:11434]: ").strip() or "http://127.0.0.1:11434"
    model = input("Model you're sharing [default qwen2.5:1.5b]: ").strip() or "qwen2.5:1.5b"
    share = input("How much of your box to share, percent [10-100, default 50]: ").strip() or "50"
    try:
        share = max(10, min(100, int(share)))
    except ValueError:
        share = 50
    name = input(f"Your name/label [default {os.environ.get('USER', 'you')}]: ").strip() or os.environ.get("USER", "you")
    say("Registering your contribution in the local pool…", DIM)
    # The pool is stored in the bot's own database so it routes across it.
    db_path = read_env("DB_PATH") or os.path.join(BOT_DIR, "quaestio.db")
    sys.path.insert(0, BOT_DIR)
    import sqlite3
    conn = sqlite3.connect(db_path)
    conn.execute(
        "INSERT INTO hosters (name, endpoint, model, share, enabled, added_by, at) "
        "VALUES (?, ?, ?, ?, 1, 'cli', ?)",
        (name, endpoint, model, share, datetime.datetime.now().isoformat()),
    )
    conn.commit()
    conn.close()
    say(f"Done. You're contributing {share}% of your box "
        f"({endpoint}, {model}) to the pool.", GREEN)
    say("Other servers can now hand off AI calls to you. Lower the number anytime "
        "with the dashboard Host → Community pool, or re-run this command.")


# ---------------------------------------------------------------------------
# Settings — .env editor with a guided menu
# ---------------------------------------------------------------------------

ENV_QUESTIONS = [
    ("BOT_TOKEN", "Discord bot token (Developer Portal → app → Bot)", None, True),
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
    say("Disable anytime by re-running `quaestio.py localweb` and choosing N, "
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
    python3 {os.path.join(BOT_DIR, 'quaestio.py')}          interactive menu
    python3 {os.path.join(BOT_DIR, 'quaestio.py')} help     this help as text
    python3 {os.path.join(BOT_DIR, 'quaestio.py')} status   what's here / running
    python3 {os.path.join(BOT_DIR, 'quaestio.py')} settings change any setting
    python3 {os.path.join(BOT_DIR, 'quaestio.py')} contribute join the resource pool
    python3 {os.path.join(BOT_DIR, 'quaestio.py')} update   pull the latest bot
    python3 {os.path.join(BOT_DIR, 'quaestio.py')} uninstall remove everything

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
    print(f"    python3 {os.path.join(BOT_DIR, 'quaestio.py')} status")
    print(f"    python3 {os.path.join(BOT_DIR, 'quaestio.py')} settings")
    print(f"    python3 {os.path.join(BOT_DIR, 'quaestio.py')} contribute")
    print(f"    python3 {os.path.join(BOT_DIR, 'quaestio.py')} update")
    print(f"    python3 {os.path.join(BOT_DIR, 'quaestio.py')} uninstall")


def menu():
    os.system("clear" if os.name != "nt" else "cls")
    print(f"{BOLD}{CYAN}┌─────────────────────────────────────────────┐{RESET}")
    print(f"{BOLD}{CYAN}│  Quaestio — server manager                  │{RESET}")
    print(f"{BOLD}{CYAN}└─────────────────────────────────────────────┘{RESET}")
    print()
    if is_installed():
        print(f"  {GREEN}● Installed{RESET}  at {INSTALL_DIR}")
    else:
        print(f"  {YELLOW}○ Not installed yet{RESET}  (run the installer first)")
    print()
    menu_actions = [
        ("1", "Status", status, "what's installed / running"),
        ("2", "Start / Stop / Restart", restart, "control the bot"),
        ("3", "Settings", settings, "change tokens, model, timeout…"),
        ("4", "Contribute to the pool", contribute, "share part of your AI box"),
        ("5", "Local web panel", localweb, "turn the localhost settings page on/off"),
        ("6", "Update", update, "pull the latest bot code"),
        ("7", "Uninstall", uninstall, "remove everything, nothing left behind"),
        ("8", "About / help", help_text, "how everything works"),
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


def main():
    parser = argparse.ArgumentParser(description="Quaestio command-line manager",
                                     add_help=False)
    parser.add_argument("action", nargs="?", default=None,
                        help="status | start | stop | restart | update | uninstall | "
                             "contribute | settings | localweb | help | about")
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
        boom(f"Unknown action '{args.action}'. Type `python3 quaestio.py help`.")
    fn()


if __name__ == "__main__":
    main()