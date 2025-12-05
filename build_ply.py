#!/usr/bin/env python3
"""
PLY 自動建立模組
=================

這個模組負責：
1. 檢查指定的 PLY 檔案是否存在
2. 若不存在，則自動呼叫 reconstruct_simple.py 進行 3D 重建
3. 若 force_rebuild=True，會無視現有 PLY，強制重新建立

用途：
    from build_ply import ensure_ply_exists
    ply_path = ensure_ply_exists('scan_images/result_visual_hull.ply')

本檔案也可以直接從命令列執行：

    python build_ply.py --ply scan_images/result_visual_hull.ply
"""

import subprocess   # 用來執行外部程式（呼叫 reconstruct_simple.py）
import sys          # 用來取得目前使用的 Python 可執行檔路徑
from pathlib import Path  # 更方便管理路徑物件（比字串安全）


def ensure_ply_exists(ply_path, force_rebuild=False, grid_size=40, num_images=8, no_display=True):
    """
    確保指定的 PLY 檔案存在。

    ★ 功能說明 ★
    ----------------
    1. 檢查 ply_path 是否存在
    2. 若不存在 → 自動呼叫 reconstruct_simple.py 建立
    3. 若 force_rebuild=True → 不管是否存在都重建
    4. 重建後再檢查結果，確認是否成功產生 PLY

    Args:
        ply_path (str or Path): 要檢查的 PLY 路徑
        force_rebuild (bool): 若 True → 強制重建，不看舊檔
        grid_size (int): Visual Hull 重建使用的體素解析度
        num_images (int): 重建時使用的影像數量
        no_display (bool): 是否隱藏 reconstruct_simple.py 的 matplotlib 視窗

    Returns:
        Path | None:
            成功：回傳 PLY 的 Path 物件
            失敗：回傳 None
    """

    # 確保路徑轉成 Path 物件
    ply_path = Path(ply_path)

    # --------------- #
    # (1) 判斷是否需要重建
    # --------------- #
    if ply_path.exists() and not force_rebuild:
        print(f"✓ PLY 檔已存在: {ply_path}")
        return ply_path

    # --------------- #
    # (2) 進入重建流程
    # --------------- #
    print(f"{'重建' if not ply_path.exists() else '強制重建'} PLY: {ply_path}")

    try:
        # 建構要執行的命令列指令
        # sys.executable → 取得「目前 Python 執行檔」的路徑，例如：
        #   C:\Python313\python.exe
        #
        # reconstruct_simple.py → 進行 Visual Hull 重建
        # --grid_size X → 指定體素解析度
        # --num_images X → 指定影像數量
        cmd = [
            sys.executable,
            'reconstruct_simple.py',
            '--grid_size', str(grid_size),
            '--num_images', str(num_images)
        ]

        # 如果不要顯示視窗，就加入 --no-display 參數
        if no_display:
            cmd.append('--no-display')

        print(f"執行命令: {' '.join(cmd)}")

        # 執行外部程式（阻塞直到程式結束）
        # check=True → 若 reconstruct_simple.py 回傳非 0，會直接丟例外
        subprocess.run(cmd, check=True)

        # --------------- #
        # (3) 重建完成後再次檢查 PLY 是否真的生成
        # --------------- #
        if ply_path.exists():
            print(f"✓ PLY 重建成功: {ply_path}")
            return ply_path
        else:
            print(f"✗ 重建完成但找不到 PLY 檔: {ply_path}")
            return None

    except subprocess.CalledProcessError as e:
        # reconstruct_simple.py 執行失敗（程式碼錯誤、崩潰、返回異常值）
        print(f"✗ 重建腳本執行失敗: {e}")
        return None

    except Exception as e:
        # 其他非 subprocess 類型的例外（例如檔案權限、I/O 問題）
        print(f"✗ 執行出錯: {e}")
        return None


# ==========================================================
#       讓本模組也可以從命令列獨立執行
# ==========================================================
if __name__ == '__main__':
    import argparse

    # 建立 CLI （命令列介面）
    parser = argparse.ArgumentParser(description='確保 PLY 檔案存在（若需要則自動重建）')
    parser.add_argument('--ply', default='scan_images/result_visual_hull.ply', help='PLY 檔案路徑')
    parser.add_argument('--rebuild', action='store_true', help='強制重建')
    parser.add_argument('--grid_size', type=int, default=40, help='網格解析度')
    parser.add_argument('--num_images', type=int, default=8, help='影像數量')

    args = parser.parse_args()

    # 呼叫核心函式
    result = ensure_ply_exists(
        args.ply,
        force_rebuild=args.rebuild,
        grid_size=args.grid_size,
        num_images=args.num_images
    )

    # 結果輸出
    if result:
        print(f"\n✓ 完成。PLY 路徑: {result}")
        sys.exit(0)
    else:
        print(f"\n✗ 失敗。")
        sys.exit(1)
