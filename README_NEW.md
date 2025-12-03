# Arduino + ESP32-CAM 3D 掃描系統

## 簡介

本專案提供一個**完整的 3D 物體掃描解決方案**，結合 Arduino 轉盤控制、ESP32-CAM 影像擷取、和 PC 端 Python 重建協調。

### 核心元件

| 檔案 | 用途 |
|------|------|
| `TurntableController.ino` | Arduino 控制 28BYJ-48 步進馬達 + ULN2003 驅動器 |
| `esp32cam_capture.ino` | ESP32-CAM 韌體，提供 HTTP `/capture` 接口 |
| `scan_and_reconstruct.py` | PC 協調程式：轉盤控制 → 影像擷取 → 體素雕刻 → PLY 輸出 |
| `check_interface.py` | **[新增]** GUI 檢查清單（9 步驟監控） |
| `scan_with_checklist.py` | **[新增]** 掃描 + 實時 UI 狀態更新 |

## 先決條件

- **硬體**
  - Arduino UNO（或相容）+ USB 線
  - ESP32-CAM（AI-Thinker 常見腳位）+ USB 線
  - 28BYJ-48 步進馬達 + ULN2003 驅動模組
  - 轉盤機構（3D 列印或商用）

- **軟體**
  - Windows PC + Python 3.7+
  - Arduino IDE（燒錄韌體）
  - ESP-IDF 或 Arduino IDE for ESP32

## 快速上手

### 1. 環境設置

```powershell
# 建立虛擬環境
python -m venv .venv
.\.venv\Scripts\Activate.ps1

# 安裝相依套件
pip install -r requirements.txt
```

### 2. 韌體配置

**ESP32-CAM 設定**
```cpp
// esp32cam_capture.ino 中修改
const char* ssid = "YOUR_SSID";
const char* password = "YOUR_PASSWORD";
```
- 燒錄後，Serial Monitor (115200) 會顯示 IP 地址
- 若使用 AP 模式，預設 IP 為 `192.168.4.1`

**Arduino 設定**
- 確認上傳 `TurntableController.ino` 至 Arduino
- 檢查 COM 埠號（開裝置管理員）
- 28BYJ-48 接線：IN1-4 接 ULN2003 OUT 腳位 26-29

### 3. 執行掃描

#### 方法 A：命令列（簡單模式）
```powershell
# 基本掃描（需要硬體連接）
python scan_and_reconstruct.py --esp 192.168.1.100 --serial COM3 --num_images 36

# 指定體素分辨率
python scan_and_reconstruct.py --esp 192.168.1.100 --serial COM3 --voxel_res 32

# 掃描後自動視覺化
python scan_and_reconstruct.py --esp 192.168.1.100 --serial COM3 --visualize
```

#### 方法 B：GUI 檢查清單（推薦）✨ **新增**
```powershell
# 獨立演示版（無需硬體）
python check_interface.py

# 整合掃描 + GUI（實際掃描）
python scan_with_checklist.py
```

#### 方法 C：模擬模式（無硬體測試）
```powershell
# 模擬 36 張影像
python scan_and_reconstruct.py --simulate --num_images 36 --visualize

# 模擬金字塔（3 層 × 36 圖像 = 108 張）
python scan_and_reconstruct.py --simulate --sim_shape pyramid --per_ring 36 --rings 3

# 自動降級（Serial 打不開時自動改用模擬）
python scan_and_reconstruct.py --esp 192.168.1.100 --serial COM3 --num_images 36
```

### 4. 查看結果

```powershell
# 視覺化現有結果（帶 ConvexHull 邊界網格）✨ **新增**
python scan_and_reconstruct.py --visualize-only

# 結果位置
# - 影像：scan_images/img_000.jpg ... img_035.jpg
# - 點雲：scan_images/result.ply
```

## GUI 檢查清單介面

✨ **新增（2025-12-03）**

### 功能

