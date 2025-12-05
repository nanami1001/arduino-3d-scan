#!/usr/bin/env python3
"""
快速整合驗證測試
確認 check_interface.py 已完全整合到 main_ui.py 中
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
        'check_interface.py': 'Original checklist (reference)',
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
    """驗證 main_ui.py 包含所有必要的整合"""
    print("\n🔍 驗證 main_ui.py 整合...")
    
    main_ui_path = Path('main_ui.py')
    if not main_ui_path.exists():
        print("  ✗ main_ui.py 不存在")
        return False
    
    content = main_ui_path.read_text(encoding='utf-8')
    
    checks = {
        "CheckItem class": "class CheckItem:",
        "ChecklistFrame class": "class ChecklistFrame(ttk.Frame):",
        "Notebook interface": "self.notebook = ttk.Notebook(root)",
        "Checklist tab": "self.tab_checklist",
        "Rebuild updates checklist": "self.checklist_frame.update_item(6",
        "datetime import": "from datetime import datetime",
        "Tab 1 rebuild methods": "def _create_rebuild_tab(self):",
        "Tab 2 checklist": "self.checklist_frame = ChecklistFrame(self.tab_checklist)",
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
    """驗證檢查清單項目數量"""
    print("\n🔍 驗證檢查清單項目...")
    
    check_interface_path = Path('check_interface.py')
    if not check_interface_path.exists():
        print("  ⚠ check_interface.py 不存在（參考用）")
        return None
    
    content = check_interface_path.read_text(encoding='utf-8')
    item_count = content.count('CheckItem(')
    print(f"  ✓ 原始 check_interface.py: {item_count} 項目")
    
    # 驗證 main_ui.py 中是否有相同的項目
    main_ui_path = Path('main_ui.py')
    main_content = main_ui_path.read_text(encoding='utf-8')
    main_item_count = main_content.count('CheckItem(')
    print(f"  ✓ 整合後 main_ui.py: {main_item_count} 項目")
    
    return main_item_count >= item_count

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
