@echo off
REM Auto-Update Railway with Cloudflare Tunnel URL
REM Simple batch version

echo Starting Cloudflare-Railway Auto-Sync...
echo.

:loop
REM Get Cloudflare URL from Docker
for /f "tokens=*" %%i in ('docker logs relayx-cloudflare-tunnel 2^>^&1 ^| findstr "trycloudflare.com"') do set TUNNEL_LOG=%%i

REM Extract URL using PowerShell
for /f "tokens=*" %%i in ('powershell -Command "$log = '%TUNNEL_LOG%'; if ($log -match '(https://[a-zA-Z0-9-]+\.trycloudflare\.com)') { $matches[1] }"') do set CURRENT_URL=%%i

if not "%CURRENT_URL%"=="%LAST_URL%" (
    if not "%CURRENT_URL%"=="" (
        echo.
        echo [%time%] URL Changed: %CURRENT_URL%
        echo Updating Railway...
        
        REM Update Railway
        railway variables --set VOICE_GATEWAY_URL=%CURRENT_URL%
        
        if %ERRORLEVEL% EQU 0 (
            echo SUCCESS - Railway updated!
            set LAST_URL=%CURRENT_URL%
        ) else (
            echo FAILED - Could not update Railway
        )
    )
) else (
    echo [%time%] URL unchanged: %CURRENT_URL%
)

REM Wait 30 seconds
timeout /t 30 /nobreak >nul
goto loop
