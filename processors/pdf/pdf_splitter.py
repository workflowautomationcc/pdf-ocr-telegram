import os
import fitz  # PyMuPDF
from PIL import Image

def split_pdf_to_images(pdf_path, output_dir):
    os.makedirs(output_dir, exist_ok=True)

    TARGET_WIDTH = 2550
    image_paths = []

    doc = fitz.open(pdf_path)
    for i, page in enumerate(doc):
        scale = TARGET_WIDTH / page.rect.width
        mat = fitz.Matrix(scale, scale)
        pix = page.get_pixmap(matrix=mat, alpha=False)

        image = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
        path = os.path.join(output_dir, f"page_{i+1}.png")
        image.save(path, "PNG", dpi=(300, 300))
        image_paths.append(path)

    doc.close()
    return image_paths
