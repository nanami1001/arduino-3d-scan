#!/usr/bin/env python3
"""
從 8 張水平拍攝影像重建 3D 模型
使用視覺船體 (Visual Hull) 方法 + 體素雕刻
"""

import cv2
import numpy as np
import os
from pathlib import Path
import json
from scipy.spatial import ConvexHull
import matplotlib.pyplot as plt
from mpl_toolkits.mplot3d import Axes3D

def load_images(scan_dir="scan_images"):
    """載入掃描影像"""
    images = []
    for i in range(1, 9):
        img_path = Path(scan_dir) / f"{i:02d}.png"
        if img_path.exists():
            img = cv2.imread(str(img_path))
            if img is not None:
                images.append(img)
                print(f"✓ 載入: {img_path.name}")
            else:
                print(f"✗ 無法載入: {img_path.name}")
        else:
            print(f"✗ 找不到: {img_path.name}")
    
    print(f"\n已載入 {len(images)} 張影像")
    if images:
        h, w = images[0].shape[:2]
        print(f"解析度: {w}×{h}")
    
    return images

def extract_silhouette(img, threshold=127):
    """
    從影像提取物體輪廓
    假設背景是白色/亮色，物體是暗色
    """
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    
    # 二值化 - 物體為白色，背景為黑色
    _, binary = cv2.threshold(gray, threshold, 255, cv2.THRESH_BINARY_INV)
    
    # 形態學操作 - 降噪
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
    binary = cv2.morphologyEx(binary, cv2.MORPH_CLOSE, kernel, iterations=2)
    binary = cv2.morphologyEx(binary, cv2.MORPH_OPEN, kernel, iterations=1)
    
    return binary

def create_voxel_grid(width=64, height=48, depth=64):
    """建立體素網格"""
    voxels = np.ones((depth, height, width), dtype=np.uint8)
    return voxels

def camera_matrix(img_width, img_height, focal_length=None):
    """
    建立相機內部參數矩陣
    假設標準針孔相機模型
    """
    if focal_length is None:
        focal_length = img_width  # 簡單估計
    
    cx, cy = img_width / 2, img_height / 2
    K = np.array([
        [focal_length, 0, cx],
        [0, focal_length, cy],
        [0, 0, 1]
    ], dtype=np.float32)
    
    return K

def project_voxel_to_image(voxel_pos, camera_matrix, rotation, translation):
    """
    將 3D 體素投影到 2D 影像平面
    使用相機外部參數
    """
    # 世界座標轉相機座標
    R = rotation
    t = translation
    
    cam_pos = R @ voxel_pos + t
    
    # 透視投影
    if cam_pos[2] > 0:
        img_pos = camera_matrix @ (cam_pos / cam_pos[2])
        return int(img_pos[0]), int(img_pos[1])
    
    return None

