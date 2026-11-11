"""Render the original integration icon; this is not a manufacturer's trademark."""

from pathlib import Path

from PIL import Image, ImageDraw


def generate():
    folder = Path(__file__).resolve().parents[1] / "custom_components/yutai_wifi/brand"
    folder.mkdir(exist_ok=True)
    canvas = Image.new("RGBA", (1024, 1024), (0, 0, 0, 0))
    draw = ImageDraw.Draw(canvas)
    draw.ellipse((32, 32, 992, 992), fill="#00796B", outline="#FFFFFF", width=24)
    draw.rounded_rectangle((345, 190, 415, 420), radius=25, fill="#FFFFFF")
    draw.rounded_rectangle((609, 190, 679, 420), radius=25, fill="#FFFFFF")
    draw.rounded_rectangle((270, 365, 754, 720), radius=100, fill="#FFFFFF")
    draw.rounded_rectangle((474, 665, 550, 848), radius=30, fill="#FFFFFF")
    draw.polygon(((527, 420), (412, 565), (498, 565), (464, 665), (622, 505), (530, 505)), fill="#00796B")
    for size, name in ((256, "icon.png"), (512, "icon@2x.png")):
        canvas.resize((size, size), Image.Resampling.LANCZOS).save(folder / name)
    print("Generated two original, metadata-free integration icons")


if __name__ == "__main__":
    generate()
