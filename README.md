# ESP32-CAM: reconhecimento de expressões faciais

A placa ESP32-CAM tira uma foto a cada 5 segundos e a envia pelo Wi-Fi para um servidor no PC. O servidor encontra o rosto, classifica a expressão (neutro, feliz, surpreso, triste, raiva, nojo ou medo) e devolve o resultado, que aparece no Serial Monitor e em uma página web protegida por senha.

A análise acontece no PC. A página pode ser publicada na internet por um túnel, e também há um modo de vídeo ao vivo.

O resultado indica a expressão aparente na imagem, não o estado emocional real da pessoa.

## Situação atual

| Parte | Estado |
|---|---|
| Servidor com modelo de IA (`POST /analisar`) | Pronto, testado localmente |
| Vídeo da placa analisado no PC (`expressoes.py`) | Pronto, depende da qualidade do Wi-Fi |
| Placa enviando a foto ao servidor, como no pré-projeto | Funcionando; falta confirmar com um rosto na frente da câmera |
| Página web com os resultados | Pronta; falta testar com a placa e pelo túnel |

## O que é preciso

- Placa ESP32-CAM AI Thinker com base USB ESP32-CAM-MB
- Rede Wi-Fi de 2,4 GHz, com a placa e o PC conectados nela
- Arduino IDE com o pacote de placas `esp32`
- Python 3.10 ou mais recente

## 1. Gravar a placa

1. Na pasta `firmware/esp32cam_expressoes/`, copie `segredos.exemplo.h` para `segredos.h`.
2. Em `segredos.h`, preencha `WIFI_SSID`, `WIFI_SENHA` e, em `SERVIDOR_URL`, o IP do PC. Esse arquivo fica fora do git, então cada pessoa mantém o seu.
3. Abra `firmware/esp32cam_expressoes/esp32cam_expressoes.ino` no Arduino IDE.
4. Em **Tools > Board**, escolha **AI Thinker ESP32-CAM**.
5. Em **Tools > Port**, escolha a porta da placa. Ela costuma aparecer como CH340 no Gerenciador de Dispositivos.
6. Clique em **Upload**.
7. Abra o **Serial Monitor** em 115200 baud e aperte o botão RST da placa. O IP aparece no final.

Só é preciso gravar de novo ao mudar o código, a rede Wi-Fi ou o IP do PC.

## 2. Preparar o PC (só na primeira vez)

```powershell
cd pc
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
```

Os modelos de IA são baixados automaticamente no primeiro uso, se ainda não estiverem em `pc/modelos/`.

## 3. Usar

### Fotos analisadas pelo servidor

1. Na primeira vez, dê dois cliques em `Liberar firewall.bat` e confirme a permissão de administrador. Isso libera só a porta 5000, na rede local privada.
2. Dê dois cliques em `Iniciar servidor.bat` e deixe a janela aberta.
3. Ligue a placa e abra o Serial Monitor em 115200 baud.
4. Aparece o resultado de cada foto, por exemplo `Expressao: feliz (82%)`. A placa tenta enviar a cada 5 segundos, mas um Wi-Fi lento aumenta esse intervalo.

### Página na internet

1. Dê dois cliques em `Publicar na internet.bat`. Na primeira vez, ele baixa o `cloudflared`, cerca de 55 MB, para `pc/ferramentas/`.
2. A janela mostra o endereço e a senha, e a página abre no navegador. Deixe a janela aberta.
3. Na janela de login do navegador, digite a senha. O usuário pode ser qualquer um.

Para encerrar, feche a janela. Isso também fecha o servidor, então não abra o `Iniciar servidor.bat` ao mesmo tempo.

Como funciona e quais são os limites:

- A placa continua enviando pela rede local, e a análise continua no PC. O túnel só leva a página à internet, com HTTPS.
- O endereço muda toda vez e só funciona com o PC ligado e a janela aberta. É um túnel rápido do Cloudflare, sem conta e sem garantia de disponibilidade, adequado para testes e demonstrações.
- As fotos dos rostos passam pela rede do Cloudflare. No PC, só a última foto fica guardada, e apenas na memória.
- A senha fica em `pc/senha_web.txt`, fora do git. Para trocá-la, apague o arquivo e abra o servidor de novo.

### Vídeo ao vivo

Dê dois cliques em `Iniciar expressoes.bat` e informe o IP da placa. O último IP fica salvo: da próxima vez, basta apertar Enter se ele não tiver mudado.

Na janela do vídeo:

| Ação | Resultado |
|---|---|
| Tecla `q` ou fechar a janela | Encerra o programa |
| Tecla `s` | Salva o quadro atual em `pc/capturas/` |

O modelo do projeto é o HSEmotion. Para compará-lo ao FER+ na mesma janela, inicie o `expressoes.py` com `--modelo ambos`: FER+ em verde e HSEmotion em amarelo.

Se a câmera cair, o programa continua tentando reconectar sozinho.

