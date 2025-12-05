### 檢查清單介面使用說明

**check_interface.py** 和 **scan_with_checklist.py** 提供了一個完整的 GUI 介面用於監控 3D 掃描過程。

---

#### 功能特性

| 功能 | 說明 |
|------|------|
| **九步驟檢查清單** | 硬體偵測 → Serial → WiFi → 轉盤校準 → 影像擷取 → 影像處理 → 體素雕刻 → 結果匯出 → 視覺化 |
| **實時狀態更新** | ✓ (完成) / ✗ (失敗) / ⟳ (進行中) / ○ (待命) |
| **顏色編碼** | 綠色 (成功)、紅色 (失敗)、藍色 (進行中)、灰色 (待命) |
| **詳細描述** | 每個項目顯示狀態訊息和時間戳記 |
| **互動按鈕** | ▶ 開始掃描 / ⏹ 停止 / ↻ 重設 / 💾 匯出結果 |

---

#### 運行方式

**1. 獨立運行檢查清單介面（演示模式）**
```bash
python check_interface.py
```
- 顯示 9 個預設檢查項目
- 可點擊 "▶ 開始掃描" 查看狀態變化演示
- 適合測試 UI 外觀和交互

**2. 運行整合的掃描 + 檢查清單（實際掃描）**
```bash
python scan_with_checklist.py
```
- 啟動 GUI 與掃描過程後台協作
- 點擊 "▶ 開始掃描" 開始實際 3D 掃描
- 檢查清單即時顯示每個步驟的進度
- 支持 "⏹ 停止" 中止掃描
- 完成後自動顯示結果

---

#### 檢查項目解說

| 項目 | 檢查內容 |
|------|---------|
| 硬體偵測 | 驗證 Arduino UNO 連接（Serial 埠） |
| Serial 口配置 | 確認 115200 波特率與通訊穩定 |
| WiFi 連線 | 檢查 ESP32-CAM HTTP 伺服器可達 |
| 轉盤校準 | 初始化步進馬達和轉盤零位 |
| 影像擷取 | 旋轉 → 擷取 JPEG → 儲存迴圈 |
| 影像處理 | 灰階 → 高斯模糊 → Otsu 二值化 |
| 體素雕刻 | Visual Hull 3D 重建演算法 |
| 結果匯出 | 生成 ASCII PLY 點雲檔案 |
| 視覺化 | 3D 散點圖 + ConvexHull 邊界網格 |

---

#### 與 check.png 的關聯

原始的 **check.png** (337×630) 是檢查清單的設計稿，包含：
- ✓ 綠色成功標記
- ✗ 紅色錯誤標記
- 多個檢查項目卡片
- 白色背景與整潔的排版

我們實現的 GUI 採用相同的色彩方案和結構，提供互動式版本。

---

#### 進階用法

**自訂檢查項目**
```python
from check_interface import CheckItem

item = CheckItem("自訂項目", "項目描述")
checklist.add_item(item)
checklist.update_item(index, "success", "完成訊息")
```

**與掃描程式集成**
```python
from scan_with_checklist import ScannerWithUI

scanner = ScannerWithUI(root, checklist)
scanner.start_scan(esp_ip="192.168.1.100", serial_port="COM3", 
                   num_images=36, voxel_res=32)
```

---

#### 色彩定義

- **#4CAF50 (綠色)** — 成功/完成
- **#F44336 (紅色)** — 失敗/錯誤
- **#2196F3 (藍色)** — 進行中/載入
- **#CCCCCC (灰色)** — 待命/未開始
- **#FFFFFF (白色)** — 背景
- **#333333 (深色)** — 文字

---

#### 系統需求

- Python 3.7+
- tkinter (標準庫，Windows 通常已包含)
- 相依套件: pyserial, requests, opencv-python, numpy, scipy, matplotlib

安裝所有依賴:
```bash
pip install -r requirements.txt
```

---

#### 故障排除

**Q: GUI 沒有出現**
- 確認 tkinter 已安裝: `python -m tkinter`
- Linux 使用者: `sudo apt install python3-tk`

**Q: 掃描卡在某一步**
- 檢查 Arduino/ESP32 連接
- 驗證 Serial 埠和 IP 設定正確
- 點擊 "⏹ 停止" 後重試

**Q: 顏色顯示不正確**
- 更新操作系統和 Python
- 檢查終端/IDE 的字體編碼 (UTF-8)

---

#### 相關檔案

- `check_interface.py` — 檢查清單 UI 元件
- `scan_with_checklist.py` — 掃描 + 檢查清單整合
- `scan_and_reconstruct.py` — 核心掃描邏輯
- `check.png` — 原始設計稿 (337×630)

---

**更新時間**: 2025-12-03  
**版本**: 1.0  
**許可証**: MIT
