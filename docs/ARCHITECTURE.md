# Architecture

## Overview

Flask 单页应用，后端 Python + PyMuPDF 处理 PDF，前端无框架原生 JavaScript，本地浏览器存储阅读进度。

## Backend — `app.py`

### API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/` | Index page |
| GET | `/about` | About page |
| GET | `/api/dirs` | List configured PDF source directories |
| GET | `/api/browse/<dir_key>/<path>` | Lazily browse directory tree (subdirs + PDF filenames) |
| GET | `/api/pdfs` | List all PDFs across all dirs with page counts |
| GET | `/api/pdf/<compound>/info` | PDF metadata (page count, file size) |
| GET | `/api/pdf/<compound>/toc` | PDF table of contents |
| GET | `/api/pdf/<compound>/page/<n>` | Render page N as HTML |

### Route Pattern

PDFs are referenced by compound path `dir_key/filename.pdf`. The `_resolve()` helper splits `dir_key` from filename. `dir_key` maps to a filesystem path via `config.json`.

## PDF Processing — `pdf_utils.py`

Library: **PyMuPDF (fitz) v1.25.5**

### Text Extraction Pipeline

1. `page.get_text("dict")` → blocks → lines → spans
2. `_span_to_html()` — converts each span to HTML with bold/italic/color inline tags
3. `_line_tag()` — heuristic heading detection via font size thresholds:
   - ≥24pt → `<h1>`
   - ≥18pt → `<h2>`
   - ≥14pt + mostly bold → `<h3>`
   - otherwise → `<p>`
4. `_detect_alignment()` — center/right/left from bounding box midpoint
5. `_detect_indent()` — left-padding from bbox x offset
6. `_make_element()` — groups consecutive same-tag lines into one element, preserving paragraph continuity for browser translation plugins

### Image Handling

- Type 1 blocks (images within PDF): base64-encoded inline `<img>`
- Full-page fallback: when text is garbled or empty, `page.get_pixmap(dpi=150)` renders page as screenshot PNG

### Garbled Detection

`_is_garbled()` strips HTML tags, then checks the ratio of letters/numbers/punctuation to total non-whitespace characters. Below 0.4 → triggers image fallback.

### TOC Extraction

`doc.get_toc()` returns `[{level, title, page}]`.

## Frontend — `static/app.js`

Pure vanilla JavaScript SPA. No frameworks, no build step.

### State (`state` object)

| Field | Type | Purpose |
|-------|------|---------|
| `currentPdf` | string | Currently open PDF compound path |
| `totalPages` | number | Total pages of current PDF |
| `currentPage` | number | Current page number |
| `toc` | array | Table of contents entries |
| `progress` | object | `{filename: [readPageNumbers]}` |
| `bookmarks` | object | `{filename: lastPage}` |
| `dirs` | array | Configured directory list |
| `browseCache` | object | `{"dirKey:path": {expanded, data}}` — lazy-loaded directory tree |
| `pdfInfoCache` | object | `{compound: {pages}}` |
| `sidebarOpen` | boolean | Sidebar visibility |
| `theme` | string | Current theme CSS class |

### Persistence

All via `localStorage`:
- `pdf_reader_progress` — per-file read page arrays
- `pdf_reader_bookmark` — per-file last-read page
- `pdf_reader_theme` — theme class name

### Directory Tree

Lazy-fetched via `/api/browse/{dirKey}/{subpath}`. Cached in `state.browseCache`. Each directory node tracks expand/collapse state. Non-PDF files are ignored.

### Keyboard Navigation

← → arrow keys trigger `navigatePrev()` / `navigateNext()`. Suppressed when an `<input>` is focused.

## Styling — `static/style.css`

Three themes applied via CSS class on `<body>`:

| Theme class | Name | Colors |
|-------------|------|--------|
| `theme-classic` | 经典纸页 | Warm brown on cream |
| `theme-night` | 暗夜护眼 | Light text on dark gray |
| `theme-fresh` | 新绿清新 | Green accents on white |

## Configuration — `config.json`

```json
{
  "pdf_directories": [
    {"key": "books",  "path": "../pdf_books",                               "label": "电子书"},
    {"key": "ai",     "path": "/mnt/hgfs/linux_books/OceanOfPDF/01_AI_ML",  "label": "AIML"}
  ]
}
```

- Multiple directories sharing the same `key` are allowed — all are scanned in `/api/pdfs`, but only the first entry for a key is used in `/api/browse/`.
- `CONFIG_PATH` env var overrides the config file location (default: `config.json`).

## Dependencies

- Flask 3.1.1
- PyMuPDF 1.25.5
