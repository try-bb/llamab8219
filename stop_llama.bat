@echo off
echo Stopping llama-server service...
taskkill /F /IM llama-server.exe 2>nul
if %errorlevel% equ 0 (
    echo Service stopped successfully!
) else (
    echo No running service found
)
echo Checking port 8080...
netstat -ano | findstr :8080
echo.
echo Done! Please wait a few seconds before starting a new model.
echo.
pause
