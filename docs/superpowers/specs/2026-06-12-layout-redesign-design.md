# Layout Architecture Redesign — Design Spec

**Date:** 2026-06-12
**Status:** Approved (5/5 decisions locked)
**Research basis:** Deep-research workflow (2026-06-11, 74 min, 105 sub-agents)

## Overview

Redesign the PDF reader from a flat single-page-view layout to a professional four-container architecture matching PDF.js / Adobe Acrobat / Apple Books patterns. Five research-backed design decisions form the foundation.

## Design Decisions

### 1. Four-Container Layout Architecture

**Choice:** `#outerContainer > #sidebarContainer + #mainContainer(#toolbar + #viewerContainer)`

**Rationale:** PDF.js standard architecture, validated by VS Code PDF Viewer embedding. Replaces current floating sidebar + flat content area.

- `#outerContainer` — root flex container, full viewport height
- `#sidebarContainer` — fixed left panel (280px default, collapsible), contains TOC + SFT thumbnails + reading progress
- `#mainContainer` — remaining width, flex column
  - `#toolbar` — file name, chrome theme toggle, doc theme toggle, page indicator
  - `#viewerContainer` — scrollable content area, continuous scroll

### 2. Space-Filling Thumbnails (SFT)

**Choice:** 3-column grid thumbnail layout in sidebar, responsive column count.

**Rationale:** CHI 2006 controlled experiment (n=32): SFT page-finding 6.5s vs scrollbar thumbnails 10.4s (F1,31=66.6, p<.01).

- Column count adapts to sidebar width (2 cols @ 220px, 3 cols @ 280px, 4 cols @ 340px)
- Virtualized rendering: only render thumbnails in viewport ± 2 rows buffer
- Bidirectional sync: scroll viewer -> highlight thumbnail; click thumbnail -> scroll viewer
- Backend: `GET /api/pdf/<compound>/thumbnails?start=N&end=M` returns base64 thumbnails (dpi=30)

### 3. Dual-Layer Theme System

**Choice:** Independent Chrome theme (dark/light) × Document theme (normal/sepia/invert).

**Rationale:** Velora pattern — pdfTheme state managed independently from app dark/light mode. Allows dark chrome + sepia doc, light chrome + invert doc, etc.

- Chrome theme: CSS custom properties on `:root` (`--chrome-bg`, `--chrome-text`, `--chrome-border`, etc.)
- Document theme: CSS `filter` property applied to `#viewerContainer` only
  - Normal: `none`
  - Sepia: `sepia(100%) brightness(90%) hue-rotate(10deg)`
  - Invert: `invert(0.92) hue-rotate(180deg)`
- Transition: `filter 0.2s ease-out`
- Persistence: localStorage keys `pdf_reader_chrome_theme` and `pdf_reader_doc_theme`

### 4. Viewport Rendering with DOM Virtualization

**Choice:** IntersectionObserver-driven viewport-only rendering with pre-fetch and DOM recycling.

**Rationale:** EmbedPDF thumbnail plugin virtualizes rendering. Syncfusion research shows viewport-only rendering is essential for smooth large-document scrolling.

- Load visible pages ± 1 buffer page into DOM
- Pages scrolled out of buffer range replaced with placeholder divs (preserve scroll height)
- Pre-fetch next/prev 5 pages in background, cache in Map
- Scroll debounce: 100ms delay before triggering render during fast scroll
- Placeholder height calculated from known page count and estimated page pixel height

### 5. Composable Module Architecture

**Choice:** Split monolithic `app.js` into 8 focused modules with unidirectional data flow.

**Rationale:** react-pdf composable primitives (Document/Page/Outline/Thumbnail). EmbedPDF plugin architecture.

