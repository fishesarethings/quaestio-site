#!/usr/bin/env python3
"""Quaestio community-host installer — a full-screen TUI wizard.

Driven from install.sh when run interactively. Sets up a box that joins the
Quaestio community pool (or self-hosts the bot): AI engine choices, the model
endpoint + model, pool share and an optional own-bot token, then installs
everything with live progress.

No Discord bot token is needed — Quaestio's shared bot handles servers; this
box is optional community compute. Everything lands in ~/quaestio (or
QUAESTIO_INSTALL_DIR) and endpoint + model are encrypted at rest.
"""

import os
import shutil
import subprocess
import sys

INSTALL_DIR = os.environ.get("QUAESTIO_INSTALL_DIR") or os.environ.get("QUAESTIO_DIR") or os.path.expanduser("~/Downloads/quaestio")
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
        from textual.binding import Binding
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
        self.autostart = True     # keep serving after reboot / login
        self.endpoint_mode = "local"
        self.remote_endpoint = ""
        self.model = MODEL_DEFAULT
        self.pool_share = 50
        self.token = os.environ.get("BOT_TOKEN", "")
        self.keyfile = os.environ.get("QUAESTIO_KEY_FILE") or (
            os.path.join(os.path.expanduser("~"), ".quaestio", "keyfile") if sys.platform != "linux" else "/etc/quaestio/keyfile")


cfg = Cfg()


def _set_dirs(base: str):
    """Point the whole install at a chosen folder (portable install). Everything
    — bot code, dashboard, venv — lives under this one folder, so moving or
    deleting the folder moves or removes the entire install."""
    global INSTALL_DIR, BOT_DIR, DASH_DIR, VENV, PY, PIP
    base = os.path.abspath(os.path.expanduser(base or cfg.install_dir))
    INSTALL_DIR = base
    BOT_DIR = os.path.join(base, "bot")
    DASH_DIR = os.path.join(base, "dashboard")
    VENV = os.path.join(base, ".venv")
    PY = os.path.join(VENV, "bin", "python")
    PIP = os.path.join(VENV, "bin", "pip")
    cfg.install_dir = base
    cfg.bot_dir = BOT_DIR
    cfg.venv = VENV


# ---------------------------------------------------------------------------
# Shared navigation. Every form screen lets you move between fields/buttons
# with ↑/↓/←/→ (or hjkl) exactly like Tab does. Selects no longer hijack
# ↑/↓ to open their dropdown — arrows move focus instead; Enter/Space opens it.
# ---------------------------------------------------------------------------

NAV_KEYS = [
    ("up,k", "focus_prev", "Up"),
    ("down,j", "focus_next", "Down"),
    ("left,h", "focus_prev", "Left"),
    ("right,l", "focus_next", "Right"),
]


class NavSelect(Select, inherit_bindings=False):
    BINDINGS = [
        Binding("enter,space", "show_overlay", "Show menu", show=False),
        Binding("escape", "close_overlay", "Close menu", show=False),
    ]

    def action_close_overlay(self):
        self.expanded = False


class _NavScreen(Screen):
    BINDINGS = [("escape", "go_back", "Back")] + NAV_KEYS

    def action_go_back(self):
        try:
            self.query_one("#back").press()
        except Exception:
            pass

    def action_focus_next(self):
        self.focus_next()

    def action_focus_prev(self):
        self.focus_previous()


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
                "  Welcome! This sets up YOUR box as a Quaestio community host.\n"
                f"  Everything lands in [b]{INSTALL_DIR}[/b] on this machine.\n"
                "\n  No Discord account needed. You use Quaestio's shared bot —\n"
                "  this install only contributes AI compute to its community pool.\n"
                "\n  What you get:\n"
                "    1.  The local AI engine (Ollama + a small model, ~1 GB)\n"
                "    2.  A node in the pool — requests route to you randomly\n"
                "        and are encrypted end-to-end between participant devices\n"
                "    3.  The web admin panel (optional, one command to run)\n"
                "    4.  A 'quaestio' command for managing your host.\n"
                "\n  No subscriptions. Nothing leaves your machine unencrypted."
            )
            yield Button("Start setup →", variant="primary", id="start")


