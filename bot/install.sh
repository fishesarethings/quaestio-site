#!/usr/bin/env bash
# -----------------------------------------------------------------------------
# Quaestio — single-command installer
#
#   curl -fsSL https://quaestio.online/bot/install.sh | bash
#
# What it does, with (ideally) zero prerequisites:
#   1. Checks for Python 3.10+ / pip — auto-installs on macOS (brew) or tells
#      you the one command on Ubuntu/Debian/RHEL-family if missing.
#   2. Creates a virtualenv (venv) so nothing touches your system Python.
#   3. Installs dependencies from requirements.txt.
#   4. Opens a full-screen interactive wizard (if run from a terminal): walks
#      you through the AI/web/pool components, the connection + model and pool
#      share — the shared Quaestio bot needs no token from you. An own-bot
#      token is optional (advanced self-hosting only).
#   5. Falls back to the classic text prompts when non-interactive.
#
# Re-running is safe — it only installs missing pieces.
# -----------------------------------------------------------------------------
set -euo pipefail

INSTALL_DIR="${QUAESTIO_DIR:-$HOME/quaestio}"
MODEL="${QUAESTIO_MODEL:-qwen2.5:1.5b}"
# Pre-set this to host the AI on another computer, e.g.:
#   OLLAMA_BASE_URL=http://192.168.1.50:11434 curl -fsSL https://quaestio.online/bot/install.sh | bash
REMOTE_OLLAMA="${OLLAMA_BASE_URL:-}"
PY_MIN=(3 10)

say()  { printf '\033[1;36m[quaestio]\033[0m %s\n' "$*"; }
warn() { printf '\033[1;33m[quaestio]\033[0m %s\n' "$*"; }
die()  { printf '\033[1;31m[quaestio]\033[0m %s\n' "$*" >&2; exit 1; }

# --- 1. Python -----------------------------------------------------------------
need_python() {
  if command -v python3 >/dev/null 2>&1; then
    local maj min
    maj=$(python3 -c 'import sys; print(sys.version_info[0])')
    min=$(python3 -c 'import sys; print(sys.version_info[1])')
    if (( maj > PY_MIN[0] )) || (( maj == PY_MIN[0] && min >= PY_MIN[1] )); then
      return 0
    fi
  fi
  return 1
}

# --- 1b. Encryption keyfile ----------------------------------------------------
keyfile() {
  # Same default as bot/config.py: Linux → /etc/quaestio/keyfile (sudo),
  # macOS → ~/.quaestio/keyfile (no sudo), override with QUAESTIO_KEY_FILE.
  local dflt
  if [[ -n "${QUAESTIO_KEY_FILE:-}" ]]; then
    local keyfile="$QUAESTIO_KEY_FILE"
  elif [[ "$(uname -s)" == "Linux" ]]; then
    local keyfile="/etc/quaestio/keyfile"
  else
    local keyfile="$HOME/.quaestio/keyfile"
  fi
  if [[ ! -f "$keyfile" ]]; then
    say "Creating encryption key at $keyfile"$([[ "$(uname -s)" == "Linux" ]] && echo " (needs sudo on Linux)").
    # Prefer the venv python (cryptography is guaranteed there after pip
    # install) so we only ever ask for sudo once on Linux.
    local genpy="$VENV/bin/python"
    [[ -x "$genpy" ]] || genpy="python3"
    if [[ "$(uname -s)" == "Linux" ]]; then
      sudo mkdir -p "$(dirname "$keyfile")"
      sudo "$genpy" -c "from cryptography.fernet import Fernet; open('$keyfile','wb').write(Fernet.generate_key())"
      sudo chmod 600 "$keyfile"
    else
      mkdir -p "$(dirname "$keyfile")"
      "$genpy" -c "from cryptography.fernet import Fernet; open('$keyfile','wb').write(Fernet.generate_key())"
      chmod 600 "$keyfile"
    fi
    say "Keyfile created."
  fi
}

