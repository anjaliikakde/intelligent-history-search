/**
 * content.js — Injected into every http/https page.
 *
 * Responsibilities:
 * - Extract page title, meta description, and visible body text
 * - Respond to GET_METADATA requests from background.js
 *
 * Rules:
 * - Never send data anywhere directly — only respond to background.js
 * - Extract minimal content — not the full DOM
 * - Never access forms, passwords, or input values
 * - Max 500 chars of body text — config.py MAX_CONTENT_LENGTH
 */

const MAX_CONTENT_LENGTH = 500;

// ---------------------------------------------------------------------------
// Metadata extractor
// ---------------------------------------------------------------------------

function extractMetadata() {
  const title = document.title?.trim() || "";

  // Meta description — most reliable content summary
  const metaDesc = (
    document.querySelector('meta[name="description"]')?.content ||
    document.querySelector('meta[property="og:description"]')?.content ||
    ""
  ).trim();

  // Body text — first visible paragraph text, stripped of tags
  const bodyText = extractBodyText();

  // Combine: meta description first (more reliable), then body text
  const combined = [metaDesc, bodyText]
    .filter(Boolean)
    .join(" ")
    .slice(0, MAX_CONTENT_LENGTH)
    .trim();

  return {
    title,
    content: combined,
  };
}

// ---------------------------------------------------------------------------
// Body text extractor — minimal, no full DOM serialization
// ---------------------------------------------------------------------------

function extractBodyText() {
  // Prefer article/main content areas over generic body
  const contentSelectors = [
    "article",
    "main",
    '[role="main"]',
    ".content",
    "#content",
    "body",
  ];

  for (const selector of contentSelectors) {
    const el = document.querySelector(selector);
    if (!el) continue;

    // Get text content — browser strips tags automatically
    const text = el.innerText || el.textContent || "";

    // Clean: collapse whitespace, strip control chars
    const cleaned = text
      .replace(/[\x00-\x1f\x7f]/g, " ")
      .replace(/\s+/g, " ")
      .trim();

    if (cleaned.length > 50) {
      return cleaned.slice(0, MAX_CONTENT_LENGTH);
    }
  }

  return "";
}

// ---------------------------------------------------------------------------
// Message listener — respond to background.js requests
// ---------------------------------------------------------------------------

chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  // Only accept messages from our own extension background
  if (sender.id !== chrome.runtime.id) return;

  if (message.type === "GET_METADATA") {
    try {
      sendResponse(extractMetadata());
    } catch (err) {
      sendResponse({ title: "", content: "" });
    }
  }
});