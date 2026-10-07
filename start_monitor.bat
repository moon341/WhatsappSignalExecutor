@echo off
REM ============================================================
REM WhatsApp Signal Bridge - Start Monitor
REM ============================================================
REM Starts the WhatsApp Web monitor for trade signals.
REM ============================================================

cd /d C:\WhatsAppSignalBot
echo Starting WhatsApp Signal Bridge Monitor...
echo Press Ctrl+C to stop.
echo.
python monitor.py
pause
