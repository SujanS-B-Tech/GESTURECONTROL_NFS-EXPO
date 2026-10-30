@echo off
title GESTUREDRIVE X — Environment Setup
echo ======================================================================
echo   GESTUREDRIVE X - Environment Setup ^& Dependency Installation
echo ======================================================================
echo.

:: Detect Python 3.12 launcher or fallback to system python
set PYTHON_CMD=
py -3.12 --version >nul 2>&1
if %ERRORLEVEL% EQU 0 (
    set PYTHON_CMD=py -3.12
) else (
    py -3 --version >nul 2>&1
    if %ERRORLEVEL% EQU 0 (
        set PYTHON_CMD=py -3
    ) else (
        python --version >nul 2>&1
        if %ERRORLEVEL% EQU 0 (
            set PYTHON_CMD=python
        )
    )
)

if "%PYTHON_CMD%"=="" (
    echo [ERROR] Python was not found on your system!
    echo Please install Python 3.12 (64-bit) from python.org and add it to PATH.
    pause
    exit /b 1
)

echo Using Python launcher: %PYTHON_CMD%
%PYTHON_CMD% --version

:: Check if .venv is broken or missing pyvenv.cfg
if exist ".venv" (
    if not exist ".venv\pyvenv.cfg" (
        echo [WARNING] Existing .venv is damaged: pyvenv.cfg is missing. Rebuilding...
        rmdir /s /q ".venv"
    )
)

if not exist ".venv\Scripts\python.exe" (
    echo Creating virtual environment in .venv...
    %PYTHON_CMD% -m venv .venv
    if %ERRORLEVEL% NEQ 0 (
        echo [ERROR] Failed to create virtual environment.
        pause
        exit /b 1
    )
)

echo.
echo Installing / Updating required dependencies from requirements.txt...
".venv\Scripts\python.exe" -m pip install --upgrade pip
".venv\Scripts\pip.exe" install -r requirements.txt
if %ERRORLEVEL% NEQ 0 (
    echo.
    echo [ERROR] Failed to install dependencies.
    pause
    exit /b 1
)

echo.
echo Running diagnostic test suite...
".venv\Scripts\python.exe" main.py --test
if %ERRORLEVEL% NEQ 0 (
    echo.
    echo [WARNING] Diagnostic tests reported warnings or failures.
) else (
    echo.
    echo [SUCCESS] GESTUREDRIVE X environment is completely set up and verified!
    echo You can now launch the application by running run_gesturedrive.bat.
)

pause
