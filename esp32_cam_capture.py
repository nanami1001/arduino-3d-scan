"""
ESP32-CAM 圖像採集器（GUI 版）

流程：
1. 啟動後先輸入 ESP32-CAM 影像串流網址
2. 用滑桿設定採集間隔 0.1 ~ 5.0 秒
3. 程式固定以 10 秒 / 圈計算每圈採集張數
4. 擷取完成後，使用相同的 num_photo 觸發 PLY 重建
"""
from __future__ import annotations

import re
import signal
import threading
import time
from pathlib import Path

import requests
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from build_ply import ensure_ply_exists

TURNTABLE_PERIOD_SECONDS = 10.0
CAPTURE_INTERVAL_MIN = 0.1
CAPTURE_INTERVAL_MAX = 5.0
CAPTURE_INTERVAL_STEP = 0.1
DEFAULT_SAVE_DIR = Path("scan_images")
DEFAULT_IMAGE_FORMAT = "png"
DEFAULT_PLY_PATH = Path("scan_images/result_visual_hull.ply")
DEFAULT_GRID_SIZE = 40
DEFAULT_TIMEOUT = 10.0
DEFAULT_MAX_RETRIES = 2
DEFAULT_RETRY_DELAY = 2.0

STOP = False
session = requests.Session()


def signal_handler(signum, frame):
    global STOP
    STOP = True


def calculate_num_photo(capture_interval: float) -> int:
    if capture_interval <= 0:
        raise ValueError("capture_interval must be positive")
    return max(1, int(round(TURNTABLE_PERIOD_SECONDS / capture_interval)))


def ensure_save_dir(path: Path):
    try:
        path.mkdir(parents=True, exist_ok=True)
    except Exception as exc:
        raise RuntimeError(f"Failed to create directory {path}: {exc}") from exc


def find_next_index(save_dir: Path, exts=("png", "jpg", "jpeg")) -> int:
    pattern = re.compile(r"^(\d+)\.(" + "|".join(re.escape(ext) for ext in exts) + r")$", re.IGNORECASE)
    max_index = 0
    for path in save_dir.iterdir() if save_dir.exists() else []:
        if path.is_file():
            match = pattern.match(path.name)
            if match:
                try:
                    max_index = max(max_index, int(match.group(1)))
                except ValueError:
                    pass
    return max_index + 1


def format_image_name(index: int, image_format: str) -> str:
    return f"{index:02d}.{image_format}"


def save_image(data: bytes, path: Path):
    try:
        with open(path, "wb") as file_handle:
            file_handle.write(data)
    except Exception as exc:
        raise IOError(f"Save failed: {exc}") from exc


def capture_once(url: str, timeout: float) -> bytes:
    headers = {
        "Connection": "close",
        "User-Agent": "ESP32-CAM-Capture",
    }

    response = session.get(
        url,
        timeout=(5, timeout),
        headers=headers,
        stream=False,
    )
    response.raise_for_status()
    data = response.content

    try:
        response.close()
    except Exception:
        pass

    return data


class CaptureApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("ESP32-CAM 圖像採集器")
        self.geometry("860x620")
        self.minsize(820, 560)

        self.url_var = tk.StringVar()
        self.interval_var = tk.DoubleVar(value=0.5)
        self.interval_display_var = tk.StringVar()
        self.num_photo_display_var = tk.StringVar()
        self.status_var = tk.StringVar(value="等待輸入 URL")
        self.save_dir_var = tk.StringVar(value=str(DEFAULT_SAVE_DIR))
        # 新增：儲存資料夾選擇模式（existing / new）
        self.folder_mode_var = tk.StringVar(value="new")
        self.existing_folder_var = tk.StringVar(value=str(DEFAULT_SAVE_DIR))
        self.new_folder_name_var = tk.StringVar(value="")
        self.turntable_var = tk.StringVar(value=f"轉盤速度：{TURNTABLE_PERIOD_SECONDS:.0f} 秒 / 圈")

        self.is_running = False
        self.stop_requested = False
        self.capture_thread = None

        self._build_ui()
        self._refresh_estimates()

        try:
            signal.signal(signal.SIGINT, signal_handler)
            signal.signal(signal.SIGTERM, signal_handler)
        except Exception:
            pass

    def _build_ui(self):
        main = ttk.Frame(self, padding=14)
        main.pack(fill=tk.BOTH, expand=True)

        title = ttk.Label(main, text="ESP32-CAM 圖像採集與 PLY 連動流程", font=("Arial", 16, "bold"))
        title.pack(anchor=tk.W, pady=(0, 10))

        url_frame = ttk.LabelFrame(main, text="步驟 1：輸入 ESP32-CAM URL")
        url_frame.pack(fill=tk.X, pady=(0, 10))
        ttk.Label(url_frame, text="影像串流網址").grid(row=0, column=0, sticky=tk.W, padx=8, pady=8)
        url_entry = ttk.Entry(url_frame, textvariable=self.url_var)
        url_entry.grid(row=0, column=1, sticky=tk.EW, padx=8, pady=8)
        url_frame.columnconfigure(1, weight=1)
        ttk.Label(url_frame, text="必須先輸入有效 URL，程式才會開始擷取。", foreground="#666666").grid(
            row=1, column=0, columnspan=2, sticky=tk.W, padx=8, pady=(0, 8)
        )

        settings_frame = ttk.Frame(main)
        settings_frame.pack(fill=tk.X, pady=(0, 10))

        fixed_frame = ttk.LabelFrame(settings_frame, text="固定條件")
        fixed_frame.pack(fill=tk.X, pady=(0, 10))
        ttk.Label(fixed_frame, textvariable=self.turntable_var).pack(anchor=tk.W, padx=8, pady=(8, 2))
        ttk.Label(fixed_frame, text="此參數固定不可修改").pack(anchor=tk.W, padx=8, pady=(0, 8))

        slider_frame = ttk.LabelFrame(settings_frame, text="步驟 2：採集間隔設定")
        slider_frame.pack(fill=tk.X)

        self.interval_scale = tk.Scale(
            slider_frame,
            from_=CAPTURE_INTERVAL_MIN,
            to=CAPTURE_INTERVAL_MAX,
            orient=tk.HORIZONTAL,
            resolution=CAPTURE_INTERVAL_STEP,
            variable=self.interval_var,
            command=self._on_interval_change,
            length=500,
        )
        self.interval_scale.pack(fill=tk.X, padx=10, pady=(8, 6))

        info_row = ttk.Frame(slider_frame)
        info_row.pack(fill=tk.X, padx=8, pady=(0, 10))
        ttk.Label(info_row, textvariable=self.interval_display_var).pack(side=tk.LEFT)
        ttk.Label(info_row, textvariable=self.num_photo_display_var).pack(side=tk.RIGHT)

        save_row = ttk.Frame(main)
        save_row.pack(fill=tk.X, pady=(0, 10))
        ttk.Label(save_row, text="儲存路徑：").pack(side=tk.LEFT)
        ttk.Label(save_row, textvariable=self.save_dir_var).pack(side=tk.LEFT)

        # 儲存選項：使用既有資料夾 或 建立新資料夾
        choice_frame = ttk.LabelFrame(main, text="儲存選項")
        choice_frame.pack(fill=tk.X, pady=(0, 10))

        rb1 = ttk.Radiobutton(choice_frame, text="建立新資料夾（推薦）", variable=self.folder_mode_var, value="new", command=self._on_folder_mode_change)
        rb1.grid(row=0, column=0, sticky=tk.W, padx=8, pady=6)

        ttk.Label(choice_frame, text="資料夾名稱（空白使用預設 MM_DD_HH_MM）").grid(row=0, column=1, sticky=tk.W)
        self.new_folder_entry = ttk.Entry(choice_frame, textvariable=self.new_folder_name_var, width=20)
        self.new_folder_entry.grid(row=0, column=2, sticky=tk.W, padx=8)

        rb2 = ttk.Radiobutton(choice_frame, text="使用既有資料夾", variable=self.folder_mode_var, value="existing", command=self._on_folder_mode_change)
        rb2.grid(row=1, column=0, sticky=tk.W, padx=8, pady=6)

        self.existing_folder_entry = ttk.Entry(choice_frame, textvariable=self.existing_folder_var, width=40)
        self.existing_folder_entry.grid(row=1, column=1, columnspan=2, sticky=tk.W, padx=8)
        ttk.Button(choice_frame, text="瀏覽", command=self._browse_existing_folder).grid(row=1, column=3, padx=6)

        self._on_folder_mode_change()

        button_row = ttk.Frame(main)
        button_row.pack(fill=tk.X, pady=(0, 10))
        self.start_button = ttk.Button(button_row, text="開始擷取並生成 PLY", command=self.on_start)
        self.start_button.pack(side=tk.LEFT, padx=(0, 8))
        self.stop_button = ttk.Button(button_row, text="停止", command=self.on_stop, state=tk.DISABLED)
        self.stop_button.pack(side=tk.LEFT)

        status_frame = ttk.LabelFrame(main, text="即時狀態")
        status_frame.pack(fill=tk.X, pady=(0, 10))
        ttk.Label(status_frame, textvariable=self.status_var).pack(anchor=tk.W, padx=8, pady=8)

        log_frame = ttk.LabelFrame(main, text="執行日誌")
        log_frame.pack(fill=tk.BOTH, expand=True)
        self.log_text = tk.Text(log_frame, height=16, wrap="word")
        scrollbar = ttk.Scrollbar(log_frame, orient=tk.VERTICAL, command=self.log_text.yview)
        self.log_text.configure(yscrollcommand=scrollbar.set)
        self.log_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

    def _on_interval_change(self, _value=None):
        self._refresh_estimates()

    def _on_folder_mode_change(self):
        mode = self.folder_mode_var.get()
        if mode == "new":
            self.new_folder_entry.config(state=tk.NORMAL)
            self.existing_folder_entry.config(state=tk.DISABLED)
        else:
            self.new_folder_entry.config(state=tk.DISABLED)
            self.existing_folder_entry.config(state=tk.NORMAL)

    def _browse_existing_folder(self):
        folder = filedialog.askdirectory(initialdir=str(DEFAULT_SAVE_DIR), title="選擇既有資料夾")
        if folder:
            self.existing_folder_var.set(folder)

    def _compute_default_folder_name(self):
        now = time.localtime()
        return f"{now.tm_mon}_{now.tm_mday}_{now.tm_hour}_{now.tm_min}"

    def _resolve_save_dir(self) -> Path:
        # 根據使用者選擇決定儲存資料夾
        if self.folder_mode_var.get() == "existing":
            p = Path(self.existing_folder_var.get())
            return p
        # new folder -> 在 DEFAULT_SAVE_DIR 下建立
        name = self.new_folder_name_var.get().strip()
        if not name:
            name = self._compute_default_folder_name()
        p = DEFAULT_SAVE_DIR / name
        return p

    def _refresh_estimates(self):
        interval = float(self.interval_var.get())
        num_photo = calculate_num_photo(interval)
        self.interval_display_var.set(f"目前採集間隔：{interval:.1f} 秒")
        self.num_photo_display_var.set(f"預計擷取數量：{num_photo} 張")
        self.status_var.set(f"轉盤速度 10 秒 / 圈，{interval:.1f} 秒 / 張 → 約 {num_photo} 張 / 圈")

    def _append_log(self, text: str):
        def write_line():
            timestamp = time.strftime("%H:%M:%S")
            self.log_text.insert("end", f"[{timestamp}] {text}\n")
            self.log_text.see("end")
            self.status_var.set(text)

        if threading.current_thread() is threading.main_thread():
            write_line()
        else:
            self.after(0, write_line)

    def _set_running_state(self, running: bool):
        state = tk.DISABLED if running else tk.NORMAL
        self.start_button.config(state=state)
        self.stop_button.config(state=tk.NORMAL if running else tk.DISABLED)
        self.interval_scale.config(state=state)

    def on_start(self):
        if self.is_running:
            return

        url = self.url_var.get().strip()
        if not url:
            messagebox.showerror("URL 必填", "請先輸入 ESP32-CAM 的影像串流網址。")
            return
        if not url.startswith(("http://", "https://")):
            messagebox.showerror("URL 格式錯誤", "請輸入完整網址，例如 http://192.168.1.100/capture")
            return

        interval = float(self.interval_var.get())
        num_photo = calculate_num_photo(interval)

        # 決定儲存路徑（不刪除既有資料）
        save_dir = self._resolve_save_dir()
        try:
            ensure_save_dir(save_dir)
        except Exception as exc:
            messagebox.showerror("儲存路徑錯誤", str(exc))
            return

        self.is_running = True
        self.stop_requested = False
        self._set_running_state(True)
        self._append_log(f"開始流程：URL={url}")
        self._append_log(f"固定轉盤速度：{TURNTABLE_PERIOD_SECONDS:.0f} 秒 / 圈")
        self._append_log(f"採集間隔：{interval:.1f} 秒，預計擷取 {num_photo} 張")

        self.capture_thread = threading.Thread(
            target=self._worker,
            args=(url, interval, num_photo, save_dir),
            daemon=True,
        )
        self.capture_thread.start()

    def on_stop(self):
        if not self.is_running:
            return
        self.stop_requested = True
        self._append_log("已送出停止請求。")

    def _worker(self, url: str, interval: float, num_photo: int, save_dir: Path):
        # save_dir 已由呼叫者解析（不會覆寫既有資料）
        image_format = DEFAULT_IMAGE_FORMAT
        timeout = DEFAULT_TIMEOUT
        max_retries = DEFAULT_MAX_RETRIES
        retry_delay = DEFAULT_RETRY_DELAY

        try:
            next_index = find_next_index(save_dir, exts=("png", "jpg", "jpeg"))
            captured = 0
            failed = 0
            start_time = time.perf_counter()

            while captured < num_photo and not self.stop_requested and not STOP:
                current_num = captured + 1
                self._append_log(f"[{current_num}/{num_photo}] 擷取中...")
                success = False
                attempts = 0

                while attempts <= max_retries and not success and not self.stop_requested and not STOP:
                    try:
                        data = capture_once(url, timeout=timeout)
                        filename = format_image_name(next_index, image_format)
                        save_path = save_dir / filename
                        save_image(data, save_path)
                        self._append_log(f"已儲存：{save_path}")
                        success = True
                    except requests.exceptions.HTTPError as exc:
                        status = getattr(exc.response, "status_code", "") if hasattr(exc, "response") else ""
                        self._append_log(f"擷取失敗：HTTP {status} - {exc}")
                    except requests.exceptions.Timeout:
                        self._append_log(f"擷取失敗：Timeout after {timeout}s")
                    except requests.exceptions.RequestException as exc:
                        self._append_log(f"擷取失敗：{exc}")
                    except IOError as exc:
                        self._append_log(f"儲存失敗：{exc}")

                    attempts += 1
                    if not success and attempts <= max_retries and not self.stop_requested and not STOP:
                        time.sleep(retry_delay)

                if not success:
                    failed += 1
                    self._append_log("擷取失敗，流程停止。")
                    break

                captured += 1
                next_index += 1

                next_target = start_time + captured * interval
                sleep_time = next_target - time.perf_counter()
                if sleep_time > 0 and not self.stop_requested and not STOP:
                    time.sleep(sleep_time)

            if self.stop_requested or STOP:
                self._append_log(f"流程已停止。已擷取 {captured} 張，失敗 {failed} 張。")
                return

            self._append_log(f"擷取完成：成功 {captured} 張，失敗 {failed} 張。")
            self._append_log("開始生成 PLY，num_images 使用同一個 num_photo 參數。")

            ply_path = ensure_ply_exists(
                DEFAULT_PLY_PATH,
                force_rebuild=True,
                grid_size=DEFAULT_GRID_SIZE,
                num_images=num_photo,
                no_display=True,
            )

            if ply_path:
                self._append_log(f"PLY 生成成功：{ply_path}")
            else:
                self._append_log("PLY 生成失敗。")

        finally:
            self.is_running = False
            self.after(0, lambda: self._set_running_state(False))


def main() -> int:
    app = CaptureApp()
    app.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
