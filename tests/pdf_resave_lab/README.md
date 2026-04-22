# PDF Resave Lab

Isolated test area for automatic PDF rewrite/resave before split.

## Structure

- `input/` - drop source PDFs here
- `output/` - generated PDFs and PNGs land here
- `scripts/` - lab runners and resavers

## Usage

Run the newest PDF from `input/`:

```bash
python3 tests/pdf_resave_lab/scripts/run_resave_test.py --resaver mutool_clean
```

Run a specific PDF:

```bash
python3 tests/pdf_resave_lab/scripts/run_resave_test.py --pdf "/full/path/to/file.pdf" --resaver mutool_clean
```

Current behavior:

- saves the original PDF into the output run folder
- runs the selected automatic resaver to produce `resaved.pdf`
- splits both PDFs for comparison

Output format:

```text
tests/pdf_resave_lab/output/<run_name>/
  original.pdf
  resaved.pdf
  original_split/page_1.png
  resaved_split/page_1.png
```
