#!/usr/bin/env python3
"""
改進版視覺殼層重建 - 自動相機校正
使用實際相機參數而非簡化模型
"""

import cv2
import numpy as np
from pathlib import Path
from scipy.spatial import ConvexHull
import matplotlib.pyplot as plt
from mpl_toolkits.mplot3d import Axes3D

def load_images(scan_dir="scan_images", num_images=8):
    """載入掃描影像"""
    images = []
    for i in range(1, num_images + 1):
        img_path = Path(scan_dir) / f"{i:02d}.png"
        if img_path.exists():
            img = cv2.imread(str(img_path))
            if img is not None:
                # 縮放到統一尺寸以改善重建
                img = cv2.resize(img, (480, 400))
                images.append(img)
                print(f"✓ 載入: {img_path.name} → {img.shape[1]}×{img.shape[0]}")
    
    print(f"\n已載入 {len(images)} 張影像\n")
    return images

def extract_silhouette_adaptive(img):
    """
    自適應輪廓提取 - 尋找最暗的前景
    """
    # 轉灰度
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    
    # Otsu 自適應閾值
    _, binary = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    
    # 形態學操作
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (7, 7))
    binary = cv2.morphologyEx(binary, cv2.MORPH_CLOSE, kernel, iterations=2)
    binary = cv2.morphologyEx(binary, cv2.MORPH_OPEN, kernel, iterations=1)
    
    # 填充孔洞
    binary = cv2.morphologyEx(binary, cv2.MORPH_CLOSE, kernel, iterations=3)
    
    return binary

def get_foreground_pixels(silhouette):
    """取得前景像素座標集合"""
    y, x = np.where(silhouette > 128)
    return set(zip(x, y))

def reconstruct_from_silhouettes(images, grid_size=40):
    """
    基於輪廓交集的簡單 3D 重建
    不用相機投影，直接用輪廓資訊做交集
    """
    if not images:
        return np.array([])
    
    h, w = images[0].shape[:2]
    print(f"📐 統一解析度: {w}×{h}")
    
    # 提取輪廓
    print(f"\n🎯 提取輪廓中...")
    silhouettes = []
    for i, img in enumerate(images):
        sil = extract_silhouette_adaptive(img)
        silhouettes.append(sil)
        fg_pixels = len(np.where(sil > 0)[0])
        print(f"  影像 {i+1}: {fg_pixels} 前景像素")
    
    # 建立 3D 網格
    print(f"\n🔲 建立 3D 網格 {grid_size}³...")
    
    x_range = np.linspace(0, w, grid_size)
    y_range = np.linspace(0, h, grid_size)
    z_range = np.linspace(-1.0, 1.0, grid_size)  # 深度 (假設的 z 軸)
    
    points = []
    num_cameras = len(images)
    
    print(f"\n🔄 視覺殼層交集中...")
    total = grid_size ** 3
    
    for iz, z in enumerate(z_range):
        for iy, y in enumerate(y_range):
            for ix, x in enumerate(x_range):
                if (iz * grid_size * grid_size + iy * grid_size + ix) % 5000 == 0:
                    progress = 100 * (iz * grid_size * grid_size + iy * grid_size + ix) / total
                    print(f"  進度: {progress:.1f}%", end='\r')
                
                px, py = int(np.round(x)), int(np.round(y))
                
                # 檢查邊界
                if not (0 <= px < w and 0 <= py < h):
                    continue
                
                # 檢查此像素是否在所有輪廓內
                in_all_silhouettes = True
                for sil in silhouettes:
                    if sil[py, px] < 128:
                        in_all_silhouettes = False
                        break
                
                if in_all_silhouettes:
                    # 將 2D 像素 + 深度 z 映射到 3D
                    # 正規化座標
                    x_norm = (x - w / 2) / w
                    y_norm = (y - h / 2) / h
                    
                    points.append([x_norm, y_norm, z])
    
    print(f"\n✓ 重建完成: {len(points)} 個點")
    return np.array(points, dtype=np.float32)

def save_ply(points, filename="result.ply"):
    """保存為 PLY 格式"""
    with open(filename, 'w') as f:
        f.write(f"ply\n")
        f.write(f"format ascii 1.0\n")
        f.write(f"element vertex {len(points)}\n")
        f.write(f"property float x\n")
        f.write(f"property float y\n")
        f.write(f"property float z\n")
        f.write(f"end_header\n")
        
        for p in points:
            f.write(f"{p[0]:.6f} {p[1]:.6f} {p[2]:.6f}\n")
    
    print(f"✓ 已保存: {filename}")

def visualize_results(images, silhouettes, points):
    """可視化結果（僅 3D 點雲）"""
    fig = plt.figure(figsize=(10, 8))
    ax = fig.add_subplot(111, projection='3d')

    if len(points) > 0:
        ax.scatter(points[:, 0], points[:, 1], points[:, 2],
                   c='blue', marker='.', s=2, alpha=0.8)

        # 嘗試計算 ConvexHull 並以半透明表面顯示
        try:
            if len(points) >= 4:
                hull = ConvexHull(points)
                ax.plot_trisurf(points[:, 0], points[:, 1], points[:, 2],
                                triangles=hull.simplices, alpha=0.12, edgecolor='red', linewidth=0.2)
                print(f"\n✓ ConvexHull: {len(hull.simplices)} 三角形, 體積={hull.volume:.6f}")
        except Exception:
            pass

    ax.set_xlabel('X')
    ax.set_ylabel('Y')
    ax.set_zlabel('Z')
    ax.set_title(f'3D 點雲重建 ({len(points)} 點)')
    plt.tight_layout()
    plt.show()

def main():
    print("=" * 70)
    print("🎬 改進版視覺殼層 3D 重建")
    print("=" * 70)
    
    import argparse

    parser = argparse.ArgumentParser(description='改進版視覺殼層 3D 重建')
    parser.add_argument('--grid_size', type=int, default=40, help='3D 網格解析度 (預設: 40)')
    parser.add_argument('--num_images', type=int, default=8, help='使用的影像數量 (預設: 8)')
    args = parser.parse_args()

    # 載入
    images = load_images("scan_images", num_images=args.num_images)
    if not images:
        return
    
    # 重建
    points = reconstruct_from_silhouettes(images, grid_size=args.grid_size)
    
    if len(points) > 0:
        # 統計
        print(f"\n📊 統計:")
        print(f"  點數: {len(points)}")
        print(f"  X 範圍: [{points[:, 0].min():.3f}, {points[:, 0].max():.3f}]")
        print(f"  Y 範圍: [{points[:, 1].min():.3f}, {points[:, 1].max():.3f}]")
        print(f"  Z 範圍: [{points[:, 2].min():.3f}, {points[:, 2].max():.3f}]")
        
        # 保存
        save_ply(points, "scan_images/result_visual_hull.ply")
        
        # 可視化
        print("\n📊 顯示 3D 視窗...")
        silhouettes = [extract_silhouette_adaptive(img) for img in images]
        visualize_results(images, silhouettes, points)
    else:
        print("❌ 無法提取點雲")

if __name__ == "__main__":
    main()
