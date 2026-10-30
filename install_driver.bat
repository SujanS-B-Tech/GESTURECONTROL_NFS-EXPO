@echo off
echo ============================================================
echo   GESTUREDRIVE X - ViGEmBus Driver Installer (Elevated)
echo ============================================================
echo Requesting administrator privileges to install ViGEmBus driver...

powershell -Command "Start-Process msiexec.exe -ArgumentList '/i \"%~dp0assets\drivers\ViGEmBusSetup_x64.msi\"' -Verb RunAs"

echo.
echo Please click 'Yes' on the Windows User Account Control (UAC) prompt.
echo Once the setup wizard completes, return to GESTUREDRIVE X.
pause

