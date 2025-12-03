#!/usr/bin/env python3
"""
視覺殼層 (Visual Hull) 3D 重建
直接從 8 張 2D 影像輪廓推算 3D 形狀
"""

import cv2
import numpy as np
from pathlib import Path
from scipy.spatial import ConvexHull
import matplotlib.pyplot as plt
from mpl_toolkits.mplot3d import Axes3D
from tqdm import tqdm

def load_images(scan_dir="scan_images", num_images=8):
    """載入掃描影像"""
    images = []
    for i in range(1, num_images + 1):
        img_path = Path(scan_dir) / f"{i:02d}.png"
        if img_path.exists():
            img = cv2.imread(str(img_path))
            if img is not None:
                images.append(img)
                print(f"✓ 載入: {img_path.name} ({img.shape[1]}×{img.shape[0]})")
    
    print(f"\n已載入 {len(images)} 張影像\n")
    return images

def extract_silhouette(img, threshold=120, use_hsv=True):
    """
    提取物體輪廓
    嘗試多種方法自動偵測前景
    """
    # 方法1: 基於 HSV 顏色空間（較穩健）
    if use_hsv:
        hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
        
        # 尋找非白色（物體通常比背景暗）
        # 白色: S < 50, V > 200
        lower_white = np.array([0, 0, 200])
        upper_white = np.array([180, 50, 255])
        white_mask = cv2.inRange(hsv, lower_white, upper_white)
        
        # 反轉 = 物體
        binary = 255 - white_mask
    else:
        # 方法2: 灰度閾值
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        _, binary = cv2.threshold(gray, threshold, 255, cv2.THRESH_BINARY_INV)
    
    # 形態學操作
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
    binary = cv2.morphologyEx(binary, cv2.MORPH_CLOSE, kernel, iterations=3)
    binary = cv2.morphologyEx(binary, cv2.MORPH_OPEN, kernel, iterations=1)
    
    return binary

def get_silhouette_mask(silhouette, img_w, img_h):
    """從二值圖像獲取輪廓像素集合"""
    y_coords, x_coords = np.where(silhouette > 0)
    if len(x_coords) == 0:
        return set()
    return set(zip(x_coords, y_coords))

def project_3d_to_2d(point_3d, angle_idx, num_cameras=8, radius=2.0, focal_length=400):
    """
    將 3D 點投影到 2D 影像
    簡化假設: 相機圍繞物體圓周排列
    """
    angle = 2 * np.pi * angle_idx / num_cameras
    
    # 相機位置 (圍繞 Y 軸)
    cam_x = radius * np.cos(angle)
    cam_z = radius * np.sin(angle)
    cam_y = 0
    
    # 從點到相機的向量
    p = point_3d - np.array([cam_x, cam_y, cam_z])
    
    # 旋轉使相機看向原點 (簡化: 直接投影)
    # z 深度
    if p[2] < 0.1:
        return None
    
    # 透視投影
    img_x = focal_length * p[0] / p[2] + 223  # 中心 446/2
    img_y = focal_length * p[1] / p[2] + 195  # 中心 391/2
    
    return int(img_x), int(img_y)

