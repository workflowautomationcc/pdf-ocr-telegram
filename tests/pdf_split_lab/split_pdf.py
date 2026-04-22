import argparse
import shutil
import subprocess
import sys
from pathlib import Path

import fitz  # PyMuPDF
from PIL import Image


LAB_DIR = Path(__file__).resolve().parent
INPUT_DIR = LAB_DIR / "input"
OUTPUT_DIR = LAB_DIR / "output"
TARGET_WIDTH = 2550


def parse_args():
    parser = argparse.ArgumentParser(description="Split a PDF into PNGs for local renderer testing.")
    parser.add_argument("--pdf", help="Optional PDF path. Defaults to the newest PDF in input/.")
    parser.add_argument(
        "--renderer",
        choices=["pymupdf", "pdftocairo", "mutool", "all"],
        default="pymupdf",
        help="Renderer to use.",
    )
    parser.add_argument(
        "--output-name",
        help="Optional output folder name. Defaults to the PDF filename without extension.",
    )
    parser.add_argument(
        "--keep-old",
        action="store_true",
        help="Keep old output instead of clearing the target folder first.",
    )
    return parser.parse_args()


def pick_pdf(pdf_arg):
    if pdf_arg:
        pdf_path = Path(pdf_arg).expanduser().resolve()
        if not pdf_path.exists():
            raise FileNotFoundError(f"PDF not found: {pdf_path}")
        return pdf_path

    pdf_files = sorted(
        (path for path in INPUT_DIR.glob("*.pdf") if path.is_file()),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )
    if not pdf_files:
        raise FileNotFoundError(f"No PDFs found in {INPUT_DIR}")
    return pdf_files[0]


def prepare_output_dir(base_dir, keep_old):
    if base_dir.exists() and not keep_old:
        shutil.rmtree(base_dir)
    base_dir.mkdir(parents=True, exist_ok=True)


def render_with_pymupdf(pdf_path, output_dir):
    doc = fitz.open(pdf_path)
    image_paths = []

    for i, page in enumerate(doc, start=1):
        scale = TARGET_WIDTH / page.rect.width
        pix = page.get_pixmap(matrix=fitz.Matrix(scale, scale), alpha=False)
        image = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
        out_path = output_dir / f"page_{i}.png"
        image.save(out_path, "PNG", dpi=(300, 300))
        image_paths.append(out_path)

    doc.close()
    return image_paths


def render_with_pdftocairo(pdf_path, output_dir):
    binary = shutil.which("pdftocairo")
    if not binary:
        raise RuntimeError("pdftocairo is not installed")

    prefix = output_dir / "page"
    cmd = [binary, "-png", "-r", "300", str(pdf_path), str(prefix)]
    subprocess.run(cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

    generated = sorted(output_dir.glob("page-*.png"))
    if not generated:
        raise RuntimeError("pdftocairo produced no PNG files")

    image_paths = []
    for i, src in enumerate(generated, start=1):
        dst = output_dir / f"page_{i}.png"
        src.rename(dst)
        image_paths.append(dst)
    return image_paths


def render_with_mutool(pdf_path, output_dir):
    binary = shutil.which("mutool")
    if not binary:
        raise RuntimeError("mutool is not installed")

    pattern = output_dir / "page_%d.png"
    cmd = [binary, "draw", "-o", str(pattern), "-r", "300", str(pdf_path)]
    subprocess.run(cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

    image_paths = sorted(output_dir.glob("page_*.png"))
    if not image_paths:
        raise RuntimeError("mutool produced no PNG files")
    return image_paths


def render(pdf_path, renderer, output_dir):
    output_dir.mkdir(parents=True, exist_ok=True)

    if renderer == "pymupdf":
        return render_with_pymupdf(pdf_path, output_dir)
    if renderer == "pdftocairo":
        return render_with_pdftocairo(pdf_path, output_dir)
    if renderer == "mutool":
        return render_with_mutool(pdf_path, output_dir)
    raise ValueError(f"Unsupported renderer: {renderer}")


def main():
    args = parse_args()
    pdf_path = pick_pdf(args.pdf)
    output_name = args.output_name or pdf_path.stem
    base_output_dir = OUTPUT_DIR / output_name

    prepare_output_dir(base_output_dir, args.keep_old)

    renderers = ["pymupdf", "pdftocairo", "mutool"] if args.renderer == "all" else [args.renderer]

    print(f"PDF: {pdf_path}")
    print(f"Output: {base_output_dir}")

    for renderer in renderers:
        renderer_output_dir = base_output_dir / renderer
        renderer_output_dir.mkdir(parents=True, exist_ok=True)
        image_paths = render(pdf_path, renderer, renderer_output_dir)
        print(f"[{renderer}] wrote {len(image_paths)} page(s) to {renderer_output_dir}")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)
