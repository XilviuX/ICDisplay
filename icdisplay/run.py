#!/usr/bin/env python3
"""
ICDisplay — Home Assistant OLED Monitor
SSD1306 128x64 via I2C
"""

import os
import time
import requests
import threading
from datetime import datetime
from PIL import Image, ImageDraw, ImageFont
from luma.core.interface.serial import i2c
from luma.oled.device import ssd1306, sh1106

# ── Config ────────────────────────────────────────────────────────────────────
HA_URL          = os.environ.get("HA_URL",         "http://172.16.137.11:8123")
HA_TOKEN        = os.environ.get("HA_TOKEN",       "")
I2C_BUS         = int(os.environ.get("I2C_BUS",    "1"))
I2C_ADDRESS     = int(os.environ.get("I2C_ADDRESS","0x3C"), 16)
SENSOR_TEMP     = os.environ.get("SENSOR_TEMP",    "sensor.temperature_interieure_moyenne")
SENSOR_HUMIDITY = os.environ.get("SENSOR_HUMIDITY","sensor.humidite_interieure_moyenne")

REFRESH_SENSORS = 30
FRAME_DELAY     = 0.05

W, H = 128, 64

# ── Fonts ─────────────────────────────────────────────────────────────────────
def load_font(size, bold=False):
    paths = [
        f"/usr/share/fonts/dejavu/DejaVuSans{'Bold' if bold else ''}.ttf",
        f"/usr/share/fonts/truetype/dejavu/DejaVuSans{'Bold' if bold else ''}.ttf",
        f"/usr/share/fonts/dejavu/DejaVuSans{'Bold' if bold else ''}.ttf",
    ]
    for p in paths:
        if os.path.exists(p):
            try:
                return ImageFont.truetype(p, size)
            except Exception:
                pass
    return ImageFont.load_default()

# ── HA Client ─────────────────────────────────────────────────────────────────
class HAClient:
    def __init__(self):
        self.headers = {
            "Authorization": f"Bearer {HA_TOKEN}",
            "Content-Type": "application/json",
        }
        self.temp     = "--"
        self.humidity = "--"
        self.online   = False
        self._lock    = threading.Lock()

    def fetch(self):
        try:
            r = requests.get(f"{HA_URL}/api/", headers=self.headers, timeout=5)
            if r.status_code != 200:
                with self._lock:
                    self.online = False
                return

            def get_state(entity_id):
                resp = requests.get(
                    f"{HA_URL}/api/states/{entity_id}",
                    headers=self.headers, timeout=5
                )
                if resp.status_code == 200:
                    val = resp.json().get("state", "--")
                    try:
                        return f"{float(val):.1f}"
                    except ValueError:
                        return val
                return "--"

            t = get_state(SENSOR_TEMP)
            h = get_state(SENSOR_HUMIDITY)

            with self._lock:
                self.temp     = t
                self.humidity = h
                self.online   = True

        except Exception as e:
            print(f"[HA] Erreur: {e}")
            with self._lock:
                self.online = False

    def start_polling(self):
        def loop():
            while True:
                self.fetch()
                time.sleep(REFRESH_SENSORS)
        threading.Thread(target=loop, daemon=True).start()

    def get(self):
        with self._lock:
            return self.temp, self.humidity, self.online

# ── Renderer ──────────────────────────────────────────────────────────────────
class OLEDRenderer:
    def __init__(self, device):
        self.device    = device
        self.tick      = 0
        self.pulse     = 0.0
        self.pulse_dir = 1

        self.font_big   = load_font(22, bold=True)
        self.font_med   = load_font(11, bold=True)
        self.font_small = load_font(9)
        self.font_tiny  = load_font(8)

    def _update_pulse(self):
        self.pulse += 0.05 * self.pulse_dir
        if self.pulse >= 1.0:
            self.pulse = 1.0
            self.pulse_dir = -1
        elif self.pulse <= 0.0:
            self.pulse = 0.0
            self.pulse_dir = 1

    def _draw_frame(self, temp, humidity, online):
        img  = Image.new("1", (W, H), 0)
        draw = ImageDraw.Draw(img)
        now  = datetime.now()

        # ── Ligne 1 : titre + statut ──────────────────────────────────────
        draw.text((2, 0), "loulous.lu", font=self.font_small, fill=1)

        if online:
            # Point pulsant
            r = max(2, int(2 + self.pulse * 2))
            draw.ellipse([(W-12-r, 3-r), (W-12+r, 3+r)], fill=1)
            draw.text((W-10, 0), "OK", font=self.font_tiny, fill=1)
        else:
            draw.text((W-22, 0), "OFF", font=self.font_tiny, fill=1)

        # Séparateur
        draw.line([(0, 12), (W, 12)], fill=1, width=1)

        # ── Ligne 2 : temp + humidité ─────────────────────────────────────
        draw.text((2, 14), f"{temp}°C", font=self.font_med, fill=1)
        
        hum_text = f"{humidity}%"
        bbox = draw.textbbox((0, 0), hum_text, font=self.font_med)
        hum_w = bbox[2] - bbox[0]
        draw.text((W - hum_w - 2, 14), hum_text, font=self.font_med, fill=1)

        # Icônes texte
        draw.text((2, 26), "temp", font=self.font_tiny, fill=1)
        draw.text((W - 22, 26), "hum", font=self.font_tiny, fill=1)

        # Séparateur
        draw.line([(0, 35), (W, 35)], fill=1, width=1)

        # ── Ligne 3 : heure ───────────────────────────────────────────────
        hour = now.strftime("%H:%M")
        bbox = draw.textbbox((0, 0), hour, font=self.font_big)
        w = bbox[2] - bbox[0]
        draw.text(((W - w) // 2, 37), hour, font=self.font_big, fill=1)

        # Secondes clignotantes
        if self.tick % 20 < 10:
            sec = now.strftime(":%S")
            draw.text((W - 20, 56), sec, font=self.font_tiny, fill=1)

        return img

    def render_loop(self, ha_client):
        print("[ICDisplay] Démarrage du rendu...")
        while True:
            temp, humidity, online = ha_client.get()
            self._update_pulse()
            img = self._draw_frame(temp, humidity, online)
            self.device.display(img)
            self.tick += 1
            time.sleep(FRAME_DELAY)

# ── Splash ────────────────────────────────────────────────────────────────────
def splash(device):
    img  = Image.new("1", (W, H), 0)
    draw = ImageDraw.Draw(img)
    font = load_font(12, bold=True)
    font2 = load_font(9)
    draw.text((20, 16), "ICDisplay", font=font, fill=1)
    draw.text((22, 34), "Démarrage...", font=font2, fill=1)
    device.display(img)
    time.sleep(2)

# ── Main ──────────────────────────────────────────────────────────────────────
def main():
    print(f"[ICDisplay] I2C bus={I2C_BUS} addr=0x{I2C_ADDRESS:02X}")
    serial = i2c(port=I2C_BUS, address=I2C_ADDRESS)
    device = ssd1306(serial, width=W, height=H, rotate=0, h_flip=True)

    splash(device)

    ha = HAClient()
    ha.start_polling()

    OLEDRenderer(device).render_loop(ha)

if __name__ == "__main__":
    main()
