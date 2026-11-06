"""Servidor HTTP do projeto: recebe uma foto JPEG e devolve a expressão facial aparente.

Uso:
    python servidor.py                   (só este PC, na porta 5000)
    python servidor.py --host 0.0.0.0    (aceita a rede, necessário para a placa enviar fotos)

A página em http://127.0.0.1:5000 mostra os resultados da placa e pede a senha guardada
em senha_web.txt, criada na primeira execução. Para publicá-la na internet, use publicar.py.

A placa (ou qualquer cliente HTTP) envia assim:
    POST /analisar
    Content-Type: image/jpeg
    <bytes da imagem>

Resposta:
    {"status": "OK", "expression": "happy", "label": "feliz", "confidence": 0.91, "faces": 1}

Valores de `status`:
    OK                 expressão identificada
    INCONCLUSIVE       confiança abaixo do limite: `label` vem "inconclusivo" e `expression` nulo
    NO_FACE_DETECTED   nenhum rosto: `expression`, `label` e `confidence` nulos, `faces` 0
    INVALID_IMAGE      erro 400: o corpo não é uma imagem
    IMAGE_TOO_LARGE    erro 413: imagem maior que 5 MB

Se houver vários rostos, a resposta é sobre o maior deles. Só um aparelho da rede local
pode enviar sem senha; quem vem pela internet precisa dela.
"""

import argparse
import hmac
import ipaddress
import secrets
import socket
import sys
import threading
import time
from collections import deque
from pathlib import Path

import cv2
import numpy as np
from flask import Flask, Response, jsonify, request
from werkzeug.serving import WSGIRequestHandler

from expressoes import ClassificadorHSEmotion, DetectorRostos

EM_INGLES = {
    "neutro": "neutral",
    "feliz": "happy",
    "surpreso": "surprise",
    "triste": "sad",
    "raiva": "angry",
    "nojo": "disgust",
    "medo": "fear",
}
TAMANHO_MAXIMO = 5 * 1024 * 1024
LIMITE_CONFIANCA = 0.40
ITENS_HISTORICO = 10
ARQUIVO_SENHA = Path(__file__).parent / "senha_web.txt"

