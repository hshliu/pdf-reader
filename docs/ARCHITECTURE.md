# Architecture

## Overview

Flask 单页应用，后端 Python + PyMuPDF 处理 PDF，前端模块化原生 JavaScript（8 模块），本地浏览器存储阅读进度。43 个自动化测试覆盖渲染质量和表格检测。

## Backend — `app.py`

### API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/` | Index page |
| GET | `/api/dirs` | List configured PDF source directories |
| GET | `/api/browse/<dir_key>/<path>` | Lazily browse directory tree (subdirs + PDF filenames) |
| GET | `/api/pdfs` | List all PDFs across all dirs with page counts |
| GET | `/api/pdf/<compound>/info` | PDF metadata (page count, file size) |
| GET | `/api/pdf/<compound>/toc` | PDF table of contents (chapter numbers merged into titles) |
| GET | `/api/pdf/<compound>/page/<n>` | Render page N as HTML |
| GET | `/api/thumbnails/<compound>` | Generate page thumbnails (supports `?start=&end=` range) |

### Route Pattern

PDFs are referenced by compound path `dir_key/filename.pdf`. The `_resolve()` helper splits `dir_key` from filename. `dir_key` maps to a filesystem path via `config.json`.

## PDF Processing — `pdf_utils.py`

Library: **PyMuPDF (fitz)**

### Full Rendering Pipeline (`extract_page_html`)

```
page.get_text("dict") → blocks → lines → spans
           │
           ├─ _detect_table_grid()       ← grid-based table detection (runs first)
           ├─ _merge_bullet_blocks()     ← merge ∙ / 1. markers into adjacent content
           ├─ _merge_chapter_numbers()   ← merge decorative "1" into chapter title
           ├─ _merge_adjacent_mono_blocks() ← merge consecutive monospace blocks
           ├─ For each remaining block:
           │    └─ _block_to_html() → _line_tag() / _make_element() / _span_to_html()
           ├─ y-bucket grouping → flex row layout for inline code+text
           └─ Blank page fallback → placeholder text
```

### Table Detection (`_detect_table_grid`)

Detects grid-aligned blocks and renders as `<table class="pdf-table">` with visible borders, zebra striping, and highlighted header row.

**Pipeline steps:**
1. **Candidate filtering** — skip code blocks, monospace text, narrow blocks (<15pt), full-width body text (>55% page width unless multi-column)
2. **Multi-column block splitting** — blocks with lines at different x-positions split by column group (20pt bucket); same-column multi-line text merged into one cell (e.g. "VS" + "Code" → "VS Code"); uses **actual line y-range** so header cells and data continuations within the same block land in different rows
3. **Row grouping** — y-center proximity with **18pt tolerance** and **mean-of-all anchor** (prevents drift that would merge separate header lines)
4. **Column detection** — x0 **clustering across ALL rows** (25pt gap tolerance, greedy algorithm); columns must appear in ≥40% of rows to avoid phantom columns from outlier rows
5. **Column assignment** — each block maps to nearest column anchor (30pt max distance)
6. **Horizontal merge** — same-row same-column cells merged; lines sorted by **y-position** so "Amazon" stays above "CodeWhisperer"
7. **Vertical merge** — sparse continuation rows (≤3 cells) merged upward; **unique columns** transferred to upper row (prevents orphaned rightmost columns from being dropped)
8. **Minimum rows** — ≥2 rows required before AND after merging; rows with <2 cells dropped after merge

### Span Filtering (`_span_to_html`)

- `size < 0.5pt` → filtered (invisible index markers, whitespace glyphs)
- Control characters (`\x00`–`\x1f`, `\x7f`, U+FFFD) → stripped

### Alignment Detection (`_detect_alignment`)

Three-layer defense against false center-alignment:
1. Left-margin anchor: x0 < 22% page width → `"left"`
2. Right-edge proximity: x1 > 85% page width or block > 70% page width → `"left"`
3. Center midpoint check: x-midpoint within ±12% of page center → `"center"`
4. x0 > 55% page width → `"right"`
5. Default → `"left"`

### Heading Detection (`_line_tag`)

Heuristic based on font size (largest span in the line):
- ≥24pt → `<h1>`
- ≥18pt → `<h2>`
- ≥14pt + mostly bold → `<h3>`
- otherwise → `<p>`

### Code Block Pipeline

1. `_is_monospace()` — flag bit 8 (monospace) or known monospace font name (Consolas, Courier, etc.)
2. `_is_code_block()` — ≥2 lines, all-monospace spans
3. `_block_is_all_mono()` — every span in block is monospace
4. `_merge_adjacent_mono_blocks()` — merge consecutive mono blocks (200pt y-gap cutoff); handles line number blocks (`_is_line_number_block`: numeric, small font), embedded images, and position-sorted merging; detects y-restart pattern for new code block boundaries
5. Merged blocks rendered as single `<pre>` with `is_code=True` → newline-preserving output

### Text Continuity (`_make_element`)

Body text paragraphs use **space-joining** instead of `<br>` tags. PDF line breaks are column-wrap artifacts, not author formatting.

**Mid-word break detection:** If consecutive lines are in the same column (x0 within 5pt) and the next line's first word is ≤3 characters, join without space (e.g. "consistenc" + "y" → "consistency").

**x-jump splitting:** Lines in the same block whose x0 differs by >50pt trigger a column break — the block is split into separate elements (handles multi-column table headers).

