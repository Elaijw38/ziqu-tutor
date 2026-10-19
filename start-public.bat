@echo off
REM Start ziqu-tutor and expose it through a temporary Cloudflare tunnel.
REM Keep this window open: closing it kills the public link.
REM Change ZQ_ACCESS_CODE below before sharing, and tell your audience the code.
REM
REM 公网实例固定跑 8776，本机演示仍在 8770（两者共用一个学情库 data/learners.db）。
cd /d "%~dp0"
set ZQ_ACCESS_CODE=ziqu2026
set ZQ_RATE_PER_HOUR=60
set PORT=8776

REM 先清掉 8776 上的残留进程：旧脚本不清理，结果隧道连的是几小时前加载的
REM 旧代码（曾出现知识库还停在 170 条、页面没有新功能的情况）。
for /f "tokens=5" %%p in ('netstat -ano ^| findstr /R /C:":8776 .*LISTENING"') do (
  taskkill /F /PID %%p >nul 2>&1
)
start "ziqu-tutor-public" cmd /k python src/server.py
timeout /t 2 >nul

"C:\DSH\tools\bin\cloudflared.exe" tunnel --url http://127.0.0.1:8776 --no-autoupdate
