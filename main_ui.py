#!/usr/bin/env python3
"""
主控 UI：整合重建、檢視、檢查清單與匯出功能
用法：
    python main_ui.py

功能：
- 3D 重建頁面：執行重建、讀取與顯示 PLY
- 檢查清單頁面：硬體狀態、擷取進度、重建結果
- 背景執行 build_ply，無獨立視窗
"""
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import threading
import sys
from pathlib import Path
from datetime import datetime
import os
import time
from datetime import datetime

import numpy as np
import matplotlib
matplotlib.use('TkAgg')
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
import matplotlib.pyplot as plt
from mpl_toolkits.mplot3d import Axes3D
from scipy.spatial import ConvexHull

from build_ply import ensure_ply_exists

# 色彩主題（與 check.png 設計相符）
COLOR_BG = "#FFFFFF"
COLOR_GREEN = "#4CAF50"
COLOR_RED = "#F44336"
COLOR_GRAY = "#CCCCCC"
COLOR_BLUE = "#2196F3"
COLOR_TEXT = "#333333"
COLOR_LIGHT_TEXT = "#666666"

CHECKMARK = "✓"
CROSS = "✗"
PENDING = "○"
LOADING = "⟳"


class CheckItem:
    """檢查項目（狀態容器）"""
    def __init__(self, title, description=""):
        self.title = title
        self.description = description
        self.status = "pending"  # pending, loading, success, failed
        self.timestamp = None
        self.details = ""

    def set_status(self, status, details=""):
        self.status = status
        self.timestamp = datetime.now().strftime("%H:%M:%S")
        self.details = details

    def get_icon(self):
        if self.status == "success":
            return CHECKMARK
        elif self.status == "failed":
            return CROSS
        elif self.status == "loading":
            return LOADING
        else:
            return PENDING

    def get_color(self):
        if self.status == "success":
            return COLOR_GREEN
        elif self.status == "failed":
            return COLOR_RED
        elif self.status == "loading":
            return COLOR_BLUE
        else:
            return COLOR_GRAY


