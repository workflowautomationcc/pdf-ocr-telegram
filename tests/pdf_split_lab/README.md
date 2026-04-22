# PDF Split Lab

Isolated local test area for PDF-to-PNG splitting only.

## Structure

- `input/` - drop PDFs here
- `output/` - generated PNGs land here
- `split_pdf.py` - local split runner

## Usage

Run the newest PDF from `input/`:

```bash
python3 tests/pdf_split_lab/split_pdf.py --renderer pymupdf
```

Run a specific PDF:

```bash
python3 tests/pdf_split_lab/split_pdf.py --pdf tests/pdf_split_lab/input/your_file.pdf --renderer all
```

Available renderers:

- `pymupdf`
- `pdftocairo`
- `mutool`
- `all`

Output format:

```text
tests/pdf_split_lab/output/<pdf_name>/<renderer>/page_1.png
```
