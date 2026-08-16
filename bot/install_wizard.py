#!/usr/bin/env python3
"""Quaestio interactive installer — a full-screen TUI wizard.

Driven from install.sh when run interactively. Walks you through what gets
installed, your component choices (AI engine, admin web panel), the connection
(model endpoint + model), community-pool sharing, your bot token, then installs
everything with live progress.

Everything still lands in ~/quaestio (or QUAESTIO_INSTALL_DIR) and nothing is
cloud-hosted. Re-running the installer only fills in missing pieces.
"""

import os
import shutil
import subprocess
import sys

INSTALL_DIR = os.environ.get("QUAESTIO_INSTALL_DIR") or os.environ.get("QUAESTIO_DIR") or os.path.expanduser("~/quaestio")
BOT_DIR = os.path.join(INSTALL_DIR, "bot")
DASH_DIR = os.path.join(INSTALL_DIR, "dashboard")
VENV = os.path.join(INSTALL_DIR, ".venv")
SERVICE = "/etc/systemd/system/quaestio.service"
SRC = os.environ.get("QUAESTIO_SRC", "https://raw.githubusercontent.com/fishesarethings/quaestio-site/main/bot")
MODEL_DEFAULT = os.environ.get("QUAESTIO_MODEL", "qwen2.5:1.5b")
MODELS = [
    "qwen2.5:0.5b",
    "qwen2.5:1.5b",
    "qwen2.5:3b",
    "qwen2.5:7b",
    "llama3.2:1b",
    "llama3.2:3b",
    "phi4-mini:3.8b",
]
PY = os.path.join(VENV, "bin", "python")
PIP = os.path.join(VENV, "bin", "pip")


def which(cmd):
    return shutil.which(cmd) is not None


def _models():
    return MODELS if MODEL_DEFAULT in MODELS else [MODEL_DEFAULT] + [m for m in MODELS if m != MODEL_DEFAULT]


def is_linux_systemd():
    return sys.platform.startswith("linux") and which("systemctl")


if not os.environ.get("QUAESTIO_NO_WIZARD"):
    try:
        from textual.app import App, ComposeResult
        from textual.containers import Horizontal, Vertical, VerticalScroll
        from textual.screen import ModalScreen, Screen
        from textual.widgets import Button, Checkbox, Footer, Header, Input, RichLog, Select, Static
    except Exception:
        print("[quaestio] Textual isn't installed in this environment — can't open the install wizard.")
        print("[quaestio] Run:  pip install textual   (or use the installer's classic text flow)")
        sys.exit(1)


# ---------------------------------------------------------------------------
# Shared config the screens fill in.
# ---------------------------------------------------------------------------
class Cfg:
    def __init__(self):
        self.install_dir = INSTALL_DIR
        self.bot_dir = BOT_DIR
        self.venv = VENV
        self.ai = True            # install + run the local AI engine
        self.web = False          # fetch the admin web panel
        self.pool = False         # contribute to the community pool
        self.endpoint_mode = "local"
        self.remote_endpoint = os.environ.get("OLLAMA_BASE_URL", "")
        self.model = MODEL_DEFAULT
        self.pool_share = 50
        self.token = os.environ.get("BOT_TOKEN", "")
        self.keyfile = os.environ.get("QUAESTIO_KEY_FILE") or (
            os.path.join(os.path.expanduser("~"), ".quaestio", "keyfile") if sys.platform != "linux" else "/etc/quaestio/keyfile")


cfg = Cfg()


