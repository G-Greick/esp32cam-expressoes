@echo off
rem Abre o reconhecimento de expressoes. Basta dar dois cliques neste arquivo.
cd /d "%~dp0"

set "IP="
if exist "pc\ultimo_ip.txt" set /p IP=<"pc\ultimo_ip.txt"

set "NOVO="
set /p NOVO=IP da camera (Enter para usar %IP%):
if not "%NOVO%"=="" set "IP=%NOVO%"
if "%IP%"=="" (
    echo Nenhum IP informado. O IP aparece no Serial Monitor do Arduino IDE.
    pause
    exit /b 1
)
>"pc\ultimo_ip.txt" echo %IP%

"pc\.venv\Scripts\python.exe" "pc\expressoes.py" --ip %IP%
if errorlevel 1 pause
