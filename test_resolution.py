import os
import fitz
from PIL import Image

INPUT_DIR = "test_res/input"
OUTPUT_DIR = "test_res/output"

def split(pdf_path, out_dir, target_width):
    os.makedirs(out_dir, exist_ok=True)
    doc = fitz.open(pdf_path)
    for i, page in enumerate(doc):
        scale = target_width / page.rect.width
        mat = fitz.Matrix(scale, scale)
        pix = page.get_pixmap(matrix=mat, alpha=False)
        image = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
        path = os.path.join(out_dir, f"page_{i+1}.png")
        image.save(path, "PNG")
        print(f"  {path} → {image.size}")
    doc.close()

def combine(out_dir):
    pages = []
    i = 1
    while True:
        p = os.path.join(out_dir, f"page_{i}.png")
        if not os.path.exists(p):
            break
        pages.append(p)
        i += 1
    images = [Image.open(p).convert("RGB") for p in pages]
    pdf_path = os.path.join(out_dir, "final.pdf")
    images[0].save(pdf_path, save_all=True, append_images=images[1:], resolution=300)
    size_mb = os.path.getsize(pdf_path) / 1024 / 1024
    print(f"  PDF → {pdf_path} ({size_mb:.1f} MB)")

pdfs = [f for f in os.listdir(INPUT_DIR) if f.endswith(".pdf")]
if not pdfs:
    print("No PDFs found in test_res/input/")
    exit(1)

pdf_path = os.path.join(INPUT_DIR, pdfs[0])
print(f"Input: {pdf_path}\n")

for width in [2550, 5100, 7650, 10200]:
    label = {2550: "2550 (1x)", 5100: "5100 (2x)", 7650: "7650 (3x)", 10200: "10200 (4x)"}[width]
    print(f"--- {label} ---")
    out_dir = os.path.join(OUTPUT_DIR, str(width))
    split(pdf_path, out_dir, width)
    combine(out_dir)
    print()

print("Done. Check test_res/output/")
