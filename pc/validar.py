"""Mede a qualidade do modelo em um conjunto de imagens separadas por classe.

Uso:
    python validar.py PASTA [--modelo hsemotion|ferplus] [--com-detector] [--limite N]

A PASTA deve ter uma subpasta por expressão, com o nome em inglês:
    PASTA/happy/foto1.jpg, PASTA/sad/foto2.jpg, ...

Por padrão, cada imagem é tratada como um rosto já recortado, como no FER-2013.
Use --com-detector para fotos comuns: o rosto é localizado antes, e as imagens
em que nenhum rosto é encontrado são contadas à parte.
"""

import argparse
import random
from collections import Counter
from pathlib import Path

import cv2

from expressoes import DetectorRostos, carregar_modelos
from servidor import EM_INGLES

CLASSES = list(EM_INGLES.values())
EXTENSOES = {".jpg", ".jpeg", ".png", ".bmp"}


def listar_imagens(pasta: Path, limite: int | None) -> list[tuple[Path, str]]:
    """Com limite, sorteia até N imagens por classe, sempre as mesmas a cada execução."""
    sorteio = random.Random(0)
    itens = []
    for sub in sorted(p for p in pasta.iterdir() if p.is_dir()):
        if sub.name not in CLASSES:
            print(f"Ignorando a pasta {sub.name}: não é uma classe conhecida")
            continue
        fotos = sorted(f for f in sub.iterdir() if f.suffix.lower() in EXTENSOES)
        if limite and len(fotos) > limite:
            fotos = sorteio.sample(fotos, limite)
        itens += [(f, sub.name) for f in fotos]
    return itens


def imprimir_relatorio(matriz: Counter, sem_rosto: int, ilegiveis: int):
    reais = [c for c in CLASSES if any(matriz[(c, p)] for p in CLASSES)]
    total = sum(matriz.values())
    if not total:
        print("Nenhuma imagem avaliada.")
        return
    acertos = sum(matriz[(c, c)] for c in reais)

    print(f"\nImagens avaliadas: {total}  |  sem rosto: {sem_rosto}  |  ilegíveis: {ilegiveis}")
    print(f"Acurácia geral: {acertos / total:.1%}")
    revocacoes = []
    print(f"\n{'classe':<10}{'imagens':>8}{'acerto':>8}{'precisão':>10}")
    for c in reais:
        n = sum(matriz[(c, p)] for p in CLASSES)
        previstos = sum(matriz[(r, c)] for r in reais)
        revocacoes.append(matriz[(c, c)] / n)
        precisao = f"{matriz[(c, c)] / previstos:.1%}" if previstos else "-"
        print(f"{c:<10}{n:>8}{matriz[(c, c)] / n:>8.1%}{precisao:>10}")
    print(f"\nAcurácia balanceada (média por classe): {sum(revocacoes) / len(revocacoes):.1%}")

    print("\nMatriz de confusão (% de cada classe real; linha = real, coluna = previsto):")
    colunas = [p for p in CLASSES if any(matriz[(r, p)] for r in reais)]
    print(" " * 10 + "".join(f"{p[:8]:>9}" for p in colunas))
    for r in reais:
        n = sum(matriz[(r, p)] for p in CLASSES)
        print(f"{r:<10}" + "".join(f"{matriz[(r, p)] / n:>9.0%}" for p in colunas))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("pasta", type=Path)
    ap.add_argument("--com-detector", action="store_true", help="localiza o rosto antes de classificar")
    ap.add_argument("--limite", type=int, help="máximo de imagens por classe")
    ap.add_argument("--modelo", choices=["hsemotion", "ferplus"], default="hsemotion")
    args = ap.parse_args()

    classificador = carregar_modelos(args.modelo)[0][1]
    detector = DetectorRostos() if args.com_detector else None
    para_ingles = EM_INGLES

    matriz, sem_rosto, ilegiveis = Counter(), 0, 0
    for caminho, real in listar_imagens(args.pasta, args.limite):
        img = cv2.imread(str(caminho), cv2.IMREAD_COLOR)
        if img is None:
            ilegiveis += 1
            continue
        if detector:
            caixas = detector.detectar(img)
            if not caixas:
                sem_rosto += 1
                continue
            x, y, w, h = max(caixas, key=lambda c: c[2] * c[3])
            img = img[y : y + h, x : x + w]
        rotulo, _ = classificador.classificar(img)
        matriz[(real, para_ingles[rotulo])] += 1

    imprimir_relatorio(matriz, sem_rosto, ilegiveis)


if __name__ == "__main__":
    main()
