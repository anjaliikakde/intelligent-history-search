# Browser History Search Extension

## Overview

The Browser History Search Extension is a powerful tool designed to enhance your browsing experience by providing fast and efficient search capabilities across your browser history. This extension integrates seamlessly with your browser and utilizes a native host component for secure, local processing of history data, ensuring privacy and performance.

## Features

- **Instant Search**: Quickly search through your browser history with real-time results.
- **Privacy-Focused**: All searches are processed locally using a native host, keeping your data secure.
- **User-Friendly Interface**: Intuitive popup interface for easy access.
- **Cross-Platform Support**: Compatible with major browsers supporting native messaging.
- **Customizable**: Configurable settings for personalized search experience.

## Requirements

- **Browser**: Google Chrome or Chromium-based browsers (recommended), or Firefox with native messaging support.
- **Python**: Version 3.7 or higher for the native host component.
- **Operating System**: Windows, macOS, or Linux.

## Installation

### Step 1: Install the Browser Extension

1. Download or clone this repository to your local machine.
2. Open your browser and navigate to the extensions page:
   - **Chrome**: Go to `chrome://extensions/`
   - **Firefox**: Go to `about:addons`
3. Enable "Developer mode" (Chrome) or "Debug add-ons" (Firefox).
4. Click "Load unpacked" (Chrome) or "Load Temporary Add-on" (Firefox) and select the `extension/` folder from this repository.

### Step 2: Set Up the Native Host

The native host handles secure communication between the extension and your browser's history data.

1. Ensure Python 3.7+ is installed on your system.
2. Install the required Python dependencies:
   ```
   pip install -r native-host/requirements.txt
   ```
3. Run the installation script appropriate for your operating system:
   - **Windows**: Double-click `scripts/install.bat` or run it from the command line.
   - **macOS/Linux**: Run `scripts/install.sh` from the terminal.

   This script registers the native host with your system.

### Step 3: Verify Installation

1. Restart your browser.
2. Click the extension icon in your browser toolbar to open the popup.
3. Perform a test search to ensure the native host is communicating correctly.

## Usage

1. Click the Browser History Search Extension icon in your browser toolbar.
2. Enter your search query in the popup window.
3. Browse the results and click on any entry to navigate to the page.
4. Use the settings (if available) to customize search behavior.

## Development

### Running Tests

To run the test suite for the native host components:

1. Navigate to the `native-host/` directory.
2. Install test dependencies if needed: `pip install -r requirements.txt`
3. Run tests: `python -m pytest tests/`

### Building and Packaging

- For the extension: Use browser-specific tools to package the extension for distribution.
- For the native host: Ensure all scripts are executable and dependencies are locked (see `requirements-lock.txt`).

### Contributing

We welcome contributions! Please follow these steps:

1. Fork the repository.
2. Create a feature branch.
3. Make your changes and add tests.
4. Submit a pull request.

## Troubleshooting

- **Extension not loading**: Ensure the `extension/` folder is correctly selected during installation.
- **Native host not responding**: Check that the installation script ran successfully and Python is in your PATH.
- **Search not working**: Verify browser permissions and restart the browser after installation.

