#!/usr/bin/env python3
"""
ICDisplay — Home Assistant OLED Monitor
SH1106 128x64 via I2C
"""

import os
import json
import time
import requests
import threading
from datetime import datetime
from PIL import Image, ImageDraw, ImageFont
from luma.core.interface.serial import i2c
from luma.oled.device import sh1106

# ── Config ────────────────────────────────────────────────────────────────────
def load_options():
    try:
        with open("/data/options.json") as f:
            return json.load(f)
    except Exception as e:
        print(f"[ICDisplay] options.json: {e}")
        return {}

opts       = load_options()
HA_URL     = opts.get("ha_url",      "http://172.16.137.11:8123")
HA_TOKEN   = opts.get("ha_token",    "")
I2C_BUS    = int(opts.get("i2c_bus",      1))
I2C_ADDR   = int(opts.get("i2c_address", "0x3C"), 16)
SENSOR_CPU = opts.get("sensor_cpu",  "sensor.system_monitor_utilisation_du_processeur")
SENSOR_RAM = opts.get("sensor_ram",  "sensor.system_monitor_utilisation_de_la_memoire")

print(f"[ICDisplay] URL={HA_URL} I2C=0x{I2C_ADDR:02X}")

W, H = 128, 64

# ── Polices ───────────────────────────────────────────────────────────────────
SILK    = "/usr/share/fonts/silkscreen/Silkscreen-Regular.ttf"
SILK_B  = "/usr/share/fonts/silkscreen/Silkscreen-Bold.ttf"
DEJAVU  = "/usr/share/fonts/dejavu/DejaVuSans-Bold.ttf"

def font(path, size):
    try:
        return ImageFont.truetype(path, size)
    except:
        return ImageFont.load_default()

# ── HA Client ─────────────────────────────────────────────────────────────────
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
                print(f"[HA] status {r.status_code}")
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
                print(f"[HA] CPU={cpu}% RAM={ram}%")
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
    # Silkscreen est une police pixel-perfect — utilise des tailles multiples de 8
    f_clock = font(SILK_B, 16)   # heure
    f_big   = font(SILK_B, 16)   # valeurs CPU/RAM
    f_med   = font(SILK,   8)    # labels
    f_spin  = font(SILK_B, 8)    # spinner

    tick = 0
    while True:
        cpu, ram, online = ha.get()
        now = datetime.now()

        img  = Image.new("1", (W, H), 0)
        draw = ImageDraw.Draw(img)

        # ── Heure ─────────────────────────────────────────────────────
        t = now.strftime("%H:%M:%S")
        bbox = draw.textbbox((0, 0), t, font=f_clock)
        draw.text(((W - bbox[2]) // 2, 2), t, font=f_clock, fill=1)

        # ── Séparateur ────────────────────────────────────────────────
        draw.line([(0, 22), (W, 22)], fill=1)

        # ── CPU ───────────────────────────────────────────────────────
        draw.text((2, 25),  "CPU",      font=f_med,  fill=1)
        draw.text((2, 36),  f"{cpu}%",  font=f_big,  fill=1)

        # ── RAM ───────────────────────────────────────────────────────
        draw.text((50, 25), "RAM",      font=f_med,  fill=1)
        draw.text((50, 36), f"{ram}%",  font=f_big,  fill=1)

        # ── Spinner + statut ──────────────────────────────────────────
        sp  = SPINNERS[tick % len(SPINNERS)]
        dot = "ON" if online else "OFF"
        draw.text((100, 25), sp,        font=f_spin, fill=1)
        draw.text((96,  36), dot,       font=f_spin, fill=1)

        # ── Séparateur bas ────────────────────────────────────────────
        draw.line([(0, 54), (W, 54)], fill=1)

        # ── Date ──────────────────────────────────────────────────────
        d = now.strftime("%a %d %b")
        bbox2 = draw.textbbox((0, 0), d, font=f_med)
        draw.text(((W - bbox2[2]) // 2, 56), d, font=f_med, fill=1)

        device.display(img)
        tick += 1
        time.sleep(1)


def main():
    serial = i2c(port=I2C_BUS, address=I2C_ADDR)
    device = sh1106(serial, width=W, height=H, rotate=0, h_flip=True)
    ha = HAClient()
    ha.start_polling()
    render(device, ha)

if __name__ == "__main__":
    main()
