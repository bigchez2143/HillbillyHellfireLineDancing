"""Build the instructor one-pager PDF from release/instructor-one-pager.md.

The markdown file is the editable source. The PDF is what ships in the
portable folder, beside Launch Line Dance Creator.bat. No network access.
"""
from __future__ import annotations

import argparse
from io import BytesIO
from pathlib import Path
import re
import shutil
from xml.sax.saxutils import escape


ROOT = Path(__file__).resolve().parents[1]
RELEASE_DIR = ROOT / "release"
SOURCE_NAME = "instructor-one-pager.md"
PDF_NAME = "Instructor one-pager.pdf"
SITE = "hillbillyhellfire.com"
FREEWARE_LINE = "Freeware from Hillbilly Hellfire"


def source_path():
    return RELEASE_DIR / SOURCE_NAME


def pdf_path():
    return RELEASE_DIR / PDF_NAME


def parse_markdown(text):
    """A small subset: one title, ## headings, and blank-line paragraphs."""
    if text.startswith("\ufeff"):
        text = text[1:]
    title = ""
    blocks = []
    paragraph = []

    def flush():
        body = " ".join(part.strip() for part in paragraph).strip()
        paragraph.clear()
        if body:
            blocks.append(("p", body))

    for raw in text.replace("\r\n", "\n").split("\n"):
        line = raw.strip()
        if line.startswith("# "):
            flush()
            if title:
                raise ValueError("The guide needs a single title.")
            title = line[2:].strip()
        elif line.startswith("## "):
            flush()
            heading = line[3:].strip()
            if not heading:
                raise ValueError("A heading is empty.")
            blocks.append(("h", heading))
        elif not line:
            flush()
        elif line.startswith("#"):
            raise ValueError("Use # for the title and ## for each step.")
        else:
            paragraph.append(line)
    flush()
    if not title:
        raise ValueError("The guide needs a title line starting with #.")
    if not blocks:
        raise ValueError("The guide has no steps.")
    return title, blocks


def _markup(text):
    escaped = escape(text)
    return re.sub(r"\*\*([^*]+)\*\*", r"<b>\1</b>", escaped)


def _fonts():
    import os
    import reportlab
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    directory = os.path.join(os.path.dirname(reportlab.__file__), "fonts")
    for name, filename in (("DanceSans", "Vera.ttf"), ("DanceSansBold", "VeraBd.ttf")):
        if name not in pdfmetrics.getRegisteredFontNames():
            pdfmetrics.registerFont(TTFont(name, os.path.join(directory, filename)))
    pdfmetrics.registerFontFamily(
        "DanceSans", normal="DanceSans", bold="DanceSansBold",
        italic="DanceSans", boldItalic="DanceSansBold")
    return "DanceSans", "DanceSansBold"


def render_pdf(markdown):
    """Return a one-page US Letter PDF. Raises if the guide spills to page 2."""
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import letter
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.units import inch
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer

    title, blocks = parse_markdown(markdown)
    regular, bold = _fonts()
    ember = colors.HexColor("#8a3b12")
    ink = colors.HexColor("#2a1c12")
    body = ParagraphStyle(
        "GuideBody", fontName=regular, fontSize=11, leading=14, textColor=ink, spaceAfter=3)
    heading = ParagraphStyle(
        "GuideHeading", fontName=bold, fontSize=12, leading=15, textColor=ember,
        spaceBefore=7, spaceAfter=1, keepWithNext=True)
    title_style = ParagraphStyle(
        "GuideTitle", fontName=bold, fontSize=18, leading=21, textColor=ink, spaceAfter=4)
    output = BytesIO()
    doc = SimpleDocTemplate(
        output, pagesize=letter, leftMargin=0.62 * inch, rightMargin=0.62 * inch,
        topMargin=0.58 * inch, bottomMargin=0.52 * inch,
        title=title, author="Hillbilly Hellfire",
        subject="A short class guide for Line Dance Creator")
    story = [Paragraph(_markup(title), title_style)]
    for kind, text in blocks:
        style = heading if kind == "h" else body
        story.append(Paragraph(_markup(text), style))
    story.append(Spacer(1, 4))

    def decorate(canvas, document):
        canvas.saveState()
        width, height = letter
        canvas.setFillColor(ember)
        canvas.rect(0, height - 7, width, 7, fill=1, stroke=0)
        canvas.setFillColor(colors.HexColor("#3b2414"))
        canvas.rect(0, 0, width, 26, fill=1, stroke=0)
        canvas.setFillColor(colors.white)
        canvas.setFont(regular, 8.5)
        canvas.drawString(0.62 * inch, 10, FREEWARE_LINE)
        canvas.drawRightString(width - 0.62 * inch, 10, SITE)
        canvas.restoreState()

    doc.build(story, onFirstPage=decorate, onLaterPages=decorate)
    payload = output.getvalue()
    if not payload.startswith(b"%PDF"):
        raise RuntimeError("The instructor guide did not render as a PDF.")
    from pypdf import PdfReader
    pages = len(PdfReader(BytesIO(payload)).pages)
    if pages != 1:
        raise RuntimeError(f"The instructor guide must stay on one page (got {pages}).")
    return payload


def write_pdf(destination=None):
    target = Path(destination) if destination else pdf_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(render_pdf(source_path().read_text(encoding="utf-8")))
    return target


def copy_into_portable(destination):
    """Place the committed PDF at the top of a portable folder."""
    source = pdf_path()
    payload = source.read_bytes()
    if not payload.startswith(b"%PDF"):
        raise FileNotFoundError("release/Instructor one-pager.pdf is missing or not a PDF.")
    folder = Path(destination)
    folder.mkdir(parents=True, exist_ok=True)
    target = folder / PDF_NAME
    shutil.copy2(source, target)
    return target


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, help="Write the PDF somewhere other than release/")
    args = parser.parse_args()
    target = write_pdf(args.output)
    print(target)


if __name__ == "__main__":
    main()
