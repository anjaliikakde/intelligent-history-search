#!/usr/bin/env bash
# install.sh — Mac/Linux setup script for History Search native host
#
# What this does:
# 1. Creates a Python virtual environment
# 2. Installs all dependencies
# 3. Downloads the embedding model locally
# 4. Registers the native messaging host with Chrome
# 5. Prompts user to enter their extension ID
#
# Usage:
#   chmod +x install.sh
#   ./install.sh

set -euo pipefail

# ---------------------------------------------------------------------------
# Colors
# ---------------------------------------------------------------------------
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # no color

log_info()    { echo -e "${BLUE}[INFO]${NC}  $*"; }
log_ok()      { echo -e "${GREEN}[OK]${NC}    $*"; }
log_warn()    { echo -e "${YELLOW}[WARN]${NC}  $*"; }
log_error()   { echo -e "${RED}[ERROR]${NC} $*"; }

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
HOST_DIR="${PROJECT_ROOT}/native-host"
MANIFEST_SRC="${PROJECT_ROOT}/native-host-manifest/com.historysearch.host.json"
VENV_DIR="${HOST_DIR}/.venv"
HOST_SCRIPT="${HOST_DIR}/host.py"

# Chrome native messaging host directories per platform
if [[ "$OSTYPE" == "darwin"* ]]; then
  CHROME_NM_DIR="${HOME}/Library/Application Support/Google/Chrome/NativeMessagingHosts"
  CHROMIUM_NM_DIR="${HOME}/Library/Application Support/Chromium/NativeMessagingHosts"
else
  CHROME_NM_DIR="${HOME}/.config/google-chrome/NativeMessagingHosts"
  CHROMIUM_NM_DIR="${HOME}/.config/chromium/NativeMessagingHosts"
fi

MANIFEST_DEST="${CHROME_NM_DIR}/com.historysearch.host.json"

# ---------------------------------------------------------------------------
# Check prerequisites
# ---------------------------------------------------------------------------
log_info "Checking prerequisites..."

if ! command -v python3 &>/dev/null; then
  log_error "Python 3 not found. Install Python 3.9+ and try again."
  exit 1
fi

