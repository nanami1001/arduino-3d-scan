# 指導手冊 — Arduino 與 ESP32-CAM 3D 掃描系統

本手冊包含硬體與軟體操作指引，分為兩大部份：
1. 硬體指導手冊 — Arduino 與 ESP32-CAM 設備架設
2. 軟體指導手冊 — 系統介面與功能操作

---

## 1. 硬體指導手冊 — Arduino 與 ESP32-CAM 設備架設

### 1-1. 28BYJ-48 步進馬達接線與測試

#### 1-1-1. 硬體介紹
- 28BYJ-48 步進馬達規格說明：相對低速低扭矩步進馬達，常見 5V 驅動。
- ULN2003 驅動板介紹：四路輸出、具插座方便接線，內含驅動晶片。
- Arduino 腳位需求：需 4 個數位輸出腳位控制馬達線圈，及 5V 電源。

#### 1-1-2. 接線教學
- Arduino 與 ULN2003 接線方式：
  - ULN2003 VCC -> Arduino 5V（或外部 5V 電源，依馬達電流選擇）
  - ULN2003 GND -> Arduino GND
  - ULN2003 IN1..IN4 -> Arduino D2, D3, D4, D5（範例，可依需求調整）
- 28BYJ-48 與 ULN2003 接線方式：直接插入板上插座，確保方向正確。
- 電源供應注意事項：
  - 若使用多個馬達或長時間運轉，請使用獨立穩壓 5V 電源，避免直接使用 Arduino 5V 供電。
  - 檢查電源地線需共地（Arduino GND 與外部電源 GND 相連）。

#### 1-1-3. 接線檢查（範例圖片）
- 在 `instruction manual/` 資料夾放置：`28BYJ-48_circuit_example.png` 與實體接線照片。

內容需包含：
- 完整接線圖（示意圖）
- 實體接線照片（正確示範）
- 腳位對照表（例如：IN1->D2）
- 常見接線錯誤說明（例如：未共地、電源不足、線序接反）

#### 1-1-4. 28BYJ-48 測試程式碼（Arduino）
```cpp
#include <Stepper.h>

const int stepsPerRevolution = 2048; // 28BYJ-48 常用步數

// 接腳可依實際接線調整
const int IN1 = 2;
const int IN2 = 3;
const int IN3 = 4;
const int IN4 = 5;

Stepper stepper(stepsPerRevolution, IN1, IN3, IN2, IN4);

void setup() {
  Serial.begin(115200);
  stepper.setSpeed(10); // RPM
  Serial.println("Stepper test start");
}

void loop() {
  Serial.println("Rotate one revolution CW");
  stepper.step(stepsPerRevolution);
  delay(1000);
  Serial.println("Rotate one revolution CCW");
  stepper.step(-stepsPerRevolution);
  delay(1000);
}
```

內容需包含：
- Arduino 程式碼（如上）
- 程式碼註解說明（已在程式內註記）
- 上傳步驟：使用 Arduino IDE 選擇對應板子與 COM port，上傳。
- 執行結果說明：序列埠會列印流程，馬達順時針與逆時針各轉一圈。

---

### 1-2. ESP32-CAM 接線與模式切換

#### 1-2-1. ESP32-CAM 硬體介紹
- ESP32-CAM 模組說明：內建 OV2640 相機模組、Wi-Fi、少量 GPIO。
- FTDI 燒錄器介紹：用於串列燒錄（TTL 3.3V），請選用 3.3V 電平。
- 電源需求與注意事項：ESP32-CAM 在 Wi‑Fi 與攝影時電流尖峰較高，建議使用穩定 5V → 3.3V 轉換或 5V USB 供電並注意地線。

#### 1-2-2. 燒錄模式接線
- 將 FTDI TX->RX、RX->TX、GND->GND，5V/3.3V 視 FTDI 與模組電壓輸入而定（通常使用 5V 到模組的 5V 引腳或 3.3V）。
- 進入燒錄模式步驟（常見）：
  1. 將 GPIO0 拉低（接 GND）
  2. 按 reset 或斷電重上電
  3. 使用 Arduino IDE 或 esptool 開始燒錄
