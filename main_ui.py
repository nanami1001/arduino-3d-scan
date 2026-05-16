#!/usr/bin/env python3
"""
主控 UI：整合重建、檢視、檢查清單與匯出功能

主要功能：
▪ Tab1：3D 重建（呼叫 build_ply → reconstruct_simple.py）
▪ Tab2：檢查清單（硬體狀態 / 擷取流程 / 重建狀態）
▪ 背景執行 PLY 建置，不阻塞 UI
▪ Matplotlib 3D 顯示點雲與 Hull 網格

使用方式：
    python main_ui.py
"""

# ============================================================
#  Imports
# ============================================================

import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import threading
import sys
from pathlib import Path
from datetime import datetime
import os
import time
import subprocess

# 數值、繪圖、科學運算
import numpy as np
import matplotlib
matplotlib.use('TkAgg')  # Tkinter 專用後端
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
import matplotlib.pyplot as plt
from mpl_toolkits.mplot3d import Axes3D
from scipy.spatial import ConvexHull

# 重建系統模組（自動生成 PLY）
from build_ply import ensure_ply_exists
# ESP32 攝影機模組整合（延遲載入以避免啟動時阻塞）
import importlib


# ============================================================
#  顏色主題設定（與介面 / 圖檔一致）
# ============================================================

COLOR_BG = "#FFFFFF"
COLOR_GREEN = "#4CAF50"
COLOR_RED = "#F44336"
COLOR_GRAY = "#CCCCCC"
COLOR_BLUE = "#2196F3"
COLOR_TEXT = "#333333"
COLOR_LIGHT_TEXT = "#666666"

# 狀態圖示
CHECKMARK = "✓"
CROSS = "✗"
PENDING = "○"
LOADING = "⟳"


# Checklist functionality removed per updated requirements.
# All checklist UI, data structures and related flows have been removed.


# ============================================================
#  Tooltip — 提示文字功能
# ============================================================

class Tooltip:
    """UI 滑鼠懸停提示（簡易版 Tooltip）"""

    def __init__(self, widget, text):
        self.widget = widget
        self.text = text
        self.tipwindow = None
        widget.bind("<Enter>", self.show_tip)
        widget.bind("<Leave>", self.hide_tip)

    def show_tip(self, event=None):
        if self.tipwindow or not self.text:
            return

        x = self.widget.winfo_rootx() + 10
        y = self.widget.winfo_rooty() + self.widget.winfo_height() + 5

        tw = tk.Toplevel(self.widget)
        tw.wm_overrideredirect(True)
        tw.wm_geometry(f"+{x}+{y}")
        tk.Label(
            tw, text=self.text,
            background="lightyellow", relief="solid", borderwidth=1,
            font=("Arial", 9), wraplength=250, justify="left"
        ).pack()

        self.tipwindow = tw

    def hide_tip(self, event=None):
        if self.tipwindow:
            self.tipwindow.destroy()
            self.tipwindow = None


# ============================================================
#  PLY Reader — 載入 ASCII PLY
# ============================================================

def load_ply_ascii(path):
    """
    讀取 ASCII PLY（僅 x y z）
    避免外部依賴（open3d, plyfile），直接純文字解析
    """
    pts = []
    with open(path, "r") as f:
        header = True
        for line in f:
            line = line.strip()
            if header:
                if line == "end_header":
                    header = False
                continue

            if not line:
                continue

            parts = line.split()
            if len(parts) >= 3:
                try:
                    x, y, z = map(float, parts[:3])
                    pts.append([x, y, z])
                except:
                    continue

    return np.array(pts, dtype=np.float32)


# ============================================================
#  Main UI — 主介面與事件邏輯
#  新增：啟動模式選擇（A: 使用現有樣本；B: 從 ESP32-CAM 採集）
# ============================================================

