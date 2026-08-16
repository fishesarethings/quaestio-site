# -----------------------------------------------------------------------------
# Quaestio — Windows installer (PowerShell 5.1+, right-click → Run with PowerShell,
# or:  powershell -ExecutionPolicy Bypass -File install.ps1)
#
# Mirrors install.sh for Windows. Also works when the AI lives on another
# computer: set OLLAMA_BASE_URL first, e.g.
#   $env:OLLAMA_BASE_URL = "http://192.168.1.50:11434"
# -----------------------------------------------------------------------------
$ErrorActionPreference = "Stop"

$InstallDir = if ($env:QUAESTIO_DIR) { $env:QUAESTIO_DIR } else { Join-Path $HOME "quaestio" }
$Model = if ($env:QUAESTIO_MODEL) { $env:QUAESTIO_MODEL } else { "qwen2.5:1.5b" }
$RemoteOllama = $env:OLLAMA_BASE_URL
$BotDir = Join-Path $InstallDir "bot"
$Venv = Join-Path $InstallDir ".venv"

function Say  { Write-Host "[quaestio] $args" -ForegroundColor Cyan }
function Warn { Write-Host "[quaestio] $args" -ForegroundColor Yellow }
function Die  { Write-Host "[quaestio] $args" -ForegroundColor Red; exit 1 }

# --- 1. Python ---------------------------------------------------------------
$py = Get-Command python -ErrorAction SilentlyContinue
if (-not $py) {
    Warn "Python not found. Install from https://www.python.org/downloads/ (tick 'Add to PATH'), then re-run."
    Die "Python 3.10+ is required."
}
$pyVer = & python -c "import sys; print('%d.%d' % (sys.version_info[0], sys.version_info[1]))"
Say "Python $pyVer OK."

# --- 2. Download bot code ----------------------------------------------------
New-Item -ItemType Directory -Force -Path $BotDir | Out-Null
if (-not (Test-Path (Join-Path $BotDir "bot.py"))) {
    $base = if ($env:QUAESTIO_SRC) { $env:QUAESTIO_SRC } else { "https://raw.githubusercontent.com/fishesarethings/quaestio-site/main/bot" }
    Say "Downloading Quaestio bot code…"
    Invoke-WebRequest -Uri "$base/bot.py" -OutFile (Join-Path $BotDir "bot.py") -UseBasicParsing
    Invoke-WebRequest -Uri "$base/config.py" -OutFile (Join-Path $BotDir "config.py") -UseBasicParsing
    Invoke-WebRequest -Uri "$base/quaestio.py" -OutFile (Join-Path $BotDir "quaestio.py") -UseBasicParsing
    Invoke-WebRequest -Uri "$base/install_wizard.py" -OutFile (Join-Path $BotDir "install_wizard.py") -UseBasicParsing
    Invoke-WebRequest -Uri "$base/requirements.txt" -OutFile (Join-Path $BotDir "requirements.txt") -UseBasicParsing
    Invoke-WebRequest -Uri "$base/.env.example" -OutFile (Join-Path $BotDir ".env.example") -UseBasicParsing
} else {
    Say "Bot code already present at $BotDir — skipping download."
    if (-not (Test-Path (Join-Path $BotDir "config.py"))) {
        $base = if ($env:QUAESTIO_SRC) { $env:QUAESTIO_SRC } else { "https://raw.githubusercontent.com/fishesarethings/quaestio-site/main/bot" }
        Say "Fetching config.py…"
        Invoke-WebRequest -Uri "$base/config.py" -OutFile (Join-Path $BotDir "config.py") -UseBasicParsing
    }
    if (-not (Test-Path (Join-Path $BotDir "quaestio.py"))) {
        $base = if ($env:QUAESTIO_SRC) { $env:QUAESTIO_SRC } else { "https://raw.githubusercontent.com/fishesarethings/quaestio-site/main/bot" }
        Say "Fetching the manage tool (quaestio.py)…"
        Invoke-WebRequest -Uri "$base/quaestio.py" -OutFile (Join-Path $BotDir "quaestio.py") -UseBasicParsing
    }
    if (-not (Test-Path (Join-Path $BotDir "install_wizard.py"))) {
        $base = if ($env:QUAESTIO_SRC) { $env:QUAESTIO_SRC } else { "https://raw.githubusercontent.com/fishesarethings/quaestio-site/main/bot" }
        Say "Fetching the install wizard…"
        Invoke-WebRequest -Uri "$base/install_wizard.py" -OutFile (Join-Path $BotDir "install_wizard.py") -UseBasicParsing
    }
}

