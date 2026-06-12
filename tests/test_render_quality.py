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
    """Multi-line paragraphs use <br> to preserve line structure."""
    path = _find_pdf("Agentic_Coding_with_Claude_Code")
    if not path:
        pytest.skip("Agentic Coding PDF not available")
    html = extract_page_html(path, 24)
    assert "<br>" in html["html"], "No <br> tags — line breaks not preserved"


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
    """Line numbers (1., 2., 3.) must be inside the <pre> code block."""
    path = _find_pdf("Agentic_Coding_with_Claude_Code")
    if not path:
        pytest.skip("Agentic Coding PDF not available")
    html = extract_page_html(path, 24)
    pre_blocks = re.findall(r'<pre[^>]*>(.*?)</pre>', html["html"], re.DOTALL)
    assert len(pre_blocks) >= 1, "No <pre> blocks found"
    code_block = pre_blocks[0]
    for n in [1, 2, 3]:
        assert f"{n}." in code_block, \
            f"Line number {n}. not inside <pre> code block"


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