PYTHON_VERSION=$(python3 -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
log_info "Python version: ${PYTHON_VERSION}"

REQUIRED_MINOR=9
ACTUAL_MINOR=$(python3 -c "import sys; print(sys.version_info.minor)")
if [[ "$ACTUAL_MINOR" -lt "$REQUIRED_MINOR" ]]; then
  log_error "Python 3.${REQUIRED_MINOR}+ required. Found Python ${PYTHON_VERSION}."
  exit 1
fi

log_ok "Python ${PYTHON_VERSION} — OK"

# ---------------------------------------------------------------------------
# Create virtual environment
# ---------------------------------------------------------------------------
log_info "Creating virtual environment at ${VENV_DIR}..."

if [[ -d "${VENV_DIR}" ]]; then
  log_warn "Virtual environment already exists — skipping creation"
else
  python3 -m venv "${VENV_DIR}"
  log_ok "Virtual environment created"
fi

# Activate venv
source "${VENV_DIR}/bin/activate"

# ---------------------------------------------------------------------------
# Install dependencies
# ---------------------------------------------------------------------------
log_info "Installing Python dependencies..."
pip install --quiet --upgrade pip
pip install --quiet -r "${HOST_DIR}/requirements.txt"
log_ok "Dependencies installed"

# ---------------------------------------------------------------------------
# Download embedding model (one-time, offline after this)
# ---------------------------------------------------------------------------
log_info "Downloading embedding model (one-time, ~80MB)..."
python3 - <<'PYTHON'
import sys
sys.path.insert(0, sys.argv[0].rsplit('/', 1)[0] if '/' in sys.argv[0] else '.')
import os, sys
# Add host dir to path
host_dir = os.path.join(os.path.dirname(os.path.abspath(__file__ if '__file__' in dir() else '.')))
PYTHON

cd "${HOST_DIR}"
python3 -c "from embedder import Embedder; ok = Embedder.download_model(); exit(0 if ok else 1)"
log_ok "Embedding model downloaded"

# ---------------------------------------------------------------------------
# Get extension ID from user
# ---------------------------------------------------------------------------
echo ""
log_info "To complete setup, you need your Chrome Extension ID."
log_info "Steps:"
log_info "  1. Open Chrome → chrome://extensions"
log_info "  2. Enable 'Developer mode' (top right toggle)"
log_info "  3. Click 'Load unpacked' → select: ${PROJECT_ROOT}/extension"
log_info "  4. Copy the Extension ID shown under your extension name"
echo ""
read -rp "Paste your Extension ID here: " EXTENSION_ID

if [[ -z "${EXTENSION_ID}" ]]; then
  log_error "Extension ID cannot be empty."
  exit 1
fi

# Basic format check — Chrome IDs are 32 lowercase letters
if ! echo "${EXTENSION_ID}" | grep -qE '^[a-z]{32}$'; then
  log_warn "Extension ID format looks unusual (expected 32 lowercase letters)."
  log_warn "Proceeding anyway — double-check if extension doesn't connect."
fi

# ---------------------------------------------------------------------------
# Write native messaging manifest
# ---------------------------------------------------------------------------
log_info "Installing native messaging manifest..."

mkdir -p "${CHROME_NM_DIR}"

# Get absolute path to host.py with venv python
PYTHON_PATH="${VENV_DIR}/bin/python3"

# Write manifest with real paths and extension ID
cat > "${MANIFEST_DEST}" <<JSON
{
  "name": "com.historysearch.host",
  "description": "History Search native messaging host",
  "path": "${PYTHON_PATH}",
  "type": "stdio",
  "allowed_origins": [
    "chrome-extension://${EXTENSION_ID}/"
  ]
}
JSON

# Note: Chrome native messaging "path" must point to the executable,
# and the executable must have the script path as first argument.
# For Python scripts we use a wrapper approach — write a small launcher.

LAUNCHER="${HOST_DIR}/launch_host.sh"
cat > "${LAUNCHER}" <<LAUNCHER
#!/usr/bin/env bash
exec "${PYTHON_PATH}" "${HOST_SCRIPT}" "\$@"
LAUNCHER
chmod +x "${LAUNCHER}"

# Update manifest path to point to launcher
cat > "${MANIFEST_DEST}" <<JSON
{
  "name": "com.historysearch.host",
  "description": "History Search native messaging host",
  "path": "${LAUNCHER}",
  "type": "stdio",
  "allowed_origins": [
    "chrome-extension://${EXTENSION_ID}/"
  ]
}
JSON

log_ok "Manifest installed at: ${MANIFEST_DEST}"

# Also install for Chromium if it exists
if [[ -d "$(dirname "${CHROMIUM_NM_DIR}")" ]]; then
  mkdir -p "${CHROMIUM_NM_DIR}"
  cp "${MANIFEST_DEST}" "${CHROMIUM_NM_DIR}/com.historysearch.host.json"
  log_ok "Manifest also installed for Chromium"
fi

# ---------------------------------------------------------------------------
# Done
# ---------------------------------------------------------------------------
echo ""
log_ok "======================================"
log_ok "  History Search installed!"
log_ok "======================================"
echo ""
log_info "Next steps:"
log_info "  1. Reload your extension in chrome://extensions (click the refresh icon)"
log_info "  2. Click the extension icon in Chrome toolbar"
log_info "  3. Visit some pages — they will be indexed automatically"
log_info "  4. Search your history semantically from the popup"
echo ""
log_info "Logs are at:"
if [[ "$OSTYPE" == "darwin"* ]]; then
  log_info "  ~/Library/Application Support/browser-history-search/logs/host.log"
else
  log_info "  ~/.local/share/browser-history-search/logs/host.log"
fi
echo ""