# ---------------------------------------------------------------------------
# Screens
# ---------------------------------------------------------------------------
class Welcome(Static):
    def compose(self):
        with Vertical():
            yield Static(
                " \n  ██████╗ ██╗   ██╗ █████╗ ███████╗████████╗██╗ ██████╗ \n"
                "  ██╔═══██╗██║   ██║██╔══██╗██╔════╝╚══██╔══╝██║██╔═══██╗\n"
                "  ██║   ██║██║   ██║███████║███████╗   ██║   ██║██║   ██║\n"
                "  ██║▄▄ ██║██║   ██║██╔══██║╚════██║   ██║   ██║██║▄▄ ██║\n"
                "  ╚██████╔╝╚██████╔╝██║  ██║███████║   ██║   ██║╚██████╔╝\n"
                "   ╚══▀▀═╝  ╚═════╝ ╚═╝  ╚═╝╚══════╝   ╚═╝   ╚═╝ ╚═════╝ \n",
                markup=False,
            )
            yield Static(
                "  Welcome! This installer sets up YOUR OWN AI companion for Discord.\n"
                f"  Everything will land in [b]{INSTALL_DIR}[/b] and stays on your machine.\n"
                "\n  What you get:\n"
                "    1.  The Quaestio bot  (AI chat, XP, birthdays, moderation, games)\n"
                "    2.  A local AI engine (Ollama + a small model, ~1 GB)\n"
                "    3.  The web admin panel (optional, one command to run)\n"
                "    4.  A 'quaestio' command for managing everything.\n"
                "\n  No subscriptions. Nothing leaves your hardware."
            )
            yield Button("Start setup →", variant="primary", id="start")


class Start(Screen):
    BINDINGS = [("escape", "app.pop_screen", "Back")]

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        yield Welcome()
        yield Footer()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "start":
            self.app.switch_screen("components")


class Components(Screen):
    BINDINGS = [
        ("escape", "app.pop_screen", "Back"),
        ("up,k", "focus_prev", "Up"),
        ("down,j", "focus_next", "Down"),
        ("left,h", "nav_back", "Back button"),
        ("right,l", "nav_forward", "Next button"),
    ]

    def action_focus_next(self):
        self.focus_next("Checkbox, #nav Button")

    def action_focus_prev(self):
        self.focus_previous("Checkbox, #nav Button")

    def action_nav_back(self):
        self.query_one("#nav #back", Button).focus()

    def action_nav_forward(self):
        self.query_one("#nav #next", Button).focus()

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        with Vertical(id="body"):
            yield Static("  [b]What do you want to install?[/b]", classes="title")
            yield Static("  Tick what you'd like. The bot itself is always installed.", classes="sub")
            ai = Checkbox("AI brain — Ollama + a local model (~1 GB). Required for AI chat.", value=cfg.ai, id="ai")
            web = Checkbox("Admin web panel — a browser UI for settings. Optional; you run it with one command.", value=cfg.web, id="web")
            pool = Checkbox("Contribute to the community pool — lend part of your AI box so other servers can use it. Anonymous + encrypted.", value=cfg.pool, id="pool")
            yield ai
            yield web
            yield pool
            yield Static("", classes="spacer")
            with Horizontal(id="nav"):
                yield Button("Back", variant="default", id="back")
                yield Button("Next →", variant="primary", id="next")
        yield Footer()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        cfg.ai = self.query_one("#ai", Checkbox).value
        cfg.web = self.query_one("#web", Checkbox).value
        cfg.pool = self.query_one("#pool", Checkbox).value
        if event.button.id == "back":
            self.app.switch_screen("start")
        elif event.button.id == "next":
            if not cfg.pool:
                self.app.push_screen(AskPool(), callback=self._after_pool_ask)
            else:
                self.app.switch_screen("connections")

    def _after_pool_ask(self, result) -> None:
        if result == "yes":
            cfg.pool = True
            self.app.switch_screen("connections")
        elif result == "no":
            self.app.switch_screen("connections")


class AskPool(ModalScreen):
    BINDINGS = [("escape", "dismiss_no", "No")]

    def compose(self) -> ComposeResult:
        with Vertical(classes="modal"):
            yield Static("[b]Community pool[/b]", classes="mtitle")
            yield Static(
                "You left 'Contribute to the community pool' un-ticked.\n\n"
                "The pool loans part of your AI box to other Quaestio servers\n"
                "(and borrows from them when yours is busy) — anonymous + encrypted.\n"
                "You can join or leave it anytime from `quaestio contribute`.\n"
                "\nWant to lend part of your box?", classes="mbody")
            with Horizontal(id="mnav"):
                yield Button("Yes, I'll contribute", id="yes")
                yield Button("No, skip it", variant="primary", id="no")
        yield Footer()

    def action_dismiss_no(self) -> None:
        self.dismiss("no")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        self.dismiss("yes" if event.button.id == "yes" else "no")


