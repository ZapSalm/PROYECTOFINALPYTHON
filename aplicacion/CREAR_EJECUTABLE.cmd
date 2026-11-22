@echo off
setlocal
cd /d "%~dp0"
title Smart Parking V4 - Generar EXE Windows
where py >nul 2>nul
if errorlevel 1 (
  echo ERROR: Instala Python 3.10+ con lanzador py.
  pause
  exit /b 1
)
py -3 -c "import tkinter,sys; assert sys.version_info >= (3,10)"
if errorlevel 1 goto :error
py -3 -m pip install -r "%~dp0..\requirements-dev.txt"
if errorlevel 1 goto :error
py -3 -m PyInstaller --noconfirm --clean --onefile --windowed --name SmartParkingMonitorV4 monitor_parqueo.py
if errorlevel 1 goto :error
for /f "usebackq delims=" %%D in (`powershell -NoProfile -Command "[Environment]::GetFolderPath('Desktop')"`) do set "ESCRITORIO=%%D"
if not defined ESCRITORIO goto :error
set "DEST=%ESCRITORIO%\SmartParking_Presentacion_V4"
if not exist "%DEST%" mkdir "%DEST%"
copy /y "dist\SmartParkingMonitorV4.exe" "%DEST%\SmartParkingMonitorV4.exe"
if errorlevel 1 goto :error
copy /y "%~dp0..\LEEME.txt" "%DEST%\LEEME.txt" >nul
explorer "%DEST%"
echo Ejecutable creado en: %DEST%\SmartParkingMonitorV4.exe
pause
exit /b 0
:error
echo Hubo un problema al crear el ejecutable. Puedes ejecutar ABRIR_MONITOR.cmd.
pause
exit /b 1
