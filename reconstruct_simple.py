#!/usr/bin/env python3
"""
reconstruct_simple.py 的 Open3D 強化版
-------------------------------------

功能：
✔ 完整 Visual Hull 3D 重建
✔ 完整防止 IndexError
✔ silhouette 自動清理 + 自動反轉亮背景
✔ 投影誤差修正（round + double boundary）
✔ 可由 build_ply.py 呼叫
✔ 使用 Open3D 顯示互動式 3D 點雲視窗（可旋轉、縮放、移動）
✔ 支援 --no-display（禁用顯示）
"""

import cv2
import numpy as np
from pathlib import Path
import argparse
import matplotlib.pyplot as plt

# 嘗試使用 tqdm 進度條
try:
    from tqdm import trange
    USE_TQDM = True
except:
    USE_TQDM = False


# =====================================================
# 影像讀取
# =====================================================
def load_images(folder="scan_images", num_images=8):
    images = []
    target_size = None
    for i in range(1, num_images + 1):
        path = Path(folder) / f"{i:02d}.png"
        if path.exists():
            img = cv2.imread(str(path))
            if img is not None:
                if target_size is None:
                    h, w = img.shape[:2]
                    target_size = (w, h)
                elif img.shape[1] != target_size[0] or img.shape[0] != target_size[1]:
                    # 所有影像需同尺寸，避免投影索引與 silhouette 寬高不一致
                    img = cv2.resize(img, target_size, interpolation=cv2.INTER_AREA)
                    print(f"⚠ 影像尺寸不一致，已調整為 {target_size[0]}x{target_size[1]}: {path.name}")
                print(f"✓ 已載入: {path.name}")
                images.append(img)
            else:
                print(f"✗ 無法讀取影像（cv2.imread 返回 None）：{path}")
        else:
            print(f"✗ 找不到影像: {path}")
    return images


# =====================================================
# 萃取 silhouette
# =====================================================
def extract_silhouette(img):
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

    blur = cv2.GaussianBlur(gray, (5, 5), 0)
    _, th = cv2.threshold(blur, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)

    # 背景太亮 → 自動反轉
    if np.mean(th == 255) > 0.5:
        th = 255 - th

    # 雜訊處理
    k = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (7, 7))
    th = cv2.morphologyEx(th, cv2.MORPH_OPEN, k, iterations=1)
    th = cv2.morphologyEx(th, cv2.MORPH_CLOSE, k, iterations=2)

    return (th > 0).astype(np.uint8)


# =====================================================
# 相機 Look-at Matrix
# =====================================================
def camera_lookat_matrix(cam_pos, target=np.array([0.0, 0.0, 0.0])):
    cam_pos = np.asarray(cam_pos, dtype=np.float64)
    target = np.asarray(target, dtype=np.float64)

    forward = target - cam_pos
    n = np.linalg.norm(forward)
    if n < 1e-8:
        forward = np.array([0.0, 0.0, 1.0])
    else:
        forward = forward / n

    up = np.array([0.0, 1.0, 0.0])
    if abs(np.dot(forward, up)) > 0.999:
        up = np.array([0.0, 0.0, 1.0])

    right = np.cross(forward, up)
    right /= np.linalg.norm(right)

    up = np.cross(right, forward)

    return np.column_stack((right, up, forward))


# =====================================================
# 投影（雙層邊界保護）
# =====================================================
def project_point(P, cam_pos, R, K, W, H):
    P = np.asarray(P, dtype=np.float64)
    Pw = P - cam_pos

    Pc = np.array([
        np.dot(R[:, 0], Pw),
        np.dot(R[:, 1], Pw),
        np.dot(R[:, 2], Pw)
    ], dtype=np.float64)

    if Pc[2] <= 1e-6:
        return None

    proj = K @ (Pc / Pc[2])

    u = int(round(float(proj[0])))
    v = int(round(float(proj[1])))

    if not (0 <= u < W and 0 <= v < H):
        return None

    return u, v


