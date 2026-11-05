// ESP32-CAM (AI Thinker) - captura imagens para classificação de expressões no PC.
//
// A cada 5 segundos, envia uma foto ao servidor do PC (pc/servidor.py) e mostra o
// resultado no monitor serial. O envio pausa enquanto alguém assiste ao stream.
//
// Endpoints:
//   http://<ip>/capture     -> uma foto JPEG
//   http://<ip>/status      -> JSON com resolução/qualidade/sinal Wi-Fi (rssi, em dBm)
//   http://<ip>:81/stream   -> vídeo MJPEG (abre no navegador ou no OpenCV)

#include "esp_camera.h"
#include "esp_http_server.h"
#include <HTTPClient.h>
#include <WiFi.h>

// Wi-Fi e endereco do servidor: copie segredos.exemplo.h para segredos.h e preencha.
#include "segredos.h"

const unsigned long INTERVALO_ENVIO_MS = 5000;

static volatile bool stream_ativo = false;

// Pinagem da câmera no AI Thinker ESP32-CAM
#define PWDN_GPIO_NUM 32
#define RESET_GPIO_NUM -1
#define XCLK_GPIO_NUM 0
#define SIOD_GPIO_NUM 26
#define SIOC_GPIO_NUM 27
#define Y9_GPIO_NUM 35
#define Y8_GPIO_NUM 34
#define Y7_GPIO_NUM 39
#define Y6_GPIO_NUM 36
#define Y5_GPIO_NUM 21
#define Y4_GPIO_NUM 19
#define Y3_GPIO_NUM 18
#define Y2_GPIO_NUM 5
#define VSYNC_GPIO_NUM 25
#define HREF_GPIO_NUM 23
#define PCLK_GPIO_NUM 22

#define BOUNDARY "frame"
static const char *STREAM_CONTENT_TYPE = "multipart/x-mixed-replace;boundary=" BOUNDARY;
static const char *STREAM_BOUNDARY = "\r\n--" BOUNDARY "\r\n";
static const char *STREAM_PART = "Content-Type: image/jpeg\r\nContent-Length: %u\r\n\r\n";

static esp_err_t capture_handler(httpd_req_t *req) {
  camera_fb_t *fb = esp_camera_fb_get();
  if (!fb) {
    httpd_resp_send_500(req);
    return ESP_FAIL;
  }
  httpd_resp_set_type(req, "image/jpeg");
  httpd_resp_set_hdr(req, "Access-Control-Allow-Origin", "*");
  esp_err_t res = httpd_resp_send(req, (const char *)fb->buf, fb->len);
  esp_camera_fb_return(fb);
  return res;
}

static esp_err_t status_handler(httpd_req_t *req) {
  sensor_t *s = esp_camera_sensor_get();
  char json[96];
  snprintf(json, sizeof(json), "{\"framesize\":%d,\"quality\":%d,\"psram\":%s,\"rssi\":%d}",
           s->status.framesize, s->status.quality, psramFound() ? "true" : "false", (int)WiFi.RSSI());
  httpd_resp_set_type(req, "application/json");
  httpd_resp_set_hdr(req, "Access-Control-Allow-Origin", "*");
  return httpd_resp_send(req, json, HTTPD_RESP_USE_STRLEN);
}

static esp_err_t stream_handler(httpd_req_t *req) {
  char part[64];
  esp_err_t res = httpd_resp_set_type(req, STREAM_CONTENT_TYPE);
  httpd_resp_set_hdr(req, "Access-Control-Allow-Origin", "*");
  stream_ativo = true;
  while (res == ESP_OK) {
    camera_fb_t *fb = esp_camera_fb_get();
    if (!fb) {
      res = ESP_FAIL;
      break;
    }
    size_t hlen = snprintf(part, sizeof(part), STREAM_PART, fb->len);
    res = httpd_resp_send_chunk(req, STREAM_BOUNDARY, strlen(STREAM_BOUNDARY));
    if (res == ESP_OK) res = httpd_resp_send_chunk(req, part, hlen);
    if (res == ESP_OK) res = httpd_resp_send_chunk(req, (const char *)fb->buf, fb->len);
    esp_camera_fb_return(fb);
  }
  stream_ativo = false;
  return res;
}

static void iniciar_servidores() {
  httpd_config_t config = HTTPD_DEFAULT_CONFIG();
  httpd_handle_t principal = NULL;
  if (httpd_start(&principal, &config) == ESP_OK) {
    httpd_uri_t capture = {"/capture", HTTP_GET, capture_handler, NULL};
    httpd_uri_t status = {"/status", HTTP_GET, status_handler, NULL};
    httpd_register_uri_handler(principal, &capture);
    httpd_register_uri_handler(principal, &status);
  }

  // O stream fica num servidor separado (porta 81) porque ocupa a conexão indefinidamente.
  config.server_port = 81;
  config.ctrl_port += 1;
  httpd_handle_t stream = NULL;
  if (httpd_start(&stream, &config) == ESP_OK) {
    httpd_uri_t s = {"/stream", HTTP_GET, stream_handler, NULL};
    httpd_register_uri_handler(stream, &s);
  }
}

