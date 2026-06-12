import os
import base64
import re
import unicodedata
import fitz
from html import escape


def browse_directory(directory, subpath=""):
    """List subdirectories and PDF files without opening any PDF (fast)."""
    target = os.path.join(directory, subpath) if subpath else directory
    dirs = []
    files = []
    try:
        for entry in sorted(os.listdir(target), key=str.lower):
            full = os.path.join(target, entry)
            if os.path.isdir(full):
                dirs.append(entry)
            elif entry.lower().endswith(".pdf") and os.path.isfile(full):
                files.append({"name": entry})
    except OSError:
        pass
    return {"dirs": dirs, "files": files}


def list_pdfs(directory):
    pdfs = []
    for root, _, files in sorted(os.walk(directory)):
        for f in sorted(files):
            if not f.lower().endswith('.pdf'):
                continue
            path = os.path.join(root, f)
            rel = os.path.relpath(path, directory)
            try:
                doc = fitz.open(path)
                pdfs.append({
                    "name": rel,
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


MONOSPACE_FONTS = {
    "consolas", "courier", "monaco", "menlo", "monospace",
    "source code", "fira code", "jetbrains mono", "cascadia",
    "lucida console", "dejavu sans mono", "liberation mono",
}


def _is_monospace(span):
    """Check if a span uses monospace font via flag or font name."""
    if span["flags"] & 8:
        return True
    font = span.get("font", "").lower()
    for mf in MONOSPACE_FONTS:
        if mf in font:
            return True
    return False


def _span_to_html(span):
    text = escape(span["text"])
    flags = span["flags"]
    is_bold = bool(flags & 16)
    is_italic = bool(flags & 2)
    is_mono = _is_monospace(span)

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

    if is_mono:
        text = f"<code>{text}</code>"
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


def _is_code_block(block):
    """Detect if a text block is primarily code (monospace)."""
    # Merged blocks (consecutive mono lines) are always code blocks
    if block.get("_merged"):
        return True
    if not block.get("lines"):
        return False
    mono_lines = 0
    total_lines = 0
    for line in block["lines"]:
        total_lines += 1
        spans = line["spans"]
        if spans and all(_is_monospace(s) for s in spans):
            mono_lines += 1
    # Need at least 2 monospace lines and >=50% mono ratio
    return mono_lines >= 2 and mono_lines * 2 >= total_lines


def _make_element(tag, lines_info, is_code=False):
    """Create an HTML element from grouped lines.

    lines_info is a list of (html_string, alignment, indent_px).
    Lines are joined with <br> to preserve original line breaks while
    keeping the semantic paragraph unit intact for browser translation.
    For code blocks (<pre>), lines are joined with pure newlines.
    """
    htmls = [li[0] for li in lines_info]
    aligns = [li[1] for li in lines_info]
    indents = [li[2] for li in lines_info]

    if not any(h.strip() for h in htmls):
        return ""

    if is_code:
        text = "\n".join(htmls)
    elif len(htmls) == 1:
        text = htmls[0]
    else:
        text = "<br>\n".join(htmls)

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


def _block_to_html(block, page_width=612, page_height=792):

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

    # Detect header/footer: small text at page very top or bottom
    is_header_footer = False
    if page_height:
        y0, y1 = bbox[1], bbox[3]
        sizes = [s["size"] for line in block["lines"] for s in line["spans"]]
        avg_size = sum(sizes) / len(sizes) if sizes else 0
        top_pct = y0 / page_height
        if (top_pct < 0.08 or y1 > page_height * 0.93) and avg_size < 11:
            is_header_footer = True

    # Code block: render all lines as pre/code, preserving line breaks
    if _is_code_block(block):
        lines_info = []
        for line in block["lines"]:
            line_html = "".join(_span_to_html(s) for s in line["spans"])
            lines_info.append((line_html, block_align, block_indent))
        pre_html = _make_element("pre", lines_info, is_code=True)
        if is_header_footer:
            pre_html = pre_html.replace('<pre', '<pre class="page-header-footer"', 1)
        return pre_html

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

    result = "\n".join(_make_element(tag, lines) for tag, lines in groups)
    if is_header_footer and result:
        # Add class to first element for CSS targeting
        result = result.replace("<p", '<p class="page-header-footer"', 1)
        result = result.replace("<h1", '<h1 class="page-header-footer"', 1)
        result = result.replace("<h2", '<h2 class="page-header-footer"', 1)
        result = result.replace("<h3", '<h3 class="page-header-footer"', 1)
    return result


def extract_page_html(filepath, page_num):
    doc = fitz.open(filepath)
    total = doc.page_count
    if page_num < 1 or page_num > total:
        doc.close()
        return {"html": "", "page": page_num, "total_pages": total, "has_content": False}

    page = doc[page_num - 1]
    page_width = page.rect.width
    page_height = page.rect.height
    blocks = page.get_text("dict")["blocks"]

    # Merge consecutive monospace blocks so code snippets become one <pre> block
    blocks = _merge_adjacent_mono_blocks(blocks)

    html_parts = []
    for block in blocks:
        h = _block_to_html(block, page_width, page_height)
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


def get_thumbnails(filepath, start=1, end=None):
    """Generate low-res thumbnails for a page range.

    Returns dict with {thumbnails, total_pages, start, end}.
    Each thumbnail: {page, image (base64 png data URI), width, height}.
    """
    doc = fitz.open(filepath)
    total = doc.page_count
    if end is None or end > total:
        end = total
    if start < 1:
        start = 1
    if start > total:
        doc.close()
        return {"thumbnails": [], "total_pages": total, "start": start, "end": start - 1}

    thumbs = []
    for page_num in range(start, end + 1):
        page = doc[page_num - 1]
        pix = page.get_pixmap(dpi=30)
        b64 = base64.b64encode(pix.tobytes("png")).decode()
        thumbs.append({
            "page": page_num,
            "image": f"data:image/png;base64,{b64}",
            "width": pix.width,
            "height": pix.height,
        })
    doc.close()
    return {
        "thumbnails": thumbs,
        "total_pages": total,
        "start": start,
        "end": end,
    }


def _block_is_all_mono(block):
    """Check if every span in a text block is monospace."""
    if block["type"] == 1:
        return False
    for line in block.get("lines", []):
        for s in line["spans"]:
            if not _is_monospace(s):
                return False
    return True


def _merge_adjacent_mono_blocks(blocks):
    """Merge consecutive all-monospace blocks into combined virtual blocks.

    Returns a list of blocks where consecutive mono blocks are merged.
    A merged block has all lines from its source blocks combined.
    """
    merged = []
    mono_buffer = []

    for block in blocks:
        if _block_is_all_mono(block):
            mono_buffer.append(block)
        else:
            if mono_buffer:
                merged.append(_combine_blocks(mono_buffer))
                mono_buffer = []
            merged.append(block)

    if mono_buffer:
        merged.append(_combine_blocks(mono_buffer))

    return merged


def _combine_blocks(blocks):
    """Combine multiple mono blocks into one virtual block.

    Takes lines from all blocks, adjusts bbox to encompass them all.
    """
    if len(blocks) == 1:
        return blocks[0]

    all_lines = []
    min_x0 = min_y0 = float('inf')
    max_x1 = max_y1 = 0

    for b in blocks:
        x0, y0, x1, y1 = b["bbox"]
        min_x0 = min(min_x0, x0)
        min_y0 = min(min_y0, y0)
        max_x1 = max(max_x1, x1)
        max_y1 = max(max_y1, y1)
        all_lines.extend(b.get("lines", []))

    return {
        "type": 0,
        "bbox": (min_x0, min_y0, max_x1, max_y1),
        "lines": all_lines,
        "_merged": True,  # marker to force code block rendering
    }
    doc = fitz.open(filepath)
    total = doc.page_count
    if page_num < 1 or page_num > total:
        doc.close()
        return {"html": "", "page": page_num, "total_pages": total, "has_content": False}

    page = doc[page_num - 1]
    page_width = page.rect.width
    blocks = page.get_text("dict")["blocks"]

    # Merge consecutive monospace blocks so code snippets become one <pre> block
    blocks = _merge_adjacent_mono_blocks(blocks)

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