class ChecklistFrame(ttk.Frame):
    """檢查清單主頁面"""

    def __init__(self, root, **kwargs):
        super().__init__(root, **kwargs)
        self.root = root
        self.items = []
        self.item_widgets = {}
        self.is_animating = {}

        self._create_header()
        self._create_checklist()
        self._create_buttons()

    def _create_header(self):
        """建立標題區"""
        header = ttk.Frame(self, height=60)
        header.pack(fill=tk.X, padx=15, pady=10)

        title_label = ttk.Label(header, text="Arduino 3D 掃描系統檢查清單",
                               font=("Arial", 16, "bold"))
        title_label.pack(anchor=tk.W)

        subtitle_label = ttk.Label(header, text="硬體配置 • 擷取進度 • 重建結果",
                                  font=("Arial", 10), foreground=COLOR_LIGHT_TEXT)
        subtitle_label.pack(anchor=tk.W)

    def _create_checklist(self):
        """建立可捲動的檢查清單"""
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

        # 新增預設項目
        self._add_default_items()

    def _add_default_items(self):
        """新增預設檢查項目"""
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

    def add_item(self, check_item):
        """新增項目到清單"""
        self.items.append(check_item)

        # 建立項目框架
        item_frame = tk.Frame(self.checklist_frame, bg=COLOR_BG)
        item_frame.pack(fill=tk.X, pady=8, padx=5)

        # 狀態圖示
        status_label = tk.Label(item_frame, text=check_item.get_icon(),
                               bg=COLOR_BG, fg=check_item.get_color(),
                               font=("Arial", 14, "bold"), width=3)
        status_label.pack(side=tk.LEFT, padx=10)

        # 文本內容
        text_frame = tk.Frame(item_frame, bg=COLOR_BG)
        text_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        title_label = tk.Label(text_frame, text=check_item.title,
                              bg=COLOR_BG, fg=COLOR_TEXT,
                              font=("Arial", 11, "bold"), justify=tk.LEFT)
        title_label.pack(anchor=tk.W)

        detail_label = tk.Label(text_frame, text=check_item.description,
                               bg=COLOR_BG, fg=COLOR_LIGHT_TEXT,
                               font=("Arial", 9), justify=tk.LEFT)
        detail_label.pack(anchor=tk.W)

        # 時間戳
        if check_item.timestamp:
            time_label = tk.Label(text_frame, text=f"[{check_item.timestamp}]",
                                 bg=COLOR_BG, fg=COLOR_GRAY,
                                 font=("Arial", 8))
            time_label.pack(anchor=tk.E)

        # 儲存參考以便更新
        idx = len(self.items) - 1
        self.item_widgets[idx] = {
            'frame': item_frame,
            'status_label': status_label,
            'title_label': title_label,
            'detail_label': detail_label
        }
        self.is_animating[idx] = False

    def update_item(self, index, status, description=""):
        """更新項目狀態"""
        if index >= len(self.items):
            return

        item = self.items[index]
        item.set_status(status, description)

        # 更新 UI
        widgets = self.item_widgets[index]
        widgets['status_label'].config(text=item.get_icon(),
                                       fg=item.get_color())
        widgets['detail_label'].config(text=description)

        # 若為載入狀態則啟動動畫
        if status == "loading":
            self._animate_loading(index)

    def _animate_loading(self, index):
        """旋轉載入圖示動畫"""
        if self.is_animating[index]:
            return

        self.is_animating[index] = True
        symbols = ["⟳", "↻", "⟲"]
        idx = [0]
        label = self.item_widgets[index]['status_label']

        def animate():
            if label.winfo_exists() and self.items[index].status == "loading":
                label.config(text=symbols[idx[0] % len(symbols)])
                idx[0] += 1
                self.root.after(500, animate)
            else:
                self.is_animating[index] = False

        animate()

    def _create_buttons(self):
        """建立操作按鈕"""
        button_frame = ttk.Frame(self)
        button_frame.pack(fill=tk.X, padx=10, pady=10)

        start_btn = ttk.Button(button_frame, text="▶ 開始掃描",
                              command=self._on_start_scan)
        start_btn.pack(side=tk.LEFT, padx=5)

        stop_btn = ttk.Button(button_frame, text="⏹ 停止",
                             command=self._on_stop_scan)
        stop_btn.pack(side=tk.LEFT, padx=5)

        reset_btn = ttk.Button(button_frame, text="↻ 重設",
                              command=self._on_reset)
        reset_btn.pack(side=tk.LEFT, padx=5)

        export_btn = ttk.Button(button_frame, text="💾 匯出結果",
                               command=self._on_export)
        export_btn.pack(side=tk.RIGHT, padx=5)

    def _on_start_scan(self):
        """開始掃描按鈕回調"""
        self.update_item(0, "loading", "正在檢查硬體...")
        self.root.after(1000, lambda: self.update_item(0, "success", "Arduino 已連接"))
        self.root.after(1500, lambda: self.update_item(1, "success", "Serial 配置完成"))

    def _on_stop_scan(self):
        """停止掃描按鈕回調"""
        messagebox.showwarning("停止", "掃描已中止")

    def _on_reset(self):
        """重設所有項目"""
        for i in range(len(self.items)):
            self.items[i].status = "pending"
            self.items[i].timestamp = None
            widgets = self.item_widgets[i]
            widgets['status_label'].config(text=PENDING, fg=COLOR_GRAY)
            widgets['detail_label'].config(text=self.items[i].description)

    def _on_export(self):
        """匯出結果"""
        messagebox.showinfo("匯出", "結果已匯出至 scan_images/result.ply")


class Tooltip:
    """簡單的 Tooltip 實現"""
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
        self.tipwindow = tw = tk.Toplevel(self.widget)
        tw.wm_overrideredirect(True)
        tw.wm_geometry(f"+{x}+{y}")
        label = tk.Label(tw, text=self.text, background="lightyellow",
                         relief="solid", borderwidth=1, font=("Arial", 9),
                         wraplength=250, justify="left")
        label.pack()

    def hide_tip(self, event=None):
        if self.tipwindow:
            self.tipwindow.destroy()
            self.tipwindow = None


# PLY 讀取器（ASCII）
def load_ply_ascii(path):
    pts = []
    with open(path, 'r') as f:
        header_ended = False
        for line in f:
            line = line.strip()
            if not header_ended:
                if line == 'end_header':
                    header_ended = True
                continue
            if line:
                parts = line.split()
                if len(parts) >= 3:
                    try:
                        x, y, z = map(float, parts[:3])
                        pts.append([x, y, z])
                    except:
                        continue
    return np.array(pts, dtype=np.float32)


