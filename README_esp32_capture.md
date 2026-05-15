# ESP32-CAM 定時圖片採集 — 範例說明

此範例提供一個可直接執行的 Python 工具 `esp32_cam_capture.py`，可定時向 ESP32-CAM 的 HTTP API 擷取影像並儲存到本地資料夾，適合作為建立影像資料集（AI Dataset）之用。

主要特性

- 支援秒或毫秒級的間隔（例如 `5`, `0.5`, `500ms`）
- 支援設定總張數 `--total`
- 自動建立儲存資料夾
- 依序編號命名（1.png, 2.png, ...），啟動時會從資料夾內現有檔案決定下一個編號以避免覆蓋
- 支援 `png`, `jpg`, `jpeg` 副檔名
- 提供錯誤處理、重試與略過失敗選項

快速開始

1. 安裝依賴（建議建立虛擬環境）

```bash
pip install -r requirements.txt
```

2. 執行範例（每 5 秒拍 100 張，存到 `dataset/train`，副檔名 png）：

```bash
python esp32_cam_capture.py --url http://192.168.1.100/capture --interval 5 --total 100 --save dataset/train --format png
```

3. 毫秒範例（每 500 毫秒拍 100 張）：

```bash
python esp32_cam_capture.py --url http://192.168.1.100/capture --interval 500ms --total 100 --save dataset/train --format jpg
```

重要參數

- `--url / -u`：ESP32-CAM 的 capture API，例如 `http://192.168.1.100/capture`
- `--interval / -i`：採集間隔，支援秒或 `ms` 後綴
- `--total / -n`：總張數
- `--save / -d`：儲存資料夾
- `--format / -f`：副檔名（png/jpg/jpeg）
- `--max-retries`：發生錯誤時重試次數（預設 2）
- `--retry-delay`：重試間隔（秒）
- `--skip-failed`：遇到失敗時略過並繼續

日誌範例

- 成功：

```
[1/100] Capturing...
Saved: dataset/train/1.png
```

- 失敗：

```
[2/100] Capturing...
Capture Failed: Timeout after 10s
Skipped failed capture.
```

進階建議

- 若需要高頻率（ms 級）且長時間穩定採集，建議把儲存工作丟到背景緒或寫入快取佇列，避免網路或儲存 I/O 拉長 capture 耗時。
- 若要做多台 ESP32 同時採集，可用多個進程或非同步實作（此範例為同步簡單實作）。
