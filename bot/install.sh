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
#   3. Installs dependencies (just discord.py) from requirements.txt.
#   4. Detects Ollama: prompts to install it if missing (this machine only),
#      and offers to pull a small smart model (qwen2.5:1.5b, ~1 GB) so AI works
#      immediately with zero manual steps.
#   5. Prompts once for your Discord bot token, writes .env (chmod 600).
#   6. Installs a systemd service (Linux) OR prints a run command (macOS).
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
  local keyfile="${QUAESTIO_KEY_FILE:-/etc/quaestio/keyfile}"
  if [[ ! -f "$keyfile" ]]; then
    say "Creating encryption key at $keyfile (needs sudo on Linux)."
    if [[ "$(uname -s)" == "Linux" ]]; then
      sudo mkdir -p "$(dirname "$keyfile")"
      sudo python3 -c "from cryptography.fernet import Fernet; import sys; open('$keyfile','wb').write(Fernet.generate_key())" 2>/dev/null \
        || sudo "$VENV/bin/python" -c "from cryptography.fernet import Fernet; open('$keyfile','wb').write(Fernet.generate_key())"
      sudo chmod 600 "$keyfile"
    else
      mkdir -p "$(dirname "$keyfile")"
      python3 -c "from cryptography.fernet import Fernet; open('$keyfile','wb').write(Fernet.generate_key())" 2>/dev/null \
        || "$VENV/bin/python" -c "from cryptography.fernet import Fernet; open('$keyfile','wb').write(Fernet.generate_key())"
      chmod 600 "$keyfile"
    fi
    say "Keyfile created."
  fi
}

if ! need_python; then
  warn "Python ${PY_MIN[0]}.${PY_MIN[1]}+ not found."
  if [[ "$(uname -s)" == "Darwin" ]]; then
    if command -v brew >/dev/null 2>&1; then
      say "Installing Python via Homebrew — this may take a few minutes."
      brew install python@3.12
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
  BASE="${QUAESTIO_SRC:-https://raw.githubusercontent.com/fishesarethings/quaestio-site/main/bot}"
  curl -fsSL "$BASE/bot.py" -o "$BOT_DIR/bot.py" || die "Could not download bot.py (check your network)."
  curl -fsSL "$BASE/config.py" -o "$BOT_DIR/config.py" || warn "Could not download config.py."
  curl -fsSL "$BASE/quaestio.py" -o "$BOT_DIR/quaestio.py" || warn "Could not download the manage tool."
  curl -fsSL "$BASE/requirements.txt" -o "$BOT_DIR/requirements.txt"
  curl -fsSL "$BASE/.env.example" -o "$BOT_DIR/.env.example" || true
else
  say "Bot code already present at $BOT_DIR — skipping download."
  # Make sure config.py exists too (added in a later version)
  if [[ ! -f "$BOT_DIR/config.py" ]]; then
    say "Fetching config.py…"
    BASE="${QUAESTIO_SRC:-https://raw.githubusercontent.com/fishesarethings/quaestio-site/main/bot}"
    curl -fsSL "$BASE/config.py" -o "$BOT_DIR/config.py" || warn "Could not download config.py."
  fi
  if [[ ! -f "$BOT_DIR/quaestio.py" ]]; then
    say "Fetching the manage tool (quaestio.py)…"
    BASE="${QUAESTIO_SRC:-https://raw.githubusercontent.com/fishesarethings/quaestio-site/main/bot}"
    curl -fsSL "$BASE/quaestio.py" -o "$BOT_DIR/quaestio.py" || warn "Could not download the manage tool."
  fi
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

# --- 3b. Encryption keyfile ----------------------------------------------------
keyfile

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
    say "Pulling a small smart AI model ($MODEL, ~1 GB) — first run takes a minute or two."
    ollama pull "$MODEL" || warn "Model pull failed; you can run 'ollama pull $MODEL' later."
  else
    say "Model '$MODEL' already present."
  fi
else
  warn "Ollama not detected — the AI commands will be offline until you install it."
fi

# --- 5. Token / .env -----------------------------------------------------------
ENV_FILE="$BOT_DIR/.env"
if [[ ! -f "$ENV_FILE" ]] || ! grep -q '[^#]' "$ENV_FILE" 2>/dev/null || grep -qi 'your-bot-token-here' "$ENV_FILE"; then
  echo
  warn "Discord bot token needed (Developer Portal → your app → Bot → Reset Token)."
  if [[ -t 0 ]]; then
    read -r -p "Paste your bot token (hidden): " -s token
    echo
  else
    die "Non-interactive run — set BOT_TOKEN=... and re-run, or write $ENV_FILE yourself."
  fi
  [[ -z "$token" ]] && die "No token given."
  printf 'BOT_TOKEN=%s\n' "$token" > "$ENV_FILE"
  if [[ -n "$REMOTE_OLLAMA" ]]; then
    printf 'OLLAMA_BASE_URL=%s\n' "$REMOTE_OLLAMA" >> "$ENV_FILE"
  else
    printf 'OLLAMA_BASE_URL=http://127.0.0.1:11434\n' >> "$ENV_FILE"
  fi
  printf 'OLLAMA_MODEL=%s\nRPC_LARGE_IMAGE=logo\n' "$MODEL" >> "$ENV_FILE"
  chmod 600 "$ENV_FILE"
  say "Token saved to $ENV_FILE (permissions 600)."
else
  say "Config already present at $ENV_FILE."
fi

# --- 6. Service / launch -------------------------------------------------------
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
    sudo systemctl enable --now quaestio.service
    say "Quaestio is running as a service!  Status: systemctl status quaestio  Logs: journalctl -u quaestio -f"
  else
    say "Systemd service already installed — restarting it."
    sudo systemctl restart quaestio.service
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
say "Manage it anytime (settings, update, uninstall, pool contribution):"
say "    python3 \"$BOT_DIR/quaestio.py\""
say "Or start fresh:"
say "    python3 \"$BOT_DIR/quaestio.py\" help"