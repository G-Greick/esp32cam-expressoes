"""Lê o vídeo do ESP32-CAM, detecta rostos e classifica a expressão facial.

Uso:
    python expressoes.py --ip 192.168.0.50 [--modelo hsemotion|ferplus|ambos]

O modelo do projeto é o HSEmotion. Use --modelo ambos para compará-lo ao FER+:
FER+ em verde e HSEmotion em amarelo.

Teclas na janela: q = sair, s = salvar o quadro atual em ./capturas/
Fechar a janela pelo X também encerra o programa.
"""

import argparse
import http.client
import time
import urllib.request
from pathlib import Path

import cv2
import numpy as np
import onnxruntime as ort

PASTA = Path(__file__).parent
MODELO_PADRAO = PASTA / "modelos" / "emotion-ferplus-8.onnx"
URL_MODELO = (
    "https://github.com/onnx/models/raw/main/validated/vision/"
    "body_analysis/emotion_ferplus/model/emotion-ferplus-8.onnx"
)
MODELO_HSEMOTION = PASTA / "modelos" / "enet_b0_8_best_vgaf.onnx"
URL_HSEMOTION = (
    "https://github.com/HSE-asavchenko/face-emotion-recognition/raw/main/"
    "models/affectnet_emotions/onnx/enet_b0_8_best_vgaf.onnx"
)
DETECTOR = PASTA / "modelos" / "face_detection_yunet_2023mar.onnx"
URL_DETECTOR = (
    "https://github.com/opencv/opencv_zoo/raw/main/models/"
    "face_detection_yunet/face_detection_yunet_2023mar.onnx"
)
# Ordem das saídas do modelo FER+
EXPRESSOES = ["neutro", "feliz", "surpreso", "triste", "raiva", "nojo", "medo", "desprezo"]
# Ordem das saídas do modelo HSEmotion
EXPRESSOES_HSEMOTION = ["raiva", "desprezo", "nojo", "medo", "feliz", "neutro", "triste", "surpreso"]
JANELA = "ESP32-CAM - expressoes"
TEMPO_LIMITE_MS = 5000
ESPERA_RECONEXAO_S = 2


def baixar_se_preciso(caminho: Path, url: str):
    if not caminho.exists():
        print(f"Baixando {caminho.name} ...")
        caminho.parent.mkdir(parents=True, exist_ok=True)
        urllib.request.urlretrieve(url, caminho)


class DetectorRostos:
    """Detector YuNet (incluso no OpenCV). Retorna caixas (x, y, w, h)."""

    def __init__(self, confianca_min: float = 0.7):
        baixar_se_preciso(DETECTOR, URL_DETECTOR)
        self.det = cv2.FaceDetectorYN.create(str(DETECTOR), "", (320, 320), confianca_min)

    def detectar(self, quadro: np.ndarray) -> list[tuple[int, int, int, int]]:
        h, w = quadro.shape[:2]
        self.det.setInputSize((w, h))
        _, rostos = self.det.detect(quadro)
        if rostos is None:
            return []
        caixas = []
        for r in rostos:
            x, y, cw, ch = (int(v) for v in r[:4])
            x, y = max(x, 0), max(y, 0)
            cw, ch = min(cw, w - x), min(ch, h - y)
            if cw > 20 and ch > 20:
                caixas.append((x, y, cw, ch))
        return caixas


class Classificador:
    """Classificador de expressões. Para usar outro modelo, troque esta classe:
    basta que `classificar(rosto_bgr)` retorne (rótulo, confiança)."""

    def __init__(self, caminho_modelo: Path):
        if caminho_modelo == MODELO_PADRAO:
            baixar_se_preciso(caminho_modelo, URL_MODELO)
        self.sessao = ort.InferenceSession(str(caminho_modelo), providers=["CPUExecutionProvider"])
        self.entrada = self.sessao.get_inputs()[0].name

    def classificar(self, rosto_bgr: np.ndarray) -> tuple[str, float]:
        cinza = cv2.cvtColor(rosto_bgr, cv2.COLOR_BGR2GRAY)
        x = cv2.resize(cinza, (64, 64)).astype(np.float32)[np.newaxis, np.newaxis]
        logits = self.sessao.run(None, {self.entrada: x})[0][0]
        prob = np.exp(logits - logits.max())
        prob /= prob.sum()
        i = int(prob.argmax())
        return EXPRESSOES[i], float(prob[i])


