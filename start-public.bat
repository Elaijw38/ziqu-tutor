@echo off
REM Start ziqu-tutor and expose it through a temporary Cloudflare tunnel.
REM Keep this window open: closing it kills the public link.
REM Change ZQ_ACCESS_CODE below before sharing, and tell your audience the code.
cd /d "%~dp0"
set ZQ_ACCESS_CODE=ziqu2026
set ZQ_RATE_PER_HOUR=60
set PORT=8776
start "ziqu-tutor-server" cmd /k python src/server.py
timeout /t 2 >nul
"C:\DSH\tools\bin\cloudflared.exe" tunnel --url http://127.0.0.1:8776 --no-autoupdate
