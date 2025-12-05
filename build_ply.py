#!/usr/bin/env python3
"""
PLY 自動建立模組
負責檢查 PLY 檔案是否存在，若不存在則自動呼叫 reconstruct_simple.py 進行重建。

用法 (in Python):
    from build_ply import ensure_ply_exists
    ply_path = ensure_ply_exists('scan_images/result_visual_hull.ply', force_rebuild=False)
    if ply_path:
        print(f'PLY 已就緒: {ply_path}')
"""
import subprocess
import sys
from pathlib import Path


def ensure_ply_exists(ply_path, force_rebuild=False, grid_size=40, num_images=8, no_display=True):
    """
    確保 PLY 檔案存在。若不存在或 force_rebuild=True，自動執行重建。
    
    Args:
        ply_path: PLY 檔案路徑 (str or Path)
        force_rebuild: 若 True，忽略現有檔案並強制重建
        grid_size: 重建時的 3D 網格解析度 (預設: 40)
        num_images: 使用的影像數量 (預設: 8)
        no_display: 若 True，重建時不顯示獨立視窗 (預設: True)
    
    Returns:
        成功時回傳 PLY 檔案路徑 (Path 物件)；失敗時回傳 None
    """
    ply_path = Path(ply_path)
    
    # 檢查檔案是否已存在且不需要強制重建
    if ply_path.exists() and not force_rebuild:
        print(f"✓ PLY 檔已存在: {ply_path}")
        return ply_path
    
    # 需要重建
    print(f"{'重建' if not ply_path.exists() else '強制重建'} PLY: {ply_path}")
    try:
        cmd = [
            sys.executable, 
            'reconstruct_simple.py',
            '--grid_size', str(grid_size),
            '--num_images', str(num_images)
        ]
        if no_display:
            cmd.append('--no-display')
        print(f"執行命令: {' '.join(cmd)}")
        result = subprocess.run(cmd, check=True)
        
        # 檢查重建後檔案是否存在
        if ply_path.exists():
            print(f"✓ PLY 重建成功: {ply_path}")
            return ply_path
        else:
            print(f"✗ 重建完成但找不到 PLY 檔: {ply_path}")
            return None
    except subprocess.CalledProcessError as e:
        print(f"✗ 重建腳本執行失敗: {e}")
        return None
    except Exception as e:
        print(f"✗ 執行出錯: {e}")
        return None


if __name__ == '__main__':
    # 命令列使用範例
    import argparse
    
    parser = argparse.ArgumentParser(description='確保 PLY 檔案存在（若需要則自動重建）')
    parser.add_argument('--ply', default='scan_images/result_visual_hull.ply', help='PLY 檔案路徑')
    parser.add_argument('--rebuild', action='store_true', help='強制重建')
    parser.add_argument('--grid_size', type=int, default=40, help='網格解析度')
    parser.add_argument('--num_images', type=int, default=8, help='影像數量')
    
    args = parser.parse_args()
    
    result = ensure_ply_exists(
        args.ply, 
        force_rebuild=args.rebuild,
        grid_size=args.grid_size,
        num_images=args.num_images
    )
    
    if result:
        print(f"\n✓ 完成。PLY 路徑: {result}")
        sys.exit(0)
    else:
        print(f"\n✗ 失敗。")
        sys.exit(1)
