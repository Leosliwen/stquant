@echo off
setlocal

set "PYTHON_EXE=D:\gjzqqmt\qmt_env\python.exe"
set "AGENT_DIR=D:\gjzqqmt\python_scripts\qmt_agent"
set "AGENT_SCRIPT=%AGENT_DIR%\qmt_agent.py"
set "AGENT_PORT=8710"
set "AGENT_URL=http://127.0.0.1:%AGENT_PORT%/health"

for /f "tokens=5" %%p in ('netstat -ano ^| findstr /R /C:":%AGENT_PORT% .*LISTENING"') do (
    set "LISTEN_PID=%%p"
)

if defined LISTEN_PID goto stop_agent
goto start_agent

:start_agent
echo qmt_agent is not listening on port %AGENT_PORT%.
echo Starting qmt_agent...
powershell -NoProfile -ExecutionPolicy Bypass -Command "Start-Process -FilePath '%PYTHON_EXE%' -ArgumentList '%AGENT_SCRIPT%' -WorkingDirectory '%AGENT_DIR%' -WindowStyle Hidden"
timeout /t 2 /nobreak >nul
echo Health check:
powershell -NoProfile -ExecutionPolicy Bypass -Command "try { (Invoke-WebRequest -UseBasicParsing -Uri '%AGENT_URL%' -TimeoutSec 5).Content } catch { Write-Host $_.Exception.Message; exit 1 }"
pause
goto end

:stop_agent
echo Port %AGENT_PORT% is listening. Stopping PID %LISTEN_PID%...
powershell -NoProfile -ExecutionPolicy Bypass -Command "Stop-Process -Id %LISTEN_PID% -Force"
timeout /t 1 /nobreak >nul
echo qmt_agent stopped.
pause
goto end

:end
endlocal
