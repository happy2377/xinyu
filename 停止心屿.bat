@echo off
setlocal EnableExtensions

echo Stopping Xinyu services ...

for /f "tokens=5" %%p in ('netstat -ano ^| findstr ":8000" ^| findstr "LISTENING"') do (
  taskkill /PID %%p /F >nul 2>nul
)
for /f "tokens=5" %%p in ('netstat -ano ^| findstr ":3000" ^| findstr "LISTENING"') do (
  taskkill /PID %%p /F >nul 2>nul
)

echo Done. Backend and frontend have been stopped.
ping -n 4 127.0.0.1 >nul
exit /b 0
