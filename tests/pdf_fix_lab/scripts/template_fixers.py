import shutil


def arl_transport_fixer(input_pdf, output_pdf):
    shutil.copy2(input_pdf, output_pdf)


FIXERS = {
    "arl_transport": arl_transport_fixer,
}
