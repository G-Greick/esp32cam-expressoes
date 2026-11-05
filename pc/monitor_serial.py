"""Reinicia o ESP32-CAM e mostra o que ele imprime na serial (para ver o IP).

Uso: python monitor_serial.py [PORTA] [SEGUNDOS]   (padrão: detecta a porta CH340, 20)
"""

import sys
import time

import serial
from serial.tools import list_ports


def detectar_porta() -> str:
    """Procura a base USB da placa (a ESP32-CAM-MB usa o chip CH340)."""
    for p in list_ports.comports():
        if "CH340" in p.description:
            return p.device
    sys.exit("Placa não encontrada: confira o cabo USB ou informe a porta (ex.: COM9).")


porta = sys.argv[1] if len(sys.argv) > 1 else detectar_porta()
segundos = float(sys.argv[2]) if len(sys.argv) > 2 else 20

s = serial.Serial()
s.port, s.baudrate, s.timeout = porta, 115200, 0.5
# Na placa ESP32-CAM-MB, DTR/RTS ligados seguram a placa em reset/bootloader.
s.dtr = False
s.rts = False
s.open()
s.rts = True
time.sleep(0.1)
s.rts = False  # pulso de reset

fim = time.time() + segundos
while time.time() < fim:
    linha = s.readline()
    if linha:
        print(linha.decode(errors="replace").rstrip(), flush=True)
s.close()
