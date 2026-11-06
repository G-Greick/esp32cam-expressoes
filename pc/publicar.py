"""Abre o servidor e publica a página na internet por um túnel do Cloudflare.

Uso:
    python publicar.py

A análise continua rodando neste PC e a placa continua enviando pela rede local. O túnel só
leva a página à internet, com HTTPS e pedindo a senha. O endereço muda a cada execução e deixa
de funcionar quando este programa fecha.
"""

import re
import shutil
import subprocess
import sys
import threading
import time
import urllib.request
import webbrowser
from pathlib import Path

from expressoes import baixar_se_preciso
from servidor import porta_ocupada, senha_web

PASTA = Path(__file__).parent
PORTA = 5000
CLOUDFLARED = PASTA / "ferramentas" / "cloudflared.exe"
URL_CLOUDFLARED = (
    "https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-windows-amd64.exe"
)
ENDERECO = re.compile(r"https://[a-z0-9-]+\.trycloudflare\.com")
ESPERA_ENDERECO_S = 60


def caminho_cloudflared() -> str:
    instalado = shutil.which("cloudflared")
    if instalado:
        return instalado
    baixar_se_preciso(CLOUDFLARED, URL_CLOUDFLARED)
    return str(CLOUDFLARED)


def acompanhar_tunel(tunel: subprocess.Popen, achou: threading.Event, guardado: list[str]):
    """Lê o que o túnel escreve até ele fechar, para ele não parar com a saída cheia."""
    for linha in tunel.stderr:
        if not achou.is_set():
            encontrado = ENDERECO.search(linha)
            if encontrado:
                guardado.append(encontrado.group())
                achou.set()


def main():
    if porta_ocupada(PORTA):
        sys.exit(f"Ja existe um servidor aberto na porta {PORTA}. Feche-o antes de publicar.")

    programa = caminho_cloudflared()
    servidor = subprocess.Popen([sys.executable, str(PASTA / "servidor.py"), "--host", "0.0.0.0", "--porta", str(PORTA)])
    tunel = subprocess.Popen(
        [programa, "tunnel", "--no-autoupdate", "--url", f"http://127.0.0.1:{PORTA}"],
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    achou, guardado = threading.Event(), []
    threading.Thread(target=acompanhar_tunel, args=(tunel, achou, guardado), daemon=True).start()

    try:
        if not achou.wait(ESPERA_ENDERECO_S):
            sys.exit("O tunel nao informou um endereco. Verifique a conexao com a internet e tente de novo.")
        # O túnel costuma ficar pronto antes do servidor, que ainda está carregando os modelos.
        while not porta_ocupada(PORTA):
            if servidor.poll() is not None:
                sys.exit("O servidor nao abriu. Veja a mensagem acima.")
            time.sleep(0.5)
        endereco = guardado[0]
        print(f"\n{'=' * 60}\nPagina na internet: {endereco}\nSenha: {senha_web()}  (o usuario pode ser qualquer um)")
        print(f"Para encerrar, feche esta janela.\n{'=' * 60}\n", flush=True)
        webbrowser.open(endereco)
        while servidor.poll() is None and tunel.poll() is None:
            time.sleep(1)
        sys.exit("O servidor ou o tunel fechou. Abra este programa de novo.")
    except KeyboardInterrupt:
        pass
    finally:
        tunel.terminate()
        servidor.terminate()


if __name__ == "__main__":
    main()
