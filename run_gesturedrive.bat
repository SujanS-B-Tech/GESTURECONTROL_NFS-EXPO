@echo off
title GESTUREDRIVE X — AI-Powered Touchless Racing Control
echo ======================================================================
echo   GESTUREDRIVE X - AI TOUCHLESS RACING CONTROL (NFS HEAT)
echo ======================================================================
echo.

if not exist ".venv\Scripts\python.exe" (
    echo [ERROR] Virtual environment not found. Please run setup first.
    pause
    exit /b 1
)

echo Starting GESTUREDRIVE X Desktop Interface...
".venv\Scripts\python.exe" main.py %*

if %ERRORLEVEL% NEQ 0 (
    echo.
    echo [NOTICE] Application exited with code %ERRORLEVEL%.
    pause
)