class Start(Screen):
    BINDINGS = [("escape", "quit_wizard", "Quit")]

    def action_quit_wizard(self):
        self.app.exit()

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        yield Welcome()
        yield Footer()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "start":
            self.app.switch_screen("components")


class Components(_NavScreen):
    BINDINGS = [
        ("escape", "go_back", "Back"),
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
            yield Static("  [b]What should this box do?[/b]", classes="title")
            yield Static("  Quaestio's shared bot runs centrally — this box only adds compute.", classes="sub")
            ai = Checkbox("AI engine — Ollama + a local model (~1 GB). Required to host in the pool.", value=cfg.ai, id="ai")
            web = Checkbox("Admin web panel — a browser UI for settings. Optional.", value=cfg.web, id="web")
            pool = Checkbox("Join the community pool — Quaestio routes AI requests to your box randomly. Anonymous + encrypted.", value=cfg.pool, id="pool")
            autostart = Checkbox("Start on login / after reboot — keeps your box serving the pool.", value=cfg.autostart, id="autostart")
            yield ai
            yield web
            yield pool
            yield autostart
            yield Static("", classes="spacer")
            with Horizontal(id="nav"):
                yield Button("Back", variant="default", id="back")
                yield Button("Next →", variant="primary", id="next")
        yield Footer()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        cfg.ai = self.query_one("#ai", Checkbox).value
        cfg.web = self.query_one("#web", Checkbox).value
        cfg.pool = self.query_one("#pool", Checkbox).value
        cfg.autostart = self.query_one("#autostart", Checkbox).value
        if event.button.id == "back":
            self.app.switch_screen("start")
        elif event.button.id == "next":
            if not cfg.pool:
                self.app.push_screen(AskPool(), callback=self._after_pool_ask)
            else:
                self.app.switch_screen("location")

    def _after_pool_ask(self, result) -> None:
        if result == "yes":
            cfg.pool = True
        self.app.switch_screen("location")


class AskPool(ModalScreen):
    BINDINGS = [("escape", "dismiss_no", "No")] + NAV_KEYS

    def action_focus_next(self):
        self.focus_next("Button")

    def action_focus_prev(self):
        self.focus_previous("Button")

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


class Connections(_NavScreen):
    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        with Vertical(id="body"):
            yield Static("  [b]Where does the AI run?[/b]", classes="title")
            yield Static(f"  [dim]Everything installs into: {cfg.install_dir} — change it on the folder step.[/dim]", classes="hint")
            mode = NavSelect(
                [("This machine (recommended)", "local"), ("Another computer on your network", "remote")],
                value=("remote" if cfg.remote_endpoint else "local"), id="mode", prompt="Pick the AI connection",
            )
            yield mode
            remote = Input(placeholder="http://192.168.1.50:11434", value=cfg.remote_endpoint, id="remote")
            remote.disabled = not cfg.remote_endpoint
            yield Static("Remote Ollama URL:", classes="lbl")
            yield remote
            yield Static("  [b]Model[/b]  — bigger = smarter, slower, more RAM.", classes="title")
            yield NavSelect([(m, m) for m in _models()], value=cfg.model, id="model", prompt="Pick a model")
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
            self.app.switch_screen("location")
        elif event.button.id == "next":
            self.app.switch_screen("pool" if cfg.pool else "review")


class Location(_NavScreen):
    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        with Vertical(id="body"):
            yield Static("  [b]Portable install — where should everything go?[/b]", classes="title")
            yield Static(
                "  Bot code, dashboard and the Python environment all live in one\n"
                "  portable folder — default is your Downloads folder. Type a path\n"
                "  below or press [b]Browse…[/b] to pick one (shows a native folder\n"
                "  selector on macOS; Linux uses zenity/kdialog if installed).",
                classes="sub")
            yield Static("Install folder:", classes="lbl")
            yield Input(value=cfg.install_dir, id="dir", placeholder="~/Downloads/quaestio")
            yield Static("", classes="spacer")
            with Horizontal(id="nav"):
                yield Button("Browse…", id="browse")
                yield Button("Back", variant="default", id="back")
                yield Button("Next →", variant="primary", id="next")
        yield Footer()

    async def _browse(self):
        import asyncio
        path = None
        if sys.platform == "darwin" and which("osascript"):
            p = await asyncio.create_subprocess_exec(
                "osascript", "-e",
                'POSIX path of (choose folder with prompt "Choose the Quaestio install folder")',
                stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL)
            out = (await p.communicate())[0].decode().strip()
            if out:
                path = out
        elif which("zenity"):
            p = await asyncio.create_subprocess_exec(
                "zenity", "--file-selection", "--directory",
                "--title=Choose the Quaestio install folder",
                stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL)
            out = (await p.communicate())[0].decode().strip()
            if out:
                path = out
        elif which("kdialog"):
            p = await asyncio.create_subprocess_exec(
                "kdialog", "--getexistingdirectory", "~",
                stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL)
            out = (await p.communicate())[0].decode().strip()
            if out:
                path = out
        if path:
            self.query_one("#dir", Input).value = path.rstrip("/")
        else:
            self.notify("No folder picker here — just type the full path above.", severity="warning")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "back":
            self.app.switch_screen("components")
        elif event.button.id == "browse":
            self.app.run_worker(self._browse())
        elif event.button.id == "next":
            _set_dirs(self.query_one("#dir", Input).value.strip() or cfg.install_dir)
            self.app.switch_screen("connections")


class Pool(_NavScreen):
    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        with Vertical(id="body"):
            yield Static("  [b]Contribute to the community pool[/b]", classes="title")
            yield Static(
                "  You'll stay anonymous — the pool only ever sees a random node ID, and your\n"
                "  endpoint + model are encrypted at rest. Nobody can piece together who you are.",
                classes="sub")
            yield NavSelect([("10% — spare cycles only", 10), ("25%", 25), ("50% (default)", 50), ("75%", 75), ("100% — share it all", 100)],
                         value=50, id="share", prompt="How much of your box to lend")
            yield Static("", classes="spacer")
            with Horizontal(id="nav"):
                yield Button("Back", variant="default", id="back")
                yield Button("Next →", variant="primary", id="next")
        yield Footer()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        cfg.pool_share = int(self.query_one("#share", Select).value or 50)
        if event.button.id == "back":
            self.app.switch_screen("connections")
        elif event.button.id == "next":
            self.app.switch_screen("review")


class Review(_NavScreen):
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
            self.app.switch_screen("pool" if cfg.pool else "connections")
        elif event.button.id == "install":
            self.app.switch_screen("run")


class Run(_NavScreen):
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
            if cfg.pool:
                log.write("Your box is registered with the community pool — press Done.")
            else:
                log.write("[b]No token needed[/b] — Quaestio's shared bot handles servers. Add your own later:  quaestio settings")
            log.write(f"Manage it anytime:  quaestio   (menu)   ·   quaestio help")
        self.query_one("#finish", Button).disabled = False

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "finish":
            self.app.exit("done")


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
    _run(["sh", "-c", "curl -fsSL https://ollama.com/install.sh | sh"], silent=True)
    return "Ollama installed"


def _step_pull_model():
    if not cfg.ai or not which("ollama"):
        return "skipped (no Ollama)"
    r = subprocess.run(["ollama", "list"], capture_output=True, text=True)
    if cfg.model in r.stdout:
        return f"model {cfg.model} already present"
    subprocess.run(["ollama", "pull", cfg.model], capture_output=True, text=True)
    return f"model {cfg.model} pulled (this can take a few minutes)"


def _step_service():
    run_script = os.path.join(INSTALL_DIR, "run-quaestio.sh")
    with open(run_script, "w") as f:
        f.write(f"""#!/usr/bin/env bash
cd "{cfg.bot_dir}"
set -a; source .env; set +a
exec "{PY}" "{os.path.join(cfg.bot_dir, 'bot.py')}"
""")
    os.chmod(run_script, 0o755)
    if not cfg.autostart:
        return f"run script ready (autostart off): {run_script}"
    if not is_linux_systemd():
        return f"run script ready: {run_script}"
    envf = os.path.join(cfg.bot_dir, ".env")
    unit = f"""[Unit]
Description=Quaestio community host
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
    _run(["sudo", "cp", "/tmp/qfsvc", SERVICE], silent=True)
    _run(["sudo", "systemctl", "daemon-reload"], silent=True)
    _run(["sudo", "systemctl", "enable", "--now", "quaestio.service"], silent=True)
    return "systemd service installed & started"


def _step_autostart():
    """Persist on reboot: systemd on Linux (done by the service step), a
    LaunchAgent on macOS that keeps Ollama serving the pool (and the bot, if a
    token is set). Toggling off removes it cleanly — never breaks boot."""
    if not cfg.autostart:
        if sys.platform == "darwin":
            plist = os.path.expanduser("~/Library/LaunchAgents/com.quaestio.host.plist")
            if os.path.exists(plist):
                subprocess.run(["launchctl", "bootout", f"gui/{os.getuid()}", plist],
                               capture_output=True)
                try:
                    os.remove(plist)
                except OSError:
                    pass
                return "autostart removed (login item uninstalled)"
        return "autostart skipped"
    if is_linux_systemd():
        return "autostart handled by the systemd service"
    if sys.platform != "darwin":
        return "autostart not available on this OS (Linux uses systemd)"
    plist_dir = os.path.expanduser("~/Library/LaunchAgents")
    os.makedirs(plist_dir, exist_ok=True)
    os.makedirs(INSTALL_DIR, exist_ok=True)
    run_host = os.path.join(INSTALL_DIR, "run-host.sh")
    with open(run_host, "w") as f:
        f.write(f'''#!/usr/bin/env bash
# Quaestio community host — kept running at login.
INSTALL_DIR="{INSTALL_DIR}"
BOT_DIR="{BOT_DIR}"
PY="{PY}"
[[ -d "$INSTALL_DIR" ]] || exit 0
cd "$BOT_DIR"
set -a; [[ -f .env ]] && source .env; set +a
if grep -q "^POOL_NODE_SECRET=" .env 2>/dev/null; then
  command -v ollama >/dev/null 2>&1 || exit 0
  pgrep -x ollama >/dev/null 2>&1 || nohup ollama serve >/dev/null 2>&1 &
fi
if [[ -n "${{BOT_TOKEN:-}}" ]]; then
  exec "$PY" "$BOT_DIR/bot.py"
fi
''')
    os.chmod(run_host, 0o755)
    plist = os.path.join(plist_dir, "com.quaestio.host.plist")
    with open(plist, "w") as f:
        f.write(f'''<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>Label</key><string>com.quaestio.host</string>
  <key>ProgramArguments</key><array><string>{run_host}</string></array>
  <key>RunAtLoad</key><true/>
  <key>KeepAlive</key><false/>
  <key>StandardOutPath</key><string>{os.path.join(INSTALL_DIR, 'host.log')}</string>
  <key>StandardErrorPath</key><string>{os.path.join(INSTALL_DIR, 'host.err.log')}</string>
</dict></plist>
''')
    subprocess.run(["launchctl", "bootout", f"gui/{os.getuid()}", plist], capture_output=True)
    subprocess.run(["launchctl", "bootstrap", f"gui/{os.getuid()}", plist], capture_output=True)
    return f"autostart on login installed ({plist})"


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


def _pool_join_remote(broker: str, join_key: str, endpoint: str, model: str, share: int) -> str:
    """Register this box with the central community-pool broker so the shared
    bot can route requests to it. The returned node secret is stored in the
    node's own .env so it can update or leave later."""
    import json as _json
    import urllib.error as _urlerr
    import urllib.request as _urlreq
    url = broker.rstrip("/") + "/api/pool/register"
    body = _json.dumps({"endpoint": endpoint, "model": model, "share": int(share)}).encode()
    req = _urlreq.Request(url, data=body, method="POST", headers={
        "Content-Type": "application/json",
        "X-Pool-Key": join_key or "",
    })
    try:
        with _urlreq.urlopen(req, timeout=20) as resp:
            data = _json.loads(resp.read().decode())
    except _urlerr.HTTPError as e:
        detail = e.read().decode(errors="replace")[:200]
        return f"pool join rejected ({e.code}) — {detail}"
    except Exception as e:
        return f"pool join failed: {e}"
    env_path = os.path.join(cfg.bot_dir, ".env")
    env_lines = []
    if os.path.exists(env_path):
        with open(env_path) as f:
            env_lines = f.readlines()
    kept = [ln for ln in env_lines if not ln.strip().startswith(("POOL_NODE_ID=", "POOL_NODE_SECRET="))]
    kept.append(f"POOL_NODE_ID={data.get('name', '')}\n")
    kept.append(f"POOL_NODE_SECRET={data.get('node_secret', '')}\n")
    with open(env_path, "w") as f:
        f.writelines(kept)
    verb = "updated" if data.get("new") is False else "joined"
    if data.get("status") == "pending":
        return (f"{verb} the community pool as {data.get('name', 'node-????')} ({share}%) — "
                "pending host approval. See the panel Host → Community pool.")
    return f"{verb} the community pool as {data.get('name', 'node-????')} ({share}%) — requests now route to you"

POOL_BROKER = os.environ.get("POOL_BROKER_URL") or "https://admin.quaestio.online"


def _step_pool():
    if not cfg.pool:
        return "skipped (not contributing)"
    endpoint = cfg.remote_endpoint if (cfg.endpoint_mode == "remote" and cfg.remote_endpoint) else "http://127.0.0.1:11434"
    join_key = os.environ.get("POOL_JOIN_KEY") or ""
    return _pool_join_remote(POOL_BROKER, join_key, endpoint, cfg.model, cfg.pool_share)


def _step_web():
    if not cfg.web:
        return "skipped (web panel not requested)"
    base = os.environ.get("QUAESTIO_SRC", "https://raw.githubusercontent.com/fishesarethings/quaestio-site/main/dashboard")
    os.makedirs(os.path.join(DASH_DIR, "static"), exist_ok=True)
    for f in ("app.py", "requirements.txt"):
        _run(["curl", "-fsSL", f"{base}/{f}", "-o", os.path.join(DASH_DIR, f)], silent=True)
    for f in ("app.js", "style.css", "index.html"):
        _run(["curl", "-fsSL", f"{base}/static/{f}", "-o", os.path.join(DASH_DIR, "static", f)], silent=True)
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
        ("Start on login", _step_autostart),
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
        "  Admin web panel:   " + ("yes (fetched to the install folder)" if cfg.web else "no"),
        "  Community pool:    " + (f"yes — {cfg.pool_share}% of your box, anonymous" if cfg.pool else "no — compute stays local only"),
        "  Start on login:    " + ("yes — keeps serving after reboot" if cfg.autostart else "no — start it manually"),
        "  Bot:               none needed — Quaestio's shared bot (add your own later: quaestio settings)",
        "",
        "  Press Install now to do everything.",
    ]
    return "\n".join(lines)


class Installer(App):
    TITLE = "Quaestio — community host"
    SCREENS = {
        "start": Start,
        "components": Components,
        "location": Location,
        "connections": Connections,
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
        result = app.run()
        if result == "done":
            print()
            if cfg.pool:
                print("[quaestio] Thanks for joining the community pool!")
                print("[quaestio] See your contributions anytime with:  quaestio pool")
            else:
                print("[quaestio] Thanks! Everything is in place.")
            print("[quaestio] Manage it anytime from any folder:  quaestio   (or:  quaestio help)")
        return
    print("[quaestio] Starting install in classic text mode...")


if __name__ == "__main__":
    main()