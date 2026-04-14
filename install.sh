#!/usr/bin/env bash
# ============================================================================
# NanoClaw + Financial Assistant -- WSL2 Installer
# https://github.com/beejak/nanoclaw
#
# Usage:
#   git clone https://github.com/beejak/nanoclaw.git
#   cd nanoclaw
#   ./install.sh
#
# What this installs:
#   - NanoClaw AI agent framework (Node.js + Docker + Claude Code)
#   - Financial Assistant (Python, Telegram bridge, NSE data, reports)
#   - systemd service for the Telegram bridge
#   - Cron schedule for all reports and health checks
# ============================================================================
set -euo pipefail

# -- Colours ------------------------------------------------------------------
RED='\033[0;31m'; YELLOW='\033[1;33m'; GREEN='\033[0;32m'
CYAN='\033[0;36m'; BOLD='\033[1m'; RESET='\033[0m'

ok()   { echo -e "${GREEN}  [OK] $*${RESET}"; }
info() { echo -e "${CYAN}  -> $*${RESET}"; }
warn() { echo -e "${YELLOW}  [WARN] $*${RESET}"; }
err()  { echo -e "${RED}  [FAIL] $*${RESET}"; }
ask()  { echo -e "${YELLOW}${BOLD}$*${RESET}"; }
hdr()  { echo -e "\n${BOLD}${CYAN}===========================================${RESET}"; \
          echo -e "${BOLD}${CYAN}  $*${RESET}"; \
          echo -e "${BOLD}${CYAN}===========================================${RESET}"; }

pause() { echo; read -rp "  Press Enter to continue..."; }
confirm() {
    # confirm "Do the thing?" -> returns 0 for yes, 1 for no
    local msg="$1"
    echo
    read -rp "  ${msg} [Y/n] " _yn
    [[ "${_yn:-y}" =~ ^[Yy]$ ]]
}

REPO_DIR="$(cd "$(dirname "$0")" && pwd)"
FA_DIR="${REPO_DIR}/extensions/fin-assistant"
ENV_FILE="${FA_DIR}/.env"
LOG_DIR="${FA_DIR}/logs"
STORE_DIR="${FA_DIR}/store"

# -- Banner -------------------------------------------------------------------
clear
echo -e "${BOLD}"
cat << 'EOF'
  NANOCLAW
EOF
echo -e "${RESET}"
echo -e "  ${CYAN}AI Agent Framework + Indian Stock Market Signal Assistant${RESET}"
echo -e "  ${CYAN}WSL2 Installer -- github.com/beejak/nanoclaw${RESET}"
echo
echo -e "  ${YELLOW}[WARN]  NOT FINANCIAL ADVICE. Personal research tool only.${RESET}"
echo
echo -e "  This script will:"
echo -e "    1. Check your WSL2 environment"
echo -e "    2. Install system dependencies"
echo -e "    3. Install NanoClaw (Node.js + Claude Code + Docker check)"
echo -e "    4. Install the Financial Assistant (Python + Telegram + NSE)"
echo -e "    5. Collect credentials (step-by-step, with instructions)"
echo -e "    6. Set up services and schedule"
echo -e "    7. Run a full health check"
echo
echo -e "  Total time: ~10 minutes, depending on your connection."
echo
confirm "Ready to start?" || { echo "Aborted."; exit 0; }

# -----------------------------------------------------------------------------
hdr "STEP 1 -- Environment check"
# -----------------------------------------------------------------------------

# WSL2 check
if grep -qi "microsoft" /proc/version 2>/dev/null; then
    ok "Running inside WSL2"
else
    warn "Not detected as WSL2 -- continuing anyway, but some steps may differ"
fi

# OS
OS_NAME=$(grep -oP '(?<=^NAME=").*(?=")' /etc/os-release 2>/dev/null || echo "Unknown")
OS_VER=$(grep -oP '(?<=^VERSION_ID=").*(?=")' /etc/os-release 2>/dev/null || echo "?")
ok "OS: ${OS_NAME} ${OS_VER}"

# Systemd
if systemctl is-system-running &>/dev/null; then
    ok "systemd is running"