class Connections(Screen):
    BINDINGS = [("escape", "app.pop_screen", "Back")]

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        with Vertical(id="body"):
            yield Static("  [b]Where does the AI run?[/b]", classes="title")
            mode = Select(
                [("This machine (recommended)", "local"), ("Another computer on your network", "remote")],
                value=("remote" if cfg.remote_endpoint else "local"), id="mode", prompt="Pick the AI connection",
            )
            yield mode
            remote = Input(placeholder="http://192.168.1.50:11434", value=cfg.remote_endpoint, id="remote")
            remote.disabled = not cfg.remote_endpoint
            yield Static("Remote Ollama URL:", classes="lbl")
            yield remote
            yield Static("  [b]Model[/b]  — bigger = smarter, slower, more RAM.", classes="title")
            yield Select([(m, m) for m in _models()], value=cfg.model, id="model", prompt="Pick a model")
            yield Static("", classes="spacer")
            with Horizontal(id="nav"):
                yield Button("Back", variant="default", id="back")
                yield Button("Next →", variant="primary", id="next")
        yield Footer()

    def on_select_changed(self, event):
        if event.control.id == "mode":
            cfg.endpoint_mode = event.value
            self.query_one("#remote").disabled = (event.value == "local")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        cfg.endpoint_mode = self.query_one("#mode", Select).value
        cfg.remote_endpoint = self.query_one("#remote", Input).value.strip()
        cfg.model = self.query_one("#model", Select).value or cfg.model
        if event.button.id == "back":
            self.app.switch_screen("components")
        elif event.button.id == "next":
            self.app.switch_screen("token")


class Token(Screen):
    BINDINGS = [("escape", "app.pop_screen", "Back")]

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        with Vertical(id="body"):
            yield Static("  [b]Your Discord bot token[/b]", classes="title")
            yield Static(
                "  Optional — Quaestio works without it until you're ready.\n"
                "  If you have one: Developer Portal → your app → Bot → Reset Token, then paste.\n"
                "  It's stored locally in bot/.env with 600 permissions and never leaves your machine.\n"
                "  Skip if you'd rather add it later with [b]quaestio settings[/b].", classes="sub")
            yield Input(placeholder="Paste token (hidden, optional)", password=True, id="token")
            yield Static("", classes="spacer")
            yield Static("  [dim]Skip if you don't have a token yet — you can add one anytime.[/dim]", classes="hint")
            with Horizontal(id="nav"):
                yield Button("Skip for now", variant="default", id="skip")
                yield Button("Back", variant="default", id="back")
                yield Button("Next →", variant="primary", id="next")
        yield Footer()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        cfg.token = self.query_one("#token", Input).value.strip()
        if event.button.id == "back":
            self.app.switch_screen("connections")
        elif event.button.id in ("skip", "next"):
            if cfg.pool:
                self.app.switch_screen("pool")
            else:
                self.app.switch_screen("review")


class Pool(Screen):
    BINDINGS = [("escape", "app.pop_screen", "Back")]

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        with Vertical(id="body"):
            yield Static("  [b]Contribute to the community pool[/b]", classes="title")
            yield Static(
                "  You'll stay anonymous — the pool only ever sees a random node ID, and your\n"
                "  endpoint + model are encrypted at rest. Nobody can piece together who you are.",
                classes="sub")
            yield Select([("10% — spare cycles only", 10), ("25%", 25), ("50% (default)", 50), ("75%", 75), ("100% — share it all", 100)],
                         value=50, id="share", prompt="How much of your box to lend")
            yield Static("", classes="spacer")
            with Horizontal(id="nav"):
                yield Button("Back", variant="default", id="back")
                yield Button("Next →", variant="primary", id="next")
        yield Footer()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        cfg.pool_share = int(self.query_one("#share", Select).value or 50)
        if event.button.id == "back":
            self.app.switch_screen("token")
        elif event.button.id == "next":
            self.app.switch_screen("review")


