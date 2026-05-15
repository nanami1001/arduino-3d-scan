import time
import serial

class TurntableController:
    def __init__(self, port, baudrate=115200, timeout=2):
        """
        port: 例如 'COM3' (Windows) 或 '/dev/ttyACM0' (Linux)
        """
        self.ser = serial.Serial(port, baudrate=baudrate, timeout=timeout)
        time.sleep(2)  # 等 Arduino 重置
        self.flush()

    def flush(self):
        """清空 Serial Buffer"""
        self.ser.reset_input_buffer()
        self.ser.reset_output_buffer()

    def send_command(self, cmd):
        """傳送字串給 Arduino 並讀取回應"""
        self.ser.write((cmd + "\n").encode("utf-8"))
        self.ser.flush()

        lines = []
        while True:
            line = self.ser.readline().decode(errors="ignore").strip()
            if not line:
                break
            lines.append(line)
        return lines

    def rotate_steps(self, steps):
        """旋轉指定步數（可正可負）"""
        lines = self.send_command(f"ROTATE_STEPS {steps}")
        return lines

    def set_delay(self, microseconds):
        """設定每步延遲（μs）"""
        return self.send_command(f"SET_DELAY {microseconds}")

    def close(self):
        self.ser.close()