else
    warn "systemd does not appear to be active"
    echo
    echo -e "  ${YELLOW}The Telegram bridge runs as a systemd service. To enable systemd in WSL2:${RESET}"
    echo
    echo -e "    1. Open ${BOLD}Notepad as Administrator${RESET} on Windows"
    echo -e "    2. Edit (or create): ${BOLD}C:\\Users\\<you>\\.wslconfig${RESET}"
    echo -e "    3. Add these lines:"
    echo
    echo -e "         [wsl2]"
    echo -e "         systemd=true"
    echo
    echo -e "    4. Save, then in PowerShell: ${BOLD}wsl --shutdown${RESET}"
    echo -e "    5. Reopen this terminal and re-run install.sh"
    echo
    if ! confirm "Continue without systemd? (bridge won't auto-start on reboot)"; then
        echo "Fix systemd and re-run. Exiting."
        exit 1
    fi
    SKIP_SYSTEMD=true
fi
SKIP_SYSTEMD=${SKIP_SYSTEMD:-false}

# -----------------------------------------------------------------------------
hdr "STEP 2 -- System packages"
# -----------------------------------------------------------------------------

info "Installing: git, python3, python3-pip, sqlite3, curl, jq"
sudo apt-get update -qq
sudo apt-get install -y -qq git python3 python3-pip sqlite3 curl jq
ok "System packages installed"

# -----------------------------------------------------------------------------
hdr "STEP 3 -- Node.js 20+"
# -----------------------------------------------------------------------------

NODE_OK=false
if command -v node &>/dev/null; then
    NODE_VER=$(node --version | grep -oP '\d+' | head -1)
    if [[ ${NODE_VER} -ge 20 ]]; then
        ok "Node.js $(node --version) already installed"
        NODE_OK=true
    else
        warn "Node.js $(node --version) found -- need 20+, upgrading"
    fi
fi

if [[ ${NODE_OK} == false ]]; then
    info "Installing Node.js 20 via NodeSource..."
    curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash - -qq
    sudo apt-get install -y -qq nodejs
    ok "Node.js $(node --version) installed"
fi

# -----------------------------------------------------------------------------
hdr "STEP 4 -- Claude Code"
# -----------------------------------------------------------------------------

if command -v claude &>/dev/null; then
    ok "Claude Code already installed ($(claude --version 2>/dev/null || echo 'version unknown'))"
else
    info "Installing Claude Code CLI..."
    sudo npm install -g @anthropic-ai/claude-code --quiet
    ok "Claude Code installed"
fi

echo
echo -e "  ${YELLOW}Claude Code requires a Claude subscription to run NanoClaw agents.${RESET}"
echo -e "  ${CYAN}Plans: https://claude.ai/pricing${RESET}"
echo -e "  If you only want the Financial Assistant, Claude Code is not needed."
echo

# -----------------------------------------------------------------------------
hdr "STEP 5 -- Docker"
# -----------------------------------------------------------------------------

if command -v docker &>/dev/null && docker info &>/dev/null 2>&1; then
    ok "Docker is running ($(docker --version))"
else
    echo
    echo -e "  ${YELLOW}Docker is required for NanoClaw agents (not for the Financial Assistant).${RESET}"
    echo
    echo -e "  ${BOLD}Recommended for WSL2:${RESET}"
    echo -e "    1. Install Docker Desktop for Windows:"
    echo -e "       ${CYAN}https://www.docker.com/products/docker-desktop/${RESET}"
    echo -e "    2. In Docker Desktop Settings -> Resources -> WSL Integration:"
    echo -e "       enable your WSL2 distro"
    echo -e "    3. Restart Docker Desktop, then re-open this terminal"
    echo
    echo -e "  ${BOLD}Alternative -- native Docker in WSL2:${RESET}"
    echo -e "    Run:  curl -fsSL https://get.docker.com | sh"
    echo -e "    Then: sudo usermod -aG docker \$USER  (then log out and back in)"
    echo
    if confirm "Install native Docker in WSL2 now?"; then
        curl -fsSL https://get.docker.com | sudo sh
        sudo usermod -aG docker "$USER"
        sudo service docker start
        ok "Docker installed -- you may need to log out and back in for group changes"
    else
        warn "Skipping Docker -- NanoClaw agents will not work until Docker is available"
    fi
fi

# -----------------------------------------------------------------------------
hdr "STEP 6 -- Python dependencies (Financial Assistant)"
# -----------------------------------------------------------------------------

info "Installing Python packages..."
pip3 install --break-system-packages -q \
    "pyrogram==2.0.106" \
    tgcrypto \
    requests \
    python-dotenv \
    "yfinance>=1.2.0" \
    "pandas>=2.0.0" \
    "pandas-ta>=0.3.14b"