| 項目 | 說明 |
|------|------|
| **9 步驟流程** | 硬體偵測 → Serial → WiFi → 轉盤校準 → 影像擷取 → 處理 → 體素雕刻 → 匯出 → 視覺化 |
| **即時狀態指示** | ✓ (成功) / ✗ (失敗) / ⟳ (進行中) / ○ (待命) |
| **色彩編碼** | 綠 (#4CAF50) 成功 / 紅 (#F44336) 失敗 / 藍 (#2196F3) 進行中 / 灰 (#CCCCCC) 待命 |
| **詳細訊息** | 每項顯示狀態、時間戳記及錯誤詳情 |
| **互動按鈕** | ▶ 開始 / ⏹ 停止 / ↻ 重設 / 💾 匯出 |

### 使用範例

```powershell
# 啟動 GUI
python scan_with_checklist.py

# 點擊 "▶ 開始掃描" 開始執行
# GUI 會實時顯示每個步驟的進度
# 完成後自動切至視覺化
```

詳細說明見 `CHECKLIST_GUIDE.md`

## 核心算法

### Voxel Carving (Visual Hull)

```
For each voxel (x, y, z) in 3D grid:
    For each camera view:
        1. 投影 voxel 至 2D 影像平面
        2. 讀取二值化矽脫圖像 silhouette[u, v]
        3. 若 silhouette[u, v] 為背景 → carve (移除) voxel
    If voxel 未被任何視圖 carve → 保留為點雲

Output: 點雲 (X, Y, Z) → 存為 PLY 格式
```

### 影像處理流程

```
原始 JPEG
  ↓ (灰階)
灰階影像
  ↓ (高斯模糊)
模糊影像
  ↓ (Otsu 自適應二值化)
矽脫圖像（白 = 物體，黑 = 背景）
```

## 完整命令列選項

```
usage: scan_and_reconstruct.py [-h] [--esp ESP] [--serial SERIAL]
                               [--steps_per_rev STEPS_PER_REV]
                               [--num_images NUM_IMAGES] [--out OUT]
                               [--voxel_res VOXEL_RES] [--simulate]
                               [--visualize] [--visualize-only]
                               [--sim_shape SIM_SHAPE] [--per_ring PER_RING]
                               [--rings RINGS] [--sim_radius SIM_RADIUS]
                               [--sim_apex SIM_APEX] [--elev_step ELEV_STEP]

options:
  -h, --help                     Show help message
  --esp ESP                      ESP32-CAM IP (default: 192.168.1.100)
  --serial SERIAL                Arduino Serial port (default: COM3)
  --steps_per_rev STEPS_PER_REV  Steps per motor revolution (default: 2048)
  --num_images NUM_IMAGES        Number of images to capture (default: 36)
  --out OUT                      Output folder (default: scan_images)
  --voxel_res VOXEL_RES          Voxel grid resolution (default: 64, max 128)
  --simulate                     Run without hardware (simulation mode)
  --visualize                    Show visualization after capture
  --visualize-only               View existing results without capture
  --sim_shape SIM_SHAPE          Simulation shape: 'ellipse' or 'pyramid'
  --per_ring PER_RING            Images per horizontal ring (simulation)
  --rings RINGS                  Number of elevation rings (simulation)
  --sim_radius SIM_RADIUS        Camera radius in meters (simulation)
  --sim_apex SIM_APEX            Pyramid apex height in meters (simulation)
  --elev_step ELEV_STEP          Elevation step between rings in degrees
```

## 進階用法

### 自訂 GUI 項目

```python
from check_interface import CheckItem, create_check_interface

root, checklist = create_check_interface()

# 新增項目
item = CheckItem("自訂檢查", "項目描述")
checklist.add_item(item)

# 更新狀態
checklist.update_item(index, "success", "完成訊息")
checklist.update_item(index, "failed", "錯誤訊息")

root.mainloop()
```

### 與掃描程式集成

```python
from scan_with_checklist import ScannerWithUI

scanner = ScannerWithUI(root, checklist)
scanner.start_scan(
    esp_ip="192.168.1.100",
    serial_port="COM3",
    num_images=36,
    voxel_res=32
)
```

### 提高重建品質

```powershell
# 增加影像數量 + 更高分辨率
python scan_and_reconstruct.py --num_images 72 --voxel_res 64

# 注意：voxel_res^3 會影響記憶體使用和時間
# voxel_res=32 → 32K 個體素 (快速)
# voxel_res=64 → 262K 個體素 (中等)
# voxel_res=128 → 2M 個體素 (很慢，需 8GB+ RAM)
```

## 最佳實踐

| 項目 | 建議 |
|------|------|
| **背景** | 使用均勻、對比度高的背景（黑色推薦） |
| **光線** | 柔光、均勻照亮、避免陰影和反光 |
| **物體** | 小於 30cm、無透明部分、表面能反光 |
| **馬達速度** | 調整 `stepDelay` 避免抖動（通常 5-10ms） |
| **影像數** | 36 或 72 張（需要平衡品質和時間） |
| **體素分辨率** | 32-64（32 快速，64 品質好） |

## 故障排除

| 問題 | 原因 | 解決方案 |
|------|------|--------|
| **Serial 打不開** | COM 埠不存在或被佔用 | 檢查裝置管理員，自動降級到模擬模式 |
| **ESP32 連不上** | IP 錯誤或 WiFi 問題 | 檢查 Serial Monitor 確認 IP 地址 |
| **影像模糊** | 馬達抖動或對焦問題 | 增加 `stepDelay` 或調整 `delayBetweenFrames` |
| **體素雕刻太慢** | 分辨率過高 | 降低 `--voxel_res` 或增加 RAM |
| **GUI 無法啟動** | tkinter 缺失 | Linux: `sudo apt install python3-tk` |
| **點雲稀疏** | 背景去除不完整 | 改善光線、調整 Otsu 門檻值 |

## 改進方向

- [ ] 使用 NumPy/Numba 向量化 voxel carving（10-100 倍加速）
- [ ] 實現 Marching Cubes 導出 STL/OBJ 網格
- [ ] 加入轉盤 homing 與限位開關
- [ ] 支援背景相減（背景圖影像）
- [ ] 自動 IP 發現（ESP32-CAM）
- [ ] WebUI 遠端監控
- [ ] CUDA/OpenCL GPU 加速

## 系統需求

- **硬體**：Windows PC, 4GB RAM (建議 8GB+), USB 埠 ×2
- **軟體**：Python 3.7+, tkinter (已內建)
- **套件**：見 `requirements.txt`

安裝全部依賴：
```bash
pip install -r requirements.txt
```

## 許可證

MIT License (自由使用、修改、發佈)

## 版本紀錄

| 版本 | 日期 | 更新 |
|------|------|------|
| v1.2 | 2025-12-03 | ✨ GUI 檢查清單、自動降級、ConvexHull 邊界網格、scipy 支援 |
| v1.1 | 2025-12-03 | `--visualize-only`、`--simulate` 模式、Pyramid 模擬 |
| v1.0 | 初版 | 基本掃描、擷取、體素雕刻 |

## 相關文件

- `CHECKLIST_GUIDE.md` — GUI 詳細說明
- `check.png` — 原始 UI 設計稿 (337×630 像素)
- `requirements.txt` — 相依套件清單

## 支援與聯絡

如有問題或改進建議，歡迎提交 Issue 或 Pull Request。

---

**最後更新**：2025-12-03  
**作者**：Arduino 3D Scanning Project  
**狀態**：積極維護中
