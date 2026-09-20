@echo off
setlocal EnableExtensions
cd /d "%~dp0"

set "BACKEND=%~dp0backend"
set "FRONTEND=%~dp0frontend"
set "URL=http://localhost:3000"

echo ============================================
echo   Xinyu Launcher
echo ============================================
echo.

netstat -ano | findstr ":8000" | findstr "LISTENING" >nul
if errorlevel 1 (
  echo [1/3] Starting backend on port 8000 ...
  start "Xinyu Backend" /min /d "%BACKEND%" cmd /c ".venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000"
) else (
  echo [1/3] Backend already running, skip.
)

netstat -ano | findstr ":3000" | findstr "LISTENING" >nul
if errorlevel 1 (
  if not exist "%FRONTEND%\node_modules" (
    echo [2/3] Installing frontend dependencies, please wait ...
    start "Xinyu npm install" /min /d "%FRONTEND%" cmd /c "npm install"
    echo       First run needs npm install; the site will open after it finishes.
    echo       If the browser shows an error, wait a moment and refresh.
  ) else (
    echo [2/3] Starting frontend on port 3000 ...
  )
  start "Xinyu Frontend" /min /d "%FRONTEND%" cmd /c "npm run dev"
) else (
  echo [2/3] Frontend already running, skip.
)

echo [3/3] Waiting for the site to be ready ...
for /l %%i in (1,1,60) do (
  curl.exe -s -o nul --max-time 2 %URL% && goto ready
  ping -n 3 127.0.0.1 >nul
)

echo.
echo Timeout waiting for the site. Opening browser anyway ...
goto open

:ready
echo Site is ready.

:open
start "" "%URL%"
echo.
echo Browser opened: %URL%
echo To stop the services, run "停止心屿.bat".
ping -n 6 127.0.0.1 >nul
exit /b 0