### Bullet & Number Merging (`_merge_bullet_blocks`)

- Detects bullet chars (•, ●, ○, ▪, –, —) and numbered markers (e.g. "1.", "2.")
- Two-pass approach: collect markers by y-position into a map, then for each non-marker block check if a marker exists at a nearby y-position
- Merged text prepended to the following content block

### Chapter Number Merging (`_merge_chapter_numbers`)

Merges decorative chapter numbers (single 1–2 digit number at >20pt font, single line) into the following heading block (≥18pt font). Prevents orphan `<h1>1</h1>` before the actual title.

### Page Header/Footer Detection

Blocks within 50pt of page top or bottom → class `page-header-footer` (small, light gray, de-emphasized). Code blocks excluded from this detection.

### Image Handling

- Type 1 blocks (images within PDF): base64-encoded inline `<img>` within `<figure>`
- Inside code blocks: image HTML is NOT escaped (raw `<figure>` embedded in `<pre>`)
- Blank page fallback: when no text blocks exist, renders placeholder text instead of full-page screenshot

### Garbled Detection (`_is_garbled`)

Strips HTML tags, checks ratio of letters/numbers/punctuation to total non-whitespace characters. Below 0.4 → triggers image fallback for the whole page.

### TOC Extraction (`get_pdf_toc`)

`doc.get_toc()` returns `[{level, title, page}]`. Bare chapter numbers adjacent to titles are merged (e.g. "1" + "Context Engineering" → "1  Context Engineering").

## Frontend — `static/js/`

Modular vanilla JavaScript. No frameworks, no build step. 8 modules:

| Module | Purpose |
|--------|---------|
| `app.js` | Main orchestrator, event binding, page navigation |
| `store.js` | State management, localStorage persistence, PDF list cache |
| `renderer.js` | Page rendering, table-row flex layout, viewport management |
| `sidebar.js` | Directory tree, TOC panel, progress display |
| `scroller.js` | Infinite scroll page loading, prefetch |
| `loader.js` | API communication, progressive page loading |
| `theme.js` | Dual-theme system (chrome UI theme + document view theme) |
| `thumbnails.js` | SFT (Small Format Thumbnail) grid for quick navigation |

### Persistence (`store.js`)

All via `localStorage`:
- `pdf_reader_progress` — per-file read page arrays
- `pdf_reader_bookmark` — per-file last-read page
- `pdf_reader_chrome_theme` — UI theme (`chrome-light` / `chrome-dark`)
- `pdf_reader_doc_theme` — document theme (`doc-theme-normal` / `doc-theme-sepia` / `doc-theme-invert`)

### Directory Tree

Lazy-fetched via `/api/browse/{dirKey}/{subpath}`. Cached in `state.browseCache`. Each directory node tracks expand/collapse state. Non-PDF files are ignored.

### Keyboard Navigation

← → arrow keys trigger prev/next page. Suppressed when an `<input>` is focused.

## Styling — `static/style.css`

### Dual-Theme System

**Chrome theme** (UI chrome — sidebar, toolbar): `chrome-light` (default), `chrome-dark`

**Document theme** (viewer content — page segments): `doc-theme-normal`, `doc-theme-sepia`, `doc-theme-invert`

### Table Styling (`table.pdf-table`)

- Collapsed borders, visible `border: 1px solid #bbb`
- Header row: dark gray background + bold font
- Zebra striping: even rows light gray background
- `overflow-wrap: break-word; word-break: break-word` — prevents overflow
- `td span { color: inherit !important }` — neutralizes PDF text colors for readability
- Page segment: `overflow-x: auto` — horizontal scroll as last resort

### Code Block Styling (`pre` / `code`)

- Light gray background (`#f5f5f0`), `1px solid #e0e0d8` border
- Monospace font stack: Consolas / Courier New / Monaco
- `pre code span { color: inherit !important }` — strips PDF syntax-highlighting colors
- `pre { color: #1a1a2e }` — dark text on light background for contrast
- `pre { white-space: pre-wrap; word-break: break-word }` — wraps long lines

### Page Layout

- Page segment: max-width 750px, centered, 40px/48px padding
- Page divider: horizontal rule with "── 第 XX 页 ──" label between pages
- Header/footer: `page-header-footer` class → 0.7em, light gray, subdued

## Configuration — `config.json`

```json
{
  "pdf_directories": [
    {"key": "books",   "path": "../pdf_books",                                "label": "电子书"},
    {"key": "manuals", "path": "/mnt/hgfs/linux_books/OceanOfPDF/01_AI_ML",  "label": "AIML"}
  ]
}
```

- Multiple directories sharing the same `key` are allowed — all are scanned in `/api/pdfs`, but only the first entry for a key is used in `/api/browse/`.
- `CONFIG_PATH` env var overrides the config file location (default: `config.json`).
- `PORT` env var overrides the server port (default: `5000`).

## Testing

- **43 tests** across 3 files:
  - `test_rendering.py` — 23 unit tests (span filtering, monospace detection, code blocks, alignment, merging)
  - `test_render_quality.py` — 12 integration tests (code blocks, images, headers, line numbers, **table column detection**, **multi-line header merging**)
  - `test_thumbnails.py` — 5 API tests (thumbnail endpoints, error handling, range support)
- **TDD required**: write/update tests before code changes (`CLAUDE.md` rule)
- Run: `python3 -m pytest tests/ -v`

## Dependencies

- Flask 3.x
- PyMuPDF (fitz)
