# scan_and_reconstruct.py
# PC-side coordinator:
# - serial -> Arduino: "ROTATE_STEPS N"
# - GET http://ESP32_IP/capture -> save JPEG
# - after collecting images -> simple voxel carving reconstruction (naive)

import sys
missing = []
try:
    import serial
except ImportError:
    missing.append('pyserial')
try:
    import requests
except ImportError:
    missing.append('requests')
try:
    import cv2
except ImportError:
    missing.append('opencv-python')
try:
    import numpy as np
except ImportError:
    missing.append('numpy')
try:
    from tqdm import tqdm
except ImportError:
    missing.append('tqdm')
try:
    import matplotlib
    import matplotlib.pyplot as plt
    from mpl_toolkits.mplot3d import Axes3D
except ImportError:
    missing.append('matplotlib')
try:
    from scipy.spatial import ConvexHull
except ImportError:
    missing.append('scipy')

if missing:
    print("Missing Python packages:", ", ".join(missing))
    print("Install them with:")
    print("    python -m pip install " + " ".join(missing))
    print("Or install all requirements: python -m pip install -r requirements.txt")
    sys.exit(1)

import time
import os
import argparse
import math

# ---------- CONFIG ----------
ESP32_IP = "192.168.1.100"   # <<--- 改成你的 ESP32-CAM IP
SERIAL_PORT = "COM3"         # <<--- 改成你的 Arduino serial port
BAUDRATE = 115200
OUTPUT_DIR = "scan_images"
STEPS_PER_REV = 2048        # 28BYJ-48 typical total steps per revolution (half-step)
# --------------------------------

def send_rotate(ser, steps):
    cmd = f"ROTATE_STEPS {steps}\n"
    ser.write(cmd.encode('utf-8'))
    ser.flush()
    # wait for "DONE"
    while True:
        line = ser.readline().decode('utf-8', errors='ignore').strip()
        if not line:
            continue
        print("[Arduino] ", line)
        if line == "DONE":
            return True
        elif line.startswith("ERR") or line.startswith("UNKNOWN"):
            print("Arduino error:", line)
            return False

def capture_image(esp_ip, save_path, timeout=10, simulate=False, sim_idx=0, sim_total=36):
    """
    If simulate==False: perform HTTP GET to ESP32 and save JPEG.
    If simulate==True: generate a synthetic image and save to `save_path`.
    """
    if simulate:
        # dispatch to shape-specific simulator (default ellipse for backward compatibility)
        if simulate_shape == 'pyramid':
            return simulate_pyramid_image(save_path, sim_idx, sim_total, per_ring, rings, sim_radius, sim_apex, elev_step)
        # default: generate a simple synthetic black background with a white rotated ellipse/circle
        w, h = 640, 480
        img = np.zeros((h, w, 3), dtype=np.uint8)
        # place object center on a small circle to simulate rotation
        angle = (sim_idx / max(1, sim_total)) * 2 * math.pi
        cx = int(w/2 + 80 * math.cos(angle))
        cy = int(h/2 + 0 * math.sin(angle))
        axes = (80, 120)
        # draw filled ellipse (white)
        M = int(np.degrees(angle))
        cv2.ellipse(img, (cx, cy), axes, M, 0, 360, (255,255,255), -1)
        # add slight shading / noise
        cv2.circle(img, (cx, cy), 10, (200,200,200), -1)
        # save
        try:
            cv2.imencode('.jpg', img)[1].tofile(save_path)
            return True
        except Exception as e:
            print('Simulate save error:', e)
            return False

    url = f"http://{esp_ip}/capture"
    try:
        r = requests.get(url, timeout=timeout)
        if r.status_code == 200 and 'image' in r.headers.get('Content-Type',''):
            with open(save_path, 'wb') as f:
                f.write(r.content)
            return True
        else:
            print("Bad response:", r.status_code, r.headers.get('Content-Type'))
            return False
    except Exception as e:
        print("Capture error:", e)
        return False

def ensure_dir(d):
    if not os.path.exists(d):
        os.makedirs(d)


