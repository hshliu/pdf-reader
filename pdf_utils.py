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
    Consecutive entries where the first is a bare number (e.g. '1')
    and the second shares the same page are merged into '1  Title'.
    """
    doc = fitz.open(filepath)
    try:
        raw = doc.get_toc()
    except Exception:
        raw = []
    doc.close()

    entries = [{"level": entry[0], "title": entry[1], "page": entry[2]}
               for entry in raw]

    # Merge bare chapter numbers with their titles
    merged = []
    i = 0
    while i < len(entries):
        entry = entries[i]
        if (re.match(r'^\d{1,2}$', entry["title"].strip()) and
                i + 1 < len(entries) and
                entries[i + 1]["page"] == entry["page"] and
                not re.match(r'^\d{1,2}$', entries[i + 1]["title"].strip())):
            # Merge "1" + "Context Engineering" → "1  Context Engineering"
            combined_title = entry["title"] + "  " + entries[i + 1]["title"]
            merged.append({"level": entries[i + 1]["level"],
                           "title": combined_title,
                           "page": entry["page"]})
            i += 2
        else:
            merged.append(entry)
            i += 1

    return merged


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
    # Image lines contain raw HTML that should not be escaped
    if span.get("_is_image_line"):
        return span["text"]

    # Filter all spans at near-zero font size (invisible PDF markers).
    # Empirically: idx_ markers render at 0.007 pt, smallest visible
    # text in the book is 7.5 pt. A < 0.5 pt threshold safely removes
    # only invisible spans with a ~7 pt safety margin.
    size = span.get("size", 12)
    if size < 0.5:
        return ""

    # Strip control characters and Unicode replacement chars (U+FFFD)
    # that result from unmappable or corrupt PDF font glyphs.
    clean = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f�]', '', span["text"])
    text = escape(clean)
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
    """Detect text alignment from bounding box.

    Body text starts at the left margin and extends toward the right page
    edge — its center equals the page center only because it fills the
    page, not because the text is aligned.  Only blocks whose left edge
    sits well past the left margin can be convincingly center-aligned.
    """
    left_margin = page_width * 0.22   # ~119pt on letter-size
    block_width = bbox[2] - bbox[0]

    # Block anchored near the left margin → body text, regardless of width.
    # Raised high enough to include list items (x0≈104) and code (x0≈86).
    if bbox[0] < left_margin:
        return "left"

    # Block extends near the right page edge → body text, never centered
    if bbox[2] > page_width * 0.85 or block_width > page_width * 0.7:
        return "left"

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
    # Line-number-only blocks are code blocks (they label code listings)
    if _is_line_number_block(block):
        return True
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
    Code blocks (<pre>) preserve line breaks with newlines.
    Body text joins consecutive lines with a space so the browser can
    flow text naturally — PDF line breaks are just column wrapping,
    not semantic breaks the author intended.
    """
    htmls = [li[0] for li in lines_info]
    aligns = [li[1] for li in lines_info]
    indents = [li[2] for li in lines_info]
    x0s = [li[3] if len(li) > 3 else 0 for li in lines_info]

    if not any(h.strip() for h in htmls):
        return ""

    if is_code:
        text = "\n".join(htmls)
    elif len(htmls) == 1:
        text = htmls[0]
    else:
        # Join body-text lines so text flows naturally.  Detect mid-word
        # breaks: only join without a space when two lines share the same
        # x-position (same column/cell) AND the second line begins with a
        # very short word fragment (≤3 chars) — a tell-tale sign of a
        # hyphenation-like break like "consistenc" + "y".
        parts = [htmls[0]]
        for i, h in enumerate(htmls[1:], start=1):
            prev_plain = re.sub(r'<[^>]+>', '', parts[-1])
            curr_plain = re.sub(r'<[^>]+>', '', h)
            same_column = (abs(x0s[i] - x0s[i - 1]) < 5) if x0s[i] and x0s[i - 1] else True
            # Length of the first word-fragment on the next line
            first_word = curr_plain.split()[0] if curr_plain.strip() else ''
            likely_hyphen_break = (
                same_column and prev_plain and curr_plain and
                prev_plain[-1].isalpha() and curr_plain[0].isalpha() and
                len(first_word) <= 3
            )
            if likely_hyphen_break:
                parts.append(h)
            else:
                parts.append(' ')
                parts.append(h)
        text = ''.join(parts)

    if not text.strip():
        return ""

    align = max(set(aligns), key=aligns.count)
    avg_indent = sum(indents) / len(indents)

    styles = []
    if align != "left":
        styles.append(f"text-align:{align}")
    # Never add padding-left on center-aligned text — it pushes
    # the content off-center visually
    if avg_indent > 15 and align != "center":
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

    # Detect header/footer: small text at page very top or bottom.
    # Code blocks are never headers/footers, even if they sit near a page edge.
    is_header_footer = False
    if page_height and not _is_code_block(block):
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
            if line.get("_is_image_line"):
                line_html = line["spans"][0]["text"]
            else:
                line_html = "".join(_span_to_html(s) for s in line["spans"])
            lines_info.append((line_html, "left", block_indent))  # code always left-aligned
        pre_html = _make_element("pre", lines_info, is_code=True)
        if is_header_footer:
            pre_html = pre_html.replace('<pre', '<pre class="page-header-footer"', 1)
        return pre_html

    groups = []
    current_tag = None
    current_lines = []
    current_x0 = None

    for line in block["lines"]:
        tag = _line_tag(line)
        line_html = "".join(_span_to_html(s) for s in line["spans"])

        line_x0 = line["bbox"][0]

        # Split groups when x-position jumps >50pt — lines are in
        # different table columns, not continuous body text.
        x_jumped = (current_x0 is not None and
                    abs(line_x0 - current_x0) > 50)

        if tag == current_tag and not x_jumped:
            current_lines.append((line_html, block_align, block_indent, line_x0))
        else:
            if current_lines and current_tag:
                groups.append((current_tag, current_lines))
            current_tag = tag
            current_lines = [(line_html, block_align, block_indent, line_x0)]
            current_x0 = line_x0

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


