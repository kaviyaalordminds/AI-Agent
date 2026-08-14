"""Real markdown -> file rendering for generated documents.

Claude drafts plain markdown (see app/documents/generator.py's system
prompt); this module turns that markdown into an actual, openable .docx
or .pdf file using real libraries (python-docx, reportlab) — never a
placeholder file or a renamed .txt. A small line-based parser produces a
shared block list both renderers consume, so heading/list/paragraph
structure is genuinely reflected in the output rather than dumped as one
unformatted blob of text.
"""
import io
import re
from dataclasses import dataclass
from typing import Literal

BlockKind = Literal["heading", "bullet", "numbered", "paragraph"]


@dataclass
class Block:
    kind: BlockKind
    text: str
    level: int = 0  # heading level (1-6); unused for other kinds


_HEADING_RE = re.compile(r"^(#{1,6})\s+(.*)$")
_BULLET_RE = re.compile(r"^[-*]\s+(.*)$")
_NUMBERED_RE = re.compile(r"^\d+\.\s+(.*)$")
_BOLD_RE = re.compile(r"\*\*(.+?)\*\*")


def parse_markdown_blocks(markdown_text: str) -> list[Block]:
    blocks: list[Block] = []
    for raw_line in markdown_text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        heading_match = _HEADING_RE.match(line)
        if heading_match:
            blocks.append(Block("heading", heading_match.group(2).strip(), level=len(heading_match.group(1))))
            continue
        bullet_match = _BULLET_RE.match(line)
        if bullet_match:
            blocks.append(Block("bullet", bullet_match.group(1).strip()))
            continue
        numbered_match = _NUMBERED_RE.match(line)
        if numbered_match:
            blocks.append(Block("numbered", numbered_match.group(1).strip()))
            continue
        blocks.append(Block("paragraph", line))
    return blocks


def _strip_bold_markers(text: str) -> str:
    return _BOLD_RE.sub(r"\1", text)


def render_docx(markdown_text: str, title: str) -> bytes:
    from docx import Document as DocxDocument
    from docx.shared import Pt

    doc = DocxDocument()
    doc.add_heading(title, level=0)

    for block in parse_markdown_blocks(markdown_text):
        text = _strip_bold_markers(block.text)
        if block.kind == "heading":
            doc.add_heading(text, level=min(block.level, 4))
        elif block.kind == "bullet":
            doc.add_paragraph(text, style="List Bullet")
        elif block.kind == "numbered":
            doc.add_paragraph(text, style="List Number")
        else:
            p = doc.add_paragraph(text)
            p.style.font.size = Pt(11)

    buffer = io.BytesIO()
    doc.save(buffer)
    return buffer.getvalue()


def render_pdf(markdown_text: str, title: str) -> bytes:
    from reportlab.lib.pagesizes import LETTER
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.lib.units import inch
    from reportlab.platypus import ListFlowable, ListItem, Paragraph, SimpleDocTemplate, Spacer

    styles = getSampleStyleSheet()
    story = [Paragraph(_escape_xml(title), styles["Title"]), Spacer(1, 0.2 * inch)]

    heading_styles = {1: styles["Heading1"], 2: styles["Heading2"], 3: styles["Heading3"]}
    pending_bullets: list[str] = []

    def flush_bullets():
        if pending_bullets:
            story.append(
                ListFlowable(
                    [ListItem(Paragraph(_escape_xml(b), styles["Normal"])) for b in pending_bullets],
                    bulletType="bullet",
                )
            )
            pending_bullets.clear()

    for block in parse_markdown_blocks(markdown_text):
        text = _strip_bold_markers(block.text)
        if block.kind == "heading":
            flush_bullets()
            style = heading_styles.get(block.level, styles["Heading3"])
            story.append(Paragraph(_escape_xml(text), style))
        elif block.kind in ("bullet", "numbered"):
            pending_bullets.append(text)
        else:
            flush_bullets()
            story.append(Paragraph(_escape_xml(text), styles["Normal"]))
            story.append(Spacer(1, 0.08 * inch))
    flush_bullets()

    buffer = io.BytesIO()
    SimpleDocTemplate(buffer, pagesize=LETTER).build(story)
    return buffer.getvalue()


def _escape_xml(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
