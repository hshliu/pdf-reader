"""Automated rendering quality checks — no human eyes needed.

These tests verify that PDF-to-HTML rendering produces correct output:
- Code blocks are detected and rendered as <pre>
- Monospace spans get <code> tags
- Images are not HTML-escaped
- Line breaks are preserved with <br>
- Headers/footers are detected and subdued
- All expected content sections are present
"""

import re
import pytest
from pdf_utils import extract_page_html


def _find_pdf(partial_name):
    """Find a PDF by partial name match across all configured directories."""
    import app
    import os
    for d in app.PDF_DIRECTORIES:
        for root, _, files in os.walk(d["path"]):
            for f in files:
                if partial_name.lower() in f.lower() and f.lower().endswith(".pdf"):
                    return os.path.join(root, f)
    return None


# === Code block detection ===


def test_code_block_is_pre_not_p():
    """Code text must render as <pre>, not as <p>."""
    path = _find_pdf("Agentic_Coding_with_Claude_Code")
    if not path:
        pytest.skip("Agentic Coding PDF not available")
    html = extract_page_html(path, 24)
    content = html["html"]
    assert "<pre" in content, "No <pre> block found"
    assert "add_context" in content


def test_monospace_spans_get_code_tags():
    """Consolas text must be wrapped in <code>."""
    path = _find_pdf("Agentic_Coding_with_Claude_Code")
    if not path:
        pytest.skip("Agentic Coding PDF not available")
    html = extract_page_html(path, 24)
    assert "<code>" in html["html"], "No <code> tags found for monospace text"


def test_line_breaks_preserved():
    """Multi-line paragraphs flow as continuous text (space-joined).
    Code blocks still preserve newlines."""
    path = _find_pdf("Agentic_Coding_with_Claude_Code")
    if not path:
        pytest.skip("Agentic Coding PDF not available")
    html = extract_page_html(path, 24)
    # Code blocks (<pre>) preserve newlines for formatting
    assert "\n" in html["html"], "No newlines — code blocks may have lost formatting"
    # Body text paragraphs contain continuous text (space-joined, no <br>)
    pre_blocks = re.findall(r'<pre[^>]*>(.*?)</pre>', html["html"], re.DOTALL)
    for pre in pre_blocks:
        assert "\n" in pre, "Code block should preserve line breaks"
    # Body <p> elements should NOT contain <br> (text flows naturally)
    p_elems = re.findall(r'<p[^>]*>(.*?)</p>', html["html"], re.DOTALL)
    for p in p_elems:
        assert "<br>" not in p, f"Body paragraph has hard break: {p[:60]}..."


def test_code_block_left_aligned():
    """Code blocks must NOT be center-aligned."""
    path = _find_pdf("Agentic_Coding_with_Claude_Code")
    if not path:
        pytest.skip("Agentic Coding PDF not available")
    html = extract_page_html(path, 24)
    for line in html["html"].split("\n"):
        if "<pre" in line:
            assert "text-align:center" not in line, \
                f"Code block center-aligned: {line[:80]}"
            assert "text-align:right" not in line, \
                f"Code block right-aligned: {line[:80]}"


def test_images_not_escaped():
    """Image HTML inside code blocks must not be escaped."""
    path = _find_pdf("Agentic_Coding_with_Claude_Code")
    if not path:
        pytest.skip("Agentic Coding PDF not available")
    html = extract_page_html(path, 24)
    assert "&lt;figure&gt;" not in html["html"], \
        "Image HTML is escaped — will display as text"


def test_line_numbers_merged_into_code():
    """Numbered steps (1., 2., 3.) merge into their list items in <p>.
    These are list markers alongside body text, not code line numbers.
    The _merge_bullet_blocks function now handles both '•' and '1.' markers."""
    path = _find_pdf("Agentic_Coding_with_Claude_Code")
    if not path:
        pytest.skip("Agentic Coding PDF not available")
    html = extract_page_html(path, 24)
    plain = re.sub(r'<[^>]+>', ' ', html["html"])
    # Numbered steps should appear inline with their content
    for pair in [("1.", "packtpub.com"), ("2.", "profile picture"), ("3.", "Download Code")]:
        assert pair[0] in plain and pair[1] in plain, \
            f"'{pair[0]}' or '{pair[1]}' missing from page 24"


def test_page_header_detected():
    """Page headers like 'xxiii'/'Preface' must get page-header-footer class."""
    path = _find_pdf("Agentic_Coding_with_Claude_Code")
    if not path:
        pytest.skip("Agentic Coding PDF not available")
    html = extract_page_html(path, 24)
    assert "page-header-footer" in html["html"], \
        "No page-header-footer class found"


