import argparse
import shutil
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT_DIR))

from processors.pdf.pdf_splitter import split_pdf_to_images
from tests.pdf_fix_lab.scripts.template_fixers import FIXERS


LAB_DIR = Path(__file__).resolve().parents[1]
INPUT_DIR = LAB_DIR / "input"
OUTPUT_DIR = LAB_DIR / "output"


def parse_args():
    parser = argparse.ArgumentParser(description="Run a template-specific PDF fix test before split.")
    parser.add_argument("--pdf", help="Optional PDF path. Defaults to the newest PDF in input/.")
    parser.add_argument("--template", required=True, help="Template fixer key, e.g. arl_transport")
    parser.add_argument("--output-name", help="Optional output folder name.")
    parser.add_argument("--keep-old", action="store_true", help="Keep old output instead of clearing it first.")
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


def main():
    args = parse_args()
    pdf_path = pick_pdf(args.pdf)

    fixer = FIXERS.get(args.template)
    if fixer is None:
        available = ", ".join(sorted(FIXERS))
        raise ValueError(f"Unknown template fixer '{args.template}'. Available: {available}")

    run_name = args.output_name or f"{pdf_path.stem}_{args.template}"
    run_dir = OUTPUT_DIR / run_name
    prepare_output_dir(run_dir, args.keep_old)

    original_pdf = run_dir / "original.pdf"
    fixed_pdf = run_dir / "fixed.pdf"

    shutil.copy2(pdf_path, original_pdf)
    fixer(str(original_pdf), str(fixed_pdf))

    original_split_dir = run_dir / "original_split"
    fixed_split_dir = run_dir / "fixed_split"

    split_pdf_to_images(str(original_pdf), str(original_split_dir))
    split_pdf_to_images(str(fixed_pdf), str(fixed_split_dir))

    print(f"Source: {pdf_path}")
    print(f"Run: {run_dir}")
    print(f"Original PDF: {original_pdf}")
    print(f"Fixed PDF: {fixed_pdf}")
    print(f"Original PNGs: {original_split_dir}")
    print(f"Fixed PNGs: {fixed_split_dir}")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)
