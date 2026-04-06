#!/usr/bin/env bash
# uninstall.sh — Cleanly removes History Search native host from Mac/Linux
#
# What this removes:
# - Native messaging manifest from Chrome/Chromium
# - Launcher script
# - Virtual environment
# - All stored data (vectors, models, logs, settings)
#
# What this does NOT remove:
# - The project source code itself
# - The Chrome extension (remove that from chrome://extensions manually)
#
# Usage:
#   chmod +x uninstall.sh
#   ./uninstall.sh

set -euo pipefail

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

log_info()  { echo -e "${BLUE}[INFO]${NC}  $*"; }
log_ok()    { echo -e "${GREEN}[OK]${NC}    $*"; }
log_warn()  { echo -e "${YELLOW}[WARN]${NC}  $*"; }
log_error() { echo -e "${RED}[ERROR]${NC} $*"; }

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
HOST_DIR="${PROJECT_ROOT}/native-host"
VENV_DIR="${HOST_DIR}/.venv"
LAUNCHER="${HOST_DIR}/launch_host.sh"

if [[ "$OSTYPE" == "darwin"* ]]; then
  CHROME_NM_DIR="${HOME}/Library/Application Support/Google/Chrome/NativeMessagingHosts"
  CHROMIUM_NM_DIR="${HOME}/Library/Application Support/Chromium/NativeMessagingHosts"
  DATA_DIR="${HOME}/Library/Application Support/browser-history-search"
else
  CHROME_NM_DIR="${HOME}/.config/google-chrome/NativeMessagingHosts"
  CHROMIUM_NM_DIR="${HOME}/.config/chromium/NativeMessagingHosts"
  DATA_DIR="${HOME}/.local/share/browser-history-search"
fi

MANIFEST_CHROME="${CHROME_NM_DIR}/com.historysearch.host.json"
MANIFEST_CHROMIUM="${CHROMIUM_NM_DIR}/com.historysearch.host.json"

# ---------------------------------------------------------------------------
# Confirm
# ---------------------------------------------------------------------------
echo ""
log_warn "This will remove the History Search native host and ALL stored data."
log_warn "Your browsing history vectors, models, and logs will be deleted."
echo ""
read -rp "Are you sure? (yes/no): " CONFIRM

if [[ "${CONFIRM}" != "yes" ]]; then
  log_info "Uninstall cancelled."
  exit 0
fi

# ---------------------------------------------------------------------------
# Remove native messaging manifests
# ---------------------------------------------------------------------------
log_info "Removing native messaging manifests..."

if [[ -f "${MANIFEST_CHROME}" ]]; then
  rm -f "${MANIFEST_CHROME}"
  log_ok "Removed: ${MANIFEST_CHROME}"
else
  log_warn "Chrome manifest not found — skipping"
fi

if [[ -f "${MANIFEST_CHROMIUM}" ]]; then
  rm -f "${MANIFEST_CHROMIUM}"
  log_ok "Removed: ${MANIFEST_CHROMIUM}"
fi

# ---------------------------------------------------------------------------
# Remove launcher
# ---------------------------------------------------------------------------
if [[ -f "${LAUNCHER}" ]]; then
  rm -f "${LAUNCHER}"
  log_ok "Removed launcher: ${LAUNCHER}"
fi

# ---------------------------------------------------------------------------
# Remove virtual environment
# ---------------------------------------------------------------------------
if [[ -d "${VENV_DIR}" ]]; then
  rm -rf "${VENV_DIR}"
  log_ok "Removed virtual environment: ${VENV_DIR}"
else
  log_warn "Virtual environment not found — skipping"
fi

# ---------------------------------------------------------------------------
# Remove all stored data
# ---------------------------------------------------------------------------
if [[ -d "${DATA_DIR}" ]]; then
  rm -rf "${DATA_DIR}"
  log_ok "Removed all stored data: ${DATA_DIR}"
else
  log_warn "Data directory not found — skipping"
fi

# ---------------------------------------------------------------------------
# Done
# ---------------------------------------------------------------------------
echo ""
log_ok "History Search has been uninstalled."
log_info "To finish: go to chrome://extensions and remove the extension manually."
echo ""