"""Export a Markdown document of docs/ to PDF with Edge, as the first DELIVERY_PLAN.pdf was made.

    uv run python docs/build_pdf.py [DELIVERY_PLAN]
"""

import subprocess
import sys
import tempfile
from pathlib import Path

import markdown

DOCS = Path(__file__).resolve().parent
EDGE = Path(r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe")
STYLE = """
@page { size: A4; margin: 16mm 14mm; }
body { font: 10.5pt/1.45 "Segoe UI", system-ui, sans-serif; color: #14212b; }
h1 { font-size: 20pt; margin: 0 0 10pt; } h2 { font-size: 14pt; margin: 18pt 0 6pt; } h3 { font-size: 12pt; }
table { border-collapse: collapse; width: 100%; margin: 6pt 0 10pt; font-size: 9pt; page-break-inside: auto; }
th, td { border: 1px solid #c9d2d9; padding: 3pt 5pt; vertical-align: top; text-align: left; }
th { background: #eef2f5; } tr { page-break-inside: avoid; }
code { font: 9pt Consolas, monospace; background: #f4f6f8; padding: 0 2pt; }
a { color: #2457c5; text-decoration: none; }
"""


def writable(path: Path) -> bool:
    try:
        with open(path, "ab"):
            return True
    except PermissionError:
        return False


def main(name: str = "DELIVERY_PLAN") -> None:
    source = DOCS / f"{name}.md"
    if (DOCS / f"{name}.pdf").exists() and not writable(DOCS / f"{name}.pdf"):
        sys.exit(f"{name}.pdf is open in another program; close it and run again")
    body = markdown.markdown(source.read_text(encoding="utf-8"), extensions=["tables", "sane_lists"])
    title = source.read_text(encoding="utf-8").splitlines()[0].lstrip("# ").strip()
    html = f"<!doctype html><html><head><meta charset='utf-8'><title>{title}</title><style>{STYLE}</style></head><body>{body}</body></html>"
    with tempfile.TemporaryDirectory() as tmp:
        page = Path(tmp) / f"{name}.html"
        page.write_text(html, encoding="utf-8")
        out = DOCS / f"{name}.pdf"
        before = out.stat().st_mtime if out.exists() else 0
        # A separate profile, or Edge hands the job to a running window and exits without printing.
        subprocess.run([str(EDGE), "--headless=new", "--disable-gpu", "--no-pdf-header-footer",
                        f"--user-data-dir={Path(tmp) / 'edge'}", f"--print-to-pdf={out}", page.as_uri()],
                       check=True, capture_output=True, timeout=120)
        if not out.exists() or out.stat().st_mtime == before:
            raise RuntimeError(f"Edge did not write {out}")
    print(out)


if __name__ == "__main__":
    main(*sys.argv[1:])
