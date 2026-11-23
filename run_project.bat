@echo off
setlocal

set "ROOT=%~dp0"
set "BACKEND=%ROOT%backend"
set "FRONTEND=%ROOT%frontend"

if exist "%ROOT%.venv\Scripts\python.exe" (
  set "PATH=%ROOT%.venv\Scripts;%PATH%"
)

echo Starting RamanCloud Preprocessing...
echo Project: %ROOT%
echo.

set "BACKEND_PYTHON="
for /f "delims=" %%P in ('powershell -NoProfile -ExecutionPolicy Bypass -File "%ROOT%scripts\select_backend_python.ps1"') do set "BACKEND_PYTHON=%%P"
if not defined BACKEND_PYTHON (
  echo Compatible backend Python was not found. Install Python 3.8, 3.9 or 3.10.
  echo Python 3.12 is only for the separate model environment.
  pause
  exit /b 1
)

where npm >nul 2>nul
if errorlevel 1 (
  echo npm was not found. Please install Node.js and try again.
  pause
  exit /b 1
)

echo Installing backend dependencies if needed...
pushd "%BACKEND%"
echo Backend Python: "%BACKEND_PYTHON%"
"%BACKEND_PYTHON%" -m pip install --disable-pip-version-check -r requirements.txt
if errorlevel 1 (
  echo Backend dependency installation failed.
  popd
  pause
  exit /b 1
)
popd

if not exist "%FRONTEND%\node_modules" (
  echo Installing frontend dependencies...
  pushd "%FRONTEND%"
  call npm ci
  if errorlevel 1 (
    echo Frontend dependency installation failed.
    popd
    pause
    exit /b 1
  )
  popd
) else (
  echo Frontend dependencies already installed.
)

echo.
echo Checking local Ollama service...
powershell -NoProfile -ExecutionPolicy Bypass -File "%ROOT%scripts\start_ollama.ps1"

echo Checking existing project services...
powershell -NoProfile -Command "try { $r=Invoke-RestMethod 'http://127.0.0.1:5000/api/health' -TimeoutSec 3; if ($r.code -eq 0) { exit 0 } } catch {}; exit 1"
if errorlevel 1 (
  start "RamanCloud Backend" cmd /k "cd /d ""%BACKEND%"" && ""%BACKEND_PYTHON%"" app.py"
) else (
  echo Backend already running; reusing it.
)
powershell -NoProfile -Command "try { $r=Invoke-RestMethod 'http://127.0.0.1:5173/api/health' -TimeoutSec 3; if ($r.code -eq 0) { exit 0 } } catch {}; exit 1"
if errorlevel 1 (
  start "RamanCloud Frontend" cmd /k "cd /d ""%FRONTEND%"" && npm run dev -- --host 127.0.0.1 --strictPort"
) else (
  echo Frontend already running; reusing it.
)

echo Waiting for the website...
powershell -NoProfile -Command "for ($i=0; $i -lt 45; $i++) { try { $r=Invoke-RestMethod 'http://127.0.0.1:5173/api/health' -TimeoutSec 2; if ($r.code -eq 0) { exit 0 } } catch {}; Start-Sleep -Seconds 1 }; exit 1"
if errorlevel 1 (
  echo Website did not become ready. Check the backend and frontend terminal errors.
  pause
  exit /b 1
)
if not "%RAMANCLOUD_NO_BROWSER%"=="1" start "" "http://127.0.0.1:5173/preprocessing/"

echo.
echo Backend:  http://127.0.0.1:5000
echo Frontend: http://127.0.0.1:5173/preprocessing/
echo.
echo Wait a few seconds for the frontend to finish starting, then open:
echo http://127.0.0.1:5173/preprocessing/
echo.
pause
