#!/usr/bin/env python3
"""
主控 UI：整合重建、檢視與匯出功能
用法：
    python main_ui.py

功能：
- 執行重建（呼叫 reconstruct_simple.py）
- 讀取與顯示 PLY（內嵌 Matplotlib）
- 顯示日誌輸出
- 開啟 scan_images 資料夾
"""
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import threading
import subprocess
import sys
from pathlib import Path
import os
import time

import numpy as np
import matplotlib
matplotlib.use('TkAgg')
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
import matplotlib.pyplot as plt
from mpl_toolkits.mplot3d import Axes3D
from scipy.spatial import ConvexHull

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

        # 參數區
        param_frame = ttk.LabelFrame(root, text='參數')
        param_frame.grid(row=0, column=0, sticky='nsew', padx=8, pady=6)

        ttk.Label(param_frame, text='Grid size').grid(row=0, column=0, sticky='w')
        self.grid_size_var = tk.IntVar(value=40)
        ttk.Entry(param_frame, textvariable=self.grid_size_var, width=8).grid(row=0, column=1, sticky='w')

        ttk.Label(param_frame, text='Num images').grid(row=1, column=0, sticky='w')
        self.num_images_var = tk.IntVar(value=8)
        ttk.Entry(param_frame, textvariable=self.num_images_var, width=8).grid(row=1, column=1, sticky='w')

        # 按鈕區
        btn_frame = ttk.Frame(root)
        btn_frame.grid(row=1, column=0, sticky='ew', padx=8)

        self.rebuild_btn = ttk.Button(btn_frame, text='重建 (Rebuild)', command=self.on_rebuild)
        self.rebuild_btn.grid(row=0, column=0, padx=4, pady=6)

        self.view_btn = ttk.Button(btn_frame, text='載入並顯示 PLY', command=self.on_view)
        self.view_btn.grid(row=0, column=1, padx=4)

        self.open_folder_btn = ttk.Button(btn_frame, text='開啟 scan_images', command=self.open_scan_folder)
        self.open_folder_btn.grid(row=0, column=2, padx=4)

        self.force_rebuild_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(btn_frame, text='強制重建 (--rebuild)', variable=self.force_rebuild_var).grid(row=0, column=3, padx=6)

        # Matplotlib 畫布
        plot_frame = ttk.LabelFrame(root, text='3D 檢視')
        plot_frame.grid(row=2, column=0, sticky='nsew', padx=8, pady=6)
        root.rowconfigure(2, weight=1)
        root.columnconfigure(0, weight=1)

        self.fig = plt.Figure(figsize=(6,5))
        self.ax = self.fig.add_subplot(111, projection='3d')
        self.canvas = FigureCanvasTkAgg(self.fig, master=plot_frame)
        self.canvas.get_tk_widget().pack(fill='both', expand=True)

        # 日誌區
        log_frame = ttk.LabelFrame(root, text='執行日誌')
        log_frame.grid(row=3, column=0, sticky='ew', padx=8, pady=6)
        self.log = tk.Text(log_frame, height=8)
        self.log.pack(fill='both', expand=True)

        # 初始載入 PLY 若存在
        if self.ply_path.exists():
            self.log_insert(f'已找到 {self.ply_path}，可直接載入或重建。')

    def log_insert(self, text):
        ts = time.strftime('%H:%M:%S')
        self.log.insert('end', f'[{ts}] {text}\n')
        self.log.see('end')

    def run_subprocess(self, cmd, on_complete=None):
        """在背景執行子程序，將 stdout/stderr 寫入日誌"""
        def worker():
            self.log_insert(f'執行: {" ".join(cmd)}')
            try:
                proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
                for line in proc.stdout:
                    self.log_insert(line.rstrip())
                proc.wait()
                self.log_insert(f'執行完成 (碼={proc.returncode})')
                if on_complete:
                    self.root.after(50, on_complete)
            except Exception as e:
                self.log_insert(f'執行錯誤: {e}')

        threading.Thread(target=worker, daemon=True).start()

    def on_rebuild(self):
        # 呼叫 reconstruct_simple.py
        grid = self.grid_size_var.get()
        num_images = self.num_images_var.get()
        cmd = [sys.executable, 'reconstruct_simple.py', '--grid_size', str(grid), '--num_images', str(num_images)]
        if self.force_rebuild_var.get():
            cmd.append('--rebuild')
        self.run_subprocess(cmd, on_complete=self.on_rebuild_complete)

    def on_rebuild_complete(self):
        self.log_insert('重建完成，嘗試載入 PLY 並顯示。')
        self.on_view()

    def on_view(self):
        path = filedialog.askopenfilename(initialdir=str(Path('scan_images')), title='選擇 PLY 檔案', filetypes=[('PLY files','*.ply'), ('All files','*.*')])
        if not path:
            # 若使用者取消，嘗試使用預設路徑
            path = str(self.ply_path)
        if not Path(path).exists():
            resp = messagebox.askyesno('找不到 PLY', f'找不到 {path}，要自動重建並產生 PLY 嗎？')
            if resp:
                self.on_rebuild()
            return
        try:
            pts = load_ply_ascii(path)
            self.display_points(pts)
            self.log_insert(f'載入 {path} ({len(pts)} 點)')
        except Exception as e:
            self.log_insert(f'載入 PLY 失敗: {e}')

    def display_points(self, pts):
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
                else:
                    self.ax.scatter(pts[:,0], pts[:,1], pts[:,2], c='blue', s=2)
            except Exception as e:
                self.log_insert(f'ConvexHull render failed: {e}')
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
            subprocess.Popen(['xdg-open', folder])

if __name__ == '__main__':
    root = tk.Tk()
    root.geometry('900x800')
    app = MainUI(root)
    root.mainloop()
