from pypdf import PdfReader


def inspect_pdf_fields(pdf_path):
    reader = PdfReader(pdf_path)

    fields = reader.get_fields()

    if not fields:
        print("No form fields found.")
        return

    print("=== PDF FORM FIELDS ===")

    for field_name, field_data in fields.items():
        value = field_data.get("/V", "")
        print(f"Field: {field_name} | Value: {value}")


if __name__ == "__main__":
    # change this to a real PDF path when testing
    sample_pdf = "data/test/sample.pdf"
    inspect_pdf_fields(sample_pdf)