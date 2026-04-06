/**
 * popup.js — Popup UI logic.
 *
 * Responsibilities:
 * - Handle search input and display results
 * - Manage settings panel (pause, expiry, clear)
 * - Communicate with background.js via chrome.runtime.sendMessage
 * - Never talk to native host directly — always through background.js
 *
 * Security rules:
 * - Never use innerHTML — always textContent or createElement
 * - Sanitize all values before rendering
 */

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const MsgType = {
  SEARCH:   "search",
  DELETE:   "delete",
  CLEAR:    "clear",
  PING:     "ping",
  SETTINGS: "settings",
  SUCCESS:  "success",
  ERROR:    "error",
  RESULTS:  "results",
  PONG:     "pong",
};

// ---------------------------------------------------------------------------
// DOM refs
// ---------------------------------------------------------------------------

const searchInput      = document.getElementById("search-input");
const btnSearch        = document.getElementById("btn-search");
const btnSettings      = document.getElementById("btn-settings");
const statusBar        = document.getElementById("status-bar");
const resultsList      = document.getElementById("results");
const emptyState       = document.getElementById("empty-state");
const settingsPanel    = document.getElementById("settings-panel");
const togglePause      = document.getElementById("toggle-pause");
const selectExpiry     = document.getElementById("select-expiry");
const btnClear         = document.getElementById("btn-clear");
const hostStatusBadge  = document.getElementById("host-status-badge");

// ---------------------------------------------------------------------------
// State
// ---------------------------------------------------------------------------

let isSettingsOpen = false;
let isSearching    = false;

// ---------------------------------------------------------------------------
// Init
// ---------------------------------------------------------------------------

async function init() {
  await loadSettings();
  pingHost();
  searchInput.focus();
}

// ---------------------------------------------------------------------------
// Settings — load from chrome.storage.local
// ---------------------------------------------------------------------------

async function loadSettings() {
  const { settings = {} } = await chrome.storage.local.get("settings");

  if (settings.pause_tracking !== undefined) {
    togglePause.checked = settings.pause_tracking;
    if (settings.pause_tracking) {
      showStatus("Tracking is paused.", false);
    }
  }

  if (settings.expiry_days !== undefined) {
    selectExpiry.value = String(settings.expiry_days);
  }
}

// ---------------------------------------------------------------------------
// Ping host — check if native host is alive
// ---------------------------------------------------------------------------

async function pingHost() {
  try {
    const response = await sendToBackground({ type: MsgType.PING });
    if (response?.type === MsgType.PONG && response.health?.embedder) {
      setBadge(hostStatusBadge, "Ready", "ok");
    } else {
      setBadge(hostStatusBadge, "Not ready", "error");
    }
  } catch {
    setBadge(hostStatusBadge, "Offline", "error");
  }
}

// ---------------------------------------------------------------------------
// Search
// ---------------------------------------------------------------------------

async function doSearch() {
  const query = searchInput.value.trim();
  if (!query || isSearching) return;

  isSearching = true;
  clearResults();
  hideEmpty();
  hideStatus();
  btnSearch.disabled = true;
  btnSearch.textContent = "…";

  try {
    const response = await sendToBackground({
      type:  MsgType.SEARCH,
      query,
      limit: 10,
    });

    if (response?.type === MsgType.ERROR) {
      showStatus(response.error || "Search failed.", true);
      return;
    }

    const results = response?.results || [];
    if (results.length === 0) {
      showEmpty();
    } else {
      renderResults(results);
    }

  } catch (err) {
    showStatus(`Error: ${err.message}`, true);
  } finally {
    isSearching    = false;
    btnSearch.disabled = false;
    btnSearch.textContent = "🔍";
  }
}

// ---------------------------------------------------------------------------
// Render results — NO innerHTML, all textContent
// ---------------------------------------------------------------------------

function renderResults(results) {
  results.forEach((r) => {
    const li = document.createElement("li");
    li.className = "result-item";
    li.setAttribute("role", "listitem");

    // Body
    const body = document.createElement("div");
    body.className = "result-item__body";

    const title = document.createElement("div");
    title.className = "result-item__title";
    title.textContent = r.title || "Untitled";

    const url = document.createElement("div");
    url.className = "result-item__url";
    url.textContent = r.url;

    body.appendChild(title);
    body.appendChild(url);

    // Meta (score + delete)
    const meta = document.createElement("div");
    meta.className = "result-item__meta";

    const score = document.createElement("span");
    score.className = "result-item__score";
    score.textContent = `${Math.round(r.score * 100)}%`;

    const deleteBtn = document.createElement("button");
    deleteBtn.className = "result-item__delete";
    deleteBtn.textContent = "✕";
    deleteBtn.title = "Remove from history";
    deleteBtn.setAttribute("aria-label", "Delete this result");

    meta.appendChild(score);
    meta.appendChild(deleteBtn);

    li.appendChild(body);
    li.appendChild(meta);

    // Click result → open URL in new tab
    body.addEventListener("click", () => {
      chrome.tabs.create({ url: r.url, active: true });
    });

    // Click delete → remove entry
    deleteBtn.addEventListener("click", async (e) => {
      e.stopPropagation();
      await deleteEntry(r.url, li);
    });

    resultsList.appendChild(li);
  });
}