class MainUI:

    def __init__(self, root):
        self.root = root
        root.title("3D Scan — 主控介面")

        self.base_dir = Path.cwd()
        self.ply_path = Path("scan_images") / "result_visual_hull.ply"
        self.is_building = False  # 避免重複建置

        # -------------------------
        #  Notebook：兩個頁面
        # -------------------------
        self.notebook = ttk.Notebook(root)
        self.notebook.pack(fill="both", expand=True, padx=8, pady=6)

        # Tab: 操作選擇（Operation selection）
        self.tab_ops = ttk.Frame(self.notebook)
        # add ops tab
        self.notebook.add(self.tab_ops, text="🔧 操作選擇")
        # create mode panel inside ops tab
        self._create_mode_panel(parent=self.tab_ops)

        # 指導手冊 Tab（整合硬體 / 軟體教學）
        self.tab_manual = ttk.Frame(self.notebook)
        self.notebook.add(self.tab_manual, text="指導手冊")
        self._create_manual_tab()

        # Tab 3 — 3D 重建（初始鎖定，需由 操作選擇 解鎖）
        self.tab_rebuild = ttk.Frame(self.notebook)
        self.notebook.add(self.tab_rebuild, text="📊 3D 重建")
        self._create_rebuild_tab()

        # 預設停用 3D 重構分頁，等待使用者在 操作選擇 完成設定後解鎖
        try:
            self.notebook.tab(self.tab_rebuild, state="disabled")
        except Exception:
            pass

    # ============================================================
    #  Tab 1 — 3D 重建（參數、按鈕、3D 顯示、日誌）
    # ============================================================

    def _create_rebuild_tab(self):
        """
        建立 3D 重建頁面：
        ▪ Grid / images 參數
        ▪ 重建按鈕、載入 PLY、開資料夾、強制重建
        ▪ Matplotlib 3D 視窗
        ▪ 執行日誌 Log
        """

        # -------------------------
        #  參數區
        # -------------------------

        param_frame = ttk.LabelFrame(self.tab_rebuild, text="參數")
        param_frame.grid(row=0, column=0, sticky="nsew", padx=8, pady=6)

        ttk.Label(param_frame, text="Grid size").grid(row=0, column=0, sticky="w")
        self.grid_size_var = tk.IntVar(value=40)
        ttk.Entry(param_frame, textvariable=self.grid_size_var, width=8).grid(row=0, column=1)

        ttk.Label(param_frame, text="Num images").grid(row=1, column=0, sticky="w")
        self.num_images_var = tk.IntVar(value=8)
        ttk.Entry(param_frame, textvariable=self.num_images_var, width=8).grid(row=1, column=1)

        # -------------------------
        #  按鈕區
        # -------------------------

        btn_frame = ttk.Frame(self.tab_rebuild)
        btn_frame.grid(row=1, column=0, sticky="ew", padx=8)

        # 重建按鈕
        self.rebuild_btn = ttk.Button(btn_frame, text="重建 (Rebuild)", command=self.on_rebuild)
        self.rebuild_btn.grid(row=0, column=0, padx=4, pady=6)

        Tooltip(self.rebuild_btn,
                "【重建】\n使用影像進行 Visual Hull 3D 重建。\n"
                "Grid size 決定體素解析度。\n完成後自動顯示模型。")

        # 載入並顯示
        self.view_btn = ttk.Button(btn_frame, text="載入並顯示 PLY", command=self.on_view)
        self.view_btn.grid(row=0, column=1, padx=4)

        # 開啟資料夾
        self.open_folder_btn = ttk.Button(btn_frame, text="開啟 scan_images",
                                          command=self.open_scan_folder)
        self.open_folder_btn.grid(row=0, column=2, padx=4)

        # 強制重建選項
        self.force_rebuild_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(btn_frame, text="強制重建 (--rebuild)",
                        variable=self.force_rebuild_var).grid(row=0, column=3, padx=6)

        # -------------------------
        #  3D 繪圖區（Matplotlib）
        # -------------------------

        plot_frame = ttk.LabelFrame(self.tab_rebuild, text="3D 檢視")
        plot_frame.grid(row=2, column=0, sticky="nsew", padx=8, pady=6)

        # 讓 3D 視窗可自動伸縮
        self.tab_rebuild.rowconfigure(2, weight=1)
        self.tab_rebuild.columnconfigure(0, weight=1)

        # Matplotlib 初始化
        self.fig = plt.Figure(figsize=(6, 5))
        self.ax = self.fig.add_subplot(111, projection="3d")
        self.canvas = FigureCanvasTkAgg(self.fig, master=plot_frame)
        self.canvas.get_tk_widget().pack(fill="both", expand=True)

        # -------------------------
        #  日誌區
        # -------------------------

        log_frame = ttk.LabelFrame(self.tab_rebuild, text="執行日誌")
        log_frame.grid(row=3, column=0, sticky="ew", padx=8, pady=6)
        self.log = tk.Text(log_frame, height=8)
        self.log.pack(fill="both", expand=True)

        # 開機訊息
        if self.ply_path.exists():
            self.log_insert(f"✓ 已找到 {self.ply_path} ，可直接載入。")
        else:
            self.log_insert("⚠ 找不到 PLY 檔，請按【重建】或【載入並顯示】。")

    # ============================================================
    #  Log 系統
    # ============================================================

    def log_insert(self, text):
        ts = time.strftime("%H:%M:%S")
        self.log.insert("end", f"[{ts}] {text}\n")
        self.log.see("end")

    # ============================================================
    #  重建按鈕事件 — 背景執行 ensure_ply_exists()
    # ============================================================

    def on_rebuild(self):
        if self.is_building:
            self.log_insert("⚠ 正在建立中，請稍候...")
            return

        # 選擇來源資料夾（含影像）
        images_folder = filedialog.askdirectory(
            initialdir=str(Path("scan_images")),
            title="選擇包含影像的資料夾"
        )
        if not images_folder:
            self.log_insert("✗ 使用者取消資料夾選擇")
            return

        grid = self.grid_size_var.get()
        num_images = self.num_images_var.get()
        force = self.force_rebuild_var.get()

        self.log_insert(f"開始重建：{images_folder}（Grid={grid}, Images={num_images}）...")
        self.is_building = True
        self.rebuild_btn.config(state="disabled")

        def worker():
            try:
                # PLY 輸出至同資料夾
                out_ply = Path(images_folder) / "result_visual_hull.ply"
                ply_path = ensure_ply_exists(
                    str(out_ply),
                    force_rebuild=force,
                    grid_size=grid,
                    num_images=num_images,
                    no_display=True,
                    images_folder=images_folder,
                )

                if ply_path:
                    self.root.after(50, lambda: self.on_rebuild_complete(str(ply_path)))
                else:
                    self.root.after(50, lambda: self.log_insert("✗ PLY 生成失敗"))

            except Exception as e:
                self.root.after(50, lambda: self.log_insert(f"✗ 錯誤：{e}"))

            finally:
                self.is_building = False
                self.root.after(50, lambda: self.rebuild_btn.config(state="normal"))

        threading.Thread(target=worker, daemon=True).start()

    # ============================================================
    #  重建完成後 → 載入 PLY
    # ============================================================

    def on_rebuild_complete(self, ply_path):
        self.log_insert("✓ 重建完成，正在載入 PLY...")
        self.log_insert("✓ Visual Hull 完成，PLY 已生成")
        self.log_insert("⟳ 正在載入 3D 點雲...")

        self.load_and_display_ply(ply_path)

    # ============================================================
    #  載入 PLY（使用者手動選擇）
    # ============================================================

    def on_view(self):
        # 直接選擇單一 .ply 檔案
        path = filedialog.askopenfilename(
            initialdir=str(Path("scan_images")),
            title="選擇 PLY 檔案",
            filetypes=[("PLY files", "*.ply"), ("All files", "*.*")]
        )

        if not path:
            self.log_insert("✗ 使用者取消選擇")
            return

        self.load_and_display_ply(path)

    # ============================================================
    #  載入 + 顯示 PLY（含自動重建 fallback）
    # ============================================================

    def load_and_display_ply(self, path):
        path = Path(path)

        # 若不存在 → 自動建立
        if not path.exists():
            self.log_insert(f"⚠ 找不到 {path}，自動生成中...")

            if self.is_building:
                self.log_insert("⚠ 建構進行中，請稍候")
                return

            self.is_building = True

            def worker():
                try:
                    result = ensure_ply_exists(
                        str(path),
                        force_rebuild=False,
                        grid_size=self.grid_size_var.get(),
                        num_images=self.num_images_var.get(),
                        no_display=True
                    )

                    if result:
                        self.root.after(50, lambda:
                            self.load_and_display_ply(str(result))
                        )
                    else:
                        self.root.after(50, lambda:
                            self.log_insert("✗ PLY 建立失敗")
                        )

                finally:
                    self.is_building = False

            threading.Thread(target=worker, daemon=True).start()
            return

        # -------------------------
        #  讀取 PLY
        # -------------------------

        try:
            pts = load_ply_ascii(str(path))
            self.log_insert(f"✓ PLY 載入成功：{len(pts)} 點")
            self.display_points(pts)
            self.log_insert(f"✓ 3D 點雲已顯示（{len(pts)} 點）")

        except Exception as e:
            self.log_insert(f"✗ 讀取 PLY 失敗：{e}")
            self.log_insert(f"✗ 視覺化失敗：{e}")

    # ============================================================
    #  顯示 3D 點雲（含 ConvexHull）
    # ============================================================

    def display_points(self, pts):
        self.ax.clear()

        if len(pts) == 0:
            self.ax.text(0.5, 0.5, 0.5, "No points", transform=self.ax.transAxes)
        else:
            try:
                # 若點數足夠 → 計算 Hull
                if len(pts) >= 4:
                    hull = ConvexHull(pts)

                    # 填滿面
                    self.ax.plot_trisurf(
                        pts[:, 0], pts[:, 1], pts[:, 2],
                        triangles=hull.simplices,
                        linewidth=0.2, edgecolor="k",
                        color="lightgreen", alpha=0.85
                    )

                    # 邊線
                    for tri in hull.simplices:
                        tri_pts = pts[tri]
                        self.ax.plot(
                            list(tri_pts[:, 0]) + [tri_pts[0, 0]],
                            list(tri_pts[:, 1]) + [tri_pts[0, 1]],
                            list(tri_pts[:, 2]) + [tri_pts[0, 2]],
                            color="black", linewidth=0.25, alpha=0.8
                        )

                    self.log_insert(f"✓ ConvexHull：{len(hull.simplices)} ")
                else:
                    self.ax.scatter(pts[:, 0], pts[:, 1], pts[:, 2], c="blue", s=2)

            except Exception as e:
                self.log_insert(f"⚠ Hull 計算失敗：{e}")
                self.ax.scatter(pts[:, 0], pts[:, 1], pts[:, 2], c="blue", s=2)

        # Label
        self.ax.set_xlabel("X")
        self.ax.set_ylabel("Y")
        self.ax.set_zlabel("Z")
        self.ax.set_title(f"Point cloud ({len(pts)} points)")

        # 坐標軸等比例
        self._set_axes_equal(self.ax)
        self.canvas.draw()

    def _set_axes_equal(self, ax):
        """確保 3D 圖等比例顯示"""
        xlim, ylim, zlim = ax.get_xlim3d(), ax.get_ylim3d(), ax.get_zlim3d()
        ranges = [xlim[1] - xlim[0], ylim[1] - ylim[0], zlim[1] - zlim[0]]
        mid = [np.mean(xlim), np.mean(ylim), np.mean(zlim)]
        r = max(ranges) / 2

        ax.set_xlim3d(mid[0] - r, mid[0] + r)
        ax.set_ylim3d(mid[1] - r, mid[1] + r)
        ax.set_zlim3d(mid[2] - r, mid[2] + r)

    # ============================================================
    #  操作選擇面板（一體化 UI）
    # ============================================================

    def _create_mode_panel(self, parent=None):
        """在指定 parent 頁面建立操作選擇面板（默認為 tab_rebuild）。"""
        if parent is None:
            parent = self.tab_rebuild
        panel = ttk.LabelFrame(parent, text="操作選擇", padding=10)

        # 將說明置頂，按鈕上下排列且放大
        panel.pack(fill=tk.X, padx=8, pady=(8, 6))

        info_label = ttk.Label(panel, text="選擇模式後，系統將進入相應流程。", foreground=COLOR_LIGHT_TEXT, anchor="w")
        info_label.pack(side=tk.TOP, fill=tk.X, padx=6, pady=(0, 8))

        # 模式變數與選擇處理
        self.mode_var = tk.StringVar(value="preview")

        def update_button_styles():
            # 簡單視覺回饋：使用 state pressed 清楚顯示選取
            if getattr(self, '_btn_preview', None):
                try:
                    if self.mode_var.get() == 'preview':
                        self._btn_preview.state(['pressed'])
                    else:
                        self._btn_preview.state(['!pressed'])
                except Exception:
                    pass
            if getattr(self, '_btn_capture', None):
                try:
                    if self.mode_var.get() == 'capture':
                        self._btn_capture.state(['pressed'])
                    else:
                        self._btn_capture.state(['!pressed'])
                except Exception:
                    pass

        def on_select_preview():
            self.mode_var.set('preview')
            update_button_styles()

        def on_select_capture():
            self.mode_var.set('capture')
            update_button_styles()

        # 大按鈕（上下排列）作為選擇控制：不直接執行動作，改為設定模式
        self._btn_preview = ttk.Button(panel, text="📸 使用現有樣本產生 3D 影像", command=on_select_preview)
        self._btn_preview.pack(fill=tk.X, padx=12, pady=(6, 8))
        try:
            self._btn_preview.config(font=("Arial", 12))
        except Exception:
            pass

        self._btn_capture = ttk.Button(panel, text="🎬 使用影像採集設備從頭開始", command=on_select_capture)
        self._btn_capture.pack(fill=tk.X, padx=12, pady=(0, 6))
        try:
            self._btn_capture.config(font=("Arial", 12))
        except Exception:
            pass

        # Start / Confirm 按鈕：解鎖並切換至 3D 重構分頁
        def on_confirm():
            mode = self.mode_var.get()
            self.log_insert(f"▶ 已選擇模式：{mode}")
            try:
                self.notebook.tab(self.tab_rebuild, state='normal')
                idx = self.notebook.index(self.tab_rebuild)
                self.notebook.select(idx)
                self.log_insert("✓ 3D 重構頁面已解鎖並切換")
            except Exception as e:
                self.log_insert(f"✗ 解鎖或切換失敗：{e}")

            if mode == 'preview':
                self._start_preview_mode()
            else:
                self._start_capture_mode()

            try:
                start_btn.config(state='disabled')
            except Exception:
                pass

        start_btn = ttk.Button(panel, text="開始", command=on_confirm)
        start_btn.pack(fill=tk.X, padx=12, pady=(8, 6))

        sep = ttk.Separator(panel, orient=tk.HORIZONTAL)
        sep.pack(fill=tk.X, pady=6)

        update_button_styles()

    def _start_preview_mode(self):
        self.log_insert("▶ 模式：使用現有樣本產生 3D 影像")
        self.log_insert("請使用【重建】或【載入並顯示】按鈕選擇資料並產生預覽。")

    def _start_capture_mode(self):
        self.log_insert("▶ 模式：使用影像採集設備從頭開始")
        self.log_insert("✓ 保留既有資料（不清除 scan_images）")

        # 硬體檢查（內建於面板下方顯示）
        checks = [
            "ESP32-CAM 已正確安裝並固定",
            "電源與網路連線已接好",
            "轉盤與固定結構已完成安裝",
            "相機視角與對位已確認",
        ]

        msg = "\n".join(checks)
        resp = messagebox.showinfo(
            "硬體檢查",
            f"請確認以下硬體與連線已完成：\n\n{msg}\n\n按 OK 確認並繼續。"
        )

        self.log_insert("✓ 硬體檢查確認")
        self.log_insert("啟動 ESP32-CAM 採集器（獨立視窗）...")

        try:
            script = Path("esp32_cam_capture.py").resolve()
            subprocess.Popen([sys.executable, str(script)])
        except Exception as e:
            self.log_insert(f"✗ 無法啟動採集器：{e}")
            messagebox.showerror("啟動失敗", f"無法啟動 esp32_cam_capture：{e}")
            return

        self.log_insert("開始監控採集結果（等待任一子資料夾下的 result_visual_hull.ply）...")
        threading.Thread(target=self._monitor_capture_completion, daemon=True).start()

    def _monitor_capture_completion(self):
        timeout = 60 * 30  # 最多等待 30 分鐘
        start = time.time()
        while time.time() - start < timeout:
            for p in Path('.').rglob('result_visual_hull.ply'):
                try:
                    if p.exists() and p.stat().st_size > 0:
                        self.root.after(50, lambda p=p: self.log_insert(f"✓ 偵測到 PLY：{p}"))
                        self.root.after(100, lambda p=p: self.load_and_display_ply(str(p)))
                        return
                except Exception:
                    continue

            time.sleep(2)

    def _create_manual_tab(self):
        """建立指導手冊頁籤：支援圖片、可滾動說明與程式碼顯示"""
        # 使用子 Notebook 區分硬體 / 軟體教學
        manual_nb = ttk.Notebook(self.tab_manual)
        manual_nb.pack(fill="both", expand=True, padx=8, pady=6)

        hw_frame = ttk.Frame(manual_nb)
        sw_frame = ttk.Frame(manual_nb)
        manual_nb.add(hw_frame, text="硬體教學")
        manual_nb.add(sw_frame, text="軟體教學")

        # --- 硬體教學子頁 ---
        hw_sub_nb = ttk.Notebook(hw_frame)
        hw_sub_nb.pack(fill="both", expand=True)

        wiring_page = ttk.Frame(hw_sub_nb)
        arduino_page = ttk.Frame(hw_sub_nb)
        esp_page = ttk.Frame(hw_sub_nb)
        hw_sub_nb.add(wiring_page, text="接線圖 / 照片")
        hw_sub_nb.add(arduino_page, text="Arduino 程式碼")
        hw_sub_nb.add(esp_page, text="ESP32-CAM 程式碼")

        from tkinter.scrolledtext import ScrolledText

        # 接線圖 / 照片（可內嵌顯示或以系統預設程式開啟）
        img_frame = ttk.Frame(wiring_page)
        img_frame.pack(fill=tk.X, padx=6, pady=(6, 2))

        assets = [
            Path("assets/manual/28byj48_wiring.png"),
            Path("assets/manual/esp32cam_flash_mode.png"),
        ]

        displayed_any = False
        try:
            from PIL import Image, ImageTk
            pil_ok = True
        except Exception:
            pil_ok = False

        def open_asset(path: Path):
            try:
                os.startfile(str(path))
            except Exception as exc:
                messagebox.showerror("無法開啟圖片", f"無法開啟 {path.name}\n{exc}")

        asset_titles = {
            "28byj48_wiring.png": "28BYJ-48 接線圖",
            "esp32cam_flash_mode.png": "ESP32-CAM 燒錄模式接線圖",
        }

        for p in assets:
            if p.exists():
                displayed_any = True
                card = ttk.Frame(img_frame)
                card.pack(side=tk.LEFT, padx=8, pady=4)

                title = ttk.Label(card, text=asset_titles.get(p.name, p.stem), foreground=COLOR_TEXT)
                title.pack(anchor=tk.W, pady=(0, 4))

                if pil_ok:
                    try:
                        img = Image.open(p)
                        img.thumbnail((360, 240))
                        tkimg = ImageTk.PhotoImage(img)
                        lbl = ttk.Label(card, image=tkimg, cursor="hand2")
                        lbl.image = tkimg
                        lbl.pack()
                        lbl.bind("<Button-1>", lambda e, p=p: open_asset(p))
                    except Exception:
                        btn = ttk.Button(card, text=f"開啟 {p.name}", command=lambda p=p: open_asset(p))
                        btn.pack(side=tk.LEFT, padx=6)
                else:
                    # Pillow not available — 提供開啟按鈕
                    btn = ttk.Button(card, text=f"開啟 {p.name}", command=lambda p=p: open_asset(p))
                    btn.pack()

        if not displayed_any:
            note = ttk.Label(img_frame, text="尚未加入接線圖。請將影像放置於 assets/manual/ 並重新啟動 UI。")
            note.pack(anchor=tk.W, padx=6)

        # 接線說明文字區
        wiring_txt = ScrolledText(wiring_page, wrap="word")
        wiring_txt.pack(fill="both", expand=True)
        wiring_msg = (
            "接線圖與實體照片放置於：\n"
            "  assets/manual/28byj48_wiring.png\n"
            "  assets/manual/esp32cam_flash_mode.png\n\n"
        )
        wiring_txt.insert("1.0", wiring_msg)
        wiring_txt.bind('<Key>', lambda e: 'break')

        # Arduino 程式碼顯示
        arduino_txt = ScrolledText(arduino_page, wrap="none")
        arduino_txt.pack(fill="both", expand=True)
        arduino_code_path = Path("Arduino hardware programming program/28BYJ48_test/28BYJ48_test.ino")
        try:
            with open(arduino_code_path, "r", encoding="utf-8") as f:
                arduino_txt.insert("1.0", f.read())
        except Exception as e:
            arduino_txt.insert("1.0", f"無法載入 Arduino 程式：{e}")
        arduino_txt.bind('<Key>', lambda e: 'break')

        # ESP32 程式碼顯示（若有）
        esp_txt = ScrolledText(esp_page, wrap="none")
        esp_txt.pack(fill="both", expand=True)
        esp_code_path = Path("Arduino hardware programming program/ESP32_CAM/example_camera.ino")
        if esp_code_path.exists():
            try:
                with open(esp_code_path, "r", encoding="utf-8") as f:
                    esp_txt.insert("1.0", f.read())
            except Exception as e:
                esp_txt.insert("1.0", f"無法載入 ESP32 程式：{e}")
        else:
            esp_txt.insert("1.0", "尚未加入 ESP32 範例程式，請將檔案放置於 Arduino hardware programming program/ESP32_CAM/ 目錄。")
        esp_txt.bind('<Key>', lambda e: 'break')

        # --- 軟體教學子頁 ---
        sw_sub_nb = ttk.Notebook(sw_frame)
        sw_sub_nb.pack(fill="both", expand=True)

        sys_page = ttk.Frame(sw_sub_nb)
        ui_page = ttk.Frame(sw_sub_nb)
        sw_sub_nb.add(sys_page, text="系統操作")
        sw_sub_nb.add(ui_page, text="介面功能")

        sys_txt = ScrolledText(sys_page, wrap="word")
        sys_txt.pack(fill="both", expand=True)
        # 載入手冊摘要
        manual_md = Path("md/GUIDE_HARDWARE_SOFTWARE.md")
        try:
            with open(manual_md, "r", encoding="utf-8") as f:
                sys_txt.insert("1.0", f.read())
        except Exception as e:
            sys_txt.insert("1.0", f"無法載入手冊：{e}")
        sys_txt.bind('<Key>', lambda e: 'break')

        ui_txt = ScrolledText(ui_page, wrap="word")
        ui_txt.pack(fill="both", expand=True)
        ui_txt.insert("1.0", "介面說明：\n- 使用 main_ui.py 的 Notebook 切換頁面\n- 在 3D 重建頁面可進行重建、載入 PLY 與啟動採集器")


        self.root.after(50, lambda: self.log_insert("⚠ 監控逾時，未偵測到 PLY。"))
    # ============================================================
    #  開啟資料夾
    # ============================================================

    def open_scan_folder(self):
        folder = str(Path("scan_images").resolve())
        if os.name == "nt":
            os.startfile(folder)
        else:
            import subprocess
            subprocess.Popen(["xdg-open", folder])


# ============================================================
#  Main
# ============================================================

if __name__ == "__main__":
    root = tk.Tk()
    root.geometry("900x800")
    app = MainUI(root)
    root.mainloop()

