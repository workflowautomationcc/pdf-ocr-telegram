from pypdf import PdfReader

reader = PdfReader("data/test/sample.pdf")

print(reader.trailer["/Root"].get("/AcroForm"))