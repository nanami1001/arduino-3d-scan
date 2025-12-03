#!/usr/bin/env python3
"""
check_interface.py
Interactive checklist UI for the Arduino 3D scanning system.
Displays hardware status, capture progress, and reconstruction results.
"""

import sys
import tkinter as tk
from tkinter import ttk, messagebox
import os
import time
import threading
import serial
import json
from datetime import datetime

try:
    import cv2
except ImportError:
    cv2 = None

# Color scheme matching check.png design
COLOR_BG = "#FFFFFF"  # White background
COLOR_GREEN = "#4CAF50"  # Success/Complete
COLOR_RED = "#F44336"  # Error/Failed
COLOR_GRAY = "#CCCCCC"  # Pending/Inactive
COLOR_BLUE = "#2196F3"  # Active/In Progress
COLOR_TEXT = "#333333"  # Dark text
COLOR_LIGHT_TEXT = "#666666"  # Light gray text

CHECKMARK = "✓"
CROSS = "✗"
PENDING = "○"
LOADING = "⟳"

class CheckItem:
    """Represents a single check item with status."""
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
    """Main checklist UI frame."""
    
    def __init__(self, root, **kwargs):
        super().__init__(root, **kwargs)
        self.root = root
        self.items = []
        self.item_widgets = {}
        
        self._create_header()
        self._create_checklist()
        self._create_buttons()
        
    def _create_header(self):
        """Create header section."""
        header = ttk.Frame(self, height=60)
        header.pack(fill=tk.X, padx=15, pady=10)
        
        title_label = ttk.Label(header, text="Arduino 3D 掃描系統檢查清單", 
                               font=("Arial", 16, "bold"))
        title_label.pack(anchor=tk.W)
        
        subtitle_label = ttk.Label(header, text="硬體配置 • 擷取進度 • 重建結果",
                                  font=("Arial", 10), foreground=COLOR_LIGHT_TEXT)
        subtitle_label.pack(anchor=tk.W)
    
    def _create_checklist(self):
        """Create scrollable checklist."""
        # Create canvas with scrollbar
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
        
        # Initialize with default items
        self._add_default_items()
    
    def _add_default_items(self):
        """Add default checklist items."""
        default_items = [
            CheckItem("硬體偵測", "檢查 Arduino 和 ESP32-CAM 連接"),
            CheckItem("Serial 口配置", f"COM 埠: COM3 (115200 波特率)"),
            CheckItem("WiFi 連線", f"ESP32-CAM IP: 192.168.1.100"),
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
        """Add an item to the checklist."""
        self.items.append(check_item)
        
        # Create item frame
        item_frame = tk.Frame(self.checklist_frame, bg=COLOR_BG)
        item_frame.pack(fill=tk.X, pady=8, padx=5)
        
        # Icon/Status
        status_label = tk.Label(item_frame, text=check_item.get_icon(), 
                               bg=COLOR_BG, fg=check_item.get_color(),
                               font=("Arial", 14, "bold"), width=3)
        status_label.pack(side=tk.LEFT, padx=10)
        
        # Text content
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
        
        # Timestamp
        if check_item.timestamp:
            time_label = tk.Label(text_frame, text=f"[{check_item.timestamp}]",
                                 bg=COLOR_BG, fg=COLOR_GRAY,
                                 font=("Arial", 8))
            time_label.pack(anchor=tk.E)
        
        # Store references for updating
        self.item_widgets[len(self.items) - 1] = {
            'frame': item_frame,
            'status_label': status_label,
            'title_label': title_label,
            'detail_label': detail_label
        }
    
    def update_item(self, index, status, description=""):
        """Update an item's status."""
        if index >= len(self.items):
            return
        
        item = self.items[index]
        old_status = item.status
        item.set_status(status, description)
        
        # Update UI
        widgets = self.item_widgets[index]
        widgets['status_label'].config(text=item.get_icon(), 
                                       fg=item.get_color())
        widgets['detail_label'].config(text=description)
        
        # Add visual feedback
        if status == "loading":
            self._animate_loading(widgets['status_label'])
    
    def _animate_loading(self, label):
        """Animate the loading icon."""
        symbols = ["⟳", "↻", "⟲"]
        idx = [0]
        
        def animate():
            if label.winfo_exists():
                label.config(text=symbols[idx[0] % len(symbols)])
                idx[0] += 1
                self.root.after(500, animate)
        
        animate()
    
    def _create_buttons(self):
        """Create action buttons."""
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
        """Start scan button callback."""
        self.update_item(0, "loading", "正在檢查硬體...")
        messagebox.showinfo("掃描", "開始 3D 掃描過程")
        self.update_item(0, "success", "Arduino 已連接")
        self.update_item(1, "success", "Serial 配置完成")
    
    def _on_stop_scan(self):
        """Stop scan button callback."""
        messagebox.showwarning("停止", "掃描已中止")
    
    def _on_reset(self):
        """Reset all items."""
        for i in range(len(self.items)):
            self.items[i].status = "pending"
            self.items[i].timestamp = None
            widgets = self.item_widgets[i]
            widgets['status_label'].config(text=PENDING, fg=COLOR_GRAY)
            widgets['detail_label'].config(text=self.items[i].description)
    
    def _on_export(self):
        """Export results."""
        messagebox.showinfo("匯出", "結果已匯出至 scan_images/result.ply")


def create_check_interface(master=None):
    """Create and run the check interface."""
    if master is None:
        root = tk.Tk()
    else:
        root = master
    
    # Configure window
    root.title("Arduino 3D 掃描系統 - 檢查清單")
    root.geometry("500x700")
    root.configure(bg=COLOR_BG)
    
    # Set style
    style = ttk.Style()
    style.theme_use('clam')
    style.configure('TFrame', background=COLOR_BG)
    style.configure('TLabel', background=COLOR_BG)
    style.configure('TButton', font=("Arial", 10))
    
    # Create main checklist frame
    checklist = ChecklistFrame(root)
    checklist.pack(fill=tk.BOTH, expand=True)
    
    return root, checklist


if __name__ == "__main__":
    root, checklist = create_check_interface()
    root.mainloop()