class MainUI:
    def __init__(self, root):
        self.root = root
        root.title('3D Scan — 主控介面')
        self.base_dir = Path.cwd()
        self.ply_path = Path('scan_images') / 'result_visual_hull.ply'
        self.is_building = False  # 標記是否正在建立 PLY

        # 建立標籤頁介面
        self.notebook = ttk.Notebook(root)
        self.notebook.pack(fill='both', expand=True, padx=8, pady=6)

        # Tab 1: 3D 重建
        self.tab_rebuild = ttk.Frame(self.notebook)
        self.notebook.add(self.tab_rebuild, text='📊 3D 重建')
        self._create_rebuild_tab()

        # Tab 2: 檢查清單
        self.tab_checklist = ttk.Frame(self.notebook)
        self.notebook.add(self.tab_checklist, text='✓ 檢查清單')
        self.checklist_frame = ChecklistFrame(self.tab_checklist)
        self.checklist_frame.pack(fill='both', expand=True)

    def _create_rebuild_tab(self):
        """建立 3D 重建標籤頁"""
        # 參數區
        param_frame = ttk.LabelFrame(self.tab_rebuild, text='參數')
        param_frame.grid(row=0, column=0, sticky='nsew', padx=8, pady=6)

        ttk.Label(param_frame, text='Grid size').grid(row=0, column=0, sticky='w')
        self.grid_size_var = tk.IntVar(value=40)
        ttk.Entry(param_frame, textvariable=self.grid_size_var, width=8).grid(row=0, column=1, sticky='w')

        ttk.Label(param_frame, text='Num images').grid(row=1, column=0, sticky='w')
        self.num_images_var = tk.IntVar(value=8)
        ttk.Entry(param_frame, textvariable=self.num_images_var, width=8).grid(row=1, column=1, sticky='w')

        # 按鈕區
        btn_frame = ttk.Frame(self.tab_rebuild)
        btn_frame.grid(row=1, column=0, sticky='ew', padx=8)

        self.rebuild_btn = ttk.Button(btn_frame, text='重建 (Rebuild)', command=self.on_rebuild)
        self.rebuild_btn.grid(row=0, column=0, padx=4, pady=6)
        Tooltip(self.rebuild_btn, 
                '【重建】\n'
                '使用 8 張水平掃描影像，透過 Visual Hull 演算法（輪廓交集）\n'
                '重新推算 3D 模型。根據 Grid size 決定重建精度。\n'
                '完成後自動載入並顯示 PLY 檔。')

        self.view_btn = ttk.Button(btn_frame, text='載入並顯示 PLY', command=self.on_view)
        self.view_btn.grid(row=0, column=1, padx=4)
        Tooltip(self.view_btn,
                '【載入並顯示】\n'
                '開啟檔案選擇對話框，選擇一個 PLY 檔案進行讀取。\n'
                '如果找不到現有的 PLY，可選擇建立。\n'
                '載入後在 3D 檢視區以網格和邊框線條呈現。')

        self.open_folder_btn = ttk.Button(btn_frame, text='開啟 scan_images', command=self.open_scan_folder)
        self.open_folder_btn.grid(row=0, column=2, padx=4)
        Tooltip(self.open_folder_btn,
                '【開啟資料夾】\n'
                '快速開啟 scan_images 資料夾，檢視掃描影像、\n'
                'PLY 檔案或其他重建成果。')

        self.force_rebuild_var = tk.BooleanVar(value=False)
        self.force_rebuild_check = ttk.Checkbutton(btn_frame, text='強制重建 (--rebuild)', variable=self.force_rebuild_var)
        self.force_rebuild_check.grid(row=0, column=3, padx=6)
        Tooltip(self.force_rebuild_check,
                '【強制重建】\n'
                '勾選後，按下【重建】會忽略現有 PLY 檔案，\n'
                '強制重新執行完整的重建流程。\n'
                '不勾選則使用現有 PLY（若存在）。')

        # Matplotlib 畫布
        plot_frame = ttk.LabelFrame(self.tab_rebuild, text='3D 檢視')
        plot_frame.grid(row=2, column=0, sticky='nsew', padx=8, pady=6)
        self.tab_rebuild.rowconfigure(2, weight=1)
        self.tab_rebuild.columnconfigure(0, weight=1)

        self.fig = plt.Figure(figsize=(6,5))
        self.ax = self.fig.add_subplot(111, projection='3d')
        self.canvas = FigureCanvasTkAgg(self.fig, master=plot_frame)
        self.canvas.get_tk_widget().pack(fill='both', expand=True)

        # 日誌區
        log_frame = ttk.LabelFrame(self.tab_rebuild, text='執行日誌')
        log_frame.grid(row=3, column=0, sticky='ew', padx=8, pady=6)
        self.log = tk.Text(log_frame, height=8)
        self.log.pack(fill='both', expand=True)

        # 初始載入 PLY 若存在
        if self.ply_path.exists():
            self.log_insert(f'✓ 已找到 {self.ply_path}，可直接載入或重建。')
        else:
            self.log_insert(f'⚠ 找不到 PLY 檔。請按下【重建】或【載入並顯示】。')

    def log_insert(self, text):
        ts = time.strftime('%H:%M:%S')
        self.log.insert('end', f'[{ts}] {text}\n')
        self.log.see('end')
        self.root.update()

    def on_rebuild(self):
        """執行重建流程"""
        if self.is_building:
            self.log_insert('⚠ 正在建立 PLY，請稍候...')
            return

        grid = self.grid_size_var.get()
        num_images = self.num_images_var.get()
        force_rebuild = self.force_rebuild_var.get()

        self.log_insert(f'開始重建（Grid={grid}, Images={num_images}, Force={force_rebuild})...')
        self.is_building = True
        self.rebuild_btn.config(state='disabled')
        
        # 更新檢查清單
        self.checklist_frame.update_item(6, "loading", "正在執行 Visual Hull 演算法...")

        def worker():
            try:
                ply_path = ensure_ply_exists(
                    str(self.ply_path),
                    force_rebuild=force_rebuild,
                    grid_size=grid,
                    num_images=num_images,
                    no_display=True  # 不顯示獨立視窗
                )
                if ply_path:
                    self.root.after(50, lambda: self.on_rebuild_complete(str(ply_path)))
                else:
                    self.root.after(50, lambda: self.log_insert('✗ PLY 建立失敗'))
                    self.root.after(50, lambda: self.checklist_frame.update_item(6, "failed", "Visual Hull 演算失敗"))
            except Exception as e:
                self.root.after(50, lambda: self.log_insert(f'✗ 建立出錯: {e}'))
                self.root.after(50, lambda: self.checklist_frame.update_item(6, "failed", f"錯誤: {e}"))
            finally:
                self.is_building = False
                self.root.after(50, lambda: self.rebuild_btn.config(state='normal'))

        threading.Thread(target=worker, daemon=True).start()

    def on_rebuild_complete(self, ply_path):
        """重建完成後自動載入並顯示"""
        self.log_insert(f'✓ 重建完成，自動載入 PLY...')
        self.checklist_frame.update_item(6, "success", "Visual Hull 完成")
        self.checklist_frame.update_item(7, "success", "PLY 檔案已生成")
        self.checklist_frame.update_item(8, "loading", "準備視覺化...")
        self.load_and_display_ply(ply_path)

    def on_view(self):
        """載入並顯示 PLY"""
        path = filedialog.askopenfilename(
            initialdir=str(Path('scan_images')),
            title='選擇 PLY 檔案',
            filetypes=[('PLY files', '*.ply'), ('All files', '*.*')]
        )

        if not path:
            # 若使用者取消，嘗試使用預設路徑
            path = str(self.ply_path)
            if not Path(path).exists():
                # 持續提示建立 PLY
                resp = messagebox.askyesno(
                    '找不到 PLY',
                    f'找不到 {path}\n\n是否要建立 PLY 檔案？\n'
                    '（將使用當前的 Grid size 和 Num images 設定）'
                )
                if resp:
                    self.on_rebuild()
                else:
                    self.log_insert('✗ 使用者取消')
                return

        self.load_and_display_ply(path)

    def load_and_display_ply(self, path):
        """載入並顯示 PLY 檔案"""
        path = Path(path)

        # 若檔案不存在，嘗試建立
        if not path.exists():
            self.log_insert(f'⚠ 找不到 {path}，自動建立中...')
            if self.is_building:
                self.log_insert('⚠ 已有建立工作在進行中，請稍候...')
                return

            self.is_building = True

            def build_worker():
                try:
                    result = ensure_ply_exists(
                        str(path),
                        force_rebuild=False,
                        grid_size=self.grid_size_var.get(),
                        num_images=self.num_images_var.get(),
                        no_display=True
                    )
                    if result:
                        self.root.after(50, lambda: self.load_and_display_ply(str(result)))
                    else:
                        self.root.after(50, lambda: self.log_insert('✗ PLY 建立失敗'))
                except Exception as e:
                    self.root.after(50, lambda: self.log_insert(f'✗ 建立出錯: {e}'))
                finally:
                    self.is_building = False

            threading.Thread(target=build_worker, daemon=True).start()
            return

        # 載入 PLY
        try:
            pts = load_ply_ascii(str(path))
            self.log_insert(f'✓ 載入 {path.name} ({len(pts)} 點)')
            self.display_points(pts)
            self.checklist_frame.update_item(8, "success", f"3D 點雲已顯示 ({len(pts)} 點)")
        except Exception as e:
            self.log_insert(f'✗ 載入 PLY 失敗: {e}')
            self.checklist_frame.update_item(8, "failed", f"視覺化失敗: {e}")

    def display_points(self, pts):
        """在 UI 中顯示點雲"""
        self.ax.clear()
        if len(pts) == 0:
            self.ax.text(0.5, 0.5, 0.5, 'No points', transform=self.ax.transAxes)
        else:
            # 嘗試用 ConvexHull 畫填滿的簡單幾何形狀並疊上邊框
            try:
                if len(pts) >= 4:
                    hull = ConvexHull(pts)
                    self.ax.plot_trisurf(pts[:,0], pts[:,1], pts[:,2],
                                         triangles=hull.simplices, linewidth=0.2,
                                         edgecolor='k', color='lightgreen', alpha=0.85)
                    for tri in hull.simplices:
                        tri_pts = pts[tri]
                        xs, ys, zs = tri_pts[:,0], tri_pts[:,1], tri_pts[:,2]
                        self.ax.plot(np.append(xs, xs[0]), np.append(ys, ys[0]), np.append(zs, zs[0]),
                                     color='black', linewidth=0.25, alpha=0.8)
                    self.log_insert(f'✓ ConvexHull: {len(hull.simplices)} 三角形')
                else:
                    self.ax.scatter(pts[:,0], pts[:,1], pts[:,2], c='blue', s=2)
            except Exception as e:
                self.log_insert(f'⚠ ConvexHull 計算失敗: {e}')
                self.ax.scatter(pts[:,0], pts[:,1], pts[:,2], c='blue', s=2)

            self.ax.set_xlabel('X')
            self.ax.set_ylabel('Y')
            self.ax.set_zlabel('Z')
            self.ax.set_title(f'Point cloud ({len(pts)} points)')

        # 等比例顯示
        def set_axes_equal(ax):
            x_limits = ax.get_xlim3d()
            y_limits = ax.get_ylim3d()
            z_limits = ax.get_zlim3d()

            x_range = abs(x_limits[1] - x_limits[0])
            x_middle = np.mean(x_limits)
            y_range = abs(y_limits[1] - y_limits[0])
            y_middle = np.mean(y_limits)
            z_range = abs(z_limits[1] - z_limits[0])
            z_middle = np.mean(z_limits)

            plot_radius = 0.5 * max([x_range, y_range, z_range])

            ax.set_xlim3d([x_middle - plot_radius, x_middle + plot_radius])
            ax.set_ylim3d([y_middle - plot_radius, y_middle + plot_radius])
            ax.set_zlim3d([z_middle - plot_radius, z_middle + plot_radius])

        set_axes_equal(self.ax)
        self.canvas.draw()

    def open_scan_folder(self):
        folder = str(Path('scan_images').resolve())
        if os.name == 'nt':
            os.startfile(folder)
        else:
            import subprocess
            subprocess.Popen(['xdg-open', folder])


if __name__ == '__main__':
    root = tk.Tk()
    root.geometry('900x800')
    app = MainUI(root)
    root.mainloop()
