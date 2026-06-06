#!/usr/bin/env python3
"""
ICDisplay — Home Assistant OLED Monitor
SH1106 128x64 — bitmap 5x7 scale=2 uniquement
"""

import os, json, time, requests, threading
from datetime import datetime
from PIL import Image, ImageDraw
from luma.core.interface.serial import i2c
from luma.oled.device import sh1106

# ── Config ────────────────────────────────────────────────────────────────────
def load_options():
    try:
        with open("/data/options.json") as f: return json.load(f)
    except Exception as e:
        print(f"[ICDisplay] options.json: {e}"); return {}

opts       = load_options()
HA_URL     = opts.get("ha_url",      "http://172.16.137.11:8123")
HA_TOKEN   = opts.get("ha_token",    "")
I2C_BUS    = int(opts.get("i2c_bus",      1))
I2C_ADDR   = int(opts.get("i2c_address", "0x3C"), 16)
SENSOR_CPU = opts.get("sensor_cpu",  "sensor.system_monitor_utilisation_du_processeur")
SENSOR_RAM     = opts.get("sensor_ram",     "sensor.system_monitor_utilisation_de_la_memoire")
SENSOR_CPU_TEMP = opts.get("sensor_cpu_temp", "sensor.system_monitor_temperature_du_processeur")
W, H = 64, 128  # canvas de rendu pivotée

# ── Police bitmap 5x7 ─────────────────────────────────────────────────────────
FONT5X7 = {
    ' ':(0x00,0x00,0x00,0x00,0x00), '!':(0x00,0x00,0x5F,0x00,0x00),
    '%':(0x23,0x13,0x08,0x64,0x62), '+':(0x08,0x08,0x3E,0x08,0x08),
    '-':(0x08,0x08,0x08,0x08,0x08), '.':(0x00,0x60,0x60,0x00,0x00),
    '/':(0x20,0x10,0x08,0x04,0x02), ':':(0x00,0x36,0x36,0x00,0x00),
    '0':(0x3E,0x51,0x49,0x45,0x3E), '1':(0x00,0x42,0x7F,0x40,0x00),
    '2':(0x42,0x61,0x51,0x49,0x46), '3':(0x21,0x41,0x45,0x4B,0x31),
    '4':(0x18,0x14,0x12,0x7F,0x10), '5':(0x27,0x45,0x45,0x45,0x39),
    '6':(0x3C,0x4A,0x49,0x49,0x30), '7':(0x01,0x71,0x09,0x05,0x03),
    '8':(0x36,0x49,0x49,0x49,0x36), '9':(0x06,0x49,0x49,0x29,0x1E),
    'A':(0x7E,0x11,0x11,0x11,0x7E), 'B':(0x7F,0x49,0x49,0x49,0x36),
    'C':(0x3E,0x41,0x41,0x41,0x22), 'D':(0x7F,0x41,0x41,0x22,0x1C),
    'E':(0x7F,0x49,0x49,0x49,0x41), 'F':(0x7F,0x09,0x09,0x09,0x01),
    'G':(0x3E,0x41,0x41,0x51,0x32), 'H':(0x7F,0x08,0x08,0x08,0x7F),
    'I':(0x00,0x41,0x7F,0x41,0x00), 'J':(0x20,0x40,0x41,0x3F,0x01),
    'K':(0x7F,0x08,0x14,0x22,0x41), 'L':(0x7F,0x40,0x40,0x40,0x40),
    'M':(0x7F,0x02,0x04,0x02,0x7F), 'N':(0x7F,0x04,0x08,0x10,0x7F),
    'O':(0x3E,0x41,0x41,0x41,0x3E), 'P':(0x7F,0x09,0x09,0x09,0x06),
    'Q':(0x3E,0x41,0x51,0x21,0x5E), 'R':(0x7F,0x09,0x19,0x29,0x46),
    'S':(0x46,0x49,0x49,0x49,0x31), 'T':(0x01,0x01,0x7F,0x01,0x01),
    'U':(0x3F,0x40,0x40,0x40,0x3F), 'V':(0x1F,0x20,0x40,0x20,0x1F),
    'W':(0x3F,0x40,0x38,0x40,0x3F), 'X':(0x63,0x14,0x08,0x14,0x63),
    'Y':(0x03,0x04,0x78,0x04,0x03), 'Z':(0x61,0x51,0x49,0x45,0x43),
}

def draw_char(draw, x, y, ch, scale=2):
    c = ch.upper()
    cols = FONT5X7.get(c, FONT5X7[' '])
    for ci, col_data in enumerate(cols):
        for ri in range(7):
            if col_data & (1 << ri):
                px, py = x + ci * scale, y + ri * scale
                draw.rectangle([px, py, px+scale-1, py+scale-1], fill=1)
    return x + 6 * scale

