import sys
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[3]
sys.path.append(str(ROOT_DIR))

from processors.pdf.pdf_splitter import split_pdf_to_images


INBOX_DIR = ROOT_DIR / "template_setup" / "batch_setup" / "inbox_pdfs"
OUTPUT_DIR = ROOT_DIR / "template_setup" / "batch_setup" / "png_batches"


def iter_pdf_files():
    if not INBOX_DIR.exists():
        return []
    return sorted(path for path in INBOX_DIR.iterdir() if path.is_file() and path.suffix.lower() == ".pdf")


def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    pdf_files = iter_pdf_files()

    if not pdf_files:
        print(f"No PDF files found in {INBOX_DIR}")
        return

    for pdf_path in pdf_files:
        target_dir = OUTPUT_DIR / pdf_path.stem
        print(f"Splitting: {pdf_path.name}")
        split_pdf_to_images(str(pdf_path), str(target_dir))
        print(f"Saved pages to: {target_dir}")

    print("Batch split complete.")


if __name__ == "__main__":
    main()