def carve_voxels_simple(images, voxel_res=32, num_angles=8):
    """
    簡化的體素雕刻
    如果體素在任何視角的投影上不在輪廓內，則移除
    """
    h, w = images[0].shape[:2]
    silhouettes = [extract_silhouette(img) for img in images]
    
    # 建立體素網格（立方體空間）
    # 假設物體在 [-1, 1] × [-0.5, 0.5] × [-1, 1]
    voxel_grid = create_voxel_grid(voxel_res, voxel_res // 2, voxel_res)
    
    # 相機參數
    K = camera_matrix(w, h, focal_length=w * 0.8)
    
    # 相機位置 (8 個視角，圍繞 Y 軸)
    angles = np.linspace(0, 2 * np.pi, num_angles, endpoint=False)
    radius = 2.0  # 相機距離
    
    print("\n🔄 體素雕刻中...")
    
    # 對每個體素檢查
    carving_count = 0
    for z in range(voxel_grid.shape[0]):
        if z % 8 == 0:
            print(f"  進度: {z}/{voxel_grid.shape[0]}", end='\r')
        
        for y in range(voxel_grid.shape[1]):
            for x in range(voxel_grid.shape[2]):
                # 體素 3D 座標 (正規化)
                voxel_3d = np.array([
                    (x - voxel_res / 2) / (voxel_res / 2),
                    (y - voxel_res / 4) / (voxel_res / 4),
                    (z - voxel_res / 2) / (voxel_res / 2),
                    1.0
                ])[:3]
                
                # 檢查此體素在每個相機視角是否可見
                visible_in_all = True
                for angle_idx, angle in enumerate(angles):
                    # 相機位置（圍繞 Y 軸旋轉）
                    cam_x = radius * np.cos(angle)
                    cam_z = radius * np.sin(angle)
                    cam_y = 0.0
                    
                    # 從相機指向物體中心的看向向量
                    look_dir = np.array([0, 0, 0]) - np.array([cam_x, cam_y, cam_z])
                    look_dir = look_dir / np.linalg.norm(look_dir)
                    
                    # 右向量和上向量
                    right = np.array([1, 0, 0])  # 簡化
                    up = np.cross(look_dir, right)
                    up = up / np.linalg.norm(up)
                    right = np.cross(up, look_dir)
                    
                    # 建立旋轉矩陣 (簡化)
                    R = np.eye(3)
                    
                    # 平移向量
                    t = np.array([cam_x, cam_y, cam_z])
                    
                    # 投影到影像
                    proj = project_voxel_to_image(voxel_3d, K, R, t)
                    
                    if proj is None:
                        visible_in_all = False
                        break
                    
                    px, py = proj
                    
                    # 檢查投影點是否在影像範圍內
                    if not (0 <= px < w and 0 <= py < h):
                        visible_in_all = False
                        break
                    
                    # 檢查投影點是否在輪廓內
                    if silhouettes[angle_idx][py, px] == 0:  # 0 = 背景
                        visible_in_all = False
                        break
                
                if not visible_in_all:
                    voxel_grid[z, y, x] = 0
                    carving_count += 1
    
    print(f"\n✓ 雕刻完成: 移除 {carving_count} 個體素")
    
    return voxel_grid, silhouettes

def extract_point_cloud(voxel_grid, voxel_size=0.02):
    """從體素網格提取點雲"""
    points = []
    
    for z in range(voxel_grid.shape[0]):
        for y in range(voxel_grid.shape[1]):
            for x in range(voxel_grid.shape[2]):
                if voxel_grid[z, y, x] > 0:
                    # 轉換為世界座標
                    world_x = (x - voxel_grid.shape[2] / 2) * voxel_size
                    world_y = (y - voxel_grid.shape[1] / 2) * voxel_size
                    world_z = (z - voxel_grid.shape[0] / 2) * voxel_size
                    points.append([world_x, world_y, world_z])
    
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
    
    print(f"✓ 已保存: {filename}")

def visualize_3d(points, silhouettes=None):
    """可視化 3D 點雲"""
    fig = plt.figure(figsize=(14, 5))
    
    # 3D 點雲
    ax1 = fig.add_subplot(121, projection='3d')
    if len(points) > 0:
        ax1.scatter(points[:, 0], points[:, 1], points[:, 2], 
                   c='blue', marker='.', s=1, alpha=0.6)
        
        # 嘗試計算 ConvexHull
        try:
            if len(points) >= 4:
                hull = ConvexHull(points)
                hull_points = points[hull.vertices]
                ax1.plot_trisurf(hull_points[:, 0], hull_points[:, 1], hull_points[:, 2],
                               triangles=hull.simplices, alpha=0.1, edgecolor='red', linewidth=0.5)
                print(f"✓ ConvexHull: {len(hull.simplices)} 三角形, 體積={hull.volume:.6f}")
        except Exception as e:
            print(f"⚠ ConvexHull 計算失敗: {e}")
    
    ax1.set_xlabel('X')
    ax1.set_ylabel('Y')
    ax1.set_zlabel('Z')
    ax1.set_title('3D 點雲重建')
    ax1.view_init(elev=20, azim=45)
    
    # 輪廓顯示
    if silhouettes:
        ax2 = fig.add_subplot(122)
        # 顯示第一張影像的輪廓
        ax2.imshow(silhouettes[0], cmap='gray')
        ax2.set_title(f'輪廓提取 (影像 1/8)')
        ax2.axis('off')
    
    plt.tight_layout()
    plt.show()

def main():
    print("=" * 60)
    print("🔬 8 張影像 3D 重建系統")
    print("=" * 60)
    
    # 載入影像
    images = load_images("scan_images")
    if not images:
        print("❌ 無法載入影像")
        return
    
    # 體素雕刻
    voxel_grid, silhouettes = carve_voxels_simple(
        images, 
        voxel_res=32,  # 32×16×32 體素
        num_angles=8
    )
    
    # 提取點雲
    print("\n📍 提取點雲中...")
    points = extract_point_cloud(voxel_grid, voxel_size=0.02)
    print(f"✓ 提取點數: {len(points)}")
    
    if len(points) > 0:
        # 保存結果
        output_path = "scan_images/result_8images.ply"
        save_ply(points, output_path)
        
        # 可視化
        print("\n📊 顯示 3D 視窗...")
        visualize_3d(points, silhouettes)
    else:
        print("❌ 無法提取點雲 (所有體素被雕刻)")

if __name__ == "__main__":
    main()
