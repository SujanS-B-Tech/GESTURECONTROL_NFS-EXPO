@echo off
title GESTUREDRIVE X — Build Standalone Windows Executable
echo ======================================================================
echo   GESTUREDRIVE X - Standalone Binary Packaging (PyInstaller)
echo ======================================================================
echo.

if not exist ".venv\Scripts\pyinstaller.exe" (
    echo [ERROR] PyInstaller not found in .venv.
    echo Please run setup.bat first.
    pause
    exit /b 1
)

echo Building standalone application package...
".venv\Scripts\pyinstaller.exe" --noconsole ^
    --name="GESTUREDRIVE-X" ^
    --icon="assets/icon.ico" ^
    --add-data="assets;assets" ^
    --add-data="config;config" ^
    --collect-all=mediapipe ^
    --collect-all=vgamepad ^
    --collect-all=PySide6 ^
    --clean ^
    main.py

if %ERRORLEVEL% NEQ 0 (
    echo.
    echo [ERROR] PyInstaller build failed.
    pause
    exit /b 1
)

echo.
echo Copying ViGEmBus driver installer into dist folder...
if not exist "dist\GESTUREDRIVE-X\drivers" mkdir "dist\GESTUREDRIVE-X\drivers"
copy /y "assets\drivers\ViGEmBusSetup_x64.msi" "dist\GESTUREDRIVE-X\drivers\" >nul
copy /y "install_driver.bat" "dist\GESTUREDRIVE-X\" >nul

echo.
echo ======================================================================
echo [SUCCESS] Standalone release built at: dist\GESTUREDRIVE-X\
echo ======================================================================
echo.
pause

