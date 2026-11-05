@echo off
rem Permite que a placa alcance o servidor: so a porta 5000, so na rede local privada.
rem Precisa rodar uma vez. O Windows vai pedir permissao de administrador.
net session >nul 2>&1
if errorlevel 1 (
    powershell -NoProfile -Command "Start-Process -FilePath '%~f0' -Verb RunAs"
    exit /b
)
netsh advfirewall firewall delete rule name="Servidor de expressoes ESP32-CAM" >nul 2>&1
netsh advfirewall firewall add rule name="Servidor de expressoes ESP32-CAM" dir=in action=allow protocol=TCP localport=5000 profile=private remoteip=localsubnet
if errorlevel 1 (echo Nao foi possivel criar a regra.) else (echo Pronto: a porta 5000 esta liberada na rede local.)
pause