ok "Python packages installed"

# -----------------------------------------------------------------------------
hdr "STEP 7 -- Telegram API credentials"
# -----------------------------------------------------------------------------

echo
echo -e "  The Financial Assistant needs access to your personal Telegram account"
echo -e "  (to read channels you follow) and a bot (to send you reports)."
echo -e "  ${YELLOW}All credentials are stored locally in .env -- never uploaded anywhere.${RESET}"
echo

# -- TG_API_ID and TG_API_HASH ------------------------------------------------

echo -e "  ${BOLD}[1/4] Telegram API credentials${RESET}"
echo
echo -e "  How to get them:"
echo -e "    1. Open ${CYAN}https://my.telegram.org/apps${RESET} in your browser"
echo -e "    2. Log in with your Telegram phone number"
echo -e "    3. Click ${BOLD}'Create Application'${RESET} (any name/platform is fine)"
echo -e "    4. Copy the ${BOLD}App api_id${RESET} (a number) and ${BOLD}App api_hash${RESET} (a long hex string)"
echo

while true; do
    ask "  Enter your Telegram API ID (numbers only):"
    read -rp "  > " TG_API_ID
    [[ "${TG_API_ID}" =~ ^[0-9]+$ ]] && break
    err "API ID must be numeric. Try again."
done

ask "  Enter your Telegram API Hash:"
read -rp "  > " TG_API_HASH
while [[ -z "${TG_API_HASH}" ]]; do
    err "API Hash cannot be empty."
    read -rp "  > " TG_API_HASH
done

ok "API credentials saved"

# -- TG_SESSION ---------------------------------------------------------------

echo
echo -e "  ${BOLD}[2/4] Session file path${RESET}"
echo
echo -e "  Pyrogram saves your login session to a local file."
echo -e "  Default: ${CYAN}${HOME}/tg_session${RESET}  (recommended, press Enter to accept)"
echo
ask "  Session file path (no .session extension):"
read -rp "  > " TG_SESSION_INPUT
TG_SESSION="${TG_SESSION_INPUT:-${HOME}/tg_session}"
ok "Session path: ${TG_SESSION}"

# -- BOT_TOKEN ----------------------------------------------------------------

echo
echo -e "  ${BOLD}[3/4] Telegram Bot Token${RESET}"
echo
echo -e "  This bot is what sends you the reports. To create one:"
echo -e "    1. Open Telegram and search for ${BOLD}@BotFather${RESET}"
echo -e "    2. Send: ${BOLD}/newbot${RESET}"
echo -e "    3. Choose a name and username for your bot"
echo -e "    4. Copy the token it gives you (looks like: 1234567890:AAEg...)"
echo

ask "  Enter your Bot Token:"
read -rp "  > " BOT_TOKEN
while [[ -z "${BOT_TOKEN}" || ! "${BOT_TOKEN}" =~ : ]]; do
    err "Token looks invalid (should contain a colon). Try again."
    read -rp "  > " BOT_TOKEN
done
ok "Bot token saved"

# -- OWNER_CHAT_ID -- auto-detect ---------------------------------------------

echo
echo -e "  ${BOLD}[4/4] Your Telegram Chat ID${RESET}"
echo
echo -e "  We'll detect this automatically:"
echo -e "    1. Open Telegram"
echo -e "    2. Search for your bot by its username"
echo -e "    3. Send it: ${BOLD}/start${RESET}"
echo
ask "  Once you've sent /start to your bot, press Enter..."
read -rp ""

