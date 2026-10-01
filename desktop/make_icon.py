"""Generate a placeholder app icon ("DG" on the brand blue). Replace with a real one anytime."""

import sys

from PIL import Image, ImageDraw, ImageFont

BRAND = (37, 99, 235)  # tailwind brand-600


def make(size: int) -> Image.Image:
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    draw.rounded_rectangle([0, 0, size - 1, size - 1], radius=size // 5, fill=BRAND)
    try:
        font = ImageFont.truetype("segoeuib.ttf", int(size * 0.46))
    except OSError:
        font = ImageFont.load_default()
    draw.text((size / 2, size / 2), "DG", fill="white", font=font, anchor="mm")
    return img


if __name__ == "__main__":
    out = sys.argv[1] if len(sys.argv) > 1 else "icon.ico"
    make(256).save(out, sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
    print(f"wrote {out}")
