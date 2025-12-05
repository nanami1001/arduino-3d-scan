#!/usr/bin/env python3
"""
強化版 Visual Hull 3D 重建器
✔ 100% 防止 IndexError
✔ 投影誤差降低（使用 round + double boundary check）
✔ silhouette 穩定、乾淨
✔ 可直接被 build_ply.py 呼叫
"""

import cv2
import numpy as np
from pathlib import Path
import argparse
import matplotlib.pyplot as plt


# =====================================================
# 影像讀取
# =====================================================
def load_images(folder="scan_images", num_images=8):
    images = []
    for i in range(1, num_images + 1):
        path = Path(folder) / f"{i:02d}.png"
        if path.exists():
            img = cv2.imread(str(path))
            images.append(img)
            print(f"✓ 已載入: {path.name}")
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

    # 背景太亮 → 自動翻轉
    if np.mean(th == 255) > 0.5:
        th = 255 - th

    # 清雜訊
    k = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (7, 7))
    th = cv2.morphologyEx(th, cv2.MORPH_OPEN, k, iterations=1)
    th = cv2.morphologyEx(th, cv2.MORPH_CLOSE, k, iterations=2)

    return (th > 0).astype(np.uint8)


# =====================================================
# 相機 Look-at Matrix
# =====================================================
def camera_lookat_matrix(cam_pos, target=np.array([0, 0, 0])):
    forward = target - cam_pos
    forward = forward / np.linalg.norm(forward)

    up = np.array([0, 1, 0])
    right = np.cross(forward, up)
    right = right / np.linalg.norm(right)

    up = np.cross(right, forward)
    return np.vstack([right, up, forward]).T


# =====================================================
# 投影 → 加強防越界
# =====================================================
def project_point(P, cam_pos, R, K, W, H):

    Pw = P - cam_pos

    Pc = np.array([
        np.dot(R[:, 0], Pw),
        np.dot(R[:, 1], Pw),
        np.dot(R[:, 2], Pw)
    ])

    if Pc[2] <= 1e-6:
        return None

    proj = K @ (Pc / Pc[2])

    # 先 round 再檢查
    u = int(round(proj[0]))
    v = int(round(proj[1]))

    # 第一層防越界（投影後檢查）
    if not (0 <= u < W and 0 <= v < H):
        return None

    return u, v


# =====================================================
# Visual Hull Carving（完全防越界版）
# =====================================================
def voxel_carve(images, grid=40):

    H, W = images[0].shape[:2]
    silhouettes = [extract_silhouette(img) for img in images]
    N = len(images)

    coords = np.linspace(-1, 1, grid)
    voxel = np.ones((grid, grid, grid), dtype=np.uint8)

    # Camera Intrinsic
    fx = fy = W * 1.2
    cx, cy = W / 2, H / 2
    K = np.array([[fx, 0, cx],
                  [0, fy, cy],
                  [0, 0, 1]])

    # Camera 旋轉
    angles = np.linspace(0, 2 * np.pi, N, endpoint=False)
    radius = 2.5
    cam_pos_list = [np.array([radius * np.cos(a), 0, radius * np.sin(a)]) for a in angles]
    R_list = [camera_lookat_matrix(cp) for cp in cam_pos_list]

    print("\n🔄 體素雕刻中 ...")

    removed = 0
    total = grid * grid * grid

    for ix, x in enumerate(coords):
        print(f"slice {ix}/{grid}", end="\r")
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

                    # ⭐ 完全防越界（第二層保護）
                    if v < 0 or v >= silhouettes[i].shape[0] or u < 0 or u >= silhouettes[i].shape[1]:
                        keep = False
                        break

                    # 真正 silhouette 判斷
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
# export PLY
# =====================================================
def save_ply(points, out_path):
    out = Path(out_path)
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
    parser.add_argument("--no-display", action="store_true")
    parser.add_argument("--output", default="scan_images/result_visual_hull.ply")
    args = parser.parse_args()

    print("=============================================")
    print("🔧 Visual Hull 重建開始")
    print("=============================================\n")

    images = load_images(num_images=args.num_images)
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
