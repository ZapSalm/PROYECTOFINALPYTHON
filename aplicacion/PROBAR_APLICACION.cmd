@echo off
cd /d "%~dp0"
py -3 PRUEBAS.py
if errorlevel 1 goto :fail
py -3 PRUEBAS_RED.py
if errorlevel 1 goto :fail
echo Todas las pruebas de Python pasaron.
pause
exit /b 0
:fail
echo Revisar errores anteriores.
pause
exit /b 1