def _is_list_marker(text):
    """Check if text is a list marker: bullet char OR numbered item like '1.' '2.'"""
    BULLETS = {'•', '◦', '▪', '▸', '▹', '►', '○', '●', '–', '—', '‣', '⁃'}
    if text in BULLETS:
        return True
    # Numbered list item: "1.", "2.", … up to "99."
    if re.match(r'^\d{1,2}\.$', text):
        return True
    return False


def _merge_bullet_blocks(blocks):
    """Merge list-marker blocks (•, 1., 2., …) into adjacent content at same y.

    PDFs often place list markers as separate single-line blocks at the same
    y as the list item text.  Without merging, markers render as standalone
    <p> elements stacked together, separated from their list items.

    Strategy: two-pass.  First collect every marker block into a {y: (char, x)}
    map.  Then scan every content block; if a marker sits at the same y and
    to the left, prepend the marker to the first span and remove the marker.
    """

    # Pass 1: collect marker blocks keyed by rounded y position
    bullet_map = {}   # y_rounded (int) → (index, char, x0)
    for i, b in enumerate(blocks):
        if b["type"] != 0:
            continue
        lines = b.get("lines", [])
        if len(lines) != 1:
            continue
        text = "".join(s["text"].strip() for s in lines[0]["spans"]).strip()
        if not _is_list_marker(text):
            continue
        y = lines[0]["bbox"][1]
        x = lines[0]["bbox"][0]
        bullet_map[int(y)] = (i, text, x)

    if not bullet_map:
        return blocks

    remove_indices = set()

    # Pass 2: for each content block, check if a bullet shares the same y
    for i, b in enumerate(blocks):
        if b["type"] != 0:
            continue
        b_lines = b.get("lines", [])
        if not b_lines:
            continue
        content_y = b_lines[0]["bbox"][1]
        content_x = b_lines[0]["bbox"][0]

        # Check a small y-window (±3pt) for a matching bullet
        for y_key in range(int(content_y) - 3, int(content_y) + 4):
            entry = bullet_map.get(y_key)
            if entry is None:
                continue
            bi, bchar, bx = entry
            if bi in remove_indices:
                continue
            if bx < content_x:
                # Merge: prepend bullet char to first span and extend
                # the block/line/span bbox leftward so padding-left CSS
                # aligns the bullet (not the text after it) to the indent.
                first_span = b_lines[0]["spans"][0]
                first_span["text"] = bchar + " " + first_span["text"]
                # Extend bboxes to the bullet's x position
                b["bbox"] = (bx, b["bbox"][1], b["bbox"][2], b["bbox"][3])
                b_lines[0]["bbox"] = (bx, b_lines[0]["bbox"][1],
                                      b_lines[0]["bbox"][2], b_lines[0]["bbox"][3])
                sx0, sy0, sx1, sy1 = first_span.get("bbox", (bx, 0, bx, 0))
                first_span["bbox"] = (bx, sy0, sx1, sy1)
                remove_indices.add(bi)
                break

    return [b for idx, b in enumerate(blocks) if idx not in remove_indices]


