@echo off
rem Abre o servidor de analise e a pagina de teste. Basta dar dois cliques neste arquivo.
rem Para encerrar, feche esta janela.
cd /d "%~dp0"
start "" /min cmd /c "timeout /t 4 /nobreak >nul & start http://127.0.0.1:5000"
"pc\.venv\Scripts\python.exe" "pc\servidor.py" --host 0.0.0.0
if errorlevel 1 pause
