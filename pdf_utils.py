import os
import base64
import re
import unicodedata
import fitz
from html import escape


def list_pdfs(directory):
    pdfs = []
    for f in sorted(os.listdir(directory)):
        if f.lower().endswith('.pdf'):
            path = os.path.join(directory, f)
            try:
                doc = fitz.open(path)
                pdfs.append({
                    "name": f,
                    "pages": doc.page_count,
                    "size": os.path.getsize(path),
                })
                doc.close()
            except Exception:
                continue
    return pdfs


def get_pdf_info(filepath):
    doc = fitz.open(filepath)
    info = {
        "name": os.path.basename(filepath),
        "pages": doc.page_count,
        "size": os.path.getsize(filepath),
    }
    doc.close()
    return info


def get_pdf_toc(filepath):
    """Extract table of contents from a PDF.

    Returns a list of {level, title, page} dicts, or empty list.
    """
    doc = fitz.open(filepath)
    try:
        raw = doc.get_toc()
    except Exception:
        raw = []
    doc.close()
    return [{"level": entry[0], "title": entry[1], "page": entry[2]} for entry in raw]


def _span_to_html(span):
    text = escape(span["text"])
    flags = span["flags"]
    is_bold = bool(flags & 16)
    is_italic = bool(flags & 2)

    if is_bold and is_italic:
        text = f"<b><i>{text}</i></b>"
    elif is_bold:
        text = f"<b>{text}</b>"
    elif is_italic:
        text = f"<i>{text}</i>"

    color = span.get("color", 0)
    r = (color >> 16) & 0xFF
    g = (color >> 8) & 0xFF
    b = color & 0xFF
    if r != 0 or g != 0 or b != 0:
        hex_color = f"#{r:02x}{g:02x}{b:02x}"
        if hex_color != "#000000":
            text = f'<span style="color:{hex_color}">{text}</span>'
    return text


def _line_tag(line):
    """Determine tag for a single line based on its spans."""
    sizes = [s["size"] for s in line["spans"]]
    avg = sum(sizes) / len(sizes) if sizes else 0
    bold_chars = sum(len(s["text"]) for s in line["spans"] if s["flags"] & 16)
    total_chars = sum(len(s["text"]) for s in line["spans"])
    is_mostly_bold = bold_chars > total_chars * 0.6 if total_chars > 0 else False
    if avg >= 24:
        return "h1"
    if avg >= 18:
        return "h2"
    if avg >= 14 and is_mostly_bold:
        return "h3"
    return "p"


def _detect_alignment(bbox, page_width):
    """Detect text alignment from bounding box."""
    center = (bbox[0] + bbox[2]) / 2
    center_threshold = page_width * 0.12
    if abs(center - page_width / 2) < center_threshold:
        return "center"
    if bbox[0] > page_width * 0.55:
        return "right"
    return "left"


def _detect_indent(bbox):
    """Detect text indentation from bounding box (in points)."""
    indent = bbox[0] - 50
    return max(0, indent)


def _make_element(tag, lines_info):
    """Create an HTML element from grouped lines.

    lines_info is a list of (html_string, alignment, indent_px).
    All lines are joined with space to preserve paragraph continuity,
    allowing browser translation plugins to translate by paragraph.
    """
    htmls = [li[0] for li in lines_info]
    aligns = [li[1] for li in lines_info]
    indents = [li[2] for li in lines_info]

    text = " ".join(htmls)
    if not text.strip():
        return ""

    align = max(set(aligns), key=aligns.count)
    avg_indent = sum(indents) / len(indents)

    styles = []
    if align != "left":
        styles.append(f"text-align:{align}")
    if avg_indent > 15:
        styles.append(f"padding-left:{avg_indent:.0f}px")

    style_str = (' style="' + "; ".join(styles) + '"') if styles else ""
    return f"<{tag}{style_str}>{text}</{tag}>"


def _block_to_html(block, page_width=612):
    if block["type"] == 1:
        ext = block.get("ext", "png")
        img_data = block.get("image")
        if not img_data:
            return ""
        b64 = base64.b64encode(img_data).decode()
        w = block.get("width", 0)
        h = block.get("height", 0)
        return f'<figure><img src="data:image/{ext};base64,{b64}" width="{w}" height="{h}" style="max-width:100%;height:auto"></figure>'

    if not block["lines"]:
        return ""

    bbox = block["bbox"]
    block_align = _detect_alignment(bbox, page_width)
    block_indent = _detect_indent(bbox)

    groups = []
    current_tag = None
    current_lines = []

    for line in block["lines"]:
        tag = _line_tag(line)
        line_html = "".join(_span_to_html(s) for s in line["spans"])

        if tag == current_tag:
            current_lines.append((line_html, block_align, block_indent))
        else:
            if current_lines and current_tag:
                groups.append((current_tag, current_lines))
            current_tag = tag
            current_lines = [(line_html, block_align, block_indent)]

    if current_lines and current_tag:
        groups.append((current_tag, current_lines))

    return "\n".join(_make_element(tag, lines) for tag, lines in groups)


def _is_garbled(html_content, threshold=0.4):
    """Detect if extracted text is garbled by checking readability ratio."""
    text = re.sub(r'<[^>]+>', '', html_content)
    text = text.strip()
    if not text:
        return False

    readable = 0
    total = 0
    for c in text:
        if c in ' \n\r\t':
            continue
        total += 1
        cat = unicodedata.category(c)
        if cat.startswith('L') or cat.startswith('N') or c in '.,:;!?()-"\'':
            readable += 1

    if total == 0:
        return False
    return (readable / total) < threshold


def extract_page_html(filepath, page_num):
    doc = fitz.open(filepath)
    total = doc.page_count
    if page_num < 1 or page_num > total:
        doc.close()
        return {"html": "", "page": page_num, "total_pages": total, "has_content": False}

    page = doc[page_num - 1]
    page_width = page.rect.width
    blocks = page.get_text("dict")["blocks"]

    html_parts = []
    for block in blocks:
        h = _block_to_html(block, page_width)
        if h:
            html_parts.append(h)

    html_content = "\n".join(html_parts) if html_parts else ""

    if not html_content or _is_garbled(html_content):
        pix = page.get_pixmap(dpi=150)
        b64 = base64.b64encode(pix.tobytes("png")).decode()
        html_content = f'<figure><img src="data:image/png;base64,{b64}" style="max-width:100%;height:auto"></figure>'

    doc.close()
    return {
        "html": html_content,
        "page": page_num,
        "total_pages": total,
        "has_content": bool(html_content),
    }
