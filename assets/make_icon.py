"""アプリアイコン(gagaku.ico / gagaku.png)を生成する。要 Pillow。"""
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

HERE = Path(__file__).parent
S = 256

img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
d = ImageDraw.Draw(img)
d.rounded_rectangle((8, 8, S - 8, S - 8), radius=44, fill=(158, 32, 28), outline=(212, 175, 55), width=10)
d.rounded_rectangle((26, 26, S - 26, S - 26), radius=30, outline=(212, 175, 55, 150), width=3)
font = ImageFont.truetype(r"C:\Windows\Fonts\yumindb.ttf", 170)
d.text((S / 2, S / 2 + 4), "雅", font=font, fill=(250, 244, 230), anchor="mm")

img.save(HERE / "gagaku.png")
img.save(HERE / "gagaku.ico", sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
print("ok")
