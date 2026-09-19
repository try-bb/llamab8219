@echo off
setlocal enabledelayedexpansion

echo ===============================================
echo        Llama.cpp Model Selector
echo ===============================================
echo Scanning models...
echo.

set "models_dir=C:\Users\Administrator\.lmstudio\models"
set "llama_dir=%~dp0"
set "server_exe=%llama_dir%llama-bin\llama-server.exe"

set "model_count=0"

for /r "%models_dir%" %%f in (*.gguf) do (
    echo %%~nf | findstr /i "mmproj" >nul
    if errorlevel 1 (
        set /a model_count+=1
        set "model_!model_count!=%%f"
        set "model_name_!model_count!=%%~nf"
        echo [!model_count!] %%~nf
    )
)

echo.
if %model_count% equ 0 (
    echo No models found!
    pause
    exit /b
)

echo Select model number:
set /p model_choice=

if not defined model_%model_choice% (
    echo Invalid selection!
    pause
    exit /b
)

set "selected_model=!model_%model_choice%!"
set "selected_model_name=!model_name_%model_choice%!"

echo.
echo Selected model: %selected_model_name%
echo Model path: %selected_model%
echo.

rem Set context based on model size
set "default_context=8192"

echo %selected_model_name% | findstr /i "27B" >nul
if !errorlevel! equ 0 (
    set "default_context=4096"
    echo [27B model - recommended context: 4096]
)

echo %selected_model_name% | findstr /i "9B" >nul
if !errorlevel! equ 0 (
    set "default_context=8192"
    echo [9B model - recommended context: 8192]
)

echo %selected_model_name% | findstr /i "0.8B" >nul
if !errorlevel! equ 0 (
    set "default_context=16384"
    echo [0.8B model - recommended context: 16384]
)

echo %selected_model_name% | findstr /i "2B" >nul
if !errorlevel! equ 0 (
    set "default_context=16384"
    echo [2B model - recommended context: 16384]
)

echo %selected_model_name% | findstr /i "4B" >nul
if !errorlevel! equ 0 (
    set "default_context=8192"
    echo [4B model - recommended context: 8192]
)

echo.
echo Recommended context: %default_context%
echo Press Enter to use recommended, or type custom value:
set /p custom_context=

if "!custom_context!"=="" (
    set "context=!default_context!"
) else (
    set "context=!custom_context!"
)

echo.
echo =========================================
echo Final settings:
echo   Model: %selected_model_name%
echo   Context: !context! tokens
echo   Server: http://localhost:8081
echo =========================================
echo.
echo Starting Llama server...
echo Press Ctrl+C to stop
echo.

"%server_exe%" -m "%selected_model%" -ngl 999 -c !context! --port 8081 --host 127.0.0.1 --api-key sk-123456

echo.
echo Server stopped.
pause
