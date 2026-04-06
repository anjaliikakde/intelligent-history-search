from PIL import Image
from pathlib import Path

BASE_DIR = Path(__file__).parent

SOURCE_IMAGE = BASE_DIR / "icon.png"

sizes = [16, 48, 128]

img = Image.open(SOURCE_IMAGE)

for size in sizes:
    resized = img.resize((size, size), Image.LANCZOS)
    output_file = BASE_DIR / f"icon{size}.png"
    resized.save(output_file)

print("Icons created successfully.")