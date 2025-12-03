## 快速啟動指南 (Quick Start)

### 🚀 最快 3 分鐘開始

#### 1️⃣ **不需硬體 — 試試看 GUI**（推薦首先嘗試）

```powershell
# 開啟互動式檢查清單介面（演示版本）
python check_interface.py

# 或整合版本（模擬掃描 + GUI）
python scan_with_checklist.py
```

✨ 你會看到：
- 九步驟檢查清單
- 點擊 "▶ 開始掃描" 看狀態更新
- 綠色 ✓ 成功、紅色 ✗ 失敗、藍色 ⟳ 進行中

---

#### 2️⃣ **模擬完整流程**（仍無需硬體）

```powershell
# 生成 36 張模擬影像 + 體素雕刻 + 視覺化
python scan_and_reconstruct.py --simulate --num_images 36 --visualize

# 或金字塔形狀（3 層 × 36 圖像）
python scan_and_reconstruct.py --simulate --sim_shape pyramid --per_ring 36 --rings 3 --visualize
```

✨ 結果位置：
- 影像：`scan_images/img_000.jpg` ... `img_035.jpg`
- 點雲：`scan_images/result.ply` ← 用以下命令查看

---

#### 3️⃣ **查看現有重建結果**（最簡單）

```powershell
# 顯示 3D 點雲 + 自動 ConvexHull 邊界網格
python scan_and_reconstruct.py --visualize-only
```

✨ 開啟 matplotlib 3D 視窗
- 藍色點 = 重建的 3D 點
- 紅色線 = 自動計算的邊界網格

---

### 📋 命令參考

| 命令 | 用途 |
|------|------|
| `python check_interface.py` | 開啟 GUI 檢查清單（演示） |
| `python scan_with_checklist.py` | 掃描 + GUI（實際執行） |
| `python scan_and_reconstruct.py --simulate --visualize` | 模擬掃描 + 結果 |
| `python scan_and_reconstruct.py --visualize-only` | 查看現有結果 |

---

### 🔧 初次使用（有硬體）

1. **安裝依賴**
   ```powershell
   pip install -r requirements.txt
   ```

2. **配置韌體**
   - 編輯 `esp32cam_capture.ino`：設定 WiFi SSID/密碼
   - 燒錄至 ESP32-CAM，記下 IP 地址
   - 燒錄 `TurntableController.ino` 至 Arduino

3. **執行掃描**
   ```powershell
   python scan_with_checklist.py
   # 程式會自動提示輸入 IP 和 COM 埠
   ```

---

### 🎯 常見用法

```powershell
# 基本掃描 36 張影像
python scan_and_reconstruct.py --esp 192.168.1.100 --serial COM3 --num_images 36

# 高品質掃描（72 張 + 高分辨率）
python scan_and_reconstruct.py --esp 192.168.1.100 --serial COM3 --num_images 72 --voxel_res 64

# 快速掃描（低分辨率）
python scan_and_reconstruct.py --esp 192.168.1.100 --serial COM3 --num_images 36 --voxel_res 16

# 模擬 + 視覺化
python scan_and_reconstruct.py --simulate --num_images 36 --visualize
```

---

### 📊 預期輸出

```
Angle step: 10.0 deg; steps per angle: 56.88...
Capture finished. Images saved: 36
Carving: 100% |████████| 36/36
Points: (2450, 3)
Saved PLY: scan_images/result.ply
ConvexHull computed: 1250 triangles, volume=0.054321
```

---

### ❓ 遇到問題？

| 問題 | 解決 |
|------|------|
| `ModuleNotFoundError` | `pip install -r requirements.txt` |
| Serial 打不開 | 自動降級到 `--simulate` 模式 |
| ESP32 連不上 | 檢查 IP 和 WiFi，用 `--simulate` 先測試 |
| GUI 沒出現 | Windows 通常已有 tkinter；Linux 須安裝 |

---

### 📚 完整說明

- 詳見 `README_NEW.md`（完整中文文檔）
- GUI 說明：`CHECKLIST_GUIDE.md`
- 原始設計稿：`check.png` (337×630)

---

**祝你掃描愉快！** 🎉
