import os
from PIL import Image


def main(png_job_folder):
    pages = []

    # page 1
    page1_path = os.path.join(png_job_folder, "page_1.png")
    pages.append(page1_path)

    # page 2+
    i = 2
    while True:
        path = os.path.join(png_job_folder, f"page_{i}.png")
        if not os.path.exists(path):
            break
        pages.append(path)
        i += 1

    images = [Image.open(p).convert("RGB") for p in pages]

    first = images[0]
    rest = images[1:]

    dpi = first.info.get("dpi", (300, 300))

    output_path = os.path.join(png_job_folder, "final.pdf")

    first.save(
        output_path,
        save_all=True,
        append_images=rest,
        resolution=dpi[0]
    )