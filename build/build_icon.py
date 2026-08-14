"""Генерирует build\\AtyrauArmwrestling.ico из assets\\logo-atyrau-city.png.

Вызывается автоматически из build_installer.bat (и создаётся только для
сборки; сам файл .ico не коммитится в git).
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", "desktop-app"))  # desktop-app/
SRC = os.path.join(ROOT, "assets", "logo-atyrau-city.png")
DST = os.path.join(HERE, "AtyrauArmwrestling.ico")

img = Image.open(SRC).convert("RGBA")
img = img.resize((256, 256), Image.LANCZOS)
img.save(DST, format="ICO", sizes=[(16, 16), (32, 32), (48, 48),
                                   (64, 64), (128, 128), (256, 256)])
print("ICO:", DST, os.path.getsize(DST), "bytes")