| Module | File | Responsibility | Est. Lines |
|--------|------|----------------|------------|
| App | `js/app.js` | Init, module wiring, global event binding | ~50 |
| Store | `js/store.js` | State object, localStorage read/write | ~60 |
| DocumentLoader | `js/loader.js` | API calls, response caching, pre-fetch queue | ~80 |
| PageRenderer | `js/renderer.js` | HTML->DOM insertion, virtual DOM recycling, page dividers | ~120 |
| ScrollController | `js/scroller.js` | IntersectionObserver, debounce, currentPage tracking | ~70 |
| ThumbnailPanel | `js/thumbnails.js` | SFT grid rendering, virtualization, click-to-jump, highlight sync | ~100 |
| ThemeManager | `js/theme.js` | Chrome theme toggle, doc theme filter, CSS variable application | ~60 |
| Sidebar | `js/sidebar.js` | Directory tree, TOC rendering, progress list (existing logic refactored) | ~150 |

Data flow (unidirectional):
```
DocumentLoader (fetch -> cache)
       |
       v
PageRenderer (cache -> DOM)
       |
       v
ScrollController (IO -> currentPage)
     /       \
    v         v
ThumbnailPanel   Breadcrumb/Progress
       ^
ThemeManager (CSS filters over viewerContainer only)
```

## API Changes

### New: `GET /api/pdf/<compound>/thumbnails`

Returns low-resolution page thumbnails for the SFT grid.

**Query params:** `?start=1&end=20` (page range, 1-based, inclusive)

**Response:**
```json
{
  "thumbnails": [
    {"page": 1, "image": "data:image/png;base64,...", "width": 85, "height": 110}
  ],
  "total_pages": 200,
  "start": 1,
  "end": 20
}
```

**Implementation:** PyMuPDF `page.get_pixmap(dpi=30)`, scale to target width. PNG base64.

### Existing (unchanged)

All existing API endpoints remain as-is. The new scroll mode uses the same `/api/pdf/<compound>/page/<n>` endpoint for content HTML — just calls it N times for visible pages instead of once.

## CSS Architecture

### Chrome Theme Variables (`:root`)
```css
--chrome-bg, --chrome-text, --chrome-border,
--toolbar-bg, --sidebar-bg, --viewer-bg,
--accent, --accent-text
```

### Document Theme Filters (`#viewerContainer`)
```css
.doc-theme-normal { filter: none; }
.doc-theme-sepia  { filter: sepia(100%) brightness(90%) hue-rotate(10deg); }
.doc-theme-invert { filter: invert(0.92) hue-rotate(180deg); }
```

## HTML Structure

```html
<div id="outerContainer">
  <div id="sidebarContainer">
    <div id="toc-panel">...</div>
    <div id="thumbnail-panel">...</div>
    <div id="progress-panel">...</div>
  </div>
  <div id="mainContainer">
    <div id="toolbar">...</div>
    <div id="viewerContainer">
      <div class="page-divider">── 第 3 页 ──</div>
      <div class="page-segment" data-page="3">...</div>
      <div class="page-divider active">── 第 4 页 ● ──</div>
      <div class="page-segment" data-page="4">...</div>
    </div>
  </div>
</div>
```

## Success Criteria

1. 200-page PDF scrolls smoothly without memory growth beyond initial + 20%
2. SFT thumbnails render in sidebar grid layout (3 cols at standard width)
3. Scrolling changes current page highlights in both thumbnails and page indicator
4. Clicking a thumbnail scrolls viewer to that page's divider
5. Changing doc theme only affects viewerContainer, not chrome
6. Changing chrome theme only affects chrome, not document
7. All existing features preserved: directory tree, TOC, bookmarks, progress, keyboard navigation

## Implementation Order

1. Backend: thumbnail API (`pdf_utils.py` + `app.py` route)
2. CSS: Chrome theme variables + doc theme filters replace old style.css
3. HTML: New four-container DOM structure
4. JS Module 1: `store.js` (state + localStorage)
5. JS Module 2: `theme.js` (ThemeManager)
6. JS Module 3: `loader.js` (DocumentLoader)
7. JS Module 4: `renderer.js` (PageRenderer + virtualization)
8. JS Module 5: `scroller.js` (ScrollController)
9. JS Module 6: `thumbnails.js` (ThumbnailPanel)
10. JS Module 7: `sidebar.js` (refactor existing logic)
11. JS Module 8: `app.js` (wire everything)
12. Integration testing + manual verification
13. Remove old CSS theme classes (classic/night/fresh -> chrome dark/light)
