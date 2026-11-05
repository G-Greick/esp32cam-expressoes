// Configuracoes desta placa.
// Copie este arquivo para segredos.h, na mesma pasta, e preencha os valores.
// O segredos.h fica fora do git: nunca publique a senha do Wi-Fi.

// Rede Wi-Fi de 2,4 GHz (o ESP32 nao conecta em 5 GHz).
const char *WIFI_SSID = "NOME_DA_REDE";
const char *WIFI_SENHA = "SENHA_DA_REDE";

// Endereco do PC que roda o servidor. Se o IP do PC mudar, atualize aqui e grave de novo.
const char *SERVIDOR_URL = "http://IP_DO_PC:5000/analisar";
