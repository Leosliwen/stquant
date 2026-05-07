@echo off
powershell -NoProfile -ExecutionPolicy Bypass -Command "Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -like '*qmt_agent.py*' } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force }"
echo qmt_agent stopped.
pause
