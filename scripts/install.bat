@echo off
:: install.bat — Windows setup script for History Search native host
::
:: What this does:
:: 1. Creates a Python virtual environment
:: 2. Installs all dependencies
:: 3. Downloads the embedding model locally
:: 4. Registers the native messaging host in Windows Registry
:: 5. Prompts user to enter their extension ID
::
:: Usage: Right-click install.bat → Run as Administrator
::        OR run from Command Prompt as Administrator

setlocal EnableDelayedExpansion

:: ---------------------------------------------------------------------------
:: Paths
:: ---------------------------------------------------------------------------
set "SCRIPT_DIR=%~dp0"
set "PROJECT_ROOT=%SCRIPT_DIR%.."
:: Resolve to absolute path
pushd "%PROJECT_ROOT%"
set "PROJECT_ROOT=%CD%"
popd

set "HOST_DIR=%PROJECT_ROOT%\native-host"
set "VENV_DIR=%HOST_DIR%\.venv"
set "HOST_SCRIPT=%HOST_DIR%\host.py"
set "PYTHON_EXE=%VENV_DIR%\Scripts\python.exe"
set "LAUNCHER=%HOST_DIR%\launch_host.bat"

echo.
echo [INFO] History Search - Windows Installer
echo [INFO] Project root: %PROJECT_ROOT%
echo.

:: ---------------------------------------------------------------------------
:: Check Python
:: ---------------------------------------------------------------------------
echo [INFO] Checking Python installation...

python --version >nul 2>&1
if errorlevel 1 (
  echo [ERROR] Python not found. Install Python 3.9+ from https://python.org
  echo [ERROR] Make sure to check "Add Python to PATH" during installation.
  pause
  exit /b 1
)

for /f "tokens=2" %%v in ('python --version 2^>^&1') do set "PYTHON_VER=%%v"
echo [OK]   Python %PYTHON_VER% found

:: ---------------------------------------------------------------------------
:: Create virtual environment
:: ---------------------------------------------------------------------------
echo [INFO] Creating virtual environment...

if exist "%VENV_DIR%" (
  echo [WARN] Virtual environment already exists - skipping
) else (
  python -m venv "%VENV_DIR%"
  if errorlevel 1 (
    echo [ERROR] Failed to create virtual environment
    pause
    exit /b 1
  )
  echo [OK]   Virtual environment created
)

:: ---------------------------------------------------------------------------
:: Install dependencies
:: ---------------------------------------------------------------------------
echo [INFO] Installing Python dependencies...

@REM "%VENV_DIR%\Scripts\pip.exe" install --quiet --upgrade pip
"%VENV_DIR%\Scripts\python.exe" -m pip install --quiet --upgrade pip
"%VENV_DIR%\Scripts\pip.exe" install --quiet -r "%HOST_DIR%\requirements.txt"

if errorlevel 1 (
  echo [ERROR] Dependency installation failed
  pause
  exit /b 1
)
echo [OK]   Dependencies installed

:: ---------------------------------------------------------------------------
:: Download embedding model
:: ---------------------------------------------------------------------------
echo [INFO] Downloading embedding model (one-time, ~80MB)...

cd /d "%HOST_DIR%"
"%PYTHON_EXE%" -c "from embedder import Embedder; ok = Embedder.download_model(); exit(0 if ok else 1)"

if errorlevel 1 (
  echo [ERROR] Model download failed. Check your internet connection.
  pause
  exit /b 1
)
echo [OK]   Embedding model downloaded

:: ---------------------------------------------------------------------------
:: Get Extension ID
:: ---------------------------------------------------------------------------
echo.
echo [INFO] To complete setup, you need your Chrome Extension ID.
echo [INFO] Steps:
echo [INFO]   1. Open Chrome -^> chrome://extensions
echo [INFO]   2. Enable 'Developer mode' (top right toggle)
echo [INFO]   3. Click 'Load unpacked' -^> select: %PROJECT_ROOT%\extension
echo [INFO]   4. Copy the Extension ID shown under your extension name
echo.
set /p "EXTENSION_ID=Paste your Extension ID here: "

if "%EXTENSION_ID%"=="" (
  echo [ERROR] Extension ID cannot be empty.
  pause
  exit /b 1
)

:: ---------------------------------------------------------------------------
:: Write launcher batch file
:: The native messaging manifest "path" on Windows must point to an .exe
:: or a .bat — not directly to a .py file.
:: We use a .bat launcher that calls our venv python with host.py
:: ---------------------------------------------------------------------------
echo [INFO] Writing launcher script...

(
  echo @echo off
  echo "%PYTHON_EXE%" "%HOST_SCRIPT%" %%*
) > "%LAUNCHER%"

echo [OK]   Launcher written: %LAUNCHER%

:: ---------------------------------------------------------------------------
:: Write native messaging manifest JSON
:: ---------------------------------------------------------------------------
set "MANIFEST_PATH=%HOST_DIR%\com.historysearch.host.json"

:: JSON requires forward slashes or escaped backslashes
:: Use PowerShell to write it cleanly
powershell -NoProfile -Command ^
  "$launcher = '%LAUNCHER%' -replace '\\\\', '\\\\';" ^
  "$ext_id = '%EXTENSION_ID%';" ^
  "$json = @{" ^
  "  name = 'com.historysearch.host';" ^
  "  description = 'History Search native messaging host';" ^
  "  path = $launcher;" ^
  "  type = 'stdio';" ^
  "  allowed_origins = @(\"chrome-extension://$ext_id/\")" ^
  "} | ConvertTo-Json -Depth 3;" ^
  "Set-Content -Path '%MANIFEST_PATH%' -Value $json -Encoding UTF8"

if errorlevel 1 (
  echo [ERROR] Failed to write manifest JSON
  pause
  exit /b 1
)
echo [OK]   Manifest written: %MANIFEST_PATH%

:: ---------------------------------------------------------------------------
:: Register in Windows Registry
:: Chrome reads native messaging hosts from:
:: HKCU\Software\Google\Chrome\NativeMessagingHosts\<host_name>
:: The default value = absolute path to the manifest JSON file
:: ---------------------------------------------------------------------------
echo [INFO] Registering native messaging host in Windows Registry...

set "REG_KEY=HKCU\Software\Google\Chrome\NativeMessagingHosts\com.historysearch.host"

reg add "%REG_KEY%" /ve /t REG_SZ /d "%MANIFEST_PATH%" /f >nul

if errorlevel 1 (
  echo [ERROR] Registry write failed. Try running as Administrator.
  pause
  exit /b 1
)
echo [OK]   Registry key set: %REG_KEY%

:: Also register for Chromium
set "REG_KEY_CR=HKCU\Software\Chromium\NativeMessagingHosts\com.historysearch.host"
reg add "%REG_KEY_CR%" /ve /t REG_SZ /d "%MANIFEST_PATH%" /f >nul 2>&1

:: ---------------------------------------------------------------------------
:: Done
:: ---------------------------------------------------------------------------
echo.
echo [OK]   ======================================
echo [OK]     History Search installed!
echo [OK]   ======================================
echo.
echo [INFO] Next steps:
echo [INFO]   1. Reload your extension in chrome://extensions
echo [INFO]   2. Click the extension icon in Chrome toolbar
echo [INFO]   3. Visit some pages - they will be indexed automatically
echo [INFO]   4. Search your history semantically from the popup
echo.
echo [INFO] Logs are at:
echo [INFO]   %%APPDATA%%\browser-history-search\logs\host.log
echo.

pause
endlocal