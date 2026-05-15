"""
ESP32-CAM 定時圖片採集器

用法範例：
python esp32_cam_capture.py --url http://192.168.1.100/capture --interval 500ms --total 100

說明：
- 預設儲存至 scan_images 資料夾
- 檔名格式：01.png、02.png、03.png ...
- 支援秒或毫秒格式的間隔（例如 `5`, `0.5`, `500ms`）
- 內建錯誤處理、重試與略過失敗選項
"""

from __future__ import annotations

import argparse
import logging
import re
import signal
import time
from pathlib import Path

import requests

STOP = False

# Reuse a Session for better stability across many requests
session = requests.Session()


def signal_handler(signum, frame):
    global STOP
    STOP = True
    print("Interrupted. Exiting after current operation...")


def parse_interval(interval_str) -> float:
    """解析間隔，支援秒或毫秒。回傳秒數（float）。"""
    if isinstance(interval_str, (int, float)):
        val = float(interval_str)
        if val < 0:
            raise ValueError("Interval must be non-negative")
        return val

    s = str(interval_str).strip().lower()

    if s.endswith('ms'):
        num = float(s[:-2])
        return num / 1000.0

    if s.endswith('s'):
        return float(s[:-1])

    return float(s)


def ensure_save_dir(path: Path):
    try:
        path.mkdir(parents=True, exist_ok=True)
    except Exception as e:
        raise RuntimeError(f"Failed to create directory {path}: {e}")


def find_next_index(save_dir: Path, exts=('png', 'jpg', 'jpeg')) -> int:
    pattern = re.compile(
        r'^(\d+)\.(' + '|'.join(re.escape(e) for e in exts) + r')$',
        re.IGNORECASE
    )

    max_index = 0

    for p in save_dir.iterdir() if save_dir.exists() else []:
        if p.is_file():
            m = pattern.match(p.name)

            if m:
                try:
                    idx = int(m.group(1))
                    if idx > max_index:
                        max_index = idx
                except Exception:
                    pass

    return max_index + 1


def save_image(data: bytes, path: Path):
    try:
        with open(path, 'wb') as f:
            f.write(data)
    except Exception as e:
        raise IOError(f"Save Failed: {e}")


def capture_once(url: str, timeout: float) -> bytes:
    """Capture one image from ESP32-CAM"""

    headers = {
        "Connection": "close",
        "User-Agent": "ESP32-CAM-Capture",
    }

    resp = session.get(
        url,
        timeout=(5, timeout),
        headers=headers,
        stream=False,
    )

    resp.raise_for_status()

    data = resp.content

    try:
        resp.close()
    except Exception:
        pass

    return data


def main() -> int:
    global STOP

    parser = argparse.ArgumentParser(description="ESP32-CAM 定時圖片採集器")

    parser.add_argument(
        '--url',
        '-u',
        default="http://10.165.107.241/capture",
        help='ESP32-CAM capture URL'
    )

    parser.add_argument(
        '--interval',
        '-i',
        default='5',
        help="Capture interval, e.g. '5', '0.5', '500ms'"
    )

    parser.add_argument(
        '--total',
        '-n',
        type=int,
        default=100,
        help='Total images to capture'
    )

    # 修改預設存放路徑
    parser.add_argument(
        '--save',
        '-d',
        default='scan_images',
        help='Save directory'
    )

    parser.add_argument(
        '--format',
        '-f',
        default='png',
        choices=['png', 'jpg', 'jpeg'],
        help='Image extension'
    )

    parser.add_argument(
        '--timeout',
        type=float,
        default=10.0,
        help='HTTP timeout (s)'
    )

    parser.add_argument(
        '--max-retries',
        type=int,
        default=2,
        help='Max retries on capture failure'
    )

    parser.add_argument(
        '--retry-delay',
        type=float,
        default=2.0,
        help='Delay between retries (s)'
    )

    parser.add_argument(
        '--skip-failed',
        action='store_true',
        help='Skip failed captures and continue'
    )

    parser.add_argument(
        '--start-index',
        type=int,
        default=None,
        help='Optional start index override'
    )

    parser.add_argument(
        '--verbose',
        '-v',
        action='store_true',
        help='Verbose output'
    )

    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format='%(asctime)s %(levelname)s: %(message)s'
    )

    try:
        interval = parse_interval(args.interval)
    except Exception as e:
        print(f"Invalid interval: {e}")
        return 1

    if interval <= 0:
        print("Interval must be positive")
        return 1

    if args.total <= 0:
        print("total must be positive")
        return 1

    url = args.url
    save_dir = Path(args.save)
    image_format = args.format.lower().lstrip('.')
    timeout = args.timeout
    max_retries = max(0, args.max_retries)
    retry_delay = args.retry_delay
    skip_failed = args.skip_failed

    # 建立資料夾
    try:
        ensure_save_dir(save_dir)
    except Exception as e:
        print(e)
        return 1

    # 起始編號
    if args.start_index and args.start_index > 0:
        next_index = args.start_index
    else:
        next_index = find_next_index(
            save_dir,
            exts=('png', 'jpg', 'jpeg')
        )

    signal.signal(signal.SIGINT, signal_handler)

    try:
        signal.signal(signal.SIGTERM, signal_handler)
    except Exception:
        pass

    start_time = time.perf_counter()

    captured = 0
    failed = 0

    while captured < args.total and not STOP:

        current_num = captured + 1

        print(f"[{current_num}/{args.total}] Capturing...")

        success = False
        attempts = 0

        while attempts <= max_retries and not success and not STOP:

            try:
                data = capture_once(url, timeout=timeout)

                # 命名格式：01.png 02.png ...
                filename = f"{next_index:02d}.{image_format}"

                save_path = save_dir / filename

                save_image(data, save_path)

                print(f"Saved: {save_path}")

                success = True

            except requests.exceptions.HTTPError as e:
                status = getattr(e.response, 'status_code', '')
                print(f"Capture Failed: HTTP Error {status} - {e}")

            except requests.exceptions.Timeout:
                print(f"Capture Failed: Timeout after {timeout}s")

            except requests.exceptions.RequestException as e:
                print(f"Capture Failed: {e}")

            except IOError as e:
                print(f"Save Failed: {e}")

            attempts += 1

            if not success and attempts <= max_retries and not STOP:
                time.sleep(retry_delay)

        if not success:

            failed += 1

            if skip_failed:
                print("Skipped failed capture.")
                next_index += 1
                captured += 1
            else:
                print("Stopping due to failure.")
                break

        else:
            captured += 1
            next_index += 1

        # 維持固定間隔
        next_target = start_time + captured * interval

        now = time.perf_counter()

        sleep_time = next_target - now

        if sleep_time > 0 and not STOP:
            time.sleep(sleep_time)

    print(f"Done. Captured: {captured}, Failed: {failed}")

    return 0


if __name__ == '__main__':
    raise SystemExit(main())