# --- 3. Virtualenv + deps ----------------------------------------------------
if (-not (Test-Path (Join-Path $Venv "Scripts\python.exe"))) {
    Say "Creating virtualenv…"
    & python -m venv $Venv
}
Say "Installing dependencies…"
& (Join-Path $Venv "Scripts\python.exe") -m pip install --quiet --upgrade pip
& (Join-Path $Venv "Scripts\python.exe") -m pip install --quiet -r (Join-Path $BotDir "requirements.txt")

# --- 3aa. Interactive install wizard (full-screen TUI) ------------------------
# Walks you through what gets installed, AI/web/pool choices, connection + model,
# pool share and your token, then installs everything with live progress.
# Falls back to the classic text prompts below (non-interactive consoles).
$Wizard = Join-Path $BotDir "install_wizard.py"
$WizardOK = $false
if ((Test-Path $Wizard) -and (-not $env:QUAESTIO_NO_WIZARD) -and (-not $RemoteOllama)) {
    $hasTextual = & (Join-Path $Venv "Scripts\python.exe") -c "import textual" 2>$null
    if ($LASTEXITCODE -eq 0) {
        Say "Opening the interactive installer (full-screen TUI)…"
        Say "Use ↑/↓ or Tab to move, Enter/Space to pick, Esc to go back."
        $env:BOT_TOKEN = if ($env:BOT_TOKEN) { $env:BOT_TOKEN } else { "" }
        $env:QUAESTIO_DIR = $InstallDir
        $env:QUAESTIO_SRC = if ($env:QUAESTIO_SRC) { $env:QUAESTIO_SRC } else { "https://raw.githubusercontent.com/fishesarethings/quaestio-site/main/bot" }
        $env:OLLAMA_BASE_URL = $RemoteOllama
        & (Join-Path $Venv "Scripts\python.exe") $Wizard
        if ($LASTEXITCODE -eq 0) { $WizardOK = $true }
    }
}
if ($WizardOK) {
    Say "Installer wizard finished. You're all set!"
    Say "Manage it anytime from any folder:"
    Say "    quaestio            opens a full-screen interactive TUI"
    Say "    quaestio help       shows every command"
    Say "    quaestio status     what's here / running"
    Say "    quaestio settings   change any setting"
    Say "    quaestio contribute join the resource pool"
    Say "    quaestio update     pull the latest bot"
    Say "    quaestio uninstall  remove everything"
    exit 0
}