class ClassificadorHSEmotion:
    """Modelo HSEmotion (EfficientNet-B0, treinado no AffectNet), com a mesma interface."""

    MEDIA = np.array([0.485, 0.456, 0.406], np.float32)
    DESVIO = np.array([0.229, 0.224, 0.225], np.float32)

    def __init__(self, caminho_modelo: Path = MODELO_HSEMOTION):
        baixar_se_preciso(caminho_modelo, URL_HSEMOTION)
        self.sessao = ort.InferenceSession(str(caminho_modelo), providers=["CPUExecutionProvider"])
        self.entrada = self.sessao.get_inputs()[0].name

    def classificar(self, rosto_bgr: np.ndarray) -> tuple[str, float]:
        rgb = cv2.cvtColor(cv2.resize(rosto_bgr, (224, 224)), cv2.COLOR_BGR2RGB).astype(np.float32) / 255
        x = ((rgb - self.MEDIA) / self.DESVIO).transpose(2, 0, 1)[np.newaxis]
        logits = self.sessao.run(None, {self.entrada: x})[0][0]
        prob = np.exp(logits - logits.max())
        prob /= prob.sum()
        i = int(prob.argmax())
        return EXPRESSOES_HSEMOTION[i], float(prob[i])


def carregar_modelos(escolha: str) -> list[tuple[str, object, tuple[int, int, int]]]:
    """Devolve (nome, classificador, cor BGR) de cada modelo escolhido."""
    modelos = []
    if escolha in ("ferplus", "ambos"):
        modelos.append(("FER+", Classificador(MODELO_PADRAO), (0, 255, 0)))
    if escolha in ("hsemotion", "ambos"):
        modelos.append(("HSE", ClassificadorHSEmotion(), (0, 255, 255)))
    return modelos


def abrir_fonte(ip: str):
    """Entrega quadros da câmera e reconecta sozinho se ela cair.

    Prefere o stream MJPEG; se não abrir, usa fotos via /capture. Entrega None
    enquanto a câmera está fora do ar, para a janela continuar respondendo.
    """
    url = f"http://{ip}:81/stream"
    tempos = [cv2.CAP_PROP_OPEN_TIMEOUT_MSEC, TEMPO_LIMITE_MS, cv2.CAP_PROP_READ_TIMEOUT_MSEC, TEMPO_LIMITE_MS]
    while True:
        cap = cv2.VideoCapture(url, cv2.CAP_FFMPEG, tempos)
        if cap.isOpened():
            print("Usando stream MJPEG (porta 81)")
            while True:
                ok, quadro = cap.read()
                if not ok:
                    break
                yield quadro
            print("Stream interrompido")
        cap.release()

        avisou = False
        while True:
            try:
                with urllib.request.urlopen(f"http://{ip}/capture", timeout=5) as r:
                    dados = np.frombuffer(r.read(), np.uint8)
            except (OSError, http.client.HTTPException):  # sem conexão ou foto cortada
                break
            if not avisou:
                print("Stream indisponível, usando /capture (feche outras abas com o stream)")
                avisou = True
            quadro = cv2.imdecode(dados, cv2.IMREAD_COLOR) if dados.size else None
            if quadro is not None:  # foto corrompida: só pede a próxima
                yield quadro

        print(f"Câmera sem resposta em {ip}. Confira se está ligada e se o IP está certo. Tentando de novo...")
        yield None
        time.sleep(ESPERA_RECONEXAO_S)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ip", required=True, help="IP mostrado no monitor serial do ESP32-CAM")
    ap.add_argument("--modelo", choices=["hsemotion", "ferplus", "ambos"], default="hsemotion")
    args = ap.parse_args()

    modelos = carregar_modelos(args.modelo)
    detector = DetectorRostos()
    (PASTA / "capturas").mkdir(exist_ok=True)

    t0, quadros, janela_aberta = time.time(), 0, False
    for quadro in abrir_fonte(args.ip):
        if quadro is None:  # câmera fora do ar: recomeça a contagem de fps
            t0, quadros = time.time(), 0
        else:
            for x, y, w, h in detector.detectar(quadro):
                rosto = quadro[y : y + h, x : x + w].copy()  # antes de desenhar sobre o quadro
                cv2.rectangle(quadro, (x, y), (x + w, y + h), (255, 255, 255), 2)
                for i, (nome, classificador, cor) in enumerate(modelos):
                    rotulo, conf = classificador.classificar(rosto)
                    texto = f"{rotulo} {conf:.0%}" if len(modelos) == 1 else f"{nome}: {rotulo} {conf:.0%}"
                    cv2.putText(quadro, texto, (x, max(y - 8 - 26 * i, 45 + 26 * i)),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.7, cor, 2)

            quadros += 1
            fps = quadros / max(time.time() - t0, 1e-3)
            cv2.putText(quadro, f"{fps:.1f} fps", (10, 25), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)
            cv2.imshow(JANELA, quadro)
            janela_aberta = True

        tecla = cv2.waitKey(1) & 0xFF
        if tecla == ord("q"):
            break
        if janela_aberta and cv2.getWindowProperty(JANELA, cv2.WND_PROP_VISIBLE) < 1:
            break  # janela fechada pelo X
        if tecla == ord("s") and quadro is not None:
            nome = PASTA / "capturas" / f"{time.strftime('%Y%m%d-%H%M%S')}.jpg"
            cv2.imwrite(str(nome), quadro)
            print(f"Salvo: {nome}")

    cv2.destroyAllWindows()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        pass