PAGINA = """<!doctype html>
<html lang="pt-BR"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Análise de expressões</title>
<style>
:root { color-scheme: light dark; }
body { font: 16px/1.5 system-ui, sans-serif; max-width: 44rem; margin: 2rem auto; padding: 0 1rem; }
h1 { font-size: 1.5rem; margin-bottom: .25rem; }
h2 { font-size: 1.1rem; margin-top: 2rem; }
.nota { opacity: .75; margin-top: 0; }
#foto { width: 100%; max-height: 28rem; object-fit: contain; display: block; background: #8882; border-radius: .5rem; }
#foto[hidden] { display: none; }
#resultado { font-size: 2rem; font-weight: 700; margin: 1rem 0 0; }
#estado { margin: 0; opacity: .75; }
#estado.alerta { color: #c0392b; opacity: 1; font-weight: 600; }
table { width: 100%; border-collapse: collapse; }
th, td { text-align: left; padding: .35rem .5rem .35rem 0; border-bottom: 1px solid #8884; }
#envio { margin-top: .5rem; font-weight: 600; }
</style></head><body>
<h1>Análise de expressões</h1>
<p class="nota">O resultado é a expressão aparente na imagem, não o estado emocional da pessoa.</p>

<img id="foto" alt="Última foto recebida" hidden>
<p id="resultado" role="status">Aguardando a primeira foto...</p>
<p id="estado"></p>

<h2>Últimos resultados</h2>
<table>
<thead><tr><th scope="col">Hora</th><th scope="col">Resultado</th><th scope="col">Origem</th></tr></thead>
<tbody id="historico"></tbody>
</table>

<h2>Testar com uma foto</h2>
<input id="arquivo" type="file" accept="image/*" aria-label="Escolher uma foto para analisar">
<div id="envio" role="status"></div>

<script>
const SEM_FOTOS_S = 45;
const el = (id) => document.getElementById(id);
let fotoAtual = 0;

function texto(r) {
  if (r.status === "NO_FACE_DETECTED") return "Nenhum rosto na imagem";
  const nome = r.status === "INCONCLUSIVE" ? "Inconclusivo" : r.label[0].toUpperCase() + r.label.slice(1);
  return nome + " (" + Math.round(r.confidence * 100) + "%)";
}

function trocar(no, valor) {
  if (no.textContent !== valor) no.textContent = valor;
}

function alerta(valor) {
  trocar(el("estado"), valor);
  el("estado").className = "alerta";
}

async function atualizar() {
  let d;
  try {
    const resp = await fetch("/ultimo");
    if (!resp.ok) throw new Error();
    d = await resp.json();
  } catch {
    alerta("Sem conexão com o servidor.");
    return;
  }
  if (!d.numero) return;
  trocar(el("resultado"), texto(d.resultado));
  if (d.idade_s > SEM_FOTOS_S) {
    alerta("Nenhuma foto nova há " + Math.round(d.idade_s) + " s. Verifique a placa.");
  } else {
    trocar(el("estado"), "Última foto há " + Math.round(d.idade_s) + " s, origem: " + d.origem);
    el("estado").className = "";
  }
  if (d.numero !== fotoAtual) {
    fotoAtual = d.numero;
    el("foto").src = "/foto?n=" + d.numero;
    el("foto").hidden = false;
    el("historico").replaceChildren(...d.historico.map((h) => {
      const linha = document.createElement("tr");
      for (const valor of [h.hora, texto(h), h.origem]) {
        linha.insertCell().textContent = valor;
      }
      return linha;
    }));
  }
}

el("arquivo").addEventListener("change", async (e) => {
  const foto = e.target.files[0];
  if (!foto) return;
  el("envio").textContent = "Analisando...";
  try {
    const resp = await fetch("/analisar", { method: "POST", headers: { "Content-Type": "image/jpeg" }, body: foto });
    const d = await resp.json();
    el("envio").textContent = resp.ok ? texto(d) : d.error;
    atualizar();
  } catch {
    el("envio").textContent = "Não foi possível falar com o servidor.";
  }
});

atualizar();
setInterval(atualizar, 2000);
</script></body></html>"""


def senha_web() -> str:
    """Lê a senha da página. Na primeira execução, sorteia uma e a guarda em senha_web.txt."""
    if not ARQUIVO_SENHA.exists():
        ARQUIVO_SENHA.write_text(secrets.token_urlsafe(12), encoding="ascii")
    return ARQUIVO_SENHA.read_text(encoding="ascii").strip()


def veio_da_rede_local() -> bool:
    """Verdadeiro só para conexão direta de outro aparelho da rede.

    O túnel entrega as visitas da internet pelo endereço 127.0.0.1, então esse endereço
    não conta como rede local.
    """
    if "Cf-Connecting-IP" in request.headers:
        return False
    ip = ipaddress.ip_address(request.remote_addr)
    return ip.is_private and not ip.is_loopback


def decodificar(dados: bytes) -> np.ndarray | None:
    """Devolve a imagem, ou None se os bytes não forem uma imagem."""
    if not dados:
        return None
    return cv2.imdecode(np.frombuffer(dados, np.uint8), cv2.IMREAD_COLOR)


def analisar_quadro(quadro: np.ndarray, detector: DetectorRostos, classificador: ClassificadorHSEmotion) -> dict:
    caixas = detector.detectar(quadro)
    if not caixas:
        return {"status": "NO_FACE_DETECTED", "expression": None, "label": None, "confidence": None, "faces": 0}
    x, y, w, h = max(caixas, key=lambda c: c[2] * c[3])
    rotulo, confianca = classificador.classificar(quadro[y : y + h, x : x + w])
    confianca = round(confianca, 4)
    if confianca < LIMITE_CONFIANCA:
        return {
            "status": "INCONCLUSIVE",
            "expression": None,
            "label": "inconclusivo",
            "confidence": confianca,
            "faces": len(caixas),
        }
    return {
        "status": "OK",
        "expression": EM_INGLES[rotulo],
        "label": rotulo,
        "confidence": confianca,
        "faces": len(caixas),
    }