# --- 3b. A real `quaestio` command on your PATH ------------------------------
# After install you can just type `quaestio`, `quaestio help`, `quaestio status`,
# `quaestio contribute`, … from any folder or new terminal.
$BinDir = Join-Path $InstallDir "bin"
New-Item -ItemType Directory -Force -Path $BinDir | Out-Null
$quaestioCmd = Join-Path $BinDir "quaestio.cmd"
@"
@echo off
"$Venv\Scripts\python.exe" "$BotDir\quaestio.py" %*
"@ | Set-Content -Path $quaestioCmd -Encoding ASCII
$userPath = [Environment]::GetEnvironmentVariable("Path", "User")
if ($userPath -notlike "*$BinDir*") {
    [Environment]::SetEnvironmentVariable("Path", "$BinDir;$userPath", "User")
    $env:Path = "$BinDir;$env:Path"
    Say "Added $BinDir to your user PATH (works in new terminals)."
}
Say "`"quaestio`" is now a command — try `quaestio` or `quaestio help` in a new terminal."

# --- 3c. Encryption keyfile --------------------------------------------------
$KeyFile = if ($env:QUAESTIO_KEY_FILE) { $env:QUAESTIO_KEY_FILE } else { Join-Path $env:USERPROFILE ".quaestio\keyfile" }
if (-not (Test-Path $KeyFile)) {
    New-Item -ItemType Directory -Force -Path (Split-Path $KeyFile) | Out-Null
    & (Join-Path $Venv "Scripts\python.exe") -c "from cryptography.fernet import Fernet; open(r'$KeyFile','wb').write(Fernet.generate_key())"
    Say "Encryption key created at $KeyFile."
}

# --- 4. Ollama ---------------------------------------------------------------
if (-not (Get-Command ollama -ErrorAction SilentlyContinue)) {
    Warn "Ollama not detected."
    $ans = Read-Host "Install Ollama for Windows now? [y/N]"
    if ($ans -match "^[yY]") {
        Warn "Opening Ollama download page — install it, then re-run this script."
        Start-Process "https://ollama.com/download/windows"
    }
} elseif (-not $RemoteOllama) {
    $have = & ollama list 2>$null
    if ($have -notmatch $Model) {
        Say "Pulling small smart AI model ($Model, ~1 GB)…"
        & ollama pull $Model
    }
}

# --- 5. Token / .env ---------------------------------------------------------
$EnvFile = Join-Path $BotDir ".env"
$writeEnv = $true
if (Test-Path $EnvFile) {
    $content = Get-Content $EnvFile -Raw
    if ($content -match "your-bot-token-here") { $writeEnv = $true } else { $writeEnv = $false }
}
if ($writeEnv) {
    if ($env:BOT_TOKEN) {
        $token = $env:BOT_TOKEN
        Say "Using BOT_TOKEN from the environment."
    } else {
        Warn "Discord bot token needed (Developer Portal → your app → Bot → Reset Token)."
        $token = Read-Host "Paste your bot token"
        if (-not $token) { Die "No token given." }
    }
    $envLines = @("BOT_TOKEN=$token")
    if ($RemoteOllama) { $envLines += "OLLAMA_BASE_URL=$RemoteOllama" } else { $envLines += "OLLAMA_BASE_URL=http://127.0.0.1:11434" }
    $envLines += "OLLAMA_MODEL=$Model"
    $envLines += "RPC_LARGE_IMAGE=logo"
    Set-Content -Path $EnvFile -Value ($envLines -join "`n")
    Say "Token saved to $EnvFile."
} else {
    Say "Config already present at $EnvFile."
}

# --- 6. Launch scripts -------------------------------------------------------
$runBat = Join-Path $InstallDir "run-quaestio.bat"
@"
@echo off
cd /d "$BotDir"
setlocal
for /f "tokens=1,* delims==" %%a in (.env) do set "%%a=%%b"
"$Venv\Scripts\python.exe" "$BotDir\bot.py"
"@ | Set-Content -Path $runBat -Encoding ASCII

$task = Get-ScheduledTask -TaskName "QuaestioBot" -ErrorAction SilentlyContinue
if (-not $task) {
    $ans = Read-Host "Start automatically when you log in? Create a startup task? [y/N]"
    if ($ans -match "^[yY]") {
        $action = New-ScheduledTaskAction -Execute $runBat
        $trigger = New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME
        Register-ScheduledTask -TaskName "QuaestioBot" -Action $action -Trigger $trigger -RunLevel Limited -Force | Out-Null
        Say "Startup task created (QuaestioBot)."
    }
}

Say "Done!"
Say "Start Quaestio with:  $runBat"
Say "(On a server PC you can leave it running; one chat at a time keeps it light.)"
Say "Manage it anytime from any folder:"
Say "    quaestio            opens a full-screen interactive TUI"
Say "    quaestio help       shows every command"
Say "    quaestio status     what's here / running"
Say "    quaestio settings   change any setting"
Say "    quaestio contribute join the resource pool"
Say "    quaestio update     pull the latest bot"
Say "    quaestio uninstall  remove everything"