- 常見燒錄失敗排除：
  - 檢查 FTDI 是否為 3.3V TTL
  - 確認 GPIO0 已經拉低
  - 檢查驅動程式與 COM port
  - 若電源不足，嘗試更強的電源或外接 5V

內容需包含：
- ESP32-CAM 接線圖（放於 `instruction manual/esp32cam_circuit_example.png`）
- 燒錄模式切換步驟
- 常見燒錄失敗排除清單

#### 1-2-3. 攝影模式接線
- 正常運作接線方式：確保相機模組排線正確、電源穩定、IO0 解除拉低（浮空或拉高）。
- 啟動攝影模式流程：上電後模組進入正常執行模式，Wi‑Fi 可啟用並監聽影像串流。

#### 1-2-4. ESP32-CAM 程式碼（範例）
- 以下為常見的攝影串流示例（請依實際專案調整）
```cpp
#include "esp_camera.h"
#include <WiFi.h>

// 請填入自己的 SSID 與密碼
const char* ssid = "YOUR_SSID";
const char* password = "YOUR_PASSWORD";

void startCameraServer();

void setup() {
  Serial.begin(115200);
  WiFi.begin(ssid, password);
  while (WiFi.status() != WL_CONNECTED) {
    delay(500);
    Serial.print(".");
  }
  Serial.println("");
  Serial.print("Camera ready. IP: ");
  Serial.println(WiFi.localIP());

  // 初始化相機（請配置 camera_pins.h 與 camera_pins 設定）
  camera_config_t config;
  // ... 填入模組對應設定
  esp_camera_init(&config);

  startCameraServer();
}

void loop() {
  // 伺服器循環由庫處理
}
```

內容需包含：
- 攝影串流程式碼（範例如上）
- Wi‑Fi 設定方式（SSID/Password）
- IP 位址查看方法（序列埠列印）
- 網頁攝影介面操作說明（如何開啟瀏覽器、查看串流頁面、快照按鈕）

---

## 2. 軟體指導手冊 — 系統介面與功能操作

### 2-1. 系統介面介紹
內容需包含：
- 系統首頁說明：主視窗包含「3D 重建」分頁、參數面板與日誌區。
- 功能選單介紹：主選單提供「重建」、「載入 PLY」、「啟動採集器」等按鈕。
- 狀態顯示區說明：日誌區會顯示流程訊息、錯誤與完成通知。
- 操作流程概覽：從選擇模式 → 採集或使用現有樣本 → 重建 → 檢視 PLY。

### 2-2. 系統操作流程（建議）
1. 開啟系統：執行 `main_ui.py`（確保 Python 環境與相依套件已安裝）。
2. 連接設備：若使用 ESP32-CAM，確認模組已連上 Wi‑Fi 且可透過 IP 訪問。
3. 啟動攝影功能：在主介面選擇「使用影像採集設備從頭開始」，系統會啟動 `esp32_cam_capture.py` 進行擷取。
4. 查看運作結果：在主介面使用「載入 PLY」選擇已生成的單一 `.ply` 檔案，系統會顯示 3D 點雲與凸包視覺化。
5. 關閉系統：完成後關閉主視窗或停止採集/重建流程。

---

## 附錄：檢查清單與故障排除
- 常見問題：
  - PLY 無法載入：確認檔案存在且非空，檔名為 `*.ply`。
  - 採集器無法啟動：確認 `esp32_cam_capture.py` 可執行且在相同工作目錄。
  - 馬達不動或卡住：檢查接線、電源與步進參數。

---

## 檔案與圖片位置建議
- `instruction manual/28BYJ-48_circuit_example.png`
- `instruction manual/esp32cam_circuit_example.png`
- 本手冊檔案：`md/GUIDE_HARDWARE_SOFTWARE.md`

---

若您要我把 Arduino 範例上傳至 `Arduino hardware programming program/` 中或補上更多實測照片範例，我可以繼續把檔案加入專案。