from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent
OUTPUT = ROOT / "assets" / "icon.png"
SIZE = 512


def main() -> None:
    image = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle((28, 28, 484, 484), radius=118, fill="#ef5a35")

    candidates = [
        "/usr/share/fonts/google-noto/NotoSans-Bold.ttf",
        "/usr/share/fonts/noto/NotoSans-Bold.ttf",
        "/usr/share/fonts/dejavu-sans-fonts/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/dejavu/DejaVuSans-Bold.ttf",
    ]
    font = next(
        (ImageFont.truetype(path, 285) for path in candidates if Path(path).exists()),
        ImageFont.load_default(size=285),
    )
    bounds = draw.textbbox((0, 0), "D", font=font)
    width = bounds[2] - bounds[0]
    height = bounds[3] - bounds[1]
    draw.text(
        ((SIZE - width) / 2 - bounds[0], (SIZE - height) / 2 - bounds[1] - 7),
        "D",
        fill="white",
        font=font,
    )
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    image.save(OUTPUT, "PNG", optimize=True)
    print(OUTPUT)


if __name__ == "__main__":
    main()
