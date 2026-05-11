#!/usr/bin/env python3
"""
ICDisplay — Home Assistant OLED Monitor
SH1107 128x128 via I2C
"""

import os
import time
import json
import requests
import threading
from datetime import datetime
from PIL import Image, ImageDraw, ImageFont
from luma.core.interface.serial import i2c
from luma.oled.device import sh1107

# ── Config (injected by HAOS add-on options) ─────────────────────────────────
HA_URL          = os.environ.get("HA_URL",         "http://172.16.137.11:8123")
HA_TOKEN        = os.environ.get("HA_TOKEN",       "")
I2C_BUS         = int(os.environ.get("I2C_BUS",    "1"))
I2C_ADDRESS     = int(os.environ.get("I2C_ADDRESS","0x3C"), 16)
SENSOR_TEMP     = os.environ.get("SENSOR_TEMP",    "sensor.temperature_interieure_moyenne")
SENSOR_HUMIDITY = os.environ.get("SENSOR_HUMIDITY","sensor.humidite_interieure_moyenne")

REFRESH_SENSORS = 30   # secondes entre deux appels API
FRAME_DELAY     = 0.05 # ~20fps pour l'animation

# ── Fonts ─────────────────────────────────────────────────────────────────────
def load_font(size, bold=False):
    """Tente de charger une fonte TTF, fallback sur la fonte bitmap PIL."""
    paths = [
        f"/fonts/DejaVuSans{'Bold' if bold else ''}.ttf",
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

# ── HA API ────────────────────────────────────────────────────────────────────
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
            r = requests.get(
                f"{HA_URL}/api/",
                headers=self.headers,
                timeout=5
            )
            if r.status_code != 200:
                with self._lock:
                    self.online = False
                return

            def get_state(entity_id):
                resp = requests.get(
                    f"{HA_URL}/api/states/{entity_id}",
                    headers=self.headers,
                    timeout=5
                )
                if resp.status_code == 200:
                    data = resp.json()
                    val = data.get("state", "--")
                    # Arrondi à 1 décimale si c'est un float
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
            print(f"[HA] Erreur fetch: {e}")
            with self._lock:
                self.online = False

    def start_polling(self):
        def loop():
            while True:
                self.fetch()
                time.sleep(REFRESH_SENSORS)
        t = threading.Thread(target=loop, daemon=True)
        t.start()

    def get(self):
        with self._lock:
            return self.temp, self.humidity, self.online

# ── Renderer ──────────────────────────────────────────────────────────────────
class OLEDRenderer:
    W, H = 128, 128

    def __init__(self, device):
        self.device   = device
        self.tick     = 0          # frame counter pour animations
        self.pulse    = 0.0        # 0.0 → 1.0 → 0.0 heartbeat
        self.pulse_dir = 1

        # Fontes
        self.font_big   = load_font(28, bold=True)
        self.font_med   = load_font(14, bold=True)
        self.font_small = load_font(11)
        self.font_tiny  = load_font(9)

    def _update_pulse(self):
        """Fait pulser un point entre 0 et 1."""
        speed = 0.04
        self.pulse += speed * self.pulse_dir
        if self.pulse >= 1.0:
            self.pulse = 1.0
            self.pulse_dir = -1
        elif self.pulse <= 0.0:
            self.pulse = 0.0
            self.pulse_dir = 1

    def _draw_frame(self, temp, humidity, online):
        img  = Image.new("1", (self.W, self.H), 0)
        draw = ImageDraw.Draw(img)

        now  = datetime.now()
        hour = now.strftime("%H:%M")
        sec  = now.strftime("%S")

        # ── Titre ──────────────────────────────────────────────────────────
        draw.text((4, 2), "loulous.lu", font=self.font_small, fill=1)

        # Ligne de séparation
        draw.line([(0, 16), (128, 16)], fill=1, width=1)

        # ── Statut online ──────────────────────────────────────────────────
        if online:
            # Cercle pulsant
            r = int(4 + self.pulse * 3)
            cx, cy = 10, 28
            draw.ellipse([(cx-r, cy-r), (cx+r, cy+r)], fill=1)
            draw.text((20, 22), "EN LIGNE", font=self.font_small, fill=1)
        else:
            draw.text((4, 22), "HORS LIGNE", font=self.font_small, fill=1)

        # Ligne de séparation
        draw.line([(0, 38), (128, 38)], fill=1, width=1)

        # ── Température ────────────────────────────────────────────────────
        draw.text((4, 42), "TEMP", font=self.font_tiny, fill=1)
        draw.text((4, 52), f"{temp}°C", font=self.font_med, fill=1)

        # ── Humidité ───────────────────────────────────────────────────────
        draw.text((70, 42), "HUMID", font=self.font_tiny, fill=1)
        draw.text((70, 52), f"{humidity}%", font=self.font_med, fill=1)

        # Ligne de séparation
        draw.line([(0, 72), (128, 72)], fill=1, width=1)

        # ── Heure (grande) ─────────────────────────────────────────────────
        # Calcul centrage horizontal
        bbox = draw.textbbox((0, 0), hour, font=self.font_big)
        w = bbox[2] - bbox[0]
        x = (self.W - w) // 2
        draw.text((x, 78), hour, font=self.font_big, fill=1)

        # Secondes en bas à droite
        draw.text((100, 116), f":{sec}", font=self.font_tiny, fill=1)

        # Petits pixels animés en bas à gauche (activité)
        if online:
            dot_x = (self.tick // 4) % 12
            for i in range(3):
                bx = 4 + i * 6
                by = 118
                if i == dot_x % 3:
                    draw.rectangle([(bx, by), (bx+4, by+4)], fill=1)
                else:
                    draw.rectangle([(bx, by), (bx+4, by+4)], outline=1)

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

# ── Écran de démarrage ────────────────────────────────────────────────────────
def splash(device):
    img  = Image.new("1", (128, 128), 0)
    draw = ImageDraw.Draw(img)
    font = load_font(14, bold=True)
    font2 = load_font(10)
    draw.text((14, 40), "ICDisplay", font=font, fill=1)
    draw.text((18, 60), "Démarrage...", font=font2, fill=1)
    device.display(img)
    time.sleep(2)

# ── Main ──────────────────────────────────────────────────────────────────────
def main():
    print(f"[ICDisplay] Connexion I2C bus={I2C_BUS} addr=0x{I2C_ADDRESS:02X}")
    serial = i2c(port=I2C_BUS, address=I2C_ADDRESS)
    device = sh1107(serial, width=128, height=128, rotate=0)

    splash(device)

    ha = HAClient()
    ha.start_polling()

    renderer = OLEDRenderer(device)
    renderer.render_loop(ha)

if __name__ == "__main__":
    main()