def _detect_table_grid(blocks, page_width):
    """Detect table by finding blocks arranged in a grid (rows × columns).

    Table cells are narrow blocks at consistent x-positions (columns)
    across multiple y-positions (rows).  Full-width body text and code
    blocks are excluded from grid detection.

    Returns (html_string, set_of_block_ids) or (None, None).
    """
    # Filter to blocks that could be table cells.  Wide blocks with
    # lines at different x-positions are multi-column headers — split
    # each column group into a virtual single-cell block.  Lines that
    # share the same rounded x0 are merged into one cell (e.g. "VS" +
    # "Code" stacked vertically become "VS Code").
    candidates = []
    extra_remove_ids = set()
    for b in blocks:
        if b["type"] != 0 or not b.get("lines"):
            continue
        if _is_code_block(b):
            continue
        # Also skip mono text (code snippets shouldn't be in tables)
        if b.get("lines") and all(
                all(_is_monospace(s) for s in line["spans"])
                for line in b["lines"] if line["spans"]):
            continue
        bw = b["bbox"][2] - b["bbox"][0]
        if bw < 15:  # too narrow (bullet, line number)
            continue

        lines_x = [l["bbox"][0] for l in b.get("lines", []) if l["spans"]]
        multi_col = len(set(round(x/20)*20 for x in lines_x)) >= 2 if lines_x else False

        if bw > page_width * 0.55 and not multi_col:
            continue  # wide body text, not a table

        if multi_col:
            extra_remove_ids.add(id(b))
            # Group lines by column (rounded x0) so stacked lines in
            # the same column (e.g. "VS" + "Code" → "VS Code") stay
            # together as one cell.
            col_groups = {}
            for line in b["lines"]:
                if not line["spans"]:
                    continue
                col_key = round(line["bbox"][0] / 20) * 20
                if col_key not in col_groups:
                    col_groups[col_key] = []
                col_groups[col_key].append(line)
            for col_lines in col_groups.values():
                cell_text = "".join(
                    s["text"] for l in col_lines for s in l["spans"]
                ).strip()
                if cell_text:
                    # Use the column group's actual line y-range so that
                    # header text ("Amazon", y≈74) and data continuation
                    # ("projects…", y≈113) from the same block land in
                    # different rows.  Also keeps "VS"+"Code" together
                    # because they share the same column and y-range.
                    ly0 = min(l["bbox"][1] for l in col_lines)
                    ly1 = max(l["bbox"][3] for l in col_lines)
                    candidates.append({
                        "type": 0,
                        "bbox": (col_lines[0]["bbox"][0], ly0,
                                 max(l["bbox"][2] for l in col_lines), ly1),
                        "lines": col_lines,
                        "_virtual": True,
                    })
        else:
            candidates.append(b)

    if len(candidates) < 6:
        return None, None

    # Sort by y-center, then x
    candidates.sort(key=lambda b: (
        (b["bbox"][1] + b["bbox"][3]) / 2, b["bbox"][0]))

    # Group into rows by y-center proximity (within 18pt).
    # Use the mean y-center of all cells already in the row as the anchor
    # (not a rolling pair-average) so a sequence of small steps cannot
    # drift the row boundary.  Without this, a 2-line header row whose
    # y-centers span 18 pt can be absorbed into one row via 4 pt steps.
    rows = []
    current_row = [candidates[0]]
    row_ycs = [(candidates[0]["bbox"][1] + candidates[0]["bbox"][3]) / 2]
    for b in candidates[1:]:
        yc = (b["bbox"][1] + b["bbox"][3]) / 2
        if abs(yc - sum(row_ycs) / len(row_ycs)) < 18:
            current_row.append(b)
            row_ycs.append(yc)
        else:
            rows.append(sorted(current_row, key=lambda b: b["bbox"][0]))
            current_row = [b]
            row_ycs = [yc]
    rows.append(sorted(current_row, key=lambda b: b["bbox"][0]))

    if len(rows) < 2:
        return None, None

    # Find columns by clustering x0 positions across ALL rows.
    # Using one row (even the median-count row) is fragile — a
    # repeated header on a continuation page can have fewer cells
    # than the real columns (page 19: 4 vs 5), silently dropping
    # the rightmost column.  Clustering all rows is robust.
    all_x0s = []
    for row in rows:
        for b in row:
            all_x0s.append(b["bbox"][0])
    all_x0s.sort()

    # Cluster x0 positions (greedy, gap ≤ 25 pt)
    clusters = []
    for x in all_x0s:
        placed = False
        for cluster in clusters:
            if x - cluster[-1] <= 25:
                cluster.append(x)
                placed = True
                break
        if not placed:
            clusters.append([x])

    # Keep clusters that appear across ≥ 40 % of rows
    col_x0s = []
    for cluster in clusters:
        center = sum(cluster) / len(cluster)
        row_count = sum(
            1 for row in rows
            if any(abs(b["bbox"][0] - center) < 25 for b in row)
        )
        if row_count >= max(2, len(rows) * 0.4):
            col_x0s.append(center)
    col_x0s.sort()

    if len(col_x0s) < 2:
        return None, None

    # For each row, assign each block to the nearest column.
    # Also merge cells that map to the same column within a row
    # (e.g. "Integration" + "Type" → "Integration Type").
    table_cells = []  # list of rows, each row is list of (col_idx, block)
    all_ids = set()
    for row in rows:
        row_cells = []
        for b in row:
            best_col = min(range(len(col_x0s)),
                          key=lambda j: abs(b["bbox"][0] - col_x0s[j]))
            # Only accept if close enough to the column (< 30pt)
            if abs(b["bbox"][0] - col_x0s[best_col]) < 30:
                row_cells.append((best_col, b))
                all_ids.add(id(b))
        if len(row_cells) < 2:
            continue
        # Merge cells that landed in the same column (horizontal merge)
        merged = {}
        for col_idx, b in row_cells:
            if col_idx in merged:
                existing = merged[col_idx]
                all_lines = list(existing.get("lines", [])) + list(
                    b.get("lines", []))
                # Sort by y so "Amazon" (line 1) stays above
                # "CodeWhisperer" (line 2) regardless of x-order
                all_lines.sort(key=lambda l: l["bbox"][1])
                existing["lines"] = all_lines
                existing["bbox"] = (
                    min(existing["bbox"][0], b["bbox"][0]),
                    existing["bbox"][1],
                    max(existing["bbox"][2], b["bbox"][2]),
                    max(existing["bbox"][3], b["bbox"][3]),
                )
                all_ids.add(id(b))
            else:
                merged[col_idx] = b
        table_cells.append([(col, blk) for col, blk in merged.items()])

    if len(table_cells) < 2:
        return None, None

    # Merge vertically adjacent cells that land in the same column.
    # Multi-line header cells (e.g. "GitHub\nCopilot") are often split
    # by PyMuPDF into separate blocks at different y-positions, which
    # end up in consecutive rows after y-center grouping.  Only merge
    # when the lower row is sparse (≤3 cells) to avoid collapsing
    # legitimate data rows.
    for ri in range(len(table_cells) - 1, 0, -1):
        curr_row = table_cells[ri]
        prev_row = table_cells[ri - 1]
        curr_cols = {c: b for c, b in curr_row}
        prev_cols = {c: b for c, b in prev_row}
        shared = set(curr_cols.keys()) & set(prev_cols.keys())
        unique = set(curr_cols.keys()) - set(prev_cols.keys())
        if not shared and not unique:
            continue
        if len(curr_row) > 3:
            continue
        # Merge shared columns: append lower cell's text to upper cell
        for col in shared:
            lower = curr_cols[col]
            upper = prev_cols[col]
            lower_lines = []
            for line in lower.get("lines", []):
                lt = "".join(s["text"] for s in line.get("spans", [])).strip()
                if lt:
                    lower_lines.append(lt)
            if lower_lines:
                upper["lines"] = list(upper.get("lines", [])) + list(
                    lower.get("lines", []))
            # Extend bbox downward
            upper["bbox"] = (
                upper["bbox"][0],
                upper["bbox"][1],
                upper["bbox"][2],
                max(upper["bbox"][3], lower["bbox"][3]),
            )
            all_ids.add(id(lower))
        # Transfer unique columns (in lower row but not upper) to the
        # upper row so they aren't orphaned when the lower row is dropped.
        for col in unique:
            prev_row.append((col, curr_cols[col]))
            all_ids.add(id(curr_cols[col]))
        # Remove merged/transferred cells from this row
        all_removed = shared | unique
        table_cells[ri] = [(c, b) for c, b in curr_row
                           if c not in all_removed]
    # Drop rows that became empty after merging
    table_cells = [r for r in table_cells if len(r) >= 2]

    if len(table_cells) < 2:
        return None, None

    # Build HTML table
    parts = ['<table class="pdf-table">']
    for row_cells in table_cells:
        parts.append('<tr>')
        row_cells.sort(key=lambda x: x[0])
        last_col = -1
        for col_idx, b in row_cells:
            for gap in range(last_col + 1, col_idx):
                parts.append('<td></td>')
            # Join lines within a cell: detect mid-word breaks (e.g.
            # "consistenc" + "y" → "consistency") and join those without
            # a space; otherwise join with a space.
            cell_lines = []
            for line in b["lines"]:
                lt = "".join(s["text"] for s in line["spans"]).strip()
                if lt:
                    cell_lines.append(lt)
            if cell_lines:
                joined = cell_lines[0]
                for nxt in cell_lines[1:]:
                    # Mid-word break: current ends with letter, next starts
                    # with a short fragment (≤3 chars)
                    first_word = nxt.split()[0] if nxt.strip() else ''
                    if (joined and joined[-1].isalpha() and
                            nxt and nxt[0].isalpha() and
                            len(first_word) <= 3):
                        joined += nxt
                    else:
                        joined += ' ' + nxt
                parts.append(f'<td>{joined}</td>')
            else:
                parts.append('<td></td>')
            last_col = col_idx
        parts.append('</tr>')
    parts.append('</table>')

    return '\n'.join(parts), all_ids | extra_remove_ids


