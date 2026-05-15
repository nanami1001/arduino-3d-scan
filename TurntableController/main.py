import time
import serial

# 設定 Arduino COM 埠
PORT = "COM3"  # 根據實際 COM 埠修改
BAUDRATE = 115200

# 開啟 Serial
ser = serial.Serial(PORT, BAUDRATE, timeout=2)
time.sleep(2)  # 等 Arduino 重置

def send_command(cmd):
    ser.write((cmd + "\n").encode())
    ser.flush()
    lines = []
    start = time.time()
    while True:
        if ser.in_waiting:
            line = ser.readline().decode(errors="ignore").strip()
            if line:
                lines.append(line)
        if time.time() - start > 5:  # 5 秒超時
            break
    return lines

# 設定速度 1.5ms/step
print("設定速度")
print(send_command("SET_DELAY 1500"))

# 正轉 2048 步（約半圈）
print("正轉 2048 步")
print(send_command("ROTATE_STEPS 2048"))

# 等 1 秒
time.sleep(1)

# 反轉 2048 步（回原位）
print("反轉 2048 步")
print(send_command("ROTATE_STEPS -2048"))

ser.close()