def draw_text(draw, x, y, text, scale=2):
    cx = x
    for ch in text:
        cx = draw_char(draw, cx, y, ch, scale)
    return cx

def text_w(text, scale=2):
    return len(text) * 6 * scale

def center(text, scale=2):
    return (W - text_w(text, scale)) // 2

# ── HA Client ─────────────────────────────────────────────────────────────────
class HAClient:
    def __init__(self):
        self.headers = {"Authorization": f"Bearer {HA_TOKEN}", "Content-Type": "application/json"}
        self.cpu = "--"; self.ram = "--"; self.cpu_temp = "--"; self.online = False
        self._lock = threading.Lock()

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
            cpu = get(SENSOR_CPU); ram = get(SENSOR_RAM); cpu_temp = get(SENSOR_CPU_TEMP)
            with self._lock:
                self.cpu = cpu; self.ram = ram; self.cpu_temp = cpu_temp; self.online = True
                print(f"[HA] CPU={cpu}% RAM={ram}% TEMP={cpu_temp}C")
        except Exception as e:
            print(f"[HA] {e}")
            with self._lock: self.online = False

    def start_polling(self):
        def loop():
            while True: self.fetch(); time.sleep(10)
        threading.Thread(target=loop, daemon=True).start()

    def get(self):
        with self._lock: return self.cpu, self.ram, self.cpu_temp, self.online

# ── Rendu ─────────────────────────────────────────────────────────────────────
# Layout 4 lignes, scale=2 (char = 10x14px), espacement = 16px
# Y=0  : heure
# Y=16 : CPU / RAM
# Y=32 : date
# Y=48 : barre CPU

SONAR_RADII = [2, 4, 6, 8]  # rayon du cercle sonar en pixels

def render(device, ha):
    tick = 0
    while True:
        cpu, ram, cpu_temp, online = ha.get()
        now = datetime.now()
        hms = now.strftime("%H:%M:%S")

        img  = Image.new("1", (W, H), 0)
        draw = ImageDraw.Draw(img)

        # Ligne 1 — date
        d = now.strftime("%d/%m/%Y")
        draw_text(draw, center(d, scale=1), 0, d, scale=1)

        # Ligne 2 — heure
        draw_text(draw, center(hms, scale=1), 10, hms, scale=1)

        # Ligne 3 — statut + sonar
        status = "ONLINE" if online else "OFFLINE"
        draw_text(draw, 0, 26, status, scale=1)
        # Sonar : deux cercles, le grand suit le petit avec un decalage
        cx, cy = W - 10, 29
        r1 = SONAR_RADII[tick % 4]
        draw.ellipse([cx-r1, cy-r1, cx+r1, cy+r1], outline=1)

        # Ligne 4 — temperature CPU
        temp_str = f"CPU: {cpu_temp}"
        draw_text(draw, 0, 44, temp_str, scale=1)
        tw = text_w(temp_str, scale=1)
        draw.rectangle([tw + 1, 44, tw + 2, 45], outline=1)
        draw_text(draw, tw + 4, 44, "C", scale=1)

        # Barre CPU
        try:
            pct = min(int(float(cpu)), 100)
        except:
            pct = 0
        draw_text(draw, 0, 56, "CPU", scale=1)
        cpu_pct_str = f"{cpu}%"
        draw_text(draw, W - text_w(cpu_pct_str, 1) - 1, 56, cpu_pct_str, scale=1)
        draw.rectangle([(0, 66), (W-1, 74)], outline=1)
        if pct > 0:
            fill_w = int((W - 2) * pct / 100)
            draw.rectangle([(1, 67), (fill_w, 73)], fill=1)

        # Barre RAM
        try:
            rpct = min(int(float(ram)), 100)
        except:
            rpct = 0
        draw_text(draw, 0, 78, "RAM", scale=1)
        ram_pct_str = f"{ram}%"
        draw_text(draw, W - text_w(ram_pct_str, 1) - 1, 78, ram_pct_str, scale=1)
        draw.rectangle([(0, 88), (W-1, 96)], outline=1)
        if rpct > 0:
            fill_w = int((W - 2) * rpct / 100)
            draw.rectangle([(1, 89), (fill_w, 95)], fill=1)

        device.display(img.transpose(Image.ROTATE_90))
        tick += 1
        time.sleep(1)


def main():
    print(f"[ICDisplay] I2C bus={I2C_BUS} addr=0x{I2C_ADDR:02X}")
    serial = i2c(port=I2C_BUS, address=I2C_ADDR)
    import os
    os.environ.setdefault('TZ', 'Europe/Luxembourg')
    import time as _time
    _time.tzset()
    device = sh1106(serial, width=128, height=64, rotate=0, h_flip=True)
    ha = HAClient()
    ha.start_polling()
    render(device, ha)

if __name__ == "__main__":
    main()