static bool iniciar_camera() {
  camera_config_t c = {};
  c.ledc_channel = LEDC_CHANNEL_0;
  c.ledc_timer = LEDC_TIMER_0;
  c.pin_d0 = Y2_GPIO_NUM;
  c.pin_d1 = Y3_GPIO_NUM;
  c.pin_d2 = Y4_GPIO_NUM;
  c.pin_d3 = Y5_GPIO_NUM;
  c.pin_d4 = Y6_GPIO_NUM;
  c.pin_d5 = Y7_GPIO_NUM;
  c.pin_d6 = Y8_GPIO_NUM;
  c.pin_d7 = Y9_GPIO_NUM;
  c.pin_xclk = XCLK_GPIO_NUM;
  c.pin_pclk = PCLK_GPIO_NUM;
  c.pin_vsync = VSYNC_GPIO_NUM;
  c.pin_href = HREF_GPIO_NUM;
  c.pin_sccb_sda = SIOD_GPIO_NUM;
  c.pin_sccb_scl = SIOC_GPIO_NUM;
  c.pin_pwdn = PWDN_GPIO_NUM;
  c.pin_reset = RESET_GPIO_NUM;
  c.xclk_freq_hz = 20000000;
  c.pixel_format = PIXFORMAT_JPEG;
  // VGA (640x480) é suficiente para detectar rostos a ~1-2 m e mantém um bom FPS.
  c.frame_size = FRAMESIZE_VGA;
  c.jpeg_quality = 12;  // 0-63, menor = melhor qualidade
  c.grab_mode = CAMERA_GRAB_LATEST;
  if (psramFound()) {
    c.fb_location = CAMERA_FB_IN_PSRAM;
    c.fb_count = 2;
  } else {
    c.fb_location = CAMERA_FB_IN_DRAM;
    c.fb_count = 1;
    c.frame_size = FRAMESIZE_QVGA;
  }

  esp_err_t err = esp_camera_init(&c);
  if (err != ESP_OK) {
    Serial.printf("ERRO: falha ao iniciar a camera (0x%x)\n", err);
    return false;
  }
  // A imagem saía um pouco escura: compensa a exposição e o brilho (escala de -2 a 2).
  sensor_t *s = esp_camera_sensor_get();
  s->set_ae_level(s, 1);
  s->set_brightness(s, 1);
  Serial.printf("Camera OK (PSRAM: %s)\n", psramFound() ? "sim" : "nao");
  return true;
}

// Lê um campo simples do JSON da resposta. Devolve "" se não existir.
static String campo_json(const String &json, const char *nome) {
  String chave = String("\"") + nome + "\":";
  int inicio = json.indexOf(chave);
  if (inicio < 0) return "";
  inicio += chave.length();
  while (json[inicio] == ' ') inicio++;
  if (json[inicio] == '"') {
    int fim = json.indexOf('"', inicio + 1);
    return fim < 0 ? "" : json.substring(inicio + 1, fim);
  }
  int fim = inicio;
  while (fim < (int)json.length() && json[fim] != ',' && json[fim] != '}') fim++;
  return json.substring(inicio, fim);
}

static void enviar_foto() {
  camera_fb_t *fb = esp_camera_fb_get();
  if (!fb) {
    Serial.println("ERRO: falha ao capturar a foto");
    return;
  }

  HTTPClient http;
  http.setConnectTimeout(3000);
  http.setTimeout(10000);
  http.begin(SERVIDOR_URL);
  http.addHeader("Content-Type", "image/jpeg");
  int status = http.POST(fb->buf, fb->len);
  esp_camera_fb_return(fb);

  if (status == 200) {
    String resposta = http.getString();
    if (campo_json(resposta, "faces") == "0") {
      Serial.println("Nenhum rosto na imagem");
    } else {
      int confianca = (int)(campo_json(resposta, "confidence").toFloat() * 100 + 0.5);
      Serial.printf("Expressao: %s (%d%%)\n", campo_json(resposta, "label").c_str(), confianca);
    }
  } else if (status > 0) {
    Serial.printf("ERRO: o servidor respondeu com o codigo %d\n", status);
  } else {
    Serial.printf("ERRO: sem resposta do servidor (%s). Ele esta aberto no PC?\n",
                  http.errorToString(status).c_str());
  }
  http.end();
}

void setup() {
  Serial.begin(115200);
  Serial.println();

  if (!iniciar_camera()) {
    delay(5000);
    ESP.restart();
  }

  WiFi.mode(WIFI_STA);
  WiFi.setSleep(false);  // evita travadas no stream
  WiFi.begin(WIFI_SSID, WIFI_SENHA);
  Serial.printf("Conectando em \"%s\"", WIFI_SSID);
  unsigned long inicio = millis();
  while (WiFi.status() != WL_CONNECTED) {
    delay(500);
    Serial.print(".");
    if (millis() - inicio > 20000) {
      Serial.println("\nERRO: nao conectou no Wi-Fi. Confira nome/senha e se a rede e 2,4 GHz.");
      delay(5000);
      ESP.restart();
    }
  }
  Serial.println();

  iniciar_servidores();
  String ip = WiFi.localIP().toString();
  Serial.println("Pronto!");
  Serial.printf("  Sinal Wi-Fi: %d dBm\n", (int)WiFi.RSSI());
  Serial.println("  Foto:   http://" + ip + "/capture");
  Serial.println("  Stream: http://" + ip + ":81/stream");
  Serial.printf("Enviando fotos para %s\n", SERVIDOR_URL);
}

void loop() {
  static unsigned long ultimo_envio = 0;
  if (!stream_ativo && millis() - ultimo_envio >= INTERVALO_ENVIO_MS) {
    enviar_foto();
    ultimo_envio = millis();
  }
  delay(50);
}
