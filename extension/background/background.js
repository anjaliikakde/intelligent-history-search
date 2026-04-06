/**
 * background.js — Extension service worker.
 *
 * Responsibilities:
 * - Listen for tab navigation events
 * - Request page metadata from content.js
 * - Send page data to native host for embedding + storage
 * - Handle search requests from popup.js
 * - Manage native messaging port lifecycle
 *
 * MV3 note: Service workers are ephemeral — they spin up on events
 * and shut down when idle. We reconnect the native port per-message,
 * not once globally, to avoid port-closed errors.
 */

// ---------------------------------------------------------------------------
// Constants — keep in sync with config.py MsgType
// ---------------------------------------------------------------------------

const HOST_NAME = "com.historysearch.host";

const MsgType = {
  INGEST:   "ingest",
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
// Native Messaging — send one message, get one response
// We open a port per call because MV3 service workers can be killed
// between calls, invalidating a persistent port.
// ---------------------------------------------------------------------------

function sendToHost(message) {
  return new Promise((resolve, reject) => {
    let port;

    try {
      port = chrome.runtime.connectNative(HOST_NAME);
    } catch (err) {
      reject(new Error(`Failed to connect to native host: ${err.message}`));
      return;
    }

    // Timeout — if host doesn't respond within 10s, reject
    const timer = setTimeout(() => {
      port.disconnect();
      reject(new Error("Native host timed out after 10s"));
    }, 10_000);

    port.onMessage.addListener((response) => {
      clearTimeout(timer);
      port.disconnect();
      resolve(response);
    });

    port.onDisconnect.addListener(() => {
      clearTimeout(timer);
      const err = chrome.runtime.lastError;
      if (err) {
        reject(new Error(`Native host disconnected: ${err.message}`));
      }
    });

    port.postMessage(message);
  });
}

// ---------------------------------------------------------------------------
// Tab navigation listener
// Fires when a tab finishes loading a new page
// ---------------------------------------------------------------------------

chrome.tabs.onUpdated.addListener(async (tabId, changeInfo, tab) => {
  // Only process fully loaded pages
  if (changeInfo.status !== "complete") return;

  // Skip incognito tabs — privacy guarantee
  if (tab.incognito) return;

  // Skip missing or invalid URLs
  if (!tab.url || !tab.url.startsWith("http")) return;

  // Skip extension pages
  if (tab.url.startsWith("chrome-extension://")) return;

  try {
    // Ask content.js for page metadata
    const metadata = await requestMetadata(tabId);

    await sendToHost({
      type:       MsgType.INGEST,
      url:        tab.url,
      title:      tab.title || "",
      content:    metadata?.content || "",
      incognito:  tab.incognito,
      visited_at: Date.now() / 1000,  // unix timestamp in seconds
    });

  } catch (err) {
    // Non-fatal — log and continue
    console.warn("[HistorySearch] Ingest failed:", err.message);
  }
});

// ---------------------------------------------------------------------------
// Request metadata from content.js via message passing
// ---------------------------------------------------------------------------

function requestMetadata(tabId) {
  return new Promise((resolve) => {
    // Timeout if content script doesn't respond (e.g. restricted page)
    const timer = setTimeout(() => resolve(null), 3_000);

    chrome.tabs.sendMessage(
      tabId,
      { type: "GET_METADATA" },
      (response) => {
        clearTimeout(timer);
        if (chrome.runtime.lastError) {
          // Content script not injected on this page — normal for some URLs
          resolve(null);
          return;
        }
        resolve(response);
      }
    );
  });
}

// ---------------------------------------------------------------------------
// Message handler — popup.js sends messages here
// ---------------------------------------------------------------------------

chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  // Only accept messages from our own extension
  if (sender.id !== chrome.runtime.id) return;

  handleMessage(message)
    .then(sendResponse)
    .catch((err) => {
      sendResponse({ type: MsgType.ERROR, error: err.message });
    });

  // Return true to keep the message channel open for async response
  return true;
});

// ---------------------------------------------------------------------------
// Route messages from popup to native host
// ---------------------------------------------------------------------------

async function handleMessage(message) {
  switch (message.type) {

    case MsgType.SEARCH: {
      const response = await sendToHost({
        type:  MsgType.SEARCH,
        query: message.query,
        limit: message.limit || 10,
      });
      return response;
    }

    case MsgType.DELETE: {
      const response = await sendToHost({
        type: MsgType.DELETE,
        url:  message.url,
      });
      return response;
    }

    case MsgType.CLEAR: {
      const response = await sendToHost({ type: MsgType.CLEAR });
      return response;
    }

    case MsgType.PING: {
      const response = await sendToHost({ type: MsgType.PING });
      return response;
    }

    case MsgType.SETTINGS: {
      // Persist in chrome.storage.local too — for popup to read without pinging host
      if (message.payload) {
        await chrome.storage.local.set({ settings: message.payload });
      }
      const response = await sendToHost({
        type: MsgType.SETTINGS,
        ...message.payload,
      });
      return response;
    }

    default:
      return { type: MsgType.ERROR, error: `Unknown message type: ${message.type}` };
  }
}