class MockSerial:
    """A simple mock serial class to simulate Arduino responses for ROTATE_STEPS."""
    def __init__(self):
        self._queue = []
        self._last_cmd = None

    def write(self, data):
        try:
            s = data.decode('utf-8')
        except Exception:
            s = str(data)
        self._last_cmd = s.strip()
        # parse steps
        if self._last_cmd.startswith('ROTATE_STEPS'):
            parts = self._last_cmd.split()
            n = parts[1] if len(parts) > 1 else '0'
            # simulate brief RUN then DONE
            self._queue.append(f'RUN {n}\n'.encode('utf-8'))
            self._queue.append(b'DONE\n')
        else:
            self._queue.append(b'UNKNOWN_CMD\n')

    def flush(self):
        pass

    def readline(self):
        if self._queue:
            return self._queue.pop(0)
        time.sleep(0.05)
        return b''

    def close(self):
        pass


def project_points(points_world, cam_pos, cam_target, img_w, img_h, f=800.0):
    """Project 3D points (Nx3) to image plane using simple pinhole camera.
    cam_pos, cam_target: 3D positions. Returns list of 2D points (u,v) and bool mask for in-front.
    """
    # build camera basis
    forward = (cam_target - cam_pos)
    forward = forward / np.linalg.norm(forward)
    up = np.array([0.0, 1.0, 0.0])
    right = np.cross(forward, up)
    if np.linalg.norm(right) < 1e-6:
        up = np.array([0.0, 0.0, 1.0])
        right = np.cross(forward, up)
    right = right / np.linalg.norm(right)
    true_up = np.cross(right, forward)
    R = np.vstack((right, true_up, forward))  # 3x3
    pts_cam = (R @ (points_world - cam_pos).T).T
    uv = []
    mask = []
    cx, cy = img_w / 2.0, img_h / 2.0
    for p in pts_cam:
        X, Y, Z = p[0], p[1], p[2]
        if Z <= 1e-6:
            mask.append(False)
            uv.append((0,0))
            continue
        u = f * (X / Z) + cx
        v = f * (Y / Z) + cy
        uv.append((int(round(u)), int(round(v))))
        mask.append(True)
    return uv, np.array(mask, dtype=bool)


