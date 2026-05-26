#!/usr/bin/env python3
from PIL import Image, ImageDraw, ImageFont
from luma.core.interface.serial import i2c
from luma.oled.device import ssd1306
import time, os

serial = i2c(port=1, address=0x3C)
device = ssd1306(serial, width=128, height=64, rotate=0, h_flip=True)

font = ImageFont.truetype("/usr/share/fonts/dejavu/DejaVuSans.ttf", 14)

while True:
    img = Image.new("1", (128, 64), 0)
    draw = ImageDraw.Draw(img)
    draw.text((2, 2),  "HA actif", font=font, fill=1)
    draw.text((2, 20), time.strftime("%H:%M:%S"), font=font, fill=1)
    draw.text((2, 40), "loulous.lu", font=font, fill=1)
    device.display(img)
    time.sleep(1)