if ! need_python; then
  warn "Python ${PY_MIN[0]}.${PY_MIN[1]}+ not found."
  if [[ "$(uname -s)" == "Darwin" ]]; then
    if command -v brew >/dev/null 2>&1; then
      say "Installing Python via Homebrew — this may take a few minutes (~150 MB)."
      brew install python@3.12
      # Brew links python3 into /opt/homebrew/bin (Apple Silicon) or
      # /usr/local/bin (Intel) — pick it up in THIS shell so the rest of
      # the installer sees it without opening a new terminal.
      export PATH="/opt/homebrew/bin:/usr/local/bin:$PATH"
      hash -r 2>/dev/null || true
    else
      die "Install Homebrew from https://brew.sh, then re-run (or run: brew install python@3.12)."
    fi
  else
    warn "Install it and re-run. Ubuntu/Debian:  sudo apt update && sudo apt install -y python3 python3-venv python3-pip"
    warn "Fedora/RHEL:                       sudo dnf install -y python3 python3-virtualenv python3-pip"
    die "Python ${PY_MIN[0]}.${PY_MIN[1]}+ required."
  fi
fi
say "Python $(python3 --version | awk '{print $2}') OK."

# --- 2. Location & files -------------------------------------------------------
VENV="$INSTALL_DIR/.venv"
BOT_DIR="$INSTALL_DIR/bot"
mkdir -p "$BOT_DIR"

if [[ ! -f "$BOT_DIR/bot.py" ]]; then
  say "Downloading Quaestio bot code…"
  BASE="${QUAESTIO_SRC:-https://raw.githubusercontent.com/fishesarethings/quaestio-website/main/bot}"
  curl -fsSL "$BASE/bot.py" -o "$BOT_DIR/bot.py" || die "Could not download bot.py (check your network)."
  curl -fsSL "$BASE/config.py" -o "$BOT_DIR/config.py" || warn "Could not download config.py."
  curl -fsSL "$BASE/quaestio.py" -o "$BOT_DIR/quaestio.py" || warn "Could not download the manage tool."
  curl -fsSL "$BASE/install_wizard.py" -o "$BOT_DIR/install_wizard.py" || warn "Could not download the install wizard."
  curl -fsSL "$BASE/requirements.txt" -o "$BOT_DIR/requirements.txt"
  curl -fsSL "$BASE/.env.example" -o "$BOT_DIR/.env.example" || true
else
  say "Bot code already present at $BOT_DIR — skipping download."
  # Make sure config.py exists too (added in a later version)
  if [[ ! -f "$BOT_DIR/config.py" ]]; then
    say "Fetching config.py…"
    BASE="${QUAESTIO_SRC:-https://raw.githubusercontent.com/fishesarethings/quaestio-website/main/bot}"
    curl -fsSL "$BASE/config.py" -o "$BOT_DIR/config.py" || warn "Could not download config.py."
  fi
  if [[ ! -f "$BOT_DIR/quaestio.py" ]]; then
    say "Fetching the manage tool (quaestio.py)…"
    BASE="${QUAESTIO_SRC:-https://raw.githubusercontent.com/fishesarethings/quaestio-website/main/bot}"
    curl -fsSL "$BASE/quaestio.py" -o "$BOT_DIR/quaestio.py" || warn "Could not download the manage tool."
  fi
  # The wizard gets refreshed on every run so fixes/tweaks reach you instantly.
  say "Fetching the latest install wizard…"
  BASE="${QUAESTIO_SRC:-https://raw.githubusercontent.com/fishesarethings/quaestio-website/main/bot}"
  curl -fsSL "$BASE/install_wizard.py" -o "$BOT_DIR/install_wizard.py" || warn "Could not download the install wizard."
fi
chmod +x "$BOT_DIR/quaestio.py" 2>/dev/null || true