def _merge_chapter_numbers(blocks):
    """Merge large decorative chapter numbers into the following heading.

    PDFs often place chapter numbers (e.g. '1' at 75pt) as a separate
    block above the chapter title (e.g. 'Context Engineering' at 27pt).
    Without merging, the number renders as an orphan <h1>1</h1>.
    """
    if len(blocks) < 2:
        return blocks

    remove_indices = set()
    for i in range(len(blocks) - 1):
        if i in remove_indices:
            continue
        b = blocks[i]
        if b["type"] != 0:
            continue
        b_lines = b.get("lines", [])
        if len(b_lines) != 1:
            continue
        text = "".join(s["text"].strip() for s in b_lines[0]["spans"]).strip()
        # Single short digit, large font → decorative chapter number
        sizes = [s["size"] for s in b_lines[0]["spans"]]
        avg_sz = sum(sizes) / len(sizes) if sizes else 0
        if not (re.match(r'^\d{1,2}$', text) and avg_sz > 20):
            continue

        # Next block must be a heading (large font, not code)
        nxt = blocks[i + 1]
        if nxt["type"] != 0:
            continue
        nxt_lines = nxt.get("lines", [])
        if not nxt_lines:
            continue
        nxt_sizes = [s["size"] for s in nxt_lines[0]["spans"]]
        nxt_avg = sum(nxt_sizes) / len(nxt_sizes) if nxt_sizes else 0
        if nxt_avg < 18:
            continue  # not a heading

        # Merge: prepend chapter number to heading's first span
        first_span = nxt_lines[0]["spans"][0]
        first_span["text"] = text + "  " + first_span["text"]
        # Extend heading bbox leftward to include the number
        num_x = b_lines[0]["bbox"][0]
        nxt["bbox"] = (num_x, nxt["bbox"][1], nxt["bbox"][2], nxt["bbox"][3])
        nxt_lines[0]["bbox"] = (num_x, nxt_lines[0]["bbox"][1],
                                nxt_lines[0]["bbox"][2], nxt_lines[0]["bbox"][3])
        remove_indices.add(i)

    return [b for idx, b in enumerate(blocks) if idx not in remove_indices]


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

    # Detect and extract table regions before any merging
    # ---- Table detection via block grid ----
    # Find blocks that form a grid (rows × columns).
    table_html, table_block_ids = _detect_table_grid(blocks, page_width)
    if table_html and table_block_ids:
        blocks = [b for i, b in enumerate(blocks) if id(b) not in table_block_ids]

    # Merge decorative chapter numbers into the heading that follows
    blocks = _merge_chapter_numbers(blocks)

    # Merge bullet markers into adjacent content before mono block merging
    blocks = _merge_bullet_blocks(blocks)

    # Merge consecutive monospace blocks so code snippets become one <pre> block
    blocks = _merge_adjacent_mono_blocks(blocks)

    # Generate HTML for each block, tracking y-position for row grouping.
    items = []  # (y0, html) pairs
    for block in blocks:
        h = _block_to_html(block, page_width, page_height)
        if h:
            y0 = block["bbox"][1] if block["type"] == 0 else block["bbox"][1]
            # Split x-jump-separated elements into individual items so
            # each table cell can be independently grouped by y-bucket.
            # x-jumped elements are separated by newlines (not <br>).
            parts = [p for p in h.split('\n') if p.strip()]
            if len(parts) > 1 and all(not p.startswith('<div') for p in parts):
                # Multiple independent elements from same block (table header)
                for p in parts:
                    if p.strip():
                        items.append((y0, p.strip()))
            else:
                items.append((y0, h))

    # Group items at similar y into flex rows so table cells in the same
    # visual row appear side-by-side.  Use 25pt y-buckets to group
    # within-row cells without merging adjacent rows.
    row_map = {}
    for y0, h in items:
        bucket = round(y0 / 35) * 35
        row_map.setdefault(bucket, []).append(h)

    html_parts = []
    if table_html:
        html_parts.append(table_html)
    for bucket in sorted(row_map.keys()):
        group = row_map[bucket]
        if len(group) >= 2:
            html_parts.append(
                '<div class="table-row" style="display:flex;flex-wrap:wrap;gap:8px 16px;align-items:flex-start">'
                + "\n".join(group) + '</div>')
        else:
            html_parts.extend(group)

    html_content = "\n".join(html_parts) if html_parts else ""

    # Blank page (no text, no images): return a subtle placeholder instead
    # of rendering a full-page white image.
    page_is_blank = not blocks

    if not html_content or _is_garbled(html_content):
        if page_is_blank:
            html_content = '<p class="blank-page" style="text-align:center;color:#aaa;padding:48px 0;font-style:italic">This page is blank</p>'
        else:
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


