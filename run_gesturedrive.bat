@echo off
title GESTUREDRIVE X — AI-Powered Touchless Racing Control
echo ======================================================================
echo   GESTUREDRIVE X - AI TOUCHLESS RACING CONTROL (NFS HEAT)
echo ======================================================================
echo.

if not exist ".venv\Scripts\python.exe" (
    echo [ERROR] Virtual environment not found: .venv\Scripts\python.exe is missing.
    echo Running setup.bat automatically...
    echo.
    call setup.bat
    if not exist ".venv\Scripts\python.exe" (
        pause
        exit /b 1
    )
)

if not exist ".venv\pyvenv.cfg" (
    echo [ERROR] Virtual environment is damaged: .venv\pyvenv.cfg is missing.
    echo Running setup.bat to rebuild the virtual environment...
    echo.
    call setup.bat
    if not exist ".venv\pyvenv.cfg" (
        pause
        exit /b 1
    )
)

echo Starting GESTUREDRIVE X Desktop Interface...
".venv\Scripts\python.exe" main.py %*

if %ERRORLEVEL% NEQ 0 (
    echo.
    echo [NOTICE] Application exited with code %ERRORLEVEL%.
    pause
)