OWNER_CHAT_ID=""
info "Fetching your chat ID from bot updates..."
UPDATES=$(curl -s "https://api.telegram.org/bot${BOT_TOKEN}/getUpdates" 2>/dev/null || echo "")
OWNER_CHAT_ID=$(echo "${UPDATES}" | python3 -c "
import sys, json
try:
    data = json.load(sys.stdin)
    results = data.get('result', [])
    if results:
        print(results[-1]['message']['chat']['id'])
except:
    pass
" 2>/dev/null || echo "")

if [[ -n "${OWNER_CHAT_ID}" ]]; then
    ok "Auto-detected Chat ID: ${OWNER_CHAT_ID}"
else
    warn "Could not auto-detect. Getting it manually:"
    echo
    echo -e "  Run this in another terminal:"
    echo -e "  ${CYAN}curl -s 'https://api.telegram.org/bot${BOT_TOKEN}/getUpdates' | python3 -c \"import sys,json; print(json.load(sys.stdin)['result'][-1]['message']['chat']['id'])\"${RESET}"
    echo
    ask "  Enter your Chat ID (a number, may be negative for groups):"
    read -rp "  > " OWNER_CHAT_ID
fi

# -----------------------------------------------------------------------------
hdr "STEP 8 -- Write .env and initialise database"
# -----------------------------------------------------------------------------

mkdir -p "${STORE_DIR}" "${LOG_DIR}"

cat > "${ENV_FILE}" << EOF
# Financial Assistant -- credentials
# Generated by install.sh on $(date)
# NEVER commit this file. It is already in .gitignore.

TG_API_ID=${TG_API_ID}
TG_API_HASH=${TG_API_HASH}
TG_SESSION=${TG_SESSION}

BOT_TOKEN=${BOT_TOKEN}
OWNER_CHAT_ID=${OWNER_CHAT_ID}
EOF

ok ".env written to ${ENV_FILE}"

# Init database
sqlite3 "${STORE_DIR}/messages.db" < "${FA_DIR}/db/schema.sql"
ok "Database initialised (${STORE_DIR}/messages.db)"

# -----------------------------------------------------------------------------
hdr "STEP 9 -- systemd service and crontab"
# -----------------------------------------------------------------------------

# Patch service file to use the correct path (in case repo is not at /root)
SERVICE_SRC="${FA_DIR}/systemd/fin-bridge.service"
SERVICE_TMP="/tmp/fin-bridge.service"
sed "s|/root/fin-assistant|${FA_DIR}|g" "${SERVICE_SRC}" > "${SERVICE_TMP}"

if [[ "${SKIP_SYSTEMD}" == false ]]; then
    sudo cp "${SERVICE_TMP}" /etc/systemd/system/fin-bridge.service
    sudo systemctl daemon-reload
    sudo systemctl enable fin-bridge.service
    ok "fin-bridge systemd service installed and enabled"
else
    warn "Skipped systemd setup (not available)"
    echo "  To start the bridge manually: python3 ${FA_DIR}/bridge/tg_bridge.py"
fi

# Patch and install crontab
CRON_TMP="/tmp/fa-crontab.txt"
sed "s|/root/fin-assistant|${FA_DIR}|g; s|/usr/bin/python3|$(which python3)|g" \
    "${FA_DIR}/systemd/crontab.txt" > "${CRON_TMP}"
crontab "${CRON_TMP}"
ok "Crontab installed ($(grep -c "python3" "${CRON_TMP}") scheduled jobs)"

# -----------------------------------------------------------------------------
hdr "STEP 10 -- Telegram authentication (Pyrogram)"
# -----------------------------------------------------------------------------

echo
echo -e "  Pyrogram needs to log in to your personal Telegram account."
echo -e "  ${YELLOW}This is your own account -- not the bot. Pyrogram uses the official${RESET}"
echo -e "  ${YELLOW}Telegram MTProto API (same as the app) to read channels you follow.${RESET}"
echo
echo -e "  You will be asked for:"
echo -e "    - Your phone number (international format, e.g. +919876543210)"
echo -e "    - A one-time code Telegram sends to your app"
echo -e "    - Your 2FA password ${BOLD}if you have one set${RESET}"
echo
echo -e "  Your session is saved to: ${CYAN}${TG_SESSION}.session${RESET}"
echo -e "  This file stays on your machine and is gitignored."
echo
ask "  Press Enter to start Telegram login..."
read -rp ""

cd "${FA_DIR}"
python3 bridge/fetch.py 1 10
cd "${REPO_DIR}"
ok "Pyrogram authentication complete"

# -----------------------------------------------------------------------------
hdr "STEP 11 -- Discover your Telegram channels"
# -----------------------------------------------------------------------------

echo
echo -e "  Scanning your Telegram account for all groups and channels..."
echo -e "  Nothing is stored yet -- use ${BOLD}--dry${RESET} to preview first."
echo

cd "${FA_DIR}"
python3 main.py discover --dry 2>/dev/null | tail -5
echo
if confirm "  Save all discovered channels to the database?"; then
    python3 main.py discover
    CHANNEL_COUNT=$(python3 main.py channels 2>/dev/null | grep "active /" | grep -oP '^\d+' || echo "?")
    ok "Channels saved"
    echo
    echo -e "  ${CYAN}Tip: to mute a channel:  python3 main.py disable <id>${RESET}"
    echo -e "  ${CYAN}     to list all:         python3 main.py channels${RESET}"
fi
cd "${REPO_DIR}"

# -----------------------------------------------------------------------------
hdr "STEP 12 -- Google Drive backups (optional)"
# -----------------------------------------------------------------------------

echo
echo -e "  Daily backups run automatically at 11:30 PM IST."
echo -e "  They back up your database, .env, and Telegram session."
echo -e "  Without Google Drive, backups are local only (${HOME}/fa-backups/)."
echo
echo -e "  To enable Google Drive upload you need a Google account."
echo -e "  rclone handles the OAuth -- no manual token creation needed."
echo

if confirm "  Set up Google Drive backup now?"; then
    bash "${FA_DIR}/scripts/setup-gdrive.sh"
else
    warn "Skipped -- local backups only"
    echo -e "  ${CYAN}Set it up later: bash ${FA_DIR}/scripts/setup-gdrive.sh${RESET}"
fi

# -----------------------------------------------------------------------------
hdr "STEP 13 -- Start services"
# -----------------------------------------------------------------------------

if [[ "${SKIP_SYSTEMD}" == false ]]; then
    sudo systemctl start fin-bridge
    sleep 3
    if systemctl is-active --quiet fin-bridge; then
        ok "fin-bridge is running"
    else
        err "fin-bridge failed to start -- check: journalctl -u fin-bridge -n 30"
    fi
else
    echo -e "  ${YELLOW}Start the bridge manually:${RESET}"
    echo -e "  ${CYAN}nohup python3 ${FA_DIR}/bridge/tg_bridge.py > ${LOG_DIR}/bridge.log 2>&1 &${RESET}"
fi

# -----------------------------------------------------------------------------
hdr "STEP 14 -- Health check"
# -----------------------------------------------------------------------------

echo
cd "${FA_DIR}"
python3 scripts/healthcheck.py --quiet 2>/dev/null
cd "${REPO_DIR}"

# -----------------------------------------------------------------------------
hdr "STEP 15 -- Test report"
# -----------------------------------------------------------------------------

echo
if confirm "  Send a test pre-open briefing to your Telegram bot now?"; then
    cd "${FA_DIR}"
    python3 main.py preopen --dry-run 2>/dev/null | head -20
    echo
    if confirm "  Send to Telegram (not dry-run)?"; then
        python3 main.py preopen
        ok "Report sent -- check your Telegram bot"
    fi
    cd "${REPO_DIR}"
fi

# -----------------------------------------------------------------------------
hdr "ALL DONE"
# -----------------------------------------------------------------------------

echo
echo -e "  ${GREEN}${BOLD}Installation complete.${RESET}"
echo
echo -e "  ${BOLD}Useful commands:${RESET}"
echo -e "  ${CYAN}  python3 ${FA_DIR}/main.py channels       ${RESET}-- list monitored channels"
echo -e "  ${CYAN}  python3 ${FA_DIR}/main.py hourly --dry-run${RESET}-- test hourly scan"
echo -e "  ${CYAN}  python3 ${FA_DIR}/main.py fetch 7        ${RESET}-- backfill 7 days of history"
echo -e "  ${CYAN}  python3 ${FA_DIR}/scripts/healthcheck.py ${RESET}-- run health check"
echo -e "  ${CYAN}  bash    ${FA_DIR}/scripts/backup.sh     ${RESET}-- run backup now"
echo -e "  ${CYAN}  bash    ${FA_DIR}/scripts/setup-gdrive.sh${RESET}-- connect Google Drive"
echo
echo -e "  ${BOLD}Service management:${RESET}"
echo -e "  ${CYAN}  systemctl status  fin-bridge${RESET}"
echo -e "  ${CYAN}  systemctl restart fin-bridge${RESET}"
echo -e "  ${CYAN}  tail -f ${LOG_DIR}/bridge.log${RESET}"
echo -e "  ${CYAN}  tail -f ${LOG_DIR}/cron.log${RESET}"
echo
echo -e "  ${BOLD}NanoClaw (AI agents):${RESET}"
echo -e "  ${CYAN}  cd ${REPO_DIR} && claude${RESET}  then type ${BOLD}/setup${RESET}"
echo
echo -e "  ${YELLOW}[WARN]  DISCLAIMER: This is a personal research tool. Not financial advice.${RESET}"
echo
