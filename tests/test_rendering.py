"""Tests for PDF text-to-HTML rendering pipeline."""

from pdf_utils import _span_to_html, _is_monospace, _is_code_block, _make_element, _block_is_all_mono, _merge_adjacent_mono_blocks, _detect_alignment, _detect_indent, _block_to_html


# === _is_monospace ===

def test_is_monospace_detects_flag_bit_3():
    span = {"flags": 8, "font": "Consolas", "text": "code"}
    assert _is_monospace(span) is True


def test_is_monospace_detects_font_name():
    span = {"flags": 0, "font": "Courier New", "text": "code"}
    assert _is_monospace(span) is True


def test_is_monospace_serif_not_mono():
    span = {"flags": 4, "font": "SourceSerif4-Regular", "text": "text"}
    assert _is_monospace(span) is False


# === _span_to_html ===

def test_span_to_html_wraps_monospace_in_code():
    span = {"text": "printf", "flags": 8, "font": "Consolas", "size": 9}
    html = _span_to_html(span)
    assert "<code" in html
    assert "printf" in html


def test_span_to_html_regular_text_no_code():
    span = {"text": "hello", "flags": 4, "font": "Serif", "size": 12}
    html = _span_to_html(span)
    assert "<code" not in html
    assert "hello" in html


def test_span_to_html_bold_monospace():
    span = {"text": "bold_code", "flags": 24, "font": "Consolas", "size": 9}
    html = _span_to_html(span)
    assert "<b>" in html
    assert "<code" in html
    assert "bold_code" in html


# === _span_to_html — near-zero font-size filtering ===

def test_span_to_html_filters_idx_marker_at_near_zero_size():
    """idx_ markers at 0.007pt are invisible — must be filtered."""
    span = {"text": "idx_a1b2c3d4", "flags": 0, "font": "Serif", "size": 0.0073}
    assert _span_to_html(span) == ""


def test_span_to_html_filters_empty_span_at_near_zero_size():
    """Empty/whitespace spans at near-zero size should also be filtered.
    The old regex-based approach missed these (44 exist in the test PDF)."""
    span = {"text": "", "flags": 0, "font": "Serif", "size": 0.01}
    assert _span_to_html(span) == ""


def test_span_to_html_preserves_smallest_visible_text_7_5pt():
    """7.5pt is the smallest visible font in the book (index tables).
    Must NOT be filtered."""
    span = {"text": "index entry", "flags": 0, "font": "Serif", "size": 7.5}
    assert "index entry" in _span_to_html(span)


def test_span_to_html_preserves_normal_body_text():
    """Normal 10.5pt body text must pass through unchanged."""
    span = {"text": "Normal body paragraph.", "flags": 0, "font": "Serif", "size": 10.5}
    assert "Normal body paragraph." in _span_to_html(span)


def test_span_to_html_boundary_at_threshold_not_filtered_0_5pt():
    """Size exactly 0.5 is NOT < 0.5 — must be preserved."""
    span = {"text": "boundary_text", "flags": 0, "font": "Serif", "size": 0.5}
    assert "boundary_text" in _span_to_html(span)


def test_span_to_html_boundary_below_threshold_filtered_0_49pt():
    """Size 0.49 IS < 0.5 — must be filtered.
    The old regex approach would miss this (no idx_ pattern)."""
    span = {"text": "should_be_gone", "flags": 0, "font": "Serif", "size": 0.49}
    assert _span_to_html(span) == ""


# === _is_code_block ===

def make_mock_block(lines_data):
    """Build a block dict from list of (spans_list) tuples."""
    block = {"type": 0, "bbox": (72, 100, 540, 200), "lines": []}
    for spans_data in lines_data:
        spans = []
        for text, flags, font, size in spans_data:
            spans.append({"text": text, "flags": flags, "font": font, "size": size, "color": 0})
        block["lines"].append({"spans": spans, "bbox": (72, 100, 540, 112)})
    return block


def test_is_code_block_all_monospace():
    block = make_mock_block([
        [("int main()", 8, "Consolas", 9)],
        [("    return 0;", 8, "Consolas", 9)],
        [("}", 8, "Consolas", 9)],
    ])
    assert _is_code_block(block) is True


def test_is_code_block_mixed_not_code():
    block = make_mock_block([
        [("Introduction", 20, "Jost-Bold", 16)],
        [("This is a paragraph.", 4, "Serif", 11)],
    ])
    assert _is_code_block(block) is False


def test_is_code_block_single_mono_line_not_code():
    block = make_mock_block([
        [("single_mono", 8, "Consolas", 9)],
    ])
    assert _is_code_block(block) is False


# === Line breaks in code blocks ===

def test_make_element_code_block_preserves_newlines():
    lines = [
        ("<code>int x = 1;</code>", "left", 0),
        ("<code>int y = 2;</code>", "left", 0),
        ("<code>return x + y;</code>", "left", 0),
    ]
    html = _make_element("pre", lines, is_code=True)
    assert "int x = 1;" in html
    assert "\n" in html


