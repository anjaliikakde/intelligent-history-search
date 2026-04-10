#!/usr/bin/env bash
# install.sh — Mac/Linux setup script for History Search native host
#
# What this does:
# 1. Creates a Python virtual environment
# 2. Installs all dependencies
# 3. Downloads the embedding model locally
# 4. Registers the native messaging host with Chrome, Chromium, AND Edge
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
HOST_SCRIPT="${HOST_DIR}/host.py"
MANIFEST_NAME="com.historysearch.host.json"

# Native messaging directories per browser per platform
if [[ "$OSTYPE" == "darwin"* ]]; then
  CHROME_NM_DIR="${HOME}/Library/Application Support/Google/Chrome/NativeMessagingHosts"
  CHROMIUM_NM_DIR="${HOME}/Library/Application Support/Chromium/NativeMessagingHosts"
  EDGE_NM_DIR="${HOME}/Library/Application Support/Microsoft Edge/NativeMessagingHosts"
else
  # Linux
  CHROME_NM_DIR="${HOME}/.config/google-chrome/NativeMessagingHosts"
  CHROMIUM_NM_DIR="${HOME}/.config/chromium/NativeMessagingHosts"
  EDGE_NM_DIR="${HOME}/.config/microsoft-edge/NativeMessagingHosts"
fi

# ---------------------------------------------------------------------------
# Check prerequisites
# ---------------------------------------------------------------------------
log_info "Checking prerequisites..."

if ! command -v python3 &>/dev/null; then
  log_error "Python 3 not found. Install Python 3.9+ and try again."
  exit 1
fi

PYTHON_VERSION=$(python3 -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
ACTUAL_MINOR=$(python3 -c "import sys; print(sys.version_info.minor)")

if [[ "$ACTUAL_MINOR" -lt 9 ]]; then
  log_error "Python 3.9+ required. Found Python ${PYTHON_VERSION}."
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

source "${VENV_DIR}/bin/activate"

# ---------------------------------------------------------------------------
# Install dependencies
# ---------------------------------------------------------------------------
log_info "Installing Python dependencies..."
python3 -m pip install --quiet --upgrade pip
pip install --quiet -r "${HOST_DIR}/requirements.txt"
log_ok "Dependencies installed"

# ---------------------------------------------------------------------------
# Download embedding model (one-time, offline after this)
# ---------------------------------------------------------------------------
log_info "Downloading embedding model (one-time, ~80MB)..."

cd "${HOST_DIR}"
python3 -c "from embedder import Embedder; ok = Embedder.download_model(); exit(0 if ok else 1)"
log_ok "Embedding model downloaded"

# ---------------------------------------------------------------------------
# Get extension ID from user
# ---------------------------------------------------------------------------
echo ""
log_info "To complete setup, you need your Extension ID."
log_info "Steps:"
log_info "  1. Open Chrome → chrome://extensions  OR  Edge → edge://extensions"
log_info "  2. Enable 'Developer mode' (top right toggle)"
log_info "  3. Click 'Load unpacked' → select: ${PROJECT_ROOT}/extension"
log_info "  4. Copy the Extension ID shown under your extension name"
echo ""
read -rp "Paste your Extension ID here: " EXTENSION_ID

if [[ -z "${EXTENSION_ID}" ]]; then
  log_error "Extension ID cannot be empty."
  exit 1
fi

# Basic format check — Chrome/Edge IDs are 32 lowercase letters
if ! echo "${EXTENSION_ID}" | grep -qE '^[a-z]{32}$'; then
  log_warn "Extension ID format looks unusual (expected 32 lowercase letters)."
  log_warn "Proceeding anyway — double-check if extension doesn't connect."
fi

# ---------------------------------------------------------------------------
# Write launcher script
# Native messaging "path" must be an executable — not a .py file directly.
# This launcher invokes venv python with host.py.
# ---------------------------------------------------------------------------
log_info "Writing launcher script..."

PYTHON_PATH="${VENV_DIR}/bin/python3"
LAUNCHER="${HOST_DIR}/launch_host.sh"

cat > "${LAUNCHER}" <<LAUNCHER_SCRIPT
#!/usr/bin/env bash
exec "${PYTHON_PATH}" "${HOST_SCRIPT}" "\$@"
LAUNCHER_SCRIPT

chmod +x "${LAUNCHER}"
log_ok "Launcher written: ${LAUNCHER}"

# ---------------------------------------------------------------------------
# Build manifest JSON content
# Same content for all browsers — only the destination directory differs
# ---------------------------------------------------------------------------
MANIFEST_CONTENT=$(cat <<JSON
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
)

# ---------------------------------------------------------------------------
# Helper — install manifest for one browser
# Skips silently if that browser is not installed
# ---------------------------------------------------------------------------
install_manifest() {
  local browser_name="$1"
  local nm_dir="$2"

  # Check if browser's parent config directory exists
  # If not — browser is not installed, skip
  if [[ ! -d "$(dirname "${nm_dir}")" ]]; then
    log_warn "${browser_name} not found on this system — skipping"
    return
  fi

  mkdir -p "${nm_dir}"
  echo "${MANIFEST_CONTENT}" > "${nm_dir}/${MANIFEST_NAME}"
  log_ok "Registered for ${browser_name}: ${nm_dir}/${MANIFEST_NAME}"
}

# ---------------------------------------------------------------------------
# Register for all supported browsers
# ---------------------------------------------------------------------------
log_info "Registering native messaging host..."

install_manifest "Chrome"   "${CHROME_NM_DIR}"
install_manifest "Chromium" "${CHROMIUM_NM_DIR}"
install_manifest "Edge"     "${EDGE_NM_DIR}"

# ---------------------------------------------------------------------------
# Done
# ---------------------------------------------------------------------------
echo ""
log_ok "======================================"
log_ok "  History Search installed!"
log_ok "  Supported: Chrome, Chromium, Edge"
log_ok "======================================"
echo ""
log_info "Next steps:"
log_info "  1. Reload extension: chrome://extensions or edge://extensions"
log_info "     (click the refresh icon on your extension)"
log_info "  2. Click the extension icon in the browser toolbar"
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