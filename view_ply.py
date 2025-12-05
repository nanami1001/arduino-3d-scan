#!/usr/bin/env python3
"""
簡單 PLY 檢視器（純程式讀取與繪製）
用法:
    python view_ply.py [PLY_path] [--rebuild]
例如:
    python view_ply.py scan_images/result_visual_hull.ply
    python view_ply.py --rebuild
如果不提供檔案，預設會載入 scan_images/result_visual_hull.ply
若檔案不存在會自動呼叫 build_ply.py 進行重建。
"""
import sys
import numpy as np
from scipy.spatial import ConvexHull
import matplotlib.pyplot as plt
from mpl_toolkits.mplot3d import Axes3D
from pathlib import Path

from build_ply import ensure_ply_exists


def load_ply_ascii(path):
    pts = []
    with open(path, 'r') as f:
        header_ended = False
        for line in f:
            line = line.strip()
            if not header_ended:
                if line == 'end_header':
                    header_ended = True
                continue
            if line:
                parts = line.split()
                if len(parts) >= 3:
                    try:
                        x, y, z = map(float, parts[:3])
                        pts.append([x, y, z])
                    except:
                        continue
    return np.array(pts, dtype=np.float32)


def visualize(points):
    fig = plt.figure(figsize=(8, 6))
    ax = fig.add_subplot(111, projection='3d')
    if len(points) == 0:
        print('No points to display')
        return

    # 嘗試使用 ConvexHull 畫出填滿的簡單幾何形狀
    try:
        if len(points) >= 4:
            hull = ConvexHull(points)
            # plot_trisurf with hull.simplices 可以得到填色面
            ax.plot_trisurf(points[:,0], points[:,1], points[:,2],
                            triangles=hull.simplices, linewidth=0.2,
                            edgecolor='k', color='cyan', alpha=0.85)
            # 再疊上邊框線以強調輪廓
            for tri in hull.simplices:
                tri_pts = points[tri]
                xs, ys, zs = tri_pts[:,0], tri_pts[:,1], tri_pts[:,2]
                # close loop
                ax.plot(np.append(xs, xs[0]), np.append(ys, ys[0]), np.append(zs, zs[0]),
                        color='black', linewidth=0.25, alpha=0.8)
            print(f'✓ ConvexHull: {len(hull.simplices)} triangles, volume={hull.volume:.6f}')
        else:
            ax.scatter(points[:,0], points[:,1], points[:,2], c='blue', s=2)
    except Exception as e:
        print('ConvexHull/mesh render failed:', e)
        ax.scatter(points[:,0], points[:,1], points[:,2], c='blue', s=2)

    ax.set_xlabel('X')
    ax.set_ylabel('Y')
    ax.set_zlabel('Z')
    ax.set_title(f'PLY Viewer ({len(points)} points)')

    # 使三軸呈現等比例
    def set_axes_equal(ax):
        x_limits = ax.get_xlim3d()
        y_limits = ax.get_ylim3d()
        z_limits = ax.get_zlim3d()

        x_range = abs(x_limits[1] - x_limits[0])
        x_middle = np.mean(x_limits)
        y_range = abs(y_limits[1] - y_limits[0])
        y_middle = np.mean(y_limits)
        z_range = abs(z_limits[1] - z_limits[0])
        z_middle = np.mean(z_limits)

        plot_radius = 0.5 * max([x_range, y_range, z_range])

        ax.set_xlim3d([x_middle - plot_radius, x_middle + plot_radius])
        ax.set_ylim3d([y_middle - plot_radius, y_middle + plot_radius])
        ax.set_zlim3d([z_middle - plot_radius, z_middle + plot_radius])

    set_axes_equal(ax)
    plt.tight_layout()
    plt.show()


def main():
    # 預設 PLY 路徑
    default_path = Path('scan_images') / 'result_visual_hull.ply'
    path = Path(sys.argv[1]) if len(sys.argv) > 1 else default_path

    # 支援強制重建旗標
    force_rebuild = '--rebuild' in sys.argv

    # 呼叫 build_ply 確保 PLY 存在
    ply_path = ensure_ply_exists(str(path), force_rebuild=force_rebuild)
    if not ply_path:
        print("無法取得 PLY 檔案，程式終止。")
        return

    try:
        pts = load_ply_ascii(str(ply_path))
        print(f'Loaded {len(pts)} points from {ply_path}')
        visualize(pts)
    except Exception as e:
        print('Error loading PLY:', e)

if __name__ == '__main__':
    main()
