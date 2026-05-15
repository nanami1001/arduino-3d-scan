#include "esp_camera.h"
#include <WiFi.h>
#include <WebServer.h>

#include "soc/soc.h"
#include "soc/rtc_cntl_reg.h"

// ========================================
// AI Thinker ESP32-CAM 腳位設定
// ========================================

#define PWDN_GPIO_NUM     32
#define RESET_GPIO_NUM    -1
#define XCLK_GPIO_NUM      0

#define SIOD_GPIO_NUM     26
#define SIOC_GPIO_NUM     27

#define Y9_GPIO_NUM       35
#define Y8_GPIO_NUM       34
#define Y7_GPIO_NUM       39
#define Y6_GPIO_NUM       36
#define Y5_GPIO_NUM       21
#define Y4_GPIO_NUM       19
#define Y3_GPIO_NUM       18
#define Y2_GPIO_NUM        5

#define VSYNC_GPIO_NUM    25
#define HREF_GPIO_NUM     23
#define PCLK_GPIO_NUM     22

// ========================================
// WiFi 設定
// ========================================

const char* ssid = "Redmi14";
const char* password = "1234aaaa";

// ========================================

WebServer server(80);

// ========================================
// 拍照 API
// ========================================

void handleCapture() {

  camera_fb_t * fb = esp_camera_fb_get();

  if (!fb) {
    server.send(500, "text/plain", "Camera capture failed");
    return;
  }

  WiFiClient client = server.client();

  client.println("HTTP/1.1 200 OK");
  client.println("Content-Type: image/jpeg");
  client.println("Content-Length: " + String(fb->len));
  client.println();

  client.write(fb->buf, fb->len);

  esp_camera_fb_return(fb);
}

// ========================================
// 主頁面
// ========================================

void handleRoot() {

  String html = R"rawliteral(
  <!DOCTYPE html>
  <html>
  <head>
      <meta charset="UTF-8">
      <title>ESP32-CAM</title>
      <style>
          body{
              background:#111;
              color:white;
              text-align:center;
              font-family:Arial;
          }

          img{
              width:90%;
              max-width:640px;
              border-radius:10px;
              margin-top:20px;
          }

          h1{
              margin-top:30px;
          }
      </style>
  </head>

  <body>

      <h1>ESP32-CAM Live</h1>

      <img src="/capture" id="cam">

      <script>

          setInterval(()=>{

              document.getElementById("cam").src =
              "/capture?t=" + new Date().getTime();

          },1000);

      </script>

  </body>
  </html>
  )rawliteral";

  server.send(200, "text/html", html);
}

// ========================================

void setup() {

  Serial.begin(115200);

  Serial.println();

  // 關閉 Brownout
  WRITE_PERI_REG(RTC_CNTL_BROWN_OUT_REG, 0);

  // ========================================
  // Camera Config
  // ========================================

  camera_config_t config;

  config.ledc_channel = LEDC_CHANNEL_0;
  config.ledc_timer = LEDC_TIMER_0;

  config.pin_d0 = Y2_GPIO_NUM;
  config.pin_d1 = Y3_GPIO_NUM;
  config.pin_d2 = Y4_GPIO_NUM;
  config.pin_d3 = Y5_GPIO_NUM;
  config.pin_d4 = Y6_GPIO_NUM;
  config.pin_d5 = Y7_GPIO_NUM;
  config.pin_d6 = Y8_GPIO_NUM;
  config.pin_d7 = Y9_GPIO_NUM;

  config.pin_xclk = XCLK_GPIO_NUM;

  config.pin_pclk = PCLK_GPIO_NUM;
  config.pin_vsync = VSYNC_GPIO_NUM;
  config.pin_href = HREF_GPIO_NUM;

  config.pin_sccb_sda = SIOD_GPIO_NUM;
  config.pin_sccb_scl = SIOC_GPIO_NUM;

  config.pin_pwdn = PWDN_GPIO_NUM;
  config.pin_reset = RESET_GPIO_NUM;

  config.xclk_freq_hz = 20000000;

  config.pixel_format = PIXFORMAT_JPEG;

  // 降低耗電提高穩定性
  config.frame_size = FRAMESIZE_QVGA;

  config.jpeg_quality = 12;

  config.fb_count = 1;

  // ========================================
  // 初始化 Camera
  // ========================================

  esp_err_t err = esp_camera_init(&config);

  if (err != ESP_OK) {

    Serial.printf("Camera init failed: 0x%x\n", err);

    return;
  }

  Serial.println("Camera Init OK");

  // ========================================
  // WiFi
  // ========================================

  WiFi.mode(WIFI_STA);

  WiFi.begin(ssid, password);

  Serial.print("WiFi Connecting");

  int retry = 0;

  while (WiFi.status() != WL_CONNECTED && retry < 40) {

    delay(500);

    Serial.print(".");

    retry++;
  }

  if (WiFi.status() == WL_CONNECTED) {

    Serial.println();
    Serial.println("WiFi Connected!");

    Serial.print("IP Address: ");
    Serial.println(WiFi.localIP());

  } else {

    Serial.println();
    Serial.println("WiFi Failed!");

    return;
  }

  // ========================================
  // Web Server
  // ========================================

  server.on("/", handleRoot);

  server.on("/capture", HTTP_GET, handleCapture);

  server.begin();

  Serial.println("Camera Server Started");

  Serial.print("Open Browser: http://");
  Serial.println(WiFi.localIP());
}

// ========================================

void loop() {

  server.handleClient();
}