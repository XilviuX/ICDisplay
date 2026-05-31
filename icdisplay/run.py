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

HA_URL          = os.environ.get("HA_URL",         "http://172.16.137.11:8123")
HA_TOKEN        = os.environ.get("HA_TOKEN",       "")
I2C_BUS         = int(os.environ.get("I2C_BUS",    "1"))
I2C_ADDRESS     = int(os.environ.get("I2C_ADDRESS","0x3C"), 16)
SENSOR_CPU      = os.environ.get("SENSOR_CPU",     "sensor.system_monitor_utilisation_du_processeur")
SENSOR_RAM      = os.environ.get("SENSOR_RAM",     "sensor.system_monitor_utilisation_de_la_memoire")

REFRESH_SENSORS = 10
FRAME_DELAY     = 1.0

W, H = 128, 64

FONT     = "/usr/share/fonts/dejavu/DejaVuSans.ttf"
FONT_B   = "/usr/share/fonts/dejavu/DejaVuSans-Bold.ttf"
FONT_M   = "/usr/share/fonts/dejavu/DejaVuSansMono.ttf"
FONT_MB  = "/usr/share/fonts/dejavu/DejaVuSansMono-Bold.ttf"

class HAClient:
    def __init__(self):
        self.headers = {"Authorization": f"Bearer {HA_TOKEN}", "Content-Type": "application/json"}
        self.cpu     = "--"
        self.ram     = "--"
        self.online  = False
        self._lock   = threading.Lock()

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
                time.sleep(REFRESH_SENSORS)
        threading.Thread(target=loop, daemon=True).start()

    def get(self):
        with self._lock:
            return self.cpu, self.ram, self.online


SPINNERS = ["▏", "▎", "▍", "▌", "▋", "▊", "▉", "█", "▉", "▊", "▋", "▌", "▍", "▎"]

def render(device, ha):
    font_time  = ImageFont.truetype(FONT_MB, 28)
    font_label = ImageFont.truetype(FONT,    9)
    font_val   = ImageFont.truetype(FONT_B,  11)

    tick = 0
    while True:
        cpu, ram, online = ha.get()
        now = datetime.now()

        img  = Image.new("1", (W, H), 0)
        draw = ImageDraw.Draw(img)

        # ── Heure ─────────────────────────────────────────────────────
        time_str = now.strftime("%H:%M:%S")
        bbox = draw.textbbox((0, 0), time_str, font=font_time)
        tw = bbox[2] - bbox[0]
        draw.text(((W - tw) // 2, 0), time_str, font=font_time, fill=1)

        # ── Séparateur ────────────────────────────────────────────────
        draw.line([(0, 33), (W, 33)], fill=1)

        # ── CPU / RAM ─────────────────────────────────────────────────
        draw.text((2, 35),  "CPU", font=font_label, fill=1)
        draw.text((2, 45),  f"{cpu}%", font=font_val, fill=1)

        draw.text((50, 35), "RAM", font=font_label, fill=1)
        draw.text((50, 45), f"{ram}%", font=font_val, fill=1)

        # ── Heartbeat ─────────────────────────────────────────────────
        spinner = SPINNERS[tick % len(SPINNERS)]
        status  = "EN LIGNE" if online else "OFFLINE"
        draw.text((90, 35), spinner,  font=font_val,   fill=1)
        draw.text((90, 48), status,   font=font_label, fill=1)

        device.display(img)
        tick += 1
        time.sleep(FRAME_DELAY)


def main():
    print(f"[ICDisplay] I2C bus={I2C_BUS} addr=0x{I2C_ADDRESS:02X}")
    serial = i2c(port=I2C_BUS, address=I2C_ADDRESS)
    device = sh1106(serial, width=W, height=H, rotate=0, h_flip=True)

    ha = HAClient()
    ha.start_polling()
    render(device, ha)

if __name__ == "__main__":
    main()
