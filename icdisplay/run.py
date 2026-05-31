#!/usr/bin/env python3
"""
ICDisplay — Home Assistant OLED Monitor
SH1106 128x64 via I2C
"""

import os
import time
import requests
import threading
from datetime import datetime
from PIL import Image, ImageDraw, ImageFont
from luma.core.interface.serial import i2c
from luma.oled.device import sh1106

HA_URL     = os.environ.get("HA_URL",         "http://172.16.137.11:8123")
HA_TOKEN   = os.environ.get("HA_TOKEN",       "")
I2C_BUS    = int(os.environ.get("I2C_BUS",    "1"))
I2C_ADDR   = int(os.environ.get("I2C_ADDRESS","0x3C"), 16)
SENSOR_CPU = os.environ.get("SENSOR_CPU",     "sensor.system_monitor_utilisation_du_processeur")
SENSOR_RAM = os.environ.get("SENSOR_RAM",     "sensor.system_monitor_utilisation_de_la_memoire")

W, H = 128, 64

class HAClient:
    def __init__(self):
        self.headers = {"Authorization": f"Bearer {HA_TOKEN}", "Content-Type": "application/json"}
        self.cpu    = "--"
        self.ram    = "--"
        self.online = False
        self._lock  = threading.Lock()

    def fetch(self):
        try:
            r = requests.get(f"{HA_URL}/api/", headers=self.headers, timeout=5)
            if r.status_code != 200:
                with self._lock: self.online = False
                return
            def get(eid):
                resp = requests.get(f"{HA_URL}/api/states/{eid}", headers=self.headers, timeout=5)
                if resp.status_code == 200:
                    val = resp.json().get("state", "--")
                    try: return f"{float(val):.0f}"
                    except: return val
                return "--"
            cpu = get(SENSOR_CPU)
            ram = get(SENSOR_RAM)
            with self._lock:
                self.cpu    = cpu
                self.ram    = ram
                self.online = True
        except Exception as e:
            print(f"[HA] {e}")
            with self._lock: self.online = False

    def start_polling(self):
        def loop():
            while True:
                self.fetch()
                time.sleep(10)
        threading.Thread(target=loop, daemon=True).start()

    def get(self):
        with self._lock:
            return self.cpu, self.ram, self.online


SPINNERS = ["|", "/", "-", "\\"]

def render(device, ha):
    f_big   = ImageFont.truetype("/usr/share/fonts/dejavu/DejaVuSans-Bold.ttf", 26)
    f_med   = ImageFont.truetype("/usr/share/fonts/dejavu/DejaVuSans-Bold.ttf", 13)
    f_small = ImageFont.truetype("/usr/share/fonts/dejavu/DejaVuSans.ttf",       9)

    tick = 0
    while True:
        cpu, ram, online = ha.get()
        now = datetime.now()

        img  = Image.new("1", (W, H), 0)
        draw = ImageDraw.Draw(img)

        # Heure — centrée, grande
        t = now.strftime("%H:%M:%S")
        bbox = draw.textbbox((0, 0), t, font=f_big)
        draw.text(((W - bbox[2]) // 2, 1), t, font=f_big, fill=1)

        # Séparateur
        draw.line([(0, 32), (W, 32)], fill=1)

        # CPU
        draw.text((2, 34),  "CPU",           font=f_small, fill=1)
        draw.text((2, 44),  f"{cpu}%",       font=f_med,   fill=1)

        # RAM
        draw.text((52, 34), "RAM",           font=f_small, fill=1)
        draw.text((52, 44), f"{ram}%",       font=f_med,   fill=1)

        # Spinner
        sp = SPINNERS[tick % len(SPINNERS)]
        draw.text((108, 36), sp,             font=f_med,   fill=1)
        dot = "●" if online else "○"
        draw.text((110, 52), dot,            font=f_small, fill=1)

        device.display(img)
        tick += 1
        time.sleep(1)


def main():
    print(f"[ICDisplay] I2C bus={I2C_BUS} addr=0x{I2C_ADDR:02X}")
    serial = i2c(port=I2C_BUS, address=I2C_ADDR)
    device = sh1106(serial, width=W, height=H, rotate=0, h_flip=True)
    ha = HAClient()
    ha.start_polling()
    render(device, ha)

if __name__ == "__main__":
    main()
