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
    # A line is a heading only if most of its text is bold (not just one bold term)
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


def _block_to_html(block):
    if block["type"] == 1:
        ext = block.get("ext", "png")
        img_data = block.get("image")
        if not img_data:
            return ""
        b64 = base64.b64encode(img_data).decode()
        w = block.get("width", 0)
        h = block.get("height", 0)
        return f'<figure><img src="data:image/{ext};base64,{b64}" width="{w}" height="{h}" style="max-width:100%;height:auto"></figure>'

    # Process each line as its own element to separate headings from body text
    result = []
    current_tag = None
    current_parts = []

    for line in block["lines"]:
        tag = _line_tag(line)
        line_html = ""
        for span in line["spans"]:
            line_html += _span_to_html(span)

        if tag == current_tag:
            current_parts.append(line_html)
        else:
            if current_parts and current_tag:
                text = " ".join(current_parts).strip()
                if text:
                    result.append(f"<{current_tag}>{text}</{current_tag}>")
            current_tag = tag
            current_parts = [line_html]

    # Flush remaining
    if current_parts and current_tag:
        text = " ".join(current_parts).strip()
        if text:
            result.append(f"<{current_tag}>{text}</{current_tag}>")

    return "\n".join(result)


def _is_garbled(html_content, threshold=0.4):
    """Detect if extracted text is garbled by checking readability ratio."""
    # Strip HTML tags to get plain text
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
    blocks = page.get_text("dict")["blocks"]

    html_parts = []
    for block in blocks:
        h = _block_to_html(block)
        if h:
            html_parts.append(h)

    html_content = "\n".join(html_parts) if html_parts else ""

    # If no content extracted OR content is garbled, fallback to image rendering
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