// ---------------------------------------------------------------------------
// Delete single entry
// ---------------------------------------------------------------------------

async function deleteEntry(url, listItem) {
  try {
    const response = await sendToBackground({
      type: MsgType.DELETE,
      url,
    });

    if (response?.type === MsgType.SUCCESS) {
      listItem.remove();
      if (resultsList.children.length === 0) {
        showEmpty();
      }
    } else {
      showStatus("Delete failed.", true);
    }
  } catch (err) {
    showStatus(`Delete error: ${err.message}`, true);
  }
}

// ---------------------------------------------------------------------------
// Settings panel
// ---------------------------------------------------------------------------

function toggleSettings() {
  isSettingsOpen = !isSettingsOpen;
  settingsPanel.hidden = !isSettingsOpen;
  resultsList.hidden   = isSettingsOpen;
  emptyState.hidden    = true;

  if (isSettingsOpen) {
    btnSettings.textContent = "✕";
    pingHost();
  } else {
    btnSettings.textContent = "⚙";
  }
}

// Pause tracking toggle
togglePause.addEventListener("change", async () => {
  const paused = togglePause.checked;
  await sendToBackground({
    type:    MsgType.SETTINGS,
    payload: { pause_tracking: paused },
  });

  if (paused) {
    showStatus("Tracking paused.", false);
  } else {
    hideStatus();
  }
});

// Expiry select
selectExpiry.addEventListener("change", async () => {
  const days = parseInt(selectExpiry.value, 10);
  await sendToBackground({
    type:    MsgType.SETTINGS,
    payload: { expiry_days: days },
  });
});

// Clear all
btnClear.addEventListener("click", async () => {
  const confirmed = window.confirm(
    "This will permanently delete all your stored history. Continue?"
  );
  if (!confirmed) return;

  btnClear.disabled     = true;
  btnClear.textContent  = "Clearing…";

  try {
    const response = await sendToBackground({ type: MsgType.CLEAR });
    if (response?.type === MsgType.SUCCESS) {
      showStatus("All history cleared.", false);
      clearResults();
    } else {
      showStatus("Clear failed.", true);
    }
  } catch (err) {
    showStatus(`Error: ${err.message}`, true);
  } finally {
    btnClear.disabled    = false;
    btnClear.textContent = "Clear";
  }
});

// ---------------------------------------------------------------------------
// Communication with background.js
// ---------------------------------------------------------------------------

function sendToBackground(message) {
  return new Promise((resolve, reject) => {
    chrome.runtime.sendMessage(message, (response) => {
      if (chrome.runtime.lastError) {
        reject(new Error(chrome.runtime.lastError.message));
        return;
      }
      resolve(response);
    });
  });
}

// ---------------------------------------------------------------------------
// UI helpers — all use textContent, never innerHTML
// ---------------------------------------------------------------------------

function clearResults() {
  while (resultsList.firstChild) {
    resultsList.removeChild(resultsList.firstChild);
  }
  resultsList.hidden = false;
}

function showEmpty() {
  emptyState.hidden = false;
}

function hideEmpty() {
  emptyState.hidden = true;
}

function showStatus(message, isError = false) {
  statusBar.textContent = message;
  statusBar.className   = isError ? "status-bar status-bar--error" : "status-bar";
  statusBar.hidden      = false;
}

function hideStatus() {
  statusBar.hidden = true;
}

function setBadge(el, text, type) {
  el.textContent = text;
  el.className   = type === "ok" ? "badge badge--ok" : "badge badge--error";
}

// ---------------------------------------------------------------------------
// Event listeners
// ---------------------------------------------------------------------------

btnSearch.addEventListener("click", doSearch);

searchInput.addEventListener("keydown", (e) => {
  if (e.key === "Enter") doSearch();
});

btnSettings.addEventListener("click", toggleSettings);

// ---------------------------------------------------------------------------
// Boot
// ---------------------------------------------------------------------------

init();