def reconstruct_visual_hull(images, voxel_res=48, num_cameras=8):
    """
    視覺殼層重建
    體素必須在所有相機視角的輪廓內才能保留
    """
    if not images:
        return np.array([])
    
    h, w = images[0].shape[:2]
    print(f"📐 影像解析度: {w}×{h}")
    
    # 提取所有輪廓
    print(f"\n🎯 提取 {len(images)} 個輪廓中...")
    silhouettes = []
    masks = []
    
    for i, img in enumerate(images):
        sil = extract_silhouette(img)
        silhouettes.append(sil)
        mask = get_silhouette_mask(sil, w, h)
        masks.append(mask)
        print(f"  影像 {i+1}: {len(mask)} 像素")
    
    # 建立體素網格
    print(f"\n🔲 建立體素網格 {voxel_res}³...")
    
    # 3D 空間: [-1.5, 1.5] × [-0.5, 1.0] × [-1.5, 1.5]
    x_range = np.linspace(-1.5, 1.5, voxel_res)
    y_range = np.linspace(-0.5, 1.0, voxel_res // 2)
    z_range = np.linspace(-1.5, 1.5, voxel_res)
    
    points = []
    
    print(f"\n🔄 視覺殼層雕刻中...")
    total_voxels = len(x_range) * len(y_range) * len(z_range)
    processed = 0
    
    for ix, x in enumerate(x_range):
        for iy, y in enumerate(y_range):
            for iz, z in enumerate(z_range):
                processed += 1
                if processed % 10000 == 0:
                    print(f"  進度: {processed}/{total_voxels} ({100*processed/total_voxels:.1f}%)", end='\r')
                
                point_3d = np.array([x, y, z])
                
                # 檢查此點在所有相機視角是否可見
                visible_in_all = True
                
                for cam_idx in range(num_cameras):
                    proj = project_3d_to_2d(point_3d, cam_idx, num_cameras)
                    
                    if proj is None:
                        visible_in_all = False
                        break
                    
                    px, py = proj
                    
                    # 檢查投影是否在影像範圍內
                    if not (0 <= px < w and 0 <= py < h):
                        visible_in_all = False
                        break
                    
                    # 檢查投影是否在輪廓內
                    if (px, py) not in masks[cam_idx]:
                        visible_in_all = False
                        break
                
                if visible_in_all:
                    points.append(point_3d)
    
    print(f"\n✓ 雕刻完成: 保留 {len(points)} 個體素")
    
    return np.array(points, dtype=np.float32)

def save_ply(points, filename="result.ply"):
    """保存為 PLY 格式"""
    ply_header = f"""ply
format ascii 1.0
element vertex {len(points)}
property float x
property float y
property float z
end_header
"""
    
    with open(filename, 'w') as f:
        f.write(ply_header)
        for p in points:
            f.write(f"{p[0]:.6f} {p[1]:.6f} {p[2]:.6f}\n")
    
    print(f"✓ 已保存: {filename} ({len(points)} 點)")

def visualize_3d(points, silhouettes):
    """可視化 3D 結果"""
    fig = plt.figure(figsize=(16, 6))
    
    # 3D 點雲
    ax1 = fig.add_subplot(131, projection='3d')
    if len(points) > 0:
        ax1.scatter(points[:, 0], points[:, 1], points[:, 2], 
                   c='blue', marker='.', s=1, alpha=0.7)
        
        # ConvexHull
        try:
            if len(points) >= 4:
                hull = ConvexHull(points)
                for simplex in hull.simplices:
                    triangle = points[simplex]
                    ax1.plot_trisurf(triangle[:, 0], triangle[:, 1], triangle[:, 2],
                                   alpha=0.1, edgecolor='red', linewidth=0.3)
                print(f"✓ ConvexHull: {len(hull.simplices)} 三角形, 體積={hull.volume:.6f}")
        except Exception as e:
            print(f"⚠ ConvexHull 計算失敗: {e}")
    
    ax1.set_xlabel('X')
    ax1.set_ylabel('Y')
    ax1.set_zlabel('Z')
    ax1.set_title(f'視覺殼層 ({len(points)} 點)')
    ax1.view_init(elev=20, azim=45)
    
    # 輪廓1 & 2
    ax2 = fig.add_subplot(132)
    ax2.imshow(silhouettes[0], cmap='gray')
    ax2.set_title('輪廓 1 (0°)')
    ax2.axis('off')
    
    ax3 = fig.add_subplot(133)
    if len(silhouettes) > 1:
        ax3.imshow(silhouettes[len(silhouettes)//2], cmap='gray')
        ax3.set_title(f'輪廓 {len(silhouettes)//2 + 1} (180°)')
    ax3.axis('off')
    
    plt.tight_layout()
    plt.show()

def main():
    print("=" * 70)
    print("🎬 視覺殼層 (Visual Hull) 3D 重建")
    print("=" * 70)
    
    # 載入影像
    images = load_images("scan_images", num_images=8)
    if not images:
        print("❌ 無法載入影像")
        return
    
    # 重建
    points = reconstruct_visual_hull(images, voxel_res=48, num_cameras=8)
    
    # 顯示統計
    if len(points) > 0:
        print(f"\n📊 統計:")
        print(f"  總點數: {len(points)}")
        print(f"  X 範圍: [{points[:, 0].min():.3f}, {points[:, 0].max():.3f}]")
        print(f"  Y 範圍: [{points[:, 1].min():.3f}, {points[:, 1].max():.3f}]")
        print(f"  Z 範圍: [{points[:, 2].min():.3f}, {points[:, 2].max():.3f}]")
        
        # 保存
        output_path = "scan_images/result_visual_hull.ply"
        save_ply(points, output_path)
        
        # 可視化
        print("\n📊 顯示 3D 視窗...")
        silhouettes = [extract_silhouette(img) for img in images]
        visualize_3d(points, silhouettes)
    else:
        print("❌ 無法提取點雲")

if __name__ == "__main__":
    main()