def test_make_element_paragraph_joins_lines_with_space():
    """Body text joins consecutive lines with space for natural flow.
    PDF line breaks are column-wrap artifacts, not author formatting."""
    lines = [
        ("This is a sentence.", "left", 0),
        ("It continues here.", "left", 0),
    ]
    html = _make_element("p", lines)
    assert "This is a sentence." in html
    assert "It continues here." in html
    assert "This is a sentence. It continues here." in html
    assert "<br>" not in html  # body text flows, no hard breaks


# === Block merging for code detection ===

def test_block_is_all_mono_true():
    block = make_mock_block([
        [("int x = 1;", 8, "Consolas", 9)],
    ])
    assert _block_is_all_mono(block) is True


def test_block_is_all_mono_false_mixed():
    block = make_mock_block([
        [("int x = 1;", 8, "Consolas", 9), ("text", 4, "Serif", 11)],
    ])
    assert _block_is_all_mono(block) is False


def test_merge_adjacent_mono_blocks():
    mono1 = make_mock_block([[("line1", 8, "Consolas", 9)]])
    mono2 = make_mock_block([[("line2", 8, "Consolas", 9)]])
    normal = make_mock_block([[("text", 4, "Serif", 11)]])
    mono3 = make_mock_block([[("line3", 8, "Consolas", 9)]])

    result = _merge_adjacent_mono_blocks([mono1, mono2, normal, mono3])
    # mono1 + mono2 merged, normal kept, mono3 alone
    assert len(result) == 3
    assert result[0].get("_merged") is True  # combined mono1+mono2
    assert len(result[0]["lines"]) == 2
    assert result[1] is normal
    assert result[2]["lines"][0]["spans"][0]["text"] == "line3"


def test_merged_block_detected_as_code():
    mono1 = make_mock_block([[("line1", 8, "Consolas", 9)]])
    mono2 = make_mock_block([[("line2", 8, "Consolas", 9)]])
    merged = _merge_adjacent_mono_blocks([mono1, mono2])
    assert merged[0].get("_merged") is True
    assert _is_code_block(merged[0]) is True


# === _detect_alignment ===

def test_alignment_full_width_body_text_is_left():
    """Full-width body text blocks should never be center — they're just body text."""
    # Typical body text: x0=72, x1=468, page=540.
    # Center = 270 = page center, but it's NOT centered text.
    assert _detect_alignment((72, 100, 468, 200), 540) == "left"


def test_alignment_narrow_centered_block_is_center():
    """A narrow block positioned near page center is truly centered."""
    # Narrow title: width ~200, centered on page
    center_x = 540 / 2  # 270
    block_x0 = center_x - 100  # 170
    block_x1 = center_x + 100  # 370
    assert _detect_alignment((170, 100, 370, 130), 540) == "center"


def test_alignment_right_aligned_block():
    """Block starting past 55% of page width is right-aligned."""
    page_width = 540
    assert _detect_alignment((300, 100, 400, 130), page_width) == "right"


def test_alignment_default_left():
    """Block near left margin is left-aligned."""
    assert _detect_alignment((72, 100, 300, 130), 540) == "left"


# === _detect_indent ===

def test_indent_calculation():
    """Indent is bbox x0 minus base margin (50pt)."""
    assert _detect_indent((72, 100, 200, 120)) == 22  # 72 - 50 = 22
    assert _detect_indent((50, 100, 200, 120)) == 0   # 50 - 50 = 0
    assert _detect_indent((120, 100, 200, 120)) == 70  # 120 - 50 = 70


# === Same-visual-line word grouping ===

def _make_span(text, size=15, flags=4, font="Serif", color=0):
    return {"text": text, "size": size, "flags": flags, "font": font, "color": color}


def _make_line(spans, x0=72, y0=100, x1=540, y1=115):
    """Helper: create a line dict with given spans and bbox."""
    return {
        "spans": spans,
        "bbox": (x0, y0, x1, y1),
    }


def test_same_visual_line_words_not_split():
    """Words on the same visual baseline must not be split into separate
    <p> elements even when their x-positions differ by >50pt.

    Real-world case: PDFs place each word as a separate text object,
    so PyMuPDF extracts them as separate lines at the same y but
    different x positions. The old 50pt x_jump threshold split them
    into separate groups, each becoming its own <p>."""
    block = {
        "type": 0,
        "bbox": (119, 379, 535, 394),
        "lines": [
            _make_line([_make_span("Independence")], x0=119),
            _make_line([_make_span("in")], x0=221),
            _make_line([_make_span("machines")], x0=251),
            _make_line([_make_span("signals")], x0=325),
            _make_line([_make_span("volatility")], x0=383),
            _make_line([_make_span("rather")], x0=453),
            _make_line([_make_span("than")], x0=507),
        ],
    }
    html = _block_to_html(block)
    # All 7 words must be in a single <p> — not split into multiple
    p_count = html.count("<p")
    assert p_count == 1, (
        f"Expected 1 <p> for same-visual-line words, got {p_count}: {html}"
    )
    # The sentence must read continuously
    assert "Independence in machines signals volatility rather than" in html
