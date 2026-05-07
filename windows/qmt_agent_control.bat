@echo off
setlocal

set "PYTHON_EXE=D:\gjzqqmt\qmt_env\python.exe"
set "AGENT_DIR=D:\gjzqqmt\python_scripts\qmt_agent"
set "AGENT_SCRIPT=%AGENT_DIR%\qmt_agent.py"
set "AGENT_URL=http://127.0.0.1:8710/health"

:menu
cls
echo =====================================
echo STQuant qmt_agent control
echo =====================================
echo.
echo 1. Start qmt_agent in this window
echo 2. Start qmt_agent hidden
echo 3. Stop qmt_agent
echo 4. Health check
echo 0. Exit
echo.
choice /c 12340 /n /m "Choose: "

if errorlevel 5 goto end
if errorlevel 4 goto health
if errorlevel 3 goto stop
if errorlevel 2 goto start_hidden
if errorlevel 1 goto start_foreground

:start_foreground
cls
echo Starting qmt_agent in this window.
echo Close this window or press Ctrl+C to stop it.
echo.
"%PYTHON_EXE%" "%AGENT_SCRIPT%"
pause
goto menu

:start_hidden
echo Starting qmt_agent hidden...
powershell -NoProfile -ExecutionPolicy Bypass -Command "Start-Process -FilePath '%PYTHON_EXE%' -ArgumentList '%AGENT_SCRIPT%' -WorkingDirectory '%AGENT_DIR%' -WindowStyle Hidden"
timeout /t 2 /nobreak >nul
goto health

:stop
echo Stopping qmt_agent...
powershell -NoProfile -ExecutionPolicy Bypass -Command "Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -like '*qmt_agent.py*' } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force }"
echo Done.
pause
goto menu

:health
echo Checking %AGENT_URL%
powershell -NoProfile -ExecutionPolicy Bypass -Command "try { (Invoke-WebRequest -UseBasicParsing -Uri '%AGENT_URL%' -TimeoutSec 5).Content } catch { Write-Host $_.Exception.Message; exit 1 }"
pause
goto menu

:end
endlocal
