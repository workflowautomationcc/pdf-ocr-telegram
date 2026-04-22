# PDF Fix Lab

Isolated test area for template-specific PDF preprocessing before split.

## Purpose

Use this lab to test:

1. original PDF
2. template-specific fixed PDF
3. split output for both

No production code is touched here.

## Structure

- `input/` - drop source PDFs here
- `output/` - generated PDFs and PNGs land here
- `scripts/` - lab runners and template-specific fixers

## Usage

Run the newest PDF from `input/` with a named fixer:

```bash
python3 tests/pdf_fix_lab/scripts/run_fix_test.py --template arl_transport
```

Run a specific PDF:

```bash
python3 tests/pdf_fix_lab/scripts/run_fix_test.py --pdf "/full/path/to/file.pdf" --template arl_transport
```

Current behavior:

- saves the original PDF into the output run folder
- runs the selected fixer to produce `fixed.pdf`
- splits both PDFs with PyMuPDF for comparison

Output format:

```text
tests/pdf_fix_lab/output/<run_name>/
  original.pdf
  fixed.pdf
  original_split/page_1.png
  fixed_split/page_1.png
```