def test_header_is_not_body_text():
    """page-header-footer class must only be on actual headers, not body text."""
    path = _find_pdf("Agentic_Coding_with_Claude_Code")
    if not path:
        pytest.skip("Agentic Coding PDF not available")
    html = extract_page_html(path, 24)
    headers = re.findall(
        r'<[^>]*class="[^"]*page-header-footer[^"]*"[^>]*>(.*?)</[^>]+>',
        html["html"], re.DOTALL
    )
    for h in headers:
        text = re.sub(r'<[^>]+>', '', h).strip()
        is_valid = bool(re.search(
            r'(preface|chapter|contents|part\s+\d|appendix|index|^\d+$|^[ivxlcdm]+$)',
            text, re.I
        ))
        assert is_valid, f"Body text marked as header: '{text[:50]}'"


def test_page25_has_all_sections():
    """Verify page 25 renders all expected content sections."""
    path = _find_pdf("Agentic_Coding_with_Claude_Code")
    if not path:
        pytest.skip("Agentic Coding PDF not available")
    html = extract_page_html(path, 25)
    plain = re.sub(r'<[^>]+>', ' ', html["html"])
    for keyword in ["grep", "CLAUDE_MD", "npx create-next-app",
                     "Bold", "Indicates", "Get in touch", "Errata", "Piracy"]:
        assert keyword in plain, f"'{keyword}' missing from page 25"


# === Table grid detection ===


def test_table_columns_not_inflated_by_multiline_header():
    """Multi-line header cells must not inflate column count.
    Page 18 of Mastering Claude Code has a 5-column comparison table.
    The header 'GitHub Copilot' wraps to 2 lines, which without the fix
    would create 8 apparent columns instead of 5."""
    path = _find_pdf("Mastering_Claude_Code")
    if not path:
        pytest.skip("Mastering Claude Code PDF not available")
    html = extract_page_html(path, 18)
    content = html["html"]
    assert "<table" in content, "Table not detected on page 18"
    # Count <td> in the first table row — should be exactly 5
    rows = re.findall(r'<tr>(.*?)</tr>', content, re.DOTALL)
    assert len(rows) >= 2, f"Expected ≥2 table rows, got {len(rows)}"
    first_row_cells = re.findall(r'<td[^>]*>(.*?)</td>', rows[0], re.DOTALL)
    assert len(first_row_cells) == 5, \
        f"Expected 5 columns in first row, got {len(first_row_cells)}: {first_row_cells}"


def test_multiline_header_cells_merged():
    """Multi-line header cells 'GitHub Copilot', 'ChatGPT (Code Interpreter)',
    and 'Amazon CodeWhisperer' must appear as single cells, not split."""
    path = _find_pdf("Mastering_Claude_Code")
    if not path:
        pytest.skip("Mastering Claude Code PDF not available")
    html = extract_page_html(path, 18)
    content = html["html"]
    # Remove HTML tags to get plain text per cell
    rows = re.findall(r'<tr>(.*?)</tr>', content, re.DOTALL)
    first_row_cells = re.findall(r'<td[^>]*>(.*?)</td>', rows[0], re.DOTALL)
    # Strip inner HTML tags for comparison
    cell_texts = [re.sub(r'<[^>]+>', '', c).strip() for c in first_row_cells]
    # Each header cell should be a complete label
    assert any('GitHub Copilot' in t for t in cell_texts), \
        f"'GitHub Copilot' not found merged in: {cell_texts}"
    assert any('ChatGPT (Code Interpreter)' in t or 'ChatGPT (Code\nInterpreter)' in t.replace('\n', '\n') for t in cell_texts), \
        f"'ChatGPT (Code Interpreter)' not merged in: {cell_texts}"
    assert any('Amazon CodeWhisperer' in t for t in cell_texts), \
        f"'Amazon CodeWhisperer' not merged in: {cell_texts}"


def test_table_data_rows_have_five_columns():
    """All data rows must have 5 columns (Feature | Claude Code | GitHub Copilot |
    ChatGPT (Code Interpreter) | Amazon CodeWhisperer)."""
    path = _find_pdf("Mastering_Claude_Code")
    if not path:
        pytest.skip("Mastering Claude Code PDF not available")
    html = extract_page_html(path, 18)
    content = html["html"]
    rows = re.findall(r'<tr>(.*?)</tr>', content, re.DOTALL)
    for i, row in enumerate(rows):
        cells = re.findall(r'<td[^>]*>(.*?)</td>', row, re.DOTALL)
        assert len(cells) == 5, \
            f"Row {i} has {len(cells)} columns, expected 5: {cells}"