Para desligar a câmera, desconecte o cabo USB. Fechar o programa não desliga a placa.

## Testar sem a placa

Com `Iniciar servidor.bat` aberto, a página também abre no navegador. A janela do servidor mostra a senha. Em **Testar com uma foto**, escolha uma imagem com um rosto. Para encerrar, feche a janela do servidor.

O servidor também pode ser chamado por qualquer cliente HTTP:

```
POST http://127.0.0.1:5000/analisar
Content-Type: image/jpeg
<bytes da imagem>
```

```json
{"status": "OK", "expression": "happy", "label": "feliz", "confidence": 0.91, "faces": 1}
```

| `status` | Quando acontece |
|---|---|
| `OK` | Expressão identificada |
| `INCONCLUSIVE` | Confiança abaixo de 40%: `label` vem `inconclusivo` e `expression` vem nulo |
| `NO_FACE_DETECTED` | Nenhum rosto: `expression`, `label` e `confidence` vêm nulos e `faces` vem 0 |
| `INVALID_IMAGE` | Erro 400: o corpo não é uma imagem |
| `IMAGE_TOO_LARGE` | Erro 413: imagem maior que 5 MB |

Com vários rostos, a resposta é sobre o maior.

A página, a última foto e os resultados sempre pedem a senha. O envio de fotos só dispensa a senha para aparelhos da rede local, como a placa. Qualquer aparelho nessa rede pode enviar fotos, então use apenas em rede de confiança. Quem envia pela internet ou pelo próprio PC (`127.0.0.1`) precisa da senha. Iniciado direto pelo `servidor.py`, sem `--host 0.0.0.0`, ele só aceita conexões deste PC.

## Medir a qualidade do modelo

```powershell
cd pc
.venv\Scripts\python.exe validar.py dados\fer2013_test
```

A base de teste não faz parte do repositório. A pasta informada precisa de uma subpasta por classe, com os nomes `angry`, `disgust`, `fear`, `happy`, `neutral`, `sad` e `surprise`. Para fotos comuns, em vez de rostos já recortados, adicione `--com-detector`.

O padrão é o HSEmotion. Para avaliar o FER+, adicione `--modelo ferplus`.

Resultado dos dois modelos nas 7.178 imagens de teste do FER-2013:

| Expressão | FER+ | HSEmotion |
|---|---|---|
| Neutro | 91% | 55% |
| Feliz | 87% | 79% |
| Surpresa | 77% | 43% |
| Raiva | 38% | 49% |
| Triste | 24% | 47% |
| Nojo | 16% | 62% |
| Medo | 6% | 38% |
| **Acurácia geral** | **56,5%** | **54,8%** |
| **Média por classe** | **48,5%** | **53,1%** |

Os dois modelos também têm a classe "desprezo", que o projeto descarta por não fazer parte das 7 do FER-2013.

Esses números não aplicam o limite de confiança. No HSEmotion, com o limite de 40%, 10,3% das imagens ficam inconclusivas e o acerto nas demais sobe para 58,4%.

O FER+ tende a responder "neutro" quando está em dúvida. O HSEmotion distribui melhor as respostas, mas erra mais em neutro e surpresa. O FER-2013 tem rótulos reconhecidamente ruidosos e favorece o FER+, que foi treinado com essa mesma base. Esses números não medem o desempenho com a câmera real.

O projeto usa o HSEmotion por reconhecer melhor as expressões além de neutro e feliz, mesmo com acurácia geral um pouco menor neste teste.

## Endereços da placa

| Endereço | O que faz |
|---|---|
| `http://<ip>:81/stream` | Vídeo ao vivo |
| `http://<ip>/capture` | Uma foto JPEG |
| `http://<ip>/status` | Resolução, qualidade e PSRAM |

## Problemas comuns

| Sintoma | O que verificar |
|---|---|
| `nao conectou no Wi-Fi` no Serial Monitor | Nome e senha da rede, e se ela é de 2,4 GHz |
| `Câmera sem resposta` | Se a placa está ligada, se o IP mudou e se o PC está na mesma rede |
| `segredos.h: No such file or directory` ao compilar | Copie `segredos.exemplo.h` para `segredos.h` e preencha |
| `sem resposta do servidor` no Serial Monitor | Se o servidor está aberto, se o IP em `SERVIDOR_URL` é o do PC e se o firewall permite o acesso |
| O programa usa `/capture` e fica lento | Feche abas do navegador com o stream: a placa atende um stream por vez |
| `Ja existe um servidor aberto` | Feche a outra janela do servidor antes de abrir esta |
| A página pede senha | Ela aparece na janela do servidor e em `pc/senha_web.txt` |
| Serial Monitor em branco | Aperte o botão RST da placa |
| Imagem preta | Película na lente, pouca luz ou cabo flat da câmera mal encaixado |

## Desfazer a liberação do firewall

Em um terminal aberto como administrador:

```powershell
netsh advfirewall firewall delete rule name="Servidor de expressoes ESP32-CAM"
```