class Review(Screen):
    BINDINGS = [("escape", "app.pop_screen", "Back")]

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        with Vertical(id="body"):
            yield Static("  [b]Ready to install[/b]", classes="title")
            yield Static(_plan_text(), id="plan", classes="plan")
            yield Static("", classes="spacer")
            with Horizontal(id="nav"):
                yield Button("Back", variant="default", id="back")
                yield Button("Install now →", variant="success", id="install")
        yield Footer()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "back":
            self.app.switch_screen(("pool" if cfg.pool else "token"))
        elif event.button.id == "install":
            self.app.switch_screen("run")


class Run(Screen):
    BINDINGS = [("escape", "app.pop_screen", "Back")]

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        with Vertical(id="body"):
            yield Static("  [b]Installing…[/b]", classes="title")
            log = RichLog(highlight=True, markup=True, wrap=True, id="log")
            yield log
            with Horizontal(id="nav"):
                yield Button("Done", variant="primary", id="finish", disabled=True)
        yield Footer()

    def on_mount(self) -> None:
        self.run_worker(self._install())

    async def _install(self):
        log = self.query_one("#log", RichLog)
        steps = _install_steps()
        failed = []
        for title, fn in steps:
            log.write(f"•  {title}")
            try:
                msg = fn()
                log.write(f"   ✓  {msg or 'done'}")
            except Exception as e:
                failed.append((title, e))
                log.write(f"   ✗  {e}")
        if failed:
            log.write("")
            log.write("[b]Some steps failed. You can fix them later with `quaestio settings` / `quaestio update`.[/b]")
        else:
            log.write("")
            log.write("[bold green]Done! Everything is in place.[/bold green]")
            if cfg.token:
                log.write(f"Start the bot (macOS):  {os.path.join(INSTALL_DIR, 'run-quaestio.sh')}")
            else:
                log.write("[b]No bot token yet[/b] — Quaestio starts without one. Add it anytime with:  quaestio settings")
            log.write(f"Manage it anytime:  quaestio   (menu)   ·   quaestio help")
        self.query_one("#finish", Button).disabled = False

    def on_button_pressed(self, event: Button.Pressed) -> None:
        self.app.pop_screen()


# ---------------------------------------------------------------------------
# Install steps
# ---------------------------------------------------------------------------
def _run(cmd, silent=False):
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0 and not silent:
        raise RuntimeError(r.stderr.strip().splitlines()[-1] if r.stderr.strip() else "command failed")
    return r.stdout.strip()


def _step_keyfile():
    # Same default as bot/config.py: Linux → /etc/quaestio/keyfile (sudo),
    # macOS/Windows → ~/.quaestio/keyfile (no sudo). Override: QUAESTIO_KEY_FILE.
    keypath = cfg.keyfile
    os.makedirs(os.path.dirname(keypath), exist_ok=True)
    if os.path.exists(keypath):
        return f"keyfile already exists ({keypath})"
    if sys.platform.startswith("linux") and os.geteuid() != 0 and not which("sudo"):
        raise RuntimeError("Linux keyfile needs sudo or root — run the installer with sudo.")
    code = (
        "from cryptography.fernet import Fernet; import os, stat, sys; "
        "p = sys.argv[1]; "
        "open(p, 'wb').write(Fernet.generate_key()); "
        "os.chmod(p, stat.S_IRUSR | stat.S_IWUSR)"
    )
    if sys.platform.startswith("linux") and os.geteuid() != 0:
        _run(["sudo", "mkdir", "-p", os.path.dirname(keypath)])
        _run(["sudo", "python3", "-c", code, keypath])
        _run(["sudo", "chmod", "600", keypath])
    else:
        os.makedirs(os.path.dirname(keypath), exist_ok=True)
        _run([PY, "-c", code, keypath])
    return f"keyfile created ({keypath})"


