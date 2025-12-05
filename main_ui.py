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


# ============================================================
#  CheckItem — 檢查清單項目資料結構
# ============================================================

class CheckItem:
    """
    檢查項目的資料結構：
    ▪ title: 主標題（功能名稱）
    ▪ description: 副標題（說明）
    ▪ status: pending / loading / success / failed
    ▪ timestamp: 更新時間
    """

    def __init__(self, title, description=""):
        self.title = title
        self.description = description
        self.status = "pending"
        self.timestamp = None
        self.details = ""

    def set_status(self, status, details=""):
        """更新狀態並記錄詳細描述"""
        self.status = status
        self.timestamp = datetime.now().strftime("%H:%M:%S")
        self.details = details

    def get_icon(self):
        """依狀態回傳 UI 圖示"""
        return {
            "success": CHECKMARK,
            "failed": CROSS,
            "loading": LOADING,
            "pending": PENDING,
        }.get(self.status, PENDING)

    def get_color(self):
        """依狀態回傳顏色"""
        return {
            "success": COLOR_GREEN,
            "failed": COLOR_RED,
            "loading": COLOR_BLUE,
            "pending": COLOR_GRAY,
        }.get(self.status, COLOR_GRAY)


# ============================================================
#  ChecklistFrame — 檢查清單介面
# ============================================================