def _is_line_number_block(block):
    """Check if a block contains only line numbers like '1.', '2.', etc.

    Both single-line and multi-line blocks are accepted.  List markers
    (1., 2. next to body text) are already removed by _merge_bullet_blocks
    before this runs; any single-line digit-block that survives is a
    genuine code line number.

    Excludes blocks with large font sizes (>20 pt) — those are decorative
    chapter numbers or drop-caps, not code line numbers.
    """
    if block["type"] == 1:
        return False
    lines = block.get("lines", [])
    if not lines:
        return False

    # Compute average font size — chapter numbers use 27-75pt,
    # code line numbers use 8-10pt.
    sizes = [s["size"] for line in lines for s in line["spans"]]
    avg_size = sum(sizes) / len(sizes) if sizes else 0
    if avg_size > 20:
        return False

    ln_count = 0
    total_count = 0
    for line in lines:
        text = "".join(s["text"].strip() for s in line["spans"])
        if not text:
            continue
        total_count += 1
        # Must be a short digit/digits followed by optional period
        if re.match(r'^\d{1,3}\.?$', text):
            ln_count += 1

    if total_count == 0:
        return False
    # >70% of lines must be line-number patterns
    return ln_count > total_count * 0.7


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
    """Merge consecutive mono/line-number/image blocks into combined virtual blocks.

    A code listing in a PDF may consist of:
    - Mono text blocks (actual code text)
    - Line number blocks ('1.', '2.', etc. — non-mono font)
    - Image blocks (code screenshots)
    These are merged into a single <pre> block for correct display.

    Large vertical gaps (>200pt) between code-parts indicate separate code
    listings — the buffer is flushed so they stay in separate <pre> blocks.
    """
    merged = []
    code_buffer = []

    for block in blocks:
        is_code_part = (
            _block_is_all_mono(block) or
            _is_line_number_block(block) or
            block["type"] == 1  # image
        )
        if is_code_part:
            # Check for large vertical gap from previous buffer content
            if code_buffer:
                prev_y1 = code_buffer[-1]["bbox"][3]
                this_y0 = block["bbox"][1]
                if abs(this_y0 - prev_y1) > 200:
                    # Significant gap — flush buffer as separate code block
                    merged.append(_combine_blocks(code_buffer))
                    code_buffer = []
                # Line-number restart: a new "1." after existing line numbers
                # signals the start of a new code listing
                elif _is_line_number_block(block):
                    block_text = "".join(
                        s["text"].strip()
                        for s in block["lines"][0]["spans"]
                    ).strip()
                    # Check if buffer already has line numbers
                    has_ln = any(
                        _is_line_number_block(b)
                        for b in code_buffer
                        if b["type"] == 0
                    )
                    if block_text in ("1", "1.") and has_ln:
                        merged.append(_combine_blocks(code_buffer))
                        code_buffer = []
            code_buffer.append(block)
        else:
            if code_buffer:
                merged.append(_combine_blocks(code_buffer))
                code_buffer = []
            merged.append(block)

    if code_buffer:
        merged.append(_combine_blocks(code_buffer))

    return merged


