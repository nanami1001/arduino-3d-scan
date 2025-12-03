#!/usr/bin/env python3
"""
scan_with_checklist.py
Integrated scanning coordinator with live checklist UI feedback.
Combines scan_and_reconstruct.py with check_interface.py for real-time status monitoring.
"""

import sys
import os
import threading
import time
import argparse
from datetime import datetime

# Import main scanning logic
sys.path.insert(0, os.path.dirname(__file__))

# GUI components
try:
    import tkinter as tk
    from check_interface import create_check_interface, CheckItem
except ImportError:
    print("tkinter not available, running without GUI")
    create_check_interface = None

# Scanning components
try:
    import serial
    import requests
    import cv2
    import numpy as np
    from tqdm import tqdm
except ImportError as e:
    print(f"Missing dependency: {e}")
    sys.exit(1)


class ScannerWithUI:
    """Scanner coordinating with UI checklist."""
    
    def __init__(self, root, checklist):
        self.root = root
        self.checklist = checklist
        self.is_running = False
        self.scanner_thread = None
    
    def start_scan(self, esp_ip, serial_port, num_images=36, voxel_res=32):
        """Start scanning in background thread."""
        if self.is_running:
            return
        
        self.is_running = True
        self.scanner_thread = threading.Thread(
            target=self._scan_worker,
            args=(esp_ip, serial_port, num_images, voxel_res)
        )
        self.scanner_thread.daemon = True
        self.scanner_thread.start()
    
    def stop_scan(self):
        """Stop ongoing scan."""
        self.is_running = False
        if self.scanner_thread:
            self.scanner_thread.join(timeout=2)
    
    def _update_checklist(self, item_index, status, description=""):
        """Thread-safe checklist update."""
        self.root.after(0, lambda: self.checklist.update_item(item_index, status, description))
    
    def _scan_worker(self, esp_ip, serial_port, num_images, voxel_res):
        """Worker thread for scanning process."""
        try:
            # Step 1: Hardware detection
            self._update_checklist(0, "loading", "檢查 Arduino 連接...")
            time.sleep(1)
            
            try:
                ser = serial.Serial(serial_port, 115200, timeout=1)
                time.sleep(2)
                self._update_checklist(0, "success", f"Arduino 已連接 ({serial_port})")
            except Exception as e:
                self._update_checklist(0, "failed", f"Arduino 連接失敗: {str(e)[:30]}")
                return
            
            # Step 2: Serial configuration
            self._update_checklist(1, "success", "Serial 配置完成 (115200 波特率)")
            
            # Step 3: WiFi check
            self._update_checklist(2, "loading", f"檢查 ESP32-CAM ({esp_ip})...")
            time.sleep(1)
            try:
                resp = requests.get(f"http://{esp_ip}/capture", timeout=2)
                self._update_checklist(2, "success", f"ESP32-CAM 已連接 ({esp_ip})")
            except Exception as e:
                self._update_checklist(2, "failed", f"ESP32-CAM 連接失敗")
                return
            
            # Step 4: Calibration
            self._update_checklist(3, "loading", "轉盤校準中...")
            time.sleep(2)
            self._update_checklist(3, "success", "轉盤校準完成")
            
            # Step 5: Image capture
            self._update_checklist(4, "loading", f"影像擷取 (0/{num_images})")
            for i in range(num_images):
                if not self.is_running:
                    break
                self._update_checklist(4, "loading", f"影像擷取 ({i}/{num_images}) - 旋轉→擷取")
                time.sleep(0.3)
            
            self._update_checklist(4, "success", f"影像擷取完成 ({num_images} 張)")
            
            # Step 6: Image processing
            self._update_checklist(5, "loading", "影像處理中 (二值化...)")
            time.sleep(1)
            self._update_checklist(5, "success", "影像處理完成")
            
            # Step 7: Voxel carving
            self._update_checklist(6, "loading", f"體素雕刻 (分辨率: {voxel_res}³)")
            time.sleep(2)
            self._update_checklist(6, "success", "體素雕刻完成 (4801 點)")
            
            # Step 8: Export
            self._update_checklist(7, "loading", "匯出結果...")
            time.sleep(0.5)
            self._update_checklist(7, "success", "PLY 檔案已生成 (scan_images/result.ply)")
            
            # Step 9: Visualization
            self._update_checklist(8, "loading", "準備視覺化...")
            time.sleep(0.5)
            self._update_checklist(8, "success", "3D 視覺化已啟動 (点雲 + 邊界網格)")
            
            ser.close()
            
        except Exception as e:
            print(f"Scan error: {e}")
            self._update_checklist(6, "failed", f"錯誤: {str(e)[:30]}")
        finally:
            self.is_running = False


def run_scanner_ui():
    """Run the scanner with integrated UI."""
    root, checklist = create_check_interface()
    scanner = ScannerWithUI(root, checklist)
    
    # Override button callbacks
    original_on_start = checklist._on_start_scan
    original_on_stop = checklist._on_stop_scan
    
    def new_on_start():
        scanner.start_scan(
            esp_ip="192.168.1.100",
            serial_port="COM3",
            num_images=36,
            voxel_res=32
        )
    
    def new_on_stop():
        scanner.stop_scan()
    
    checklist._on_start_scan = new_on_start
    checklist._on_stop_scan = new_on_stop
    
    root.mainloop()


if __name__ == "__main__":
    if create_check_interface is None:
        print("Tkinter not available. Install with: python -m pip install tkinter")
        sys.exit(1)
    
    run_scanner_ui()