class ChecklistFrame(ttk.Frame):
    """
    檢查清單視覺化 UI：
    ▪ 硬體偵測
    ▪ Serial 連線
    ▪ WiFi 連線
    ▪ 轉盤校準
    ▪ 影像擷取
    ▪ 影像處理
    ▪ 重建（Visual Hull）
    ▪ 匯出結果
    ▪ 視覺化

    支援狀態動畫（loading 狀態會旋轉）
    """

    def __init__(self, root, **kwargs):
        super().__init__(root, **kwargs)
        self.root = root
        self.items = []
        self.item_widgets = {}
        self.is_animating = {}

        self._create_header()
        self._create_checklist()
        self._create_buttons()

    # -------------------------------
    #  Header 區域
    # -------------------------------

    def _create_header(self):
        header = ttk.Frame(self, height=60)
        header.pack(fill=tk.X, padx=15, pady=10)

        ttk.Label(header, text="Arduino 3D 掃描系統檢查清單",
                  font=("Arial", 16, "bold")).pack(anchor=tk.W)

        ttk.Label(header, text="硬體配置 • 擷取進度 • 重建結果",
                  font=("Arial", 10), foreground=COLOR_LIGHT_TEXT).pack(anchor=tk.W)

    # -------------------------------
    #  檢查清單列表（Scrollable）
    # -------------------------------

    def _create_checklist(self):
        canvas_frame = ttk.Frame(self)
        canvas_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        canvas = tk.Canvas(canvas_frame, bg=COLOR_BG, highlightthickness=0)
        scrollbar = ttk.Scrollbar(canvas_frame, orient=tk.VERTICAL, command=canvas.yview)
        scrollable_frame = ttk.Frame(canvas)

        scrollable_frame.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )

        canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)

        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        self.checklist_frame = scrollable_frame
        self._add_default_items()

    # -------------------------------
    #  預設檢查項目
    # -------------------------------

    def _add_default_items(self):
        default_items = [
            CheckItem("硬體偵測", "檢查 Arduino 和 ESP32-CAM 連接"),
            CheckItem("Serial 口配置", "COM 埠: COM3 (115200 波特率)"),
            CheckItem("WiFi 連線", "ESP32-CAM IP: 192.168.1.100"),
            CheckItem("轉盤校準", "初始化步進馬達和轉盤"),
            CheckItem("影像擷取", "旋轉→擷取→儲存 (0/36 完成)"),
            CheckItem("影像處理", "二值化 → 矽脫圖像"),
            CheckItem("體素雕刻", "3D 重建中..."),
            CheckItem("結果匯出", "PLY 檔案生成"),
            CheckItem("視覺化", "3D 點雲顯示 + 邊界網格"),
        ]

        for item in default_items:
            self.add_item(item)

    # -------------------------------
    #  新增 UI 項目
    # -------------------------------

    def add_item(self, check_item):
        frame = tk.Frame(self.checklist_frame, bg=COLOR_BG)
        frame.pack(fill=tk.X, pady=8, padx=5)

        # 狀態標籤
        status_label = tk.Label(
            frame, text=check_item.get_icon(),
            bg=COLOR_BG, fg=check_item.get_color(),
            font=("Arial", 14, "bold"), width=3
        )
        status_label.pack(side=tk.LEFT, padx=10)

        # 文本
        text_frame = tk.Frame(frame, bg=COLOR_BG)
        text_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        title = tk.Label(
            text_frame, text=check_item.title,
            bg=COLOR_BG, fg=COLOR_TEXT,
            font=("Arial", 11, "bold")
        )
        title.pack(anchor=tk.W)

        detail = tk.Label(
            text_frame, text=check_item.description,
            bg=COLOR_BG, fg=COLOR_LIGHT_TEXT,
            font=("Arial", 9)
        )
        detail.pack(anchor=tk.W)

        # 儲存參考
        idx = len(self.items)
        self.items.append(check_item)
        self.item_widgets[idx] = {
            "frame": frame,
            "status_label": status_label,
            "title_label": title,
            "detail_label": detail
        }
        self.is_animating[idx] = False

    # -------------------------------
    #  更新項目狀態
    # -------------------------------

    def update_item(self, index, status, description=""):
        if index >= len(self.items):
            return

        item = self.items[index]
        item.set_status(status, description)

        widgets = self.item_widgets[index]
        widgets["status_label"].config(text=item.get_icon(), fg=item.get_color())
        widgets["detail_label"].config(text=description)

        # loading → 啟動動畫
        if status == "loading":
            self._animate_loading(index)

    # -------------------------------
    #  loading 圖示動畫（⟳）
    # -------------------------------

    def _animate_loading(self, index):
        if self.is_animating[index]:
            return

        self.is_animating[index] = True
        symbols = ["⟳", "↻", "⟲"]
        idx = [0]
        label = self.item_widgets[index]["status_label"]

        def animate():
            if label.winfo_exists() and self.items[index].status == "loading":
                label.config(text=symbols[idx[0] % 3])
                idx[0] += 1
                self.root.after(500, animate)
            else:
                self.is_animating[index] = False

        animate()

    # -------------------------------
    #  底部操作按鈕
    # -------------------------------

    def _create_buttons(self):
        frame = ttk.Frame(self)
        frame.pack(fill=tk.X, padx=10, pady=10)

        ttk.Button(frame, text="▶ 開始掃描",
                   command=self._on_start_scan).pack(side=tk.LEFT, padx=5)

        ttk.Button(frame, text="⏹ 停止",
                   command=self._on_stop_scan).pack(side=tk.LEFT, padx=5)

        ttk.Button(frame, text="↻ 重設",
                   command=self._on_reset).pack(side=tk.LEFT, padx=5)

        ttk.Button(frame, text="💾 匯出結果",
                   command=self._on_export).pack(side=tk.RIGHT, padx=5)

    # -------------------------------
    #  項目按鈕回調事件
    # -------------------------------

    def _on_start_scan(self):
        """模擬掃描流程：更新前兩個項目"""
        self.update_item(0, "loading", "正在檢查硬體...")
        self.root.after(1000, lambda: self.update_item(0, "success", "Arduino 已連接"))
        self.root.after(1500, lambda: self.update_item(1, "success", "Serial 配置完成"))

    def _on_stop_scan(self):
        messagebox.showwarning("停止", "掃描已中止")

    def _on_reset(self):
        """全部恢復 pending"""
        for i in range(len(self.items)):
            self.items[i].status = "pending"
            widgets = self.item_widgets[i]
            widgets["status_label"].config(text=PENDING, fg=COLOR_GRAY)
            widgets["detail_label"].config(text=self.items[i].description)

    def _on_export(self):
        messagebox.showinfo("匯出", "結果已匯出至 scan_images/result.ply")


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

        # Tab 1 — 3D 重建
        self.tab_rebuild = ttk.Frame(self.notebook)
        self.notebook.add(self.tab_rebuild, text="📊 3D 重建")
        self._create_rebuild_tab()

        # Tab 2 — 檢查清單
        self.tab_checklist = ttk.Frame(self.notebook)
        self.notebook.add(self.tab_checklist, text="✓ 檢查清單")
        self.checklist_frame = ChecklistFrame(self.tab_checklist)
        self.checklist_frame.pack(fill="both", expand=True)

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

        grid = self.grid_size_var.get()
        num_images = self.num_images_var.get()
        force = self.force_rebuild_var.get()

        self.log_insert(f"開始重建（Grid={grid}, Images={num_images}, Force={force})...")
        self.is_building = True
        self.rebuild_btn.config(state="disabled")

        # 更新檢查清單（體素雕刻項目）
        self.checklist_frame.update_item(6, "loading", "正在執行 Visual Hull 演算法...")

        # -------------------------
        # 背景執行
        # -------------------------

        def worker():
            try:
                ply_path = ensure_ply_exists(
                    str(self.ply_path),
                    force_rebuild=force,
                    grid_size=grid,
                    num_images=num_images,
                    no_display=True
                )

                if ply_path:
                    self.root.after(50, lambda: self.on_rebuild_complete(str(ply_path)))
                else:
                    self.root.after(50, lambda: self.log_insert("✗ PLY 生成失敗"))
                    self.root.after(50, lambda:
                        self.checklist_frame.update_item(6, "failed", "Visual Hull 演算失敗")
                    )

            except Exception as e:
                self.root.after(50, lambda: self.log_insert(f"✗ 錯誤：{e}"))
                self.root.after(50, lambda:
                    self.checklist_frame.update_item(6, "failed", f"錯誤：{e}")
                )

            finally:
                self.is_building = False
                self.root.after(50, lambda: self.rebuild_btn.config(state="normal"))

        threading.Thread(target=worker, daemon=True).start()

    # ============================================================
    #  重建完成後 → 載入 PLY
    # ============================================================

    def on_rebuild_complete(self, ply_path):
        self.log_insert("✓ 重建完成，正在載入 PLY...")
        self.checklist_frame.update_item(6, "success", "Visual Hull 完成")
        self.checklist_frame.update_item(7, "success", "PLY 已生成")
        self.checklist_frame.update_item(8, "loading", "正在載入 3D 點雲...")

        self.load_and_display_ply(ply_path)

    # ============================================================
    #  載入 PLY（使用者手動選擇）
    # ============================================================

    def on_view(self):
        path = filedialog.askopenfilename(
            initialdir=str(Path("scan_images")),
            title="選擇 PLY 檔案",
            filetypes=[("PLY files", "*.ply"), ("All files", "*.*")]
        )

        if not path:
            path = str(self.ply_path)
            if not Path(path).exists():
                resp = messagebox.askyesno(
                    "找不到 PLY",
                    f"找不到 {path}\n是否要立即建立 PLY？"
                )
                if resp:
                    self.on_rebuild()
                else:
                    self.log_insert("✗ 使用者取消")
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
            self.checklist_frame.update_item(8, "success", f"3D 點雲已顯示（{len(pts)} 點）")

        except Exception as e:
            self.log_insert(f"✗ 讀取 PLY 失敗：{e}")
            self.checklist_frame.update_item(8, "failed", f"視覺化失敗：{e}")

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

                    self.log_insert(f"✓ ConvexHull：{len(hull.simplices)} 三角形")
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