def _combine_blocks(blocks):
    """Combine multiple blocks (mono, line numbers, images) into one virtual block.

    Takes lines from text blocks, converts images to placeholder lines.
    Lines are sorted by y-position so that line numbers and code on the
    same visual line render adjacent to each other.
    """
    if len(blocks) == 1:
        return blocks[0]

    # Collect (y0, line_dict) pairs
    indexed_lines = []
    min_x0 = min_y0 = float('inf')
    max_x1 = max_y1 = 0

    for b in blocks:
        x0, y0, x1, y1 = b["bbox"]
        min_x0 = min(min_x0, x0)
        min_y0 = min(min_y0, y0)
        max_x1 = max(max_x1, x1)
        max_y1 = max(max_y1, y1)

        if b["type"] == 1:
            # Convert image block to a virtual text line containing the figure HTML
            ext = b.get("ext", "png")
            img_data = b.get("image")
            if img_data:
                b64 = base64.b64encode(img_data).decode()
                w = b.get("width", 0)
                h = b.get("height", 0)
                wh_attr = f' width="{w}" height="{h}"' if w and h else ""
                img_html = f'<figure><img src="data:image/{ext};base64,{b64}"{wh_attr} style="max-width:100%;height:auto"></figure>'
                indexed_lines.append((y0, {
                    "spans": [{"text": img_html, "flags": 0, "font": "", "size": 0}],
                    "bbox": b["bbox"],
                    "_is_image_line": True,
                }))
        else:
            for line in b.get("lines", []):
                ly0 = line["bbox"][1]
                indexed_lines.append((ly0, line))

    # Sort by y-position so line numbers and code sharing the same line
    # are rendered adjacent regardless of their original block order
    indexed_lines.sort(key=lambda x: x[0])
    all_lines = [l for _, l in indexed_lines]

    return {
        "type": 0,
        "bbox": (min_x0, min_y0, max_x1, max_y1),
        "lines": all_lines,
        "_merged": True,
    }