def _step_download():
    # Fetch the bot code if it isn't there yet.
    if os.path.exists(os.path.join(cfg.bot_dir, "bot.py")):
        return "bot code already present"
    os.makedirs(cfg.bot_dir, exist_ok=True)
    for f in ("bot.py", "config.py", "quaestio.py", "requirements.txt", ".env.example"):
        _run(["curl", "-fsSL", f"{SRC}/{f}", "-o", os.path.join(cfg.bot_dir, f)], silent=True)
    return "bot code downloaded"


def _step_mkdirs():
    os.makedirs(cfg.bot_dir, exist_ok=True)
    if cfg.web:
        os.makedirs(DASH_DIR, exist_ok=True)
    return f"created {cfg.install_dir}"


def _step_venv():
    if os.path.exists(PY):
        return "virtualenv already present"
    _run([sys.executable, "-m", "venv", VENV])
    _run([PIP, "--quiet", "install", "--upgrade", "pip"])
    return "virtualenv created"


def _step_crypto():
    r = subprocess.run([PY, "-c", "import cryptography"], capture_output=True, text=True)
    if r.returncode == 0:
        return "cryptography already present"
    _run([PIP, "--quiet", "install", "cryptography>=42.0"])
    return "cryptography installed"


def _step_env():
    env_file = os.path.join(cfg.bot_dir, ".env")
    lines = {}
    if os.path.exists(env_file):
        try:
            with open(env_file) as f:
                for ln in f:
                    ln = ln.strip()
                    if "=" in ln:
                        k, v = ln.split("=", 1)
                        lines[k] = v
                if not lines.get("BOT_TOKEN"):
                    lines.pop("BOT_TOKEN", None)
        except Exception:
            pass
    if cfg.token and not lines.get("BOT_TOKEN"):
        lines["BOT_TOKEN"] = cfg.token
    endpoint = cfg.remote_endpoint if (cfg.endpoint_mode == "remote" and cfg.remote_endpoint) else "http://127.0.0.1:11434"
    lines.setdefault("OLLAMA_BASE_URL", endpoint)
    lines.setdefault("OLLAMA_MODEL", cfg.model)
    lines.setdefault("RPC_LARGE_IMAGE", "logo")
    with open(env_file, "w") as f:
        for k, v in lines.items():
            f.write(f"{k}={v}\n")
    os.chmod(env_file, 0o600)
    if cfg.token:
        return ".env written (token saved, 600)"
    return ".env written (no token yet — set it later with `quaestio settings`)"


def _step_pip():
    return _run([PIP, "--quiet", "install", "-r", os.path.join(cfg.bot_dir, "requirements.txt")]) or "dependencies installed"


def _step_ollama_install():
    if not cfg.ai:
        return "skipped (AI engine not requested)"
    if which("ollama"):
        return "Ollama already installed"
    if sys.platform == "darwin" and which("brew"):
        _run(["brew", "install", "ollama"])
        return "Ollama installed via Homebrew (open the Ollama app once)"
    if sys.platform == "darwin":
        raise RuntimeError("Install Ollama from https://ollama.com/download (macOS), then re-run the installer.")
    if os.getuid() != 0 and not which("sudo"):
        raise RuntimeError("The Ollama install script needs sudo — re-run the installer with sudo.")
    subprocess.run("curl -fsSL https://ollama.com/install.sh | sh", shell=True, check=True)
    return "Ollama installed"


def _step_pull_model():
    if not cfg.ai or not which("ollama"):
        return "skipped (no Ollama)"
    r = subprocess.run(["ollama", "list"], capture_output=True, text=True)
    if cfg.model in r.stdout:
        return f"model {cfg.model} already present"
    subprocess.run(["ollama", "pull", cfg.model], check=False)
    return f"model {cfg.model} pulled"