# =====================================================
# Visual Hull carving
# =====================================================
def voxel_carve(images, grid=40):
    H, W = images[0].shape[:2]
    silhouettes = [extract_silhouette(img) for img in images]
    N = len(images)

    coords = np.linspace(-1, 1, grid)
    voxel = np.ones((grid, grid, grid), dtype=np.uint8)

    fx = fy = W * 1.2
    cx, cy = W / 2, H / 2
    K = np.array([[fx, 0, cx],
                  [0, fy, cy],
                  [0, 0, 1]])

    angles = np.linspace(0, 2 * np.pi, N, endpoint=False)
    radius = 2.5

    cam_pos_list = [np.array([radius * np.cos(a), 0, radius * np.sin(a)]) for a in angles]
    R_list = [camera_lookat_matrix(cp) for cp in cam_pos_list]

    print("\n🔄 體素雕刻中 ...")

    removed = 0
    total = grid * grid * grid

    outer_range = trange(grid, desc="slice") if USE_TQDM else range(grid)

    for ix in outer_range:
        if not USE_TQDM:
            print(f"slice {ix+1}/{grid}", end="\r")

        x = coords[ix]

        for iy, y in enumerate(coords):
            for iz, z in enumerate(coords):

                if voxel[ix, iy, iz] == 0:
                    continue

                P = np.array([x, y, z])
                keep = True

                for i in range(N):
                    proj = project_point(P, cam_pos_list[i], R_list[i], K, W, H)

                    if proj is None:
                        keep = False
                        break

                    u, v = proj

                    h_i, w_i = silhouettes[i].shape[:2]

                    # 二次越界防護
                    if u < 0 or u >= w_i or v < 0 or v >= h_i:
                        keep = False
                        break

                    if silhouettes[i][v, u] == 0:
                        keep = False
                        break

                if not keep:
                    voxel[ix, iy, iz] = 0
                    removed += 1

    print(f"\n✓ 體素雕刻完成：刪除 {removed}/{total}")
    return voxel


# =====================================================
# voxel → point cloud
# =====================================================
def voxel_to_pointcloud(voxel, grid=40):
    coords = np.linspace(-1, 1, grid)
    points = []
    for ix, x in enumerate(coords):
        for iy, y in enumerate(coords):
            for iz, z in enumerate(coords):
                if voxel[ix, iy, iz] > 0:
                    points.append([x, y, z])
    return np.array(points, dtype=np.float32)


# =====================================================
# Open3D 點雲視覺化
# =====================================================
def visualize(points):
    try:
        import open3d as o3d
    except ImportError:
        print("⚠️ 未安裝 open3d，無法使用 3D 視窗。請執行： pip install open3d")
        return

    if len(points) == 0:
        print("⚠️ 無點雲可顯示")
        return

    pcd = o3d.geometry.PointCloud()
    pcd.points = o3d.utility.Vector3dVector(points)

    # 白色點雲
    colors = np.ones((points.shape[0], 3))
    pcd.colors = o3d.utility.Vector3dVector(colors)

    o3d.visualization.draw_geometries([pcd], window_name="Visual Hull 3D Viewer")


# =====================================================
# PLY 輸出
# =====================================================
def save_ply(points, out_path):
    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w") as f:
        f.write("ply\nformat ascii 1.0\n")
        f.write(f"element vertex {len(points)}\n")
        f.write("property float x\nproperty float y\nproperty float z\n")
        f.write("end_header\n")
        for p in points:
            f.write(f"{p[0]} {p[1]} {p[2]}\n")
    print(f"✓ 已輸出 PLY: {out}")


# =====================================================
# Main
# =====================================================
def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--grid_size", type=int, default=40)
    parser.add_argument("--num_images", type=int, default=8)
    parser.add_argument("--images_folder", default="scan_images")
    parser.add_argument("--output", default="scan_images/result_visual_hull.ply")
    parser.add_argument("--no-display", action="store_true")

    args = parser.parse_args()

    print("=============================================")
    print("🔧 Visual Hull 重建開始")
    print("=============================================\n")

    images = load_images(folder=args.images_folder, num_images=args.num_images)
    if not images:
        print("❌ 無法載入影像")
        return

    voxel = voxel_carve(images, grid=args.grid_size)
    points = voxel_to_pointcloud(voxel, grid=args.grid_size)

    save_ply(points, args.output)

    if not args.no_display:
        visualize(points)


if __name__ == "__main__":
    main()