# --- 3. Virtualenv + deps ------------------------------------------------------
if [[ ! -x "$VENV/bin/python" ]]; then
  say "Creating virtualenv…"
  python3 -m venv "$VENV"
fi
say "Installing dependencies…"
"$VENV/bin/pip" --quiet install --upgrade pip
"$VENV/bin/pip" --quiet install -r "$BOT_DIR/requirements.txt"
if [[ "$(uname -s)" == "Darwin" ]]; then
  # Stock python.org Mac Pythons ship without root certificates, which makes
  # every broker call fail with CERTIFICATE_VERIFY_FAILED. Fix once here.
  _pymajmin=$(python3 -c 'import sys; print(f"{sys.version_info[0]}.{sys.version_info[1]}")' 2>/dev/null || echo "")
  _certcmd="/Applications/Python ${_pymajmin}/Install Certificates.command"
  if [[ -x "$_certcmd" ]]; then
    say "Installing Python root certificates (fixes secure pool connections)…"
    "$_certcmd" >/dev/null 2>&1 || true
  fi
fi

# --- 3aa. Interactive install wizard (skip when non-interactive / no textual) ---
# The wizard opens a full-screen TUI: the AI engine + web panel + pool choices,
# connection + model and pool share; it never needs a Discord bot token of yours.
# Falls back to the classic Q&A flow below.
INSTALL_WIZARD="$BOT_DIR/install_wizard.py"
WIZARD_OK=0
# A controlling terminal (/dev/tty) exists even when this script is piped in
# (curl … | bash), so the full-screen wizard can open. Only skip it when the
# terminal is truly absent (cron, CI, ssh without -t) or QUAESTIO_NO_WIZARD=1.
if [[ -f "$INSTALL_WIZARD" ]] && { [[ -t 0 ]] || [[ -e /dev/tty ]]; } \
   && [[ -z "${QUAESTIO_NO_WIZARD:-}" ]]; then
  if "$VENV/bin/python" -c "import textual" >/dev/null 2>&1; then
    say "Opening the interactive installer (full-screen TUI)…"
    say "Use ↑/↓ or Tab to move, Enter/Space to pick, Esc to go back."
    echo
    BOT_TOKEN="${BOT_TOKEN:-}" \
    OLLAMA_BASE_URL="${REMOTE_OLLAMA:-}" \
    POOL_BROKER_URL="${POOL_BROKER_URL:-}" \
    POOL_JOIN_KEY="${POOL_JOIN_KEY:-}" \
    QUAESTIO_MODEL="$MODEL" \
    QUAESTIO_DIR="$INSTALL_DIR" \
    QUAESTIO_KEY_FILE="${QUAESTIO_KEY_FILE:-}" \
    QUAESTIO_SRC="${QUAESTIO_SRC:-https://raw.githubusercontent.com/fishesarethings/quaestio-website/main/bot}" \
      "$VENV/bin/python" "$INSTALL_WIZARD" < /dev/tty && WIZARD_OK=1
  else
    warn "Textual isn't installed in the venv yet — the classic text flow will be used."
  fi
fi
if [[ "$WIZARD_OK" == "1" ]]; then
  say "Installer wizard finished. You're all set!"
  say ""
say "Manage it anytime from any folder:"
say "    quaestio                opens a full-screen interactive TUI"
say "    quaestio help           shows every command"
say "    quaestio status         what's here / running"
say "    quaestio settings       change any setting"
say "    quaestio contribute     join the community pool (priority routing + 3x limits)"
say "    quaestio pool           see your contributions"
say "    quaestio update         pull the latest bot"
say "    quaestio uninstall      remove everything"
  exit 0
fi