def simulate_pyramid_image(save_path, sim_idx, sim_total, per_ring, rings, radius, apex_h, elev_step=15.0):
    """Generate a silhouette image of a square pyramid centered at origin.
    Camera moves around azimuth and elevation rings.
    """
    # Determine ring and azimuth index
    per_ring = max(1, int(per_ring))
    rings = max(1, int(rings))
    total_needed = per_ring * rings
    # clamp sim_idx
    idx = int(sim_idx) % total_needed
    ring_idx = idx // per_ring
    az_idx = idx % per_ring
    az = (az_idx / per_ring) * 360.0
    # elevation: from 0 (horizontal) up to some degrees per ring
    elev_start = 0.0
    elev = elev_start + ring_idx * elev_step

    # define pyramid vertices: square base on XZ plane, apex on +Y
    base = 0.5  # half-size of base
    vertices = np.array([
        [-base, 0.0, -base],
        [ base, 0.0, -base],
        [ base, 0.0,  base],
        [-base, 0.0,  base],
        [ 0.0, apex_h, 0.0]
    ], dtype=float)

    # camera position in spherical coords (radius, elev, az)
    az_rad = math.radians(az)
    elev_rad = math.radians(elev)
    cam_x = radius * math.cos(elev_rad) * math.cos(az_rad)
    cam_y = radius * math.sin(elev_rad)
    cam_z = radius * math.cos(elev_rad) * math.sin(az_rad)
    cam_pos = np.array([cam_x, cam_y, cam_z], dtype=float)
    cam_target = np.array([0.0, 0.0, 0.0], dtype=float)

    # project vertices
    img_w, img_h = 800, 600
    uv, mask = project_points(vertices, cam_pos, cam_target, img_w, img_h, f=800.0)
    pts2 = np.array([p for p,m in zip(uv, mask) if m], dtype=np.int32)
    img = np.zeros((img_h, img_w, 3), dtype=np.uint8)
    if pts2.shape[0] >= 3:
        # convex hull of projected points gives silhouette
        hull = cv2.convexHull(pts2)
        cv2.fillConvexPoly(img, hull, (255,255,255))
    else:
        # fallback: small circle at center
        cv2.circle(img, (img_w//2, img_h//2), 50, (255,255,255), -1)

    # save
    try:
        cv2.imencode('.jpg', img)[1].tofile(save_path)
        return True
    except Exception as e:
        print('Simulate pyramid save error:', e)
        return False


# Simple mask extraction for silhouette
def extract_silhouette(img_path):
    img = cv2.imdecode(np.fromfile(img_path, dtype=np.uint8), cv2.IMREAD_COLOR)
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    # background subtraction naive: use adaptive threshold or Otsu
    blur = cv2.GaussianBlur(gray, (5,5), 0)
    _, th = cv2.threshold(blur, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    # ensure object is white, background black (may need inversion)
    # if background is white, invert
    white_ratio = np.mean(th==255)
    if white_ratio > 0.5:
        th = 255 - th
    # morphological clean
    kernel = np.ones((5,5), np.uint8)
    th = cv2.morphologyEx(th, cv2.MORPH_OPEN, kernel)
    th = cv2.morphologyEx(th, cv2.MORPH_CLOSE, kernel)
    return th

# Naive voxel carving
def voxel_carving(image_files, esp_ip, voxel_resolution=64, bound=0.5):
    """
    image_files: list of image file paths in order of angles (0..360)
    assumes camera on +Z axis, object at origin on turntable, camera distance and intrinsics approximated.
    returns boolean voxel grid and point cloud list
    """
    N = len(image_files)
    angles = np.linspace(0, 360, N, endpoint=False)
    # Create voxel grid in [-bound, bound]^3
    voxels = np.ones((voxel_resolution, voxel_resolution, voxel_resolution), dtype=bool)
    xs = np.linspace(-bound, bound, voxel_resolution)
    ys = np.linspace(-bound, bound, voxel_resolution)
    zs = np.linspace(-bound, bound, voxel_resolution)
    # Camera approximate intrinsics
    img0 = cv2.imdecode(np.fromfile(image_files[0], dtype=np.uint8), cv2.IMREAD_COLOR)
    h, w = img0.shape[:2]
    fx = fy = max(w, h)  # very rough
    cx, cy = w/2.0, h/2.0
    # For each image, carve voxels whose projection falls outside silhouette
    for idx, imgf in enumerate(tqdm(image_files, desc="Carving")):
        sil = extract_silhouette(imgf)  # binary image: object white(255)
        angle = np.deg2rad(angles[idx])
        # camera at some distance along +Z rotated around Y by angle? We'll assume camera at (0, 0, cam_z) and turntable rotates object.
        cam_z = 1.5  # camera distance (approx)
        # For each voxel, project to image
        # iterate over voxels (could be optimized)
        for ix, x in enumerate(xs):
            for iy, y in enumerate(ys):
                for iz, z in enumerate(zs):
                    if not voxels[ix,iy,iz]: 
                        continue
                    # rotate point by -angle around Y (object rotated relative to camera)
                    xr = x * math.cos(-angle) + z * math.sin(-angle)
                    yr = y
                    zr = -x * math.sin(-angle) + z * math.cos(-angle) + cam_z  # translate camera forward
                    if zr <= 0.001:
                        voxels[ix,iy,iz] = False
                        continue
                    # perspective projection
                    u = (fx * (xr / zr)) + cx
                    v = (fy * (yr / zr)) + cy
                    ui = int(round(u))
                    vi = int(round(v))
                    if ui < 0 or ui >= w or vi < 0 or vi >= h:
                        voxels[ix,iy,iz] = False
                    else:
                        # if outside silhouette (sil pixel == 0) then carve
                        if sil[vi, ui] == 0:
                            voxels[ix,iy,iz] = False
    # gather point cloud (voxel centers)
    points = []
    for ix, x in enumerate(xs):
        for iy, y in enumerate(ys):
            for iz, z in enumerate(zs):
                if voxels[ix,iy,iz]:
                    points.append((x,y,z))
    return np.array(points)

def save_ply(points, filename):
    # simple ascii ply
    with open(filename, 'w') as f:
        f.write("ply\nformat ascii 1.0\n")
        f.write(f"element vertex {len(points)}\n")
        f.write("property float x\nproperty float y\nproperty float z\n")
        f.write("end_header\n")
        for p in points:
            f.write(f"{p[0]} {p[1]} {p[2]}\n")
    print(f"Saved PLY: {filename}")


def visualize_images(out_dir, delay_ms=500):
    """Show captured images and their silhouettes in a simple OpenCV window sequence."""
    img_files = sorted([os.path.join(out_dir, f) for f in os.listdir(out_dir) if f.lower().endswith('.jpg')])
    if not img_files:
        print('No images to visualize in', out_dir)
        return
    for idx, p in enumerate(img_files):
        img = cv2.imdecode(np.fromfile(p, dtype=np.uint8), cv2.IMREAD_COLOR)
        sil = extract_silhouette(p)
        # compose side-by-side
        sil_bgr = cv2.cvtColor(sil, cv2.COLOR_GRAY2BGR)
        combo = np.hstack((cv2.resize(img, (640,480)), cv2.resize(sil_bgr, (640,480))))
        cv2.imshow('Image | Silhouette', combo)
        key = cv2.waitKey(delay_ms)
        if key == 27:  # ESC to quit
            break
    cv2.destroyAllWindows()


def visualize_pointcloud(plyfile, subsample=20000, fill_boundary=True):
    """Load simple ASCII PLY produced by save_ply and display a 3D scatter with optional ConvexHull boundary mesh."""
    if not os.path.exists(plyfile):
        print('PLY not found:', plyfile)
        return
    pts = []
    with open(plyfile, 'r') as f:
        header = True
        for line in f:
            if header:
                if line.strip() == 'end_header':
                    header = False
                continue
            parts = line.strip().split()
            if len(parts) >= 3:
                try:
                    x, y, z = float(parts[0]), float(parts[1]), float(parts[2])
                    pts.append((x, y, z))
                except Exception:
                    continue
    if not pts:
        print('No points in PLY')
        return
    pts = np.array(pts)
    pts_original = pts.copy()  # keep full point set for hull
    # subsample for plotting if too many
    if pts.shape[0] > subsample:
        idx = np.random.choice(pts.shape[0], subsample, replace=False)
        pts = pts[idx]
    fig = plt.figure(figsize=(10, 8))
    ax = fig.add_subplot(111, projection='3d')
    ax.scatter(pts[:, 0], pts[:, 1], pts[:, 2], s=1, c='blue', label='Points')
    
    # Add ConvexHull mesh (boundary fill)
    if fill_boundary and len(pts_original) >= 4:
        try:
            hull = ConvexHull(pts_original)
            # Draw hull triangles as red wireframe edges
            for simplex in hull.simplices:
                triangle = pts_original[simplex]
                for i in range(3):
                    p1 = triangle[i]
                    p2 = triangle[(i + 1) % 3]
                    ax.plot([p1[0], p2[0]], [p1[1], p2[1]], [p1[2], p2[2]], 'r-', alpha=0.2, linewidth=0.5)
            print(f"ConvexHull computed: {len(hull.simplices)} triangles, volume={hull.volume:.6f}")
        except Exception as e:
            print(f"Could not compute ConvexHull: {e}")
    
    ax.set_xlabel('X')
    ax.set_ylabel('Y')
    ax.set_zlabel('Z')
    ax.set_title(os.path.basename(plyfile) + (' [with boundary mesh]' if fill_boundary else ''))
    ax.legend()
    plt.show()

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--esp", default=ESP32_IP, help="ESP32 CAM IP")
    parser.add_argument("--serial", default=SERIAL_PORT, help="Arduino serial port")
    parser.add_argument("--steps_per_rev", type=int, default=STEPS_PER_REV, help="steps per turntable revolution")
    parser.add_argument("--num_images", type=int, default=36, help="number of images (e.g., 36)")
    parser.add_argument("--out", default=OUTPUT_DIR, help="output folder for images")
    parser.add_argument("--voxel_res", type=int, default=64, help="voxel grid resolution for carving (<=64 recommended)")
    parser.add_argument("--simulate", action='store_true', help="Run in simulation mode without Arduino/ESP32 hardware")
    parser.add_argument("--visualize", action='store_true', help="Open visualization windows after capture/reconstruction")
    parser.add_argument("--visualize-only", action='store_true', help="Only visualize existing result.ply and images without running capture/carving")
    parser.add_argument("--sim_shape", default='ellipse', help="Simulation shape: 'ellipse' or 'pyramid'")
    parser.add_argument("--per_ring", type=int, default=36, help="Number of images per horizontal ring (simulation)")
    parser.add_argument("--rings", type=int, default=2, help="Number of elevation rings (simulation)")
    parser.add_argument("--sim_radius", type=float, default=1.5, help="Camera radius from object center in simulation (meters)")
    parser.add_argument("--sim_apex", type=float, default=0.6, help="Pyramid apex height (meters) for pyramid simulation")
    parser.add_argument("--elev_step", type=float, default=15.0, help="Elevation step in degrees between rings (simulation)")
    args = parser.parse_args()

    esp_ip = args.esp
    port = args.serial
    steps_per_rev = args.steps_per_rev
    num_images = args.num_images
    out_dir = args.out
    res = args.voxel_res
    simulate = args.simulate
    visualize_flag = args.visualize if hasattr(args, 'visualize') else False
    visualize_only = args.visualize_only if hasattr(args, 'visualize_only') else False

    # ========== VISUALIZE-ONLY MODE ==========
    if visualize_only:
        print(f"Visualization-only mode: Loading {out_dir}/")
        plyfile = os.path.join(out_dir, "result.ply")
        if os.path.exists(plyfile):
            print(f"Found {plyfile}, displaying 3D point cloud...")
            visualize_pointcloud(plyfile)
        else:
            print(f"ERROR: {plyfile} not found in {out_dir}/")
        
        # also try to display images if they exist
        img_files = [f for f in os.listdir(out_dir) if f.endswith('.jpg') or f.endswith('.png')]
        if img_files:
            print(f"Found {len(img_files)} images in {out_dir}/")
            try:
                visualize_images(out_dir)
            except Exception as e:
                print(f"Could not visualize images: {e}")
        return

    # export simulation parameters to module-level globals used by simulator
    # export simulation parameters as globals so capture_image can access them
    globals()['simulate_shape'] = args.sim_shape
    globals()['per_ring'] = args.per_ring
    globals()['rings'] = args.rings
    globals()['sim_radius'] = args.sim_radius
    globals()['sim_apex'] = args.sim_apex
    globals()['elev_step'] = args.elev_step
    # when simulating pyramid, override number of images
    if simulate and globals()['simulate_shape'] == 'pyramid':
        num_images = globals()['per_ring'] * globals()['rings']

    ensure_dir(out_dir)

    angle_step = 360.0 / num_images
    steps_per_angle = steps_per_rev / 360.0 * angle_step
    print(f"Angle step: {angle_step} deg; steps per angle: {steps_per_angle}")

    print("Opening serial:", port if not simulate else '(SIMULATED)')
    if simulate:
        ser = MockSerial()
        time.sleep(0.1)
    else:
        try:
            ser = serial.Serial(port, 115200, timeout=1)
            time.sleep(2)  # wait for Arduino reset
            # flush
            try:
                ser.flushInput()
                ser.flushOutput()
            except Exception:
                pass
        except Exception as e:
            print(f"WARNING: Could not open serial port {port}: {e}")
            print("Auto-falling back to SIMULATE mode...")
            ser = MockSerial()
            simulate = True

    saved_files = []
    for i in range(num_images):
        angle = i * angle_step
        steps = int(round(steps_per_angle))
        print(f"-> Rotating to angle {angle:.2f}°, steps {steps}")
        ok = send_rotate(ser, steps)
        if not ok:
            print("Rotation failed, abort")
            break
        # small wait to let vibrations subside
        time.sleep(0.5)
        fname = os.path.join(out_dir, f"img_{i:03d}.jpg")
        ok = capture_image(esp_ip, fname, simulate=simulate, sim_idx=i, sim_total=num_images)
        if not ok:
            print("Capture failed, retrying once...")
            time.sleep(1)
            ok = capture_image(esp_ip, fname)
            if not ok:
                print("Failed to capture image for angle index", i)
                break
        print("Saved", fname)
        saved_files.append(fname)
        time.sleep(0.2)

    ser.close()
    print("Capture finished. Images saved:", len(saved_files))

    if len(saved_files) > 4:
        print("Starting voxel carving (this may take some time)...")
        pts = voxel_carving(saved_files, esp_ip, voxel_resolution=res)
        print("Points:", pts.shape)
        plyfile = os.path.join(out_dir, "result.ply")
        save_ply(pts, plyfile)
        # optional visualization
        if 'visualize' in globals() or 'visualize' in locals():
            pass
        try:
            if visualize_flag:
                visualize_images(out_dir)
                visualize_pointcloud(plyfile)
        except NameError:
            pass
    else:
        print("Not enough images for carving.")

if __name__ == "__main__":
    main()
