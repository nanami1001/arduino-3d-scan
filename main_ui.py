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

        # Tab 1 — 3D 重建
        self.tab_rebuild = ttk.Frame(self.notebook)
        self.notebook.add(self.tab_rebuild, text="📊 3D 重建")
        self._create_rebuild_tab()

        # Tab 2 — 檢查清單
        # (Checklist removed per new requirements)

        # 啟動時顯示模式選擇（延後到主迴圈以確保視窗已初始化）
        self.root.after(100, self.show_mode_selection)

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

        # 更新狀態：體素雕刻開始
        self.log_insert("⟳ 正在執行 Visual Hull 演算法...")

        # -------------------------
        # 背景執行
        # -------------------------

        # 選擇來源資料夾（dataset）
        images_folder = self._ask_dataset_folder()
        if images_folder is None:
            self.log_insert("✗ 使用者取消資料夾選擇，重建中止")
            self.is_building = False
            self.rebuild_btn.config(state="normal")
            return

        def worker():
            try:
                # 將輸出 PLY 放在選擇的資料夾內
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

    def _ask_dataset_folder(self):
        folder = filedialog.askdirectory(initialdir=str(Path("scan_images")), title="選擇資料夾作為資料來源")
        if not folder:
            return None
        return folder

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
        # 選擇來源資料夾（dataset）後載入或重建其 PLY
        folder = filedialog.askdirectory(initialdir=str(Path("scan_images")), title="選擇資料夾作為資料來源")
        if not folder:
            self.log_insert("✗ 使用者取消資料夾選擇")
            return

        ply_path = Path(folder) / "result_visual_hull.ply"
        if ply_path.exists():
            self.load_and_display_ply(str(ply_path))
            return

        resp = messagebox.askyesno("找不到 PLY", f"在所選資料夾未找到 PLY：{ply_path}\n是否要基於該資料夾立即建立 PLY？")
        if resp:
            # 啟動重建流程，使用該資料夾作為來源
            self.log_insert(f"開始為資料夾建立 PLY：{folder}")
            self.is_building = True
            self.rebuild_btn.config(state="disabled")

            def worker_build():
                try:
                    result = ensure_ply_exists(
                        str(ply_path),
                        force_rebuild=False,
                        grid_size=self.grid_size_var.get(),
                        num_images=self.num_images_var.get(),
                        no_display=True,
                        images_folder=folder,
                    )

                    if result:
                        self.root.after(50, lambda: self.load_and_display_ply(str(result)))
                    else:
                        self.root.after(50, lambda: self.log_insert("✗ PLY 建立失敗"))

                finally:
                    self.is_building = False
                    self.root.after(50, lambda: self.rebuild_btn.config(state="normal"))

            threading.Thread(target=worker_build, daemon=True).start()
        else:
            self.log_insert("✗ 使用者取消")

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
    #  啟動模式選擇與流程控制
    # ============================================================

    def show_mode_selection(self):
        dlg = tk.Toplevel(self.root)
        dlg.title("選擇操作模式")
        dlg.transient(self.root)
        dlg.grab_set()
        dlg.geometry("420x160")

        ttk.Label(dlg, text="請選擇系統操作模式：", font=("Arial", 12, "bold")).pack(anchor=tk.W, padx=12, pady=(12, 6))
        ttk.Label(dlg, text="A. 使用現有樣本產生 3D 影像（直接進入預覽模式）\nB. 使用影像採集設備從頭開始（清空資料並啟動採集）",
                  foreground=COLOR_LIGHT_TEXT).pack(anchor=tk.W, padx=12)

        btn_frame = ttk.Frame(dlg)
        btn_frame.pack(side=tk.BOTTOM, fill=tk.X, pady=12)

        ttk.Button(btn_frame, text="A: 使用現有樣本", command=lambda: (dlg.destroy(), self._mode_a())).pack(side=tk.LEFT, padx=12)
        ttk.Button(btn_frame, text="B: 從影像採集開始", command=lambda: (dlg.destroy(), self._mode_b())).pack(side=tk.RIGHT, padx=12)

    def _mode_a(self):
        self.log_insert("模式 A：使用現有樣本 → 直接進入預覽模式")

    def _mode_b(self):
        self.log_insert("模式 B：從影像採集設備開始（保留既有資料）")

        ok = self._hardware_check_dialog()
        if not ok:
            self.log_insert("✗ 使用者取消硬體檢查")
            return

        self.log_insert("啟動 ESP32-CAM 採集器（獨立視窗）。採集資料將儲存在使用者選擇或建立的新資料夾中。")
        try:
            script = Path("esp32_cam_capture.py").resolve()
            subprocess.Popen([sys.executable, str(script)])
        except Exception as e:
            messagebox.showerror("啟動失敗", f"無法啟動 esp32_cam_capture：{e}")
            return

        threading.Thread(target=self._monitor_capture_completion, daemon=True).start()

    def _clear_scan_images(self):
        folder = Path("scan_images")
        if not folder.exists():
            folder.mkdir(parents=True, exist_ok=True)
            return

        for p in folder.iterdir():
            try:
                if p.is_file():
                    p.unlink()
                elif p.is_dir():
                    import shutil
                    shutil.rmtree(p)
            except Exception as e:
                raise RuntimeError(f"刪除 {p} 失敗：{e}") from e

    def _hardware_check_dialog(self) -> bool:
        dlg = tk.Toplevel(self.root)
        dlg.title("硬體檢查")
        dlg.transient(self.root)
        dlg.grab_set()
        dlg.geometry("520x260")

        ttk.Label(dlg, text="請確認以下硬體與連線已完成：", font=("Arial", 12, "bold")).pack(anchor=tk.W, padx=12, pady=(12, 6))

        checks = [
            "ESP32-CAM 已正確安裝並固定",
            "電源與網路連線已接好",
            "轉盤與固定結構已完成安裝",
            "相機視角與對位已確認",
        ]

        for c in checks:
            ttk.Label(dlg, text=f"• {c}", foreground=COLOR_TEXT).pack(anchor=tk.W, padx=18, pady=4)

        result = {"ok": False}

        def on_ok():
            result["ok"] = True
            dlg.destroy()

        def on_cancel():
            dlg.destroy()

        btn_frame = ttk.Frame(dlg)
        btn_frame.pack(side=tk.BOTTOM, fill=tk.X, pady=12)
        ttk.Button(btn_frame, text="我已完成硬體檢查", command=on_ok).pack(side=tk.LEFT, padx=12)
        ttk.Button(btn_frame, text="取消", command=on_cancel).pack(side=tk.RIGHT, padx=12)

        self.root.wait_window(dlg)
        return result["ok"]

    def _monitor_capture_completion(self):
        self.log_insert("開始監控採集結果（等待任一子資料夾下的 result_visual_hull.ply）...")
        timeout = 60 * 30  # 最多等待 30 分鐘
        start = time.time()
        while time.time() - start < timeout:
            for p in Path('.').rglob('result_visual_hull.ply'):
                try:
                    if p.exists() and p.stat().st_size > 0:
                        self.root.after(50, lambda p=p: self.log_insert(f"✓ 偵測到 PLY：{p}，導入預覽模式"))
                        self.root.after(100, lambda: self.notebook.select(self.tab_rebuild))
                        self.root.after(150, lambda p=p: self.load_and_display_ply(str(p)))
                        return
                except Exception:
                    continue

            time.sleep(2)

        self.root.after(50, lambda: self.log_insert("⚠ 監控逾時，未偵測到 PLY。"))
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
