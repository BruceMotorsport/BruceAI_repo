@echo off
setlocal
set "SCRIPT=%~dp0start_bruceai.ps1"

rem Pause only for a manual / double-clicked run so scripted callers stay quiet.
set "PAUSE_AFTER="
if "%~1"=="" echo %CMDCMDLINE% | findstr /i /c:"/c" >nul && set "PAUSE_AFTER=1"

powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%SCRIPT%" %*
set "RC=%ERRORLEVEL%"

if defined PAUSE_AFTER (
    echo.
    if "%RC%"=="0" (
        echo BruceAI: OK. Press any key to close.
    ) else (
        echo BruceAI: FAILED with exit code %RC%. See logs\ for details. Press any key to close.
    )
    pause >nul
)
exit /b %RC%
