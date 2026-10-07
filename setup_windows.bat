@echo off
REM ============================================================
REM WhatsApp Signal Bridge - Windows Setup Script
REM ============================================================
REM Run this script to set up the project on Windows.
REM
REM Usage: Right-click → Run as administrator
REM ============================================================

echo ============================================
echo WhatsApp Signal Bridge Setup
echo ============================================
echo.

REM Create project directory
set PROJECT_DIR=C:\WhatsAppSignalBot

echo [1/5] Creating project directory: %PROJECT_DIR%
if not exist "%PROJECT_DIR%" mkdir "%PROJECT_DIR%"
echo Done.
echo.

REM Copy all project files
echo [2/5] Copying project files...
copy /Y "%~dp0monitor.py" "%PROJECT_DIR%\"
copy /Y "%~dp0parser.py" "%PROJECT_DIR%\"
copy /Y "%~dp0ai_parser.py" "%PROJECT_DIR%\"
copy /Y "%~dp0signal_writer.py" "%PROJECT_DIR%\"
copy /Y "%~dp0test_parser.py" "%PROJECT_DIR%\"
copy /Y "%~dp0test_ai_parser.py" "%PROJECT_DIR%\"
copy /Y "%~dp0requirements.txt" "%PROJECT_DIR%\"
copy /Y "%~dp0README.md" "%PROJECT_DIR%\"
copy /Y "%~dp0config.example.json" "%PROJECT_DIR%\"
copy /Y "%~dp0start_monitor.bat" "%PROJECT_DIR%\"
copy /Y "%~dp0SimpleSignalTrader.mq5" "%PROJECT_DIR%\"
if not exist "%PROJECT_DIR%\config.json" copy "%PROJECT_DIR%\config.example.json" "%PROJECT_DIR%\config.json"
echo Done.
echo.

REM Install Python dependencies
echo [3/5] Installing Python dependencies...
pip install -r "%PROJECT_DIR%\requirements.txt"
echo Done.
echo.

REM Create chrome profile directory
echo [4/5] Creating Chrome profile directory...
if not exist "%PROJECT_DIR%\chrome-profile" mkdir "%PROJECT_DIR%\chrome-profile"
echo Done.
echo.

REM Run parser tests
echo [5/5] Running parser tests...
cd /d "%PROJECT_DIR%"
python test_parser.py
echo.

echo ============================================
echo Setup Complete!
echo ============================================
echo.
echo Next steps:
echo 1. Edit %PROJECT_DIR%\config.json with your settings
echo    - Set group_name to your WhatsApp group name
echo    - Set signal_file.output_path to your MT5 MQL5\Files folder
echo 2. Copy SimpleSignalTrader.mq5 to your MT5 Experts folder
echo    (File → Open Data Folder → MQL5\Experts)
echo 3. Compile the EA in MetaEditor (F7)
echo 4. Attach EA to XAUUSD chart in MT5
echo 5. Run: python %PROJECT_DIR%\monitor.py
echo.
echo See README.md for detailed instructions.
echo.
pause