def _step_service():
    if is_linux_systemd():
        envf = os.path.join(cfg.bot_dir, ".env")
        unit = f"""[Unit]
Description=Quaestio Discord bot
After=network-online.target ollama.service
Wants=network-online.target

[Service]
WorkingDirectory={cfg.bot_dir}
EnvironmentFile={envf}
ExecStart={PY} {os.path.join(cfg.bot_dir, 'bot.py')}
Restart=on-failure
RestartSec=5
User={os.environ.get('USER', 'root')}

[Install]
WantedBy=multi-user.target
"""
        with open("/tmp/qfsvc", "w") as f:
            f.write(unit)
        os.system(
            f"sudo cp /tmp/qfsvc {SERVICE} && "
            f"sudo systemctl daemon-reload && "
            f"sudo systemctl enable --now quaestio.service >/dev/null 2>&1"
        )
        return "systemd service installed & started"
    run_script = os.path.join(INSTALL_DIR, "run-quaestio.sh")
    with open(run_script, "w") as f:
        f.write(f"""#!/usr/bin/env bash
cd "{cfg.bot_dir}"
set -a; source .env; set +a
exec "{PY}" "{os.path.join(cfg.bot_dir, 'bot.py')}"
""")
    os.chmod(run_script, 0o755)
    return f"run script ready: {run_script}"


def _step_command():
    bin_dir = os.path.join(INSTALL_DIR, "bin")
    os.makedirs(bin_dir, exist_ok=True)
    launcher = os.path.join(bin_dir, "quaestio")
    with open(launcher, "w") as f:
        f.write(f"""#!/usr/bin/env bash
exec "{PY}" "{os.path.join(cfg.bot_dir, 'quaestio.py')}" "$@"
""")
    os.chmod(launcher, 0o755)
    for d in (os.path.expanduser("~/.local/bin"), os.path.expanduser("~/bin")):
        try:
            os.makedirs(d, exist_ok=True)
            link = os.path.join(d, "quaestio")
            if os.path.islink(link) or not os.path.exists(link):
                if os.path.exists(link):
                    os.remove(link)
                os.symlink(launcher, link)
                return f"`quaestio` command ready ({link})"
        except Exception:
            continue
    return "`quaestio` command ready (add ~/.local/bin to PATH)"


def _step_pool():
    if not cfg.pool:
        return "skipped (not contributing)"
    sys.path.insert(0, cfg.bot_dir)
    try:
        import config as qcfg
        enc_ep = qcfg.maybe_encrypt("pool_endpoint", cfg.remote_endpoint if (cfg.endpoint_mode == "remote" and cfg.remote_endpoint) else "http://127.0.0.1:11434")
        enc_m = qcfg.maybe_encrypt("pool_model", cfg.model)
    except Exception:
        enc_ep, enc_m = cfg.remote_endpoint or "http://127.0.0.1:11434", cfg.model
    import sqlite3, secrets, datetime
    db_path = os.environ.get("DB_PATH") or os.path.join(cfg.bot_dir, "quaestio.db")
    conn = sqlite3.connect(db_path)
    conn.execute("""CREATE TABLE IF NOT EXISTS hosters (
        id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT, endpoint TEXT, model TEXT,
        share INTEGER DEFAULT 50, enabled INTEGER DEFAULT 1, added_by TEXT, at TEXT)""")
    conn.execute("INSERT INTO hosters (name, endpoint, model, share, enabled, added_by, at) VALUES (?,?,?,?,1,'installer',?)",
                 ("node-" + secrets.token_hex(2), enc_ep, enc_m, cfg.pool_share, datetime.datetime.now().isoformat()))
    conn.commit()
    conn.close()
    return f"contributed {cfg.pool_share}% anonymously to the pool"


