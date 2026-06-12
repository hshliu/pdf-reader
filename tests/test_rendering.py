"""Tests for PDF text-to-HTML rendering pipeline."""

from pdf_utils import _span_to_html, _is_monospace, _is_code_block, _make_element, _block_is_all_mono, _merge_adjacent_mono_blocks


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


def test_make_element_paragraph_preserves_line_breaks():
    lines = [
        ("This is a sentence.", "left", 0),
        ("It continues here.", "left", 0),
    ]
    html = _make_element("p", lines)
    assert "This is a sentence." in html
    assert "It continues here." in html
    assert "<br>" in html  # multi-line paragraphs use <br>


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