class Painel:
    """Última foto e últimos resultados, só na memória: nada vai para o disco."""

    def __init__(self):
        self.trava = threading.Lock()
        self.numero = 0
        self.foto = None
        self.resultado = None
        self.origem = None
        self.recebida_em = 0.0
        self.historico = deque(maxlen=ITENS_HISTORICO)

    def registrar(self, quadro: np.ndarray, resultado: dict, origem: str):
        # Recodificar também descarta os metadados do arquivo enviado, como a localização.
        foto = cv2.imencode(".jpg", quadro)[1].tobytes()
        with self.trava:
            self.numero += 1
            self.foto = foto
            self.resultado = resultado
            self.origem = origem
            self.recebida_em = time.time()
            self.historico.appendleft({**resultado, "hora": time.strftime("%H:%M:%S"), "origem": origem})

    def resumo(self) -> dict:
        with self.trava:
            return {
                "numero": self.numero,
                "resultado": self.resultado,
                "origem": self.origem,
                "idade_s": round(time.time() - self.recebida_em, 1) if self.numero else None,
                "historico": list(self.historico),
            }


def criar_app() -> Flask:
    app = Flask(__name__)
    app.config["MAX_CONTENT_LENGTH"] = TAMANHO_MAXIMO
    app.json.ensure_ascii = False
    detector = DetectorRostos()
    classificador = ClassificadorHSEmotion()
    # O detector guarda o tamanho da imagem, então só uma análise roda por vez.
    trava_analise = threading.Lock()
    painel = Painel()
    senha = senha_web().encode()

    @app.before_request
    def exigir_senha():
        if request.endpoint == "analisar" and veio_da_rede_local():
            return None
        auth = request.authorization
        if auth and auth.password and hmac.compare_digest(auth.password.encode(), senha):
            return None
        return Response(
            "Esta página precisa de senha.", 401, {"WWW-Authenticate": 'Basic realm="Expressoes", charset="UTF-8"'}
        )

    @app.after_request
    def sem_cache(resposta):
        # As fotos não podem ficar guardadas nos servidores do túnel nem no navegador.
        resposta.headers["Cache-Control"] = "no-store"
        return resposta

    @app.get("/")
    def inicio():
        return PAGINA

    @app.post("/analisar")
    def analisar():
        quadro = decodificar(request.get_data())
        if quadro is None:
            return jsonify(status="INVALID_IMAGE", error="O corpo da requisição não é uma imagem válida."), 400
        with trava_analise:
            resultado = analisar_quadro(quadro, detector, classificador)
        painel.registrar(quadro, resultado, "teste manual" if request.authorization else "placa")
        return jsonify(resultado)

    @app.get("/ultimo")
    def ultimo():
        return jsonify(painel.resumo())

    @app.get("/foto")
    def foto():
        with painel.trava:
            dados = painel.foto
        if dados is None:
            return jsonify(error="Nenhuma foto recebida ainda."), 404
        return Response(dados, mimetype="image/jpeg")

    @app.errorhandler(413)
    def grande_demais(_):
        return jsonify(status="IMAGE_TOO_LARGE", error="Imagem maior que 5 MB."), 413

    return app


class TratadorComLimite(WSGIRequestHandler):
    # Se a placa reiniciar no meio do envio, a conexão fica aberta sem dados.
    # O limite impede que essas conexões se acumulem para sempre.
    timeout = 15


def porta_ocupada(porta: int) -> bool:
    with socket.socket() as s:
        s.settimeout(1)
        return s.connect_ex(("127.0.0.1", porta)) == 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default="127.0.0.1", help="use 0.0.0.0 para aceitar a placa pela rede")
    ap.add_argument("--porta", type=int, default=5000)
    args = ap.parse_args()
    # No Windows, dois servidores conseguem abrir a mesma porta, e um deles fica recebendo as fotos sem aviso.
    if porta_ocupada(args.porta):
        sys.exit(f"Ja existe um servidor aberto na porta {args.porta}. Feche-o antes de abrir outro.")
    print(f"Senha da pagina: {senha_web()}", flush=True)
    criar_app().run(host=args.host, port=args.porta, threaded=True, request_handler=TratadorComLimite)


if __name__ == "__main__":
    main()