# --- 3b. A real `quaestio` command on your PATH ------------------------------
# After install you can just type `quaestio` (menu), `quaestio help`,
# `quaestio status`, `quaestio contribute`, … from any folder.
install_quaestio_command() {
  BIN_DIR="$INSTALL_DIR/bin"
  mkdir -p "$BIN_DIR"
  cat > "$BIN_DIR/quaestio" <<EOF
#!/usr/bin/env bash
# Quaestio manager — `quaestio` opens the menu, `quaestio help` lists actions.
INSTALL_DIR="$INSTALL_DIR"
VENV="$VENV"
exec "$VENV/bin/python" "$INSTALL_DIR/bot/quaestio.py" "\$@"
EOF
  chmod +x "$BIN_DIR/quaestio"

  # Symlink it into the first bin dir that's on PATH (or the usual ones).
  local target=""
  for d in "$HOME/.local/bin" "$HOME/bin"; do
    if printf '%s' "$PATH" | tr ':' '\n' | grep -qx "$d"; then
      target="$d"; break
    fi
  done
  if [[ -z "$target" ]]; then
    mkdir -p "$HOME/.local/bin" 2>/dev/null || true
    target="$HOME/.local/bin"
  fi
  ln -sf "$BIN_DIR/quaestio" "$target/quaestio"
  say "\"quaestio\" is now a command ($target/quaestio)."
  if ! printf '%s' "$PATH" | tr ':' '\n' | grep -qx "$target"; then
    # Put it on PATH for real: append to the shell startup file so every
    # new terminal (and a quick `source`) picks it up. This was the #1
    # install complaint (`quaestio: command not found` on macOS).
    for rc in "$HOME/.zshrc" "$HOME/.bashrc"; do
      case "$(basename "$rc")" in
        .zshrc) [[ "$(uname -s)" != "Darwin" ]] && [[ -n "${BASH_VERSION:-}" ]] && continue ;;
      esac
      touch "$rc" 2>/dev/null || continue
      if ! grep -qxF "export PATH=\"$target:\$PATH\" # quaestio" "$rc" 2>/dev/null; then
        printf '\nexport PATH="%s:$PATH" # quaestio\n' "$target" >> "$rc"
      fi
    done
    export PATH="$target:$PATH"
    hash -r 2>/dev/null || true
    say "Added $target to your PATH (shell startup file updated — \`quaestio\` works now and in new terminals)."
  fi
}

# --- 3c. Encryption keyfile ----------------------------------------------------
keyfile

# --- 3d. `quaestio` command on your PATH ---------------------------------------
install_quaestio_command

# --- 4. Ollama (AI) ------------------------------------------------------------
if ! command -v ollama >/dev/null 2>&1; then
  warn "Ollama (the local AI engine) is missing."
  read -r -p "Install Ollama automatically? [y/N] " yn
  if [[ "$yn" == [yY]* ]]; then
    if [[ "$(uname -s)" == "Darwin" ]]; then
      if command -v brew >/dev/null 2>&1; then
        brew install ollama
      else
        warn "Use the Ollama.app download from https://ollama.com/download (macOS)."
      fi
    else
      curl -fsSL https://ollama.com/install.sh | sh || warn "Ollama install failed — get it from https://ollama.com/download."
    fi
  fi
fi
if command -v ollama >/dev/null 2>&1; then
  if ! ollama list 2>/dev/null | grep -qi "$MODEL"; then
    say "Pulling a small smart AI model ($MODEL, ~1 GB download) — first run takes a minute or two."
    ollama pull "$MODEL" || warn "Model pull failed; you can run 'ollama pull $MODEL' later."
  else
    say "Model '$MODEL' already present."
  fi
else
  warn "Ollama not detected — the AI commands will be offline until you install it (~500 MB + ~1 GB model)."
fi

# --- 5. Config (.env) — the Discord token is always optional -------------------
# Quaestio starts without one; add it anytime with `quaestio settings`.
ENV_FILE="$BOT_DIR/.env"
rebuild=0
if [[ ! -f "$ENV_FILE" ]] || ! grep -q '[^#]' "$ENV_FILE" 2>/dev/null || grep -qi 'your-bot-token-here' "$ENV_FILE"; then
  rebuild=1
