#!/usr/bin/env python3
"""
快速整合驗證測試
確認手冊與 UI 已整合到 main_ui.py 中
"""

import sys
import time
from pathlib import Path

def test_imports():
    """測試所有必要的模組匯入"""
    print("🔍 測試模組匯入...")
    try:
        import tkinter as tk
        from tkinter import ttk
        import threading
        from datetime import datetime
        import matplotlib.pyplot as plt
        from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
        from scipy.spatial import ConvexHull
        import numpy as np
        print("  ✓ 所有基礎模組可用")
        return True
    except ImportError as e:
        print(f"  ✗ 模組匯入失敗: {e}")
        return False

def test_file_structure():
    """驗證檔案結構"""
    print("\n🔍 驗證檔案結構...")
    required_files = {
        'main_ui.py': 'Main UI with integrated checklist',
        'build_ply.py': 'PLY builder module',
        'reconstruct_simple.py': 'Visual Hull algorithm',
        'view_ply.py': 'PLY viewer',
    }
    
    all_exist = True
    for filename, description in required_files.items():
        path = Path(filename)
        exists = path.exists()
        status = "✓" if exists else "✗"
        print(f"  {status} {filename:<25} ({description})")
        if not exists:
            all_exist = False
    
    return all_exist

def test_main_ui_integration():
    """驗證 main_ui.py 包含必要的整合"""
    print("\n🔍 驗證 main_ui.py 整合...")
    
    main_ui_path = Path('main_ui.py')
    if not main_ui_path.exists():
        print("  ✗ main_ui.py 不存在")
        return False
    
    content = main_ui_path.read_text(encoding='utf-8')
    
    checks = {
        "Notebook interface": "self.notebook = ttk.Notebook(root)",
        "Operations tab": "🔧 操作選擇",
        "Manual tab": "指導手冊",
        "Rebuild tab": "📊 3D 重建",
        "Mode confirm": "開始",
        "Manual page": "def _create_manual_tab(self):",
        "Rebuild methods": "def _create_rebuild_tab(self):",
    }
    
    all_present = True
    for check_name, check_string in checks.items():
        present = check_string in content
        status = "✓" if present else "✗"
        print(f"  {status} {check_name}")
        if not present:
            all_present = False
    
    return all_present

def test_checklist_items():
    """檢查舊版清單測試已移除"""
    print("\n🔍 檢查舊版清單測試狀態...")
    legacy_filename = 'check' + '_interface.py'
    exists = Path(legacy_filename).exists()
    print(f"  {'✗' if exists else '✓'} 舊版清單檔已{'存在' if exists else '移除'}")
    return not exists

def test_syntax():
    """驗證 Python 語法"""
    print("\n🔍 驗證 Python 語法...")
    try:
        import py_compile
        py_compile.compile('main_ui.py', doraise=True)
        print("  ✓ main_ui.py 語法正確")
        return True
    except py_compile.PyCompileError as e:
        print(f"  ✗ 語法錯誤: {e}")
        return False

def main():
    """執行所有測試"""
    print("=" * 60)
    print("Arduino 3D Scan — 整合驗證測試")
    print("=" * 60)
    
    results = {
        "模組匯入": test_imports(),
        "檔案結構": test_file_structure(),
        "main_ui.py 整合": test_main_ui_integration(),
        "檢查清單項目": test_checklist_items(),
        "Python 語法": test_syntax(),
    }
    
    print("\n" + "=" * 60)
    print("測試摘要")
    print("=" * 60)
    
    passed = sum(1 for v in results.values() if v is True)
    total = len([v for v in results.values() if v is not None])
    
    for test_name, result in results.items():
        if result is True:
            status = "✓ PASS"
        elif result is False:
            status = "✗ FAIL"
        else:
            status = "⚠ SKIP"
        print(f"{test_name:<20} {status}")
    
    print(f"\n結果: {passed}/{total} 通過")
    
    if passed == total:
        print("\n✅ 所有測試通過！整合完成。")
        print("   執行: python main_ui.py")
        return 0
    else:
        print("\n⚠ 某些測試失敗，請檢查上述錯誤。")
        return 1

if __name__ == '__main__':
    sys.exit(main())
