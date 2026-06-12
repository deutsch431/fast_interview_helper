@echo off
title Interview Helper Launcher
echo ===================================================
echo   Interview Helper Suite Launcher
echo ===================================================
echo.

:: Check if local .env exists
if not exist ".env" (
    echo [INFO] Local .env not found. Checking for existing key in ielts_speaking...
    if exist "..\ielts_speaking\.env" (
        echo [INFO] Found .env in ielts_speaking. Copying API key...
        copy "..\ielts_speaking\.env" ".env" >nul
    ) else (
        echo [WARNING] .env file not found. Creating a template .env file...
        echo GEMINI_API_KEY=> .env
        echo GROQ_API_KEY=>> .env
        echo Please add your API keys inside the .env file.
    )
)

echo Starting Optimized Click-to-Record Helper...
python fast_helper.py

echo.
echo ===================================================
echo   App has exited.
echo ===================================================
pause
