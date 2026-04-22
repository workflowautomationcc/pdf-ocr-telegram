import shutil
import subprocess


def mutool_clean_resave(input_pdf, output_pdf):
    binary = shutil.which("mutool")
    if not binary:
        raise RuntimeError("mutool is not installed")

    cmd = [binary, "clean", "-d", input_pdf, output_pdf]
    subprocess.run(cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)


RESAVERS = {
    "mutool_clean": mutool_clean_resave,
}