def _step_web():
    if not cfg.web:
        return "skipped (web panel not requested)"
    base = os.environ.get("QUAESTIO_SRC", "https://raw.githubusercontent.com/fishesarethings/quaestio-site/main/dashboard")
    os.makedirs(DASH_DIR, exist_ok=True)
    for f in ("app.py", "requirements.txt"):
        subprocess.run(["curl", "-fsSL", f"{base}/{f}", "-o", os.path.join(DASH_DIR, f)], check=False)
    subprocess.run(["curl", "-fsSL", f"{base}/static/app.js", "-o", os.path.join(DASH_DIR, "static", "app.js")], check=False)
    subprocess.run(["curl", "-fsSL", f"{base}/static/style.css", "-o", os.path.join(DASH_DIR, "static", "style.css")], check=False)
    subprocess.run(["curl", "-fsSL", f"{base}/static/index.html", "-o", os.path.join(DASH_DIR, "static", "index.html")], check=False)
    return "web panel fetched (run it per README → Admin web panel)"


def _install_steps():
    return [
        ("Setting up folders", _step_mkdirs),
        ("Downloading bot code", _step_download),
        ("Virtualenv", _step_venv),
        ("Encryption support", _step_crypto),
        ("Encryption key", _step_keyfile),
        ("Bot config (.env)", _step_env),
        ("Dependencies", _step_pip),
        ("Ollama engine", _step_ollama_install),
        ("AI model", _step_pull_model),
        ("Run script / service", _step_service),
        ("quaestio command", _step_command),
        ("Community pool", _step_pool),
        ("Web admin panel", _step_web),
    ]


def _plan_text():
    endpoint = (cfg.remote_endpoint if cfg.endpoint_mode == "remote" and cfg.remote_endpoint else "http://127.0.0.1:11434")
    lines = [
        "  Install location:  " + cfg.install_dir,
        f"  AI engine:         {'Ollama + ' + cfg.model if cfg.ai else 'not installed (AI commands offline)'}",
        f"  AI connection:     {endpoint}",
        "  Admin web panel:   " + ("yes (fetched to ~/quaestio/dashboard)" if cfg.web else "no"),
        "  Community pool:    " + (f"yes — {cfg.pool_share}% anonymously" if cfg.pool else "no"),
        "  Bot token:         " + ("provided (saved to bot/.env)" if cfg.token else "skipped — add later with `quaestio settings`"),
        "",
        "  Press Install now to do everything.",
    ]
    return "\n".join(lines)


class Installer(App):
    TITLE = "Quaestio — installer"
    SCREENS = {
        "start": Start,
        "components": Components,
        "connections": Connections,
        "token": Token,
        "pool": Pool,
        "review": Review,
        "run": Run,
    }
    CSS = """
    Screen { background: #0d1117; }
    #body { padding: 0 4; }
    .title { margin: 1 0 0 0; color: #58a6ff; text-style: bold; }
    .sub { margin: 0 0 1 0; color: #8b949e; }
    .lbl { margin: 1 0 0 0; color: #8b949e; }
    .hint { margin: 0 0 1 0; color: #6e7681; }
    .spacer { height: 3; }
    .plan { color: #c9d1d9; padding: 1 2; border: round #30363d; }
    #nav { height: 5; align-horizontal: right; }
    #nav Button { margin: 0 1; }
    ModalScreen { background: #000000 60%; }
    .modal { background: #161b22; border: round #58a6ff; width: 72;
             height: auto; padding: 1 2; margin: 4 8; }
    .mtitle { color: #58a6ff; text-style: bold; }
    .mbody { color: #c9d1d9; margin: 1 0; }
    #mnav { height: 5; align-horizontal: right; }
    #mnav Button { margin: 0 1; }
    Icon { color: #58a6ff; }
    """
    BINDINGS = [
        ("ctrl+q", "quit_installer", "Quit"),
        ("escape", "switch_screen('start')", "Start"),
    ]

    def __init__(self):
        super().__init__()
        self.install_screen = Start()

    def action_quit_installer(self):
        self.exit()

    def on_mount(self):
        self.push_screen(self.install_screen)


def main():
    if "--plan" in sys.argv:
        print(_plan_text())
        return
    try:
        app = Installer()
    except Exception:
        app = None
    if app:
        app.run()
    else:
        print("[quaestio] Starting install in classic text mode...")


if __name__ == "__main__":
    main()