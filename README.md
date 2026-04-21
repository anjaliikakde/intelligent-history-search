# 🔍 Semantic Browser History Search

> Search your browser history by **meaning**, not keywords — fully local, fully private.

[![Python](https://img.shields.io/badge/Python-3.10+-3776AB?logo=python&logoColor=white)](https://python.org)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![Manifest V3](https://img.shields.io/badge/Manifest-V3-4285F4?logo=googlechrome&logoColor=white)](https://developer.chrome.com/docs/extensions/mv3/)
[![Qdrant Edge](https://img.shields.io/badge/Qdrant-Edge-DC143C?logo=qdrant&logoColor=white)](https://qdrant.tech/documentation/edge/)
[![FastEmbed](https://img.shields.io/badge/FastEmbed-BAAI%2Fbge--small-blueviolet)](https://github.com/qdrant/fastembed)

---

Ever visited a website, forgot its name, and spent 10 minutes scrolling through your history? Traditional browser search only matches exact text — it has no idea what you *meant*.

This extension fixes that. It converts every page you visit into a semantic vector embedding and stores it locally using **Qdrant Edge**. When you search, your query is embedded the same way and matched by meaning — not by string similarity.

Everything runs **on your device**. No cloud. No API keys. No data leaving your machine.

---

## Output

| Search Interface | Results View |
|:---:|:---:|
| ![Search UI](assets/search_ui.png) | ![Results](assets/results.png) |

**Example queries that work:**
- `"machine learning practice problems"` → finds a LeetCode-style ML site you visited
- `"that site about async javascript"` → finds MDN docs you read 2 weeks ago
- `"python data viz library"` → finds Matplotlib and Seaborn docs even if you only searched "charts"

---

## Architecture

```
┌─────────────────────────────────────┐
│         Browser Extension           │
│  ┌──────────┐  ┌──────────────────┐ │
│  │ popup.js │  │  background.js   │ │
│  │ (Search  │  │  (Event listener)│ │
│  │  UI)     │  └────────┬─────────┘ │
│  └────┬─────┘           │           │
│       │          ┌──────▼─────────┐ │
│       │          │   content.js   │ │
│       │          │ (Page scraper) │ │
│       │          └──────┬─────────┘ │
└───────┼─────────────────┼───────────┘
        │  Native Messaging Bridge    
        │  (JSON over stdio)          
┌───────▼─────────────────▼───────────┐
│         Local Python Backend        │
│                                     │
│  host.py → validator.py             │
│                ↓                    │
│         embedder.py                 │
│       (FastEmbed + ONNX)            │
│                ↓                    │
│          store.py                   │
│        (Qdrant Edge)                │
│                ↓                    │
│         privacy.py                  │
│    (TTL + pause controls)           │
└─────────────────────────────────────┘
```

---

## Features

- **Semantic search** — finds pages by topic and intent, not just matching words
- **Fully local** — Qdrant Edge runs embedded in the app; no Docker, no server
- **Privacy-first** — browsing data never leaves your machine
- **Auto-indexing** — captures history silently as you browse
- **TTL + pause** — configure data retention and pause tracking anytime
- **Fast** — average search latency ~120ms across 5,000 stored pages

---

## Prerequisites

Before you begin, make sure you have the following installed:

| Requirement | Version | Notes |
|---|---|---|
| [Python](https://python.org/downloads/) | 3.10+ | Used for the local backend |
| [Google Chrome](https://www.google.com/chrome/) | Latest | Manifest V3 support required |
| [pip](https://pip.pypa.io/en/stable/) | Latest | Comes bundled with Python |
| [Git](https://git-scm.com/) | Any | For cloning the repo |

> **Windows users:** The native messaging host registration uses a `.bat` launcher and writes to the Windows Registry. Make sure you run the setup script with appropriate permissions.

---

## 🚀 Getting Started

### 1. Clone the repository

```bash
git clone https://github.com/anjaliikakde/intelligent-history-search.git
cd intelligent-history-search
```

### 2. Install Python dependencies

```bash
pip install -r requirements.txt
```

This installs:
- `fastembed` — local ONNX embedding model (downloads `BAAI/bge-small-en-v1.5` on first run, ~23 MB)
- `qdrant-client` — Python client for Qdrant Edge
- `numpy` — vector operations

### 3. Register the Native Messaging host

The browser extension communicates with the Python backend through Chrome's [Native Messaging API](https://developer.chrome.com/docs/apps/nativeMessaging/). You need to register the host once.

**On Windows:**

```bash
python setup/register_host.py
```

This script:
1. Writes `com.historysearch.host.json` to the correct Chrome NativeMessagingHosts path
2. Registers `launch_host.bat` as the executable
3. Adds the registry key under `HKCU\Software\Google\Chrome\NativeMessagingHosts`

**On macOS / Linux:**

```bash
python setup/register_host_unix.py
```

> ⚠️ You only need to run this once. If you move the project folder, re-run the registration script to update the path.

### 4. Load the extension in Chrome

1. Open Chrome and go to `chrome://extensions`
2. Enable **Developer mode** (toggle in the top-right corner)
3. Click **Load unpacked**
4. Select the `extension/` folder from this repository

The extension icon will appear in your toolbar.

### 5. Verify it's working

1. Browse a few websites normally
2. Click the extension icon
3. Type a natural language query like `"python tutorial for beginners"`
4. Results ranked by semantic relevance should appear

---

## 📁 Project Structure

```
intelligent-history-search/
│
├── extension/                  # Chrome extension (Manifest V3)
│   ├── manifest.json           # Extension config, permissions, host binding
│   ├── background/
│   │   └── background.js       # Service worker — listens to tab events
│   ├── content/
│   │   └── content.js          # Injected script — extracts page title & URL
│   └── popup/
│       ├── popup.html          # Search UI layout
│       ├── popup.js            # Handles queries, renders results
│       └── popup.css           # Styling
│
├── backend/                    # Local Python backend
│   ├── host.py                 # Native messaging entrypoint & message router
│   ├── embedder.py             # FastEmbed wrapper — text → vector
│   ├── store.py                # Qdrant Edge — upsert, search, delete
│   ├── validator.py            # Input sanitisation & deduplication
│   └── privacy.py              # TTL enforcement & pause/resume logic
│
├── setup/
│   ├── register_host.py        # Windows host registration script
│   ├── register_host_unix.py   # macOS/Linux host registration script
│   └── com.historysearch.host.json  # Native messaging manifest
│
├── requirements.txt
├── LICENSE
└── README.md
```

---

## Configuration

Edit `backend/config.py` (or the relevant constants in each module) to adjust behaviour:

| Parameter | Default | Description |
|---|---|---|
| `EMBEDDING_MODEL` | `BAAI/bge-small-en-v1.5` | FastEmbed model to use |
| `VECTOR_SIZE` | `384` | Must match your chosen model's output dimension |
| `TOP_K_RESULTS` | `5` | Number of results returned per search |
| `DATA_RETENTION_DAYS` | `30` | Auto-delete entries older than this |
| `DB_PATH` | `./history_db` | Local path for Qdrant Edge storage |

---

## Privacy & Security

This extension was built with privacy as a hard constraint, not an afterthought.

- **No network calls** — the Python backend has no outbound connections
- **Permission-scoped** — `manifest.json` requests only `history`, `tabs`, `storage`, and `nativeMessaging`
- **Native messaging isolation** — Chrome verifies the host name and extension ID before allowing any communication
- **Local-only storage** — Qdrant Edge writes to a local file path; nothing is synced or uploaded
- **TTL enforcement** — `privacy.py` automatically purges entries older than your configured retention window

---

## Contributing

Contributions are welcome! Here's how to get involved.

### Reporting bugs

Open an issue and include:
- Your OS and Chrome version
- Steps to reproduce
- What you expected vs. what happened
- Any error messages from `chrome://extensions` or the Python console

### Suggesting features

Open an issue tagged `enhancement`. Check existing issues first to avoid duplicates.

### Submitting a pull request

1. **Fork** the repository and create a branch from `main`:

    ```bash
    git checkout -b feature/your-feature-name
    ```

2. **Make your changes.** Keep commits focused — one logical change per commit.

3. **Test your changes** locally before opening a PR:
    - Re-load the extension in `chrome://extensions` after any JS changes
    - Re-run `register_host.py` after any backend path changes
    - Verify search still returns relevant results after embedding changes

4. **Open a Pull Request** against `main`. Fill in the PR template describing what changed and why.

### Code style

- **Python** — follow [PEP 8](https://peps.python.org/pep-0008/); use type hints where practical
- **JavaScript** — ES2020+, no frameworks, keep it vanilla
- **Commits** — use [Conventional Commits](https://www.conventionalcommits.org/) (`feat:`, `fix:`, `docs:`, `refactor:`)

---

## 📄 License

This project is licensed under the [MIT License](LICENSE).

---

## Acknowledgements

- [Qdrant](https://qdrant.tech/) for Qdrant Edge — an embedded vector database that made fully local vector search practical
- [FastEmbed](https://github.com/qdrant/fastembed) for a lightweight, ONNX-backed embedding library with zero server dependencies
- [BAAI](https://huggingface.co/BAAI/bge-small-en-v1.5) for the `bge-small-en-v1.5` model used for semantic embeddings