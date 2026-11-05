"""Servidor HTTP do projeto: recebe uma foto JPEG e devolve a expressão facial aparente.

Uso:
    python servidor.py                   (só este PC, na porta 5000)
    python servidor.py --host 0.0.0.0    (aceita a rede, necessário para a placa enviar fotos)

Depois abra http://127.0.0.1:5000 no navegador para testar enviando uma foto.

A placa (ou qualquer cliente HTTP) envia assim:
    POST /analisar
    Content-Type: image/jpeg
    <bytes da imagem>

Resposta:
    {"expression": "happy", "label": "feliz", "confidence": 0.91, "faces": 1}

Sem rosto na imagem, `expression`, `label` e `confidence` vêm nulos e `faces` vem 0.
Se houver vários rostos, a resposta é sobre o maior deles.
"""

import argparse

import cv2
import numpy as np
from flask import Flask, jsonify, request
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
    "desprezo": "contempt",
}
TAMANHO_MAXIMO = 5 * 1024 * 1024

PAGINA = """<!doctype html>
<html lang="pt-BR"><head><meta charset="utf-8"><title>Análise de expressões</title>
<style>
body { font: 16px system-ui, sans-serif; max-width: 34rem; margin: 3rem auto; padding: 0 1rem; }
img { max-width: 100%; margin-top: 1rem; display: block; }
#r { margin-top: 1rem; font-size: 1.4rem; font-weight: 600; }
</style></head><body>
<h1>Análise de expressões</h1>
<p>Escolha uma foto com um rosto. O resultado é a expressão aparente na imagem, não o estado emocional da pessoa.</p>
<input id="f" type="file" accept="image/*">
<div id="r" role="status"></div>
<img id="p" alt="">
<script>
const r = document.getElementById("r"), p = document.getElementById("p");
document.getElementById("f").addEventListener("change", async (e) => {
  const foto = e.target.files[0];
  if (!foto) return;
  p.src = URL.createObjectURL(foto);
  p.alt = "Foto enviada";
  r.textContent = "Analisando...";
  try {
    const resp = await fetch("/analisar", { method: "POST", headers: { "Content-Type": "image/jpeg" }, body: foto });
    const d = await resp.json();
    if (!resp.ok) r.textContent = d.error;
    else if (!d.faces) r.textContent = "Nenhum rosto encontrado.";
    else r.textContent = d.label + " (" + Math.round(d.confidence * 100) + "%)";
  } catch { r.textContent = "Não foi possível falar com o servidor."; }
});
</script></body></html>"""


def analisar_imagem(dados: bytes, detector: DetectorRostos, classificador: ClassificadorHSEmotion) -> dict | None:
    """Devolve o resultado da análise, ou None se os bytes não forem uma imagem."""
    if not dados:
        return None
    quadro = cv2.imdecode(np.frombuffer(dados, np.uint8), cv2.IMREAD_COLOR)
    if quadro is None:
        return None
    caixas = detector.detectar(quadro)
    if not caixas:
        return {"expression": None, "label": None, "confidence": None, "faces": 0}
    x, y, w, h = max(caixas, key=lambda c: c[2] * c[3])
    rotulo, confianca = classificador.classificar(quadro[y : y + h, x : x + w])
    return {
        "expression": EM_INGLES[rotulo],
        "label": rotulo,
        "confidence": round(confianca, 4),
        "faces": len(caixas),
    }


def criar_app() -> Flask:
    app = Flask(__name__)
    app.config["MAX_CONTENT_LENGTH"] = TAMANHO_MAXIMO
    app.json.ensure_ascii = False
    detector = DetectorRostos()
    classificador = ClassificadorHSEmotion()

    @app.get("/")
    def inicio():
        return PAGINA

    @app.post("/analisar")
    def analisar():
        resultado = analisar_imagem(request.get_data(), detector, classificador)
        if resultado is None:
            return jsonify(error="O corpo da requisição não é uma imagem válida."), 400
        return jsonify(resultado)

    @app.errorhandler(413)
    def grande_demais(_):
        return jsonify(error="Imagem maior que 5 MB."), 413

    return app


class TratadorComLimite(WSGIRequestHandler):
    # Se a placa reiniciar no meio do envio, a conexão fica aberta sem dados. Sem limite,
    # o servidor, que atende uma foto por vez, ficaria preso nela para sempre.
    timeout = 15


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default="127.0.0.1", help="use 0.0.0.0 para aceitar a placa pela rede")
    ap.add_argument("--porta", type=int, default=5000)
    args = ap.parse_args()
    # threaded=False: o detector guarda o tamanho da imagem, então atende uma foto por vez.
    criar_app().run(host=args.host, port=args.porta, threaded=False, request_handler=TratadorComLimite)


if __name__ == "__main__":
    main()
