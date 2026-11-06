@echo off
rem Abre o servidor e publica a pagina na internet, com senha. Basta dar dois cliques neste arquivo.
rem Para encerrar, feche esta janela.
cd /d "%~dp0"
"pc\.venv\Scripts\python.exe" "pc\publicar.py"
if errorlevel 1 pause
