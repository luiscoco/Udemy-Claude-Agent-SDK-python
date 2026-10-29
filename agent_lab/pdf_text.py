"""Extract text from one bounded PDF in its own process: python -m agent_lab.pdf_text < file.pdf

The Publishing Studio runs this with a timeout, so a hostile or huge PDF cannot stall the app.
"""

import io
import sys

MAX_BYTES = 5_000_000
MAX_PAGES = 80
MAX_CHARS = 50_000


def main() -> None:
    from pypdf import PdfReader
    from pypdf.errors import PdfReadError

    data = sys.stdin.buffer.read(MAX_BYTES + 1)
    if len(data) > MAX_BYTES or not data.startswith(b"%PDF-"):
        raise SystemExit("Choose a real PDF under 5 MB.")
    try:
        reader = PdfReader(io.BytesIO(data))
        if reader.is_encrypted:
            raise SystemExit("Encrypted PDFs are not supported.")
        if len(reader.pages) > MAX_PAGES:
            raise SystemExit(f"The PDF has more than {MAX_PAGES} pages.")
        text = "\n".join(page.extract_text() or "" for page in reader.pages)
    except (PdfReadError, ValueError, KeyError, TypeError) as exc:
        raise SystemExit("This PDF cannot be read.") from exc
    sys.stdout.buffer.write(text.strip()[:MAX_CHARS].encode("utf-8"))


if __name__ == "__main__":
    main()