fi
if [[ "$rebuild" == "1" ]]; then
  if [[ -n "${BOT_TOKEN:-}" ]]; then
    say "Using BOT_TOKEN from the environment."
    printf 'BOT_TOKEN=%s\n' "$BOT_TOKEN" > "$ENV_FILE"
  else
    : > "$ENV_FILE"
    warn "No Discord bot token set — that's fine. Add one later with:  quaestio settings"
  fi
  if [[ -n "$REMOTE_OLLAMA" ]]; then
    printf 'OLLAMA_BASE_URL=%s\n' "$REMOTE_OLLAMA" >> "$ENV_FILE"
  else
    printf 'OLLAMA_BASE_URL=http://127.0.0.1:11434\n' >> "$ENV_FILE"
  fi
  printf 'OLLAMA_MODEL=%s\nRPC_LARGE_IMAGE=logo\n' "$MODEL" >> "$ENV_FILE"
  chmod 600 "$ENV_FILE"
  say "Config written to $ENV_FILE (permissions 600)."
else
  say "Config already present at $ENV_FILE."
fi

# --- 6. Service / launch -------------------------------------------------------
# Pool-only boxes (no BOT_TOKEN) get the unit installed but NOT started —
# the bot idles without a token, so starting it would just sit idle.
has_token() { grep -q '^BOT_TOKEN=.\+' "$ENV_FILE" 2>/dev/null; }
if [[ "$(uname -s)" == "Linux" ]] && command -v systemctl >/dev/null 2>&1; then
  SERVICE=/etc/systemd/system/quaestio.service
  if [[ ! -f "$SERVICE" ]]; then
    say "Installing systemd service… (may ask for your sudo password)"
    sudo tee "$SERVICE" >/dev/null <<EOF
[Unit]
Description=Quaestio Discord bot
After=network-online.target ollama.service
Wants=network-online.target

[Service]
WorkingDirectory=$BOT_DIR
EnvironmentFile=$ENV_FILE
ExecStart=$VENV/bin/python $BOT_DIR/bot.py
Restart=on-failure
RestartSec=5
User=$USER

[Install]
WantedBy=multi-user.target
EOF
    sudo systemctl daemon-reload
    if has_token; then
      sudo systemctl enable --now quaestio.service
      say "Quaestio is running as a service!  Status: systemctl status quaestio  Logs: journalctl -u quaestio -f"
    else
      sudo systemctl enable quaestio.service
      warn "No bot token — service installed but not started (pool-only mode)."
      say "Add one later with:  quaestio settings   then:  sudo systemctl restart quaestio"
    fi
  else
    if has_token; then
      say "Systemd service already installed — restarting it."
      sudo systemctl restart quaestio.service
    else
      say "Systemd service already installed — token still missing, leaving it stopped."
      say "Add one with:  quaestio settings   then:  sudo systemctl restart quaestio"
    fi
  fi
else
  RUN="$INSTALL_DIR/run-quaestio.sh"
  cat > "$RUN" <<EOF
#!/usr/bin/env bash
cd "$BOT_DIR"
set -a; source .env; set +a
exec "$VENV/bin/python" "$BOT_DIR/bot.py"
EOF
  chmod +x "$RUN"
  say "Done! Start Quaestio with:" 
  say "    $RUN"
  say "(tip: run it from a terminal, or use 'caffeinate -i $RUN' on macOS)."
fi

say "Everything ready. Your AI brain: local Ollama ($MODEL). Nothing is cloud-hosted."
say ""
say "Manage it anytime from any folder:"
say "    quaestio                opens a full-screen interactive TUI"
say "    quaestio help           shows every command"
say "    quaestio status         what's here / running"
say "    quaestio settings       change any setting"
say "    quaestio contribute     join the community pool (priority routing + 3x limits)"
say "    quaestio pool           see your contributions"
say "    quaestio update         pull the latest bot"
say "    quaestio uninstall      remove everything"