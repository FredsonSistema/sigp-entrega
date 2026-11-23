@echo off
rem Instala o SIGp do zero: clique duas vezes neste arquivo. Ele baixa e roda o instalar-sigp.ps1 do GitHub
rem (o mesmo que "irm https://raw.githubusercontent.com/FredsonSistema/sigp-entrega/main/instalar-sigp.ps1 | iex").
chcp 65001 >nul
powershell.exe -NoProfile -ExecutionPolicy Bypass -Command "[Net.ServicePointManager]::SecurityProtocol = [Net.ServicePointManager]::SecurityProtocol -bor 3072; irm https://raw.githubusercontent.com/FredsonSistema/sigp-entrega/main/instalar-sigp.ps1 | iex"
echo.
pause
