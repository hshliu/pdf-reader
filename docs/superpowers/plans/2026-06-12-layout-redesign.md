# Layout Architecture Redesign — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Redesign PDF reader from flat single-page layout to four-container professional architecture with SFT thumbnails, dual-layer theming, viewport virtualization, and composable JS modules.

**Architecture:** PDF.js-style four-container layout (#outerContainer > #sidebarContainer + #mainContainer(#toolbar + #viewerContainer)). Five independent JS modules with unidirectional data flow. CSS custom properties for chrome theme, CSS filter for document theme.

**Tech Stack:** Python 3.10, Flask 3.1, PyMuPDF 1.27, vanilla JS (no framework), pytest

**Design Spec:** `docs/superpowers/specs/2026-06-12-layout-redesign-design.md`

---

### Task 1: Test Infrastructure + Requirements Verification

**Files:**
- Create: `tests/__init__.py`
- Create: `tests/conftest.py`
- Modify: `requirements.txt` (add pytest if missing)

- [ ] **Step 1: Install test dependencies**

```bash
pip3 install pytest pytest-flask 2>&1 | tail -3
```

- [ ] **Step 2: Create test directory and files**

```bash
mkdir -p tests
```

`tests/__init__.py`:
```python
```

`tests/conftest.py`:
```python
import os
import pytest
from app import app as flask_app


@pytest.fixture
def app():
    os.environ["CONFIG_PATH"] = "config.json"
    flask_app.config["TESTING"] = True
    yield flask_app


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def sample_pdf_path():
    """Find any available PDF for testing."""
    import app
    for d in app.PDF_DIRECTORIES:
        path = d["path"]
        if os.path.isdir(path):
            for f in sorted(os.listdir(path)):
                if f.lower().endswith(".pdf"):
                    return os.path.join(path, f)
    pytest.skip("No PDF files available for testing")
```

- [ ] **Step 3: Verify pytest works with one trivial test**

```bash
python3 -m pytest tests/ -v
```
Expected: "no tests ran" (empty but no errors)

- [ ] **Step 4: Commit**

```bash
git add tests/ requirements.txt
git commit -m "test: add pytest infrastructure with Flask fixtures"
```

---

### Task 2: Backend — Thumbnail API (TDD)

**Files:**
- Create: `tests/test_thumbnails.py`
- Modify: `pdf_utils.py` (add `get_thumbnails` function)
- Modify: `app.py` (add route, add `request` to imports)

- [ ] **Step 1: Write failing tests**

`tests/test_thumbnails.py`:
```python
import pytest


def test_thumbnails_404_for_nonexistent_dir(client):
    resp = client.get("/api/pdf/nonexistent/some.pdf/thumbnails")
    assert resp.status_code == 404


def test_thumbnails_404_for_nonexistent_file(client, sample_pdf_path):
    resp = client.get("/api/pdf/books/nonexistent.pdf/thumbnails")
    assert resp.status_code == 404


def test_thumbnails_returns_valid_json(client, sample_pdf_path):
    import app
    for d in app.PDF_DIRECTORIES:
        dpath = d["path"]
        if sample_pdf_path.startswith(dpath):
            dir_key = d["key"]
            rel = sample_pdf_path[len(dpath):].lstrip("/")
            compound = dir_key + "/" + rel
            break
    else:
        pytest.skip("Cannot resolve compound")

    resp = client.get(f"/api/pdf/{compound}/thumbnails")
    assert resp.status_code == 200
    data = resp.get_json()
    assert "thumbnails" in data
    assert "total_pages" in data
    assert isinstance(data["thumbnails"], list)
    assert data["total_pages"] > 0


def test_thumbnails_range_support(client, sample_pdf_path):
    import app
    for d in app.PDF_DIRECTORIES:
        dpath = d["path"]
        if sample_pdf_path.startswith(dpath):
            dir_key = d["key"]
            rel = sample_pdf_path[len(dpath):].lstrip("/")
            compound = dir_key + "/" + rel
            break
    else:
        pytest.skip("Cannot resolve compound")

    resp = client.get(f"/api/pdf/{compound}/thumbnails?start=1&end=3")
    assert resp.status_code == 200
    data = resp.get_json()
    assert len(data["thumbnails"]) == 3
    for t in data["thumbnails"]:
        assert "page" in t
        assert "image" in t
        assert t["image"].startswith("data:image/png;base64,")


def test_thumbnails_range_clamped_to_total(client, sample_pdf_path):
    import app
    for d in app.PDF_DIRECTORIES:
        dpath = d["path"]
        if sample_pdf_path.startswith(dpath):
            dir_key = d["key"]
            rel = sample_pdf_path[len(dpath):].lstrip("/")
            compound = dir_key + "/" + rel
            break
    else:
        pytest.skip("Cannot resolve compound")

    resp = client.get(f"/api/pdf/{compound}/thumbnails?start=1&end=99999")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["end"] == data["total_pages"]
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
python3 -m pytest tests/test_thumbnails.py -v
```
Expected: tests that hit valid PDFs FAIL (404 instead of 200, since route doesn't exist yet).

- [ ] **Step 3: Implement `get_thumbnails` in pdf_utils.py**

Append to `pdf_utils.py`:

```python
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

    thumb_width = 170  # ~2x display size for retina
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
```

- [ ] **Step 4: Add route to app.py**

Add `request` to Flask imports (line 3):
```python
from flask import Flask, jsonify, render_template, request
```

Add route after the `/api/pdf/<path:compound>/toc` block:
```python
@app.route("/api/pdf/<path:compound>/thumbnails")
def pdf_thumbnails(compound):
    dir_key, filename = _resolve(compound)
    if dir_key not in DIR_MAP:
        return jsonify({"error": "PDF not found"}), 404
    filepath = os.path.join(DIR_MAP[dir_key], filename)
    if not os.path.isfile(filepath) or not filename.lower().endswith(".pdf"):
        return jsonify({"error": "PDF not found"}), 404
    try:
        start = int(request.args.get("start", 1))
        end = request.args.get("end", None)
        if end is not None:
            end = int(end)
        result = pdf_utils.get_thumbnails(filepath, start, end)
        return jsonify(result)
    except Exception as e:
        return jsonify({"error": str(e)}), 500
```

- [ ] **Step 5: Run tests — all should pass**

```bash
python3 -m pytest tests/test_thumbnails.py -v
```
Expected: 5 PASS

- [ ] **Step 6: Commit**

```bash
git add tests/test_thumbnails.py pdf_utils.py app.py
git commit -m "feat: add thumbnail API endpoint with page range support"
```

---

### Task 3: CSS — Chrome Variables + Document Filters

**Files:**
- Rewrite: `static/style.css`

- [ ] **Step 1: Write new style.css with CSS custom properties**

Write `static/style.css`:

```css
/* === Reset === */
* { margin: 0; padding: 0; box-sizing: border-box; }

/* === Chrome Theme Variables (Light default) === */
:root {
  --chrome-bg: #f5f5f0;
  --chrome-text: #1a1a1a;
  --chrome-text-secondary: #888;
  --chrome-border: #ddd;
  --sidebar-bg: #fff;
  --toolbar-bg: #fff;
  --viewer-outer-bg: #f7f7f2;
  --accent: #1a1a1a;
  --accent-text: #fff;
  --hover-bg: #e8e8e3;
  --badge-bg: #e8e8e3;
  --badge-text: #666;
  --button-bg: #fff;
  --button-border: #ddd;
  --button-text: #555;
  --page-bg: #fff;
  --page-shadow: 0 1px 4px rgba(0,0,0,0.06);
  --divider-color: #ddd;
  --progress-bar-bg: #e0e0d8;
  --progress-bar-fill: #2e7d32;
}

.chrome-dark {
  --chrome-bg: #1e1e1e;
  --chrome-text: #d4d4d4;
  --chrome-text-secondary: #999;
  --chrome-border: #3a3a3a;
  --sidebar-bg: #252526;
  --toolbar-bg: #252526;
  --viewer-outer-bg: #1e1e1e;
  --accent: #569cd6;
  --accent-text: #1e1e1e;
  --hover-bg: #333;
  --badge-bg: #3a3a3a;
  --badge-text: #aaa;
  --button-bg: #333;
  --button-border: #3a3a3a;
  --button-text: #ccc;
  --page-bg: #252526;
  --page-shadow: 0 1px 4px rgba(0,0,0,0.2);
  --divider-color: #3a3a3a;
  --progress-bar-bg: #3a3a3a;
  --progress-bar-fill: #4ec9b0;
}

body {
  font-family: "Georgia", "Noto Serif SC", "Merriweather", serif;
  background: var(--viewer-outer-bg);
  color: var(--chrome-text);
  height: 100vh;
  overflow: hidden;
}

/* === Four-Container Layout === */
#outerContainer {
  display: flex;
  height: 100vh;
  width: 100%;
}

#sidebarContainer {
  width: 280px;
  flex-shrink: 0;
  background: var(--sidebar-bg);
  border-right: 1px solid var(--chrome-border);
  overflow-y: auto;
  display: flex;
  flex-direction: column;
}

#sidebarContainer.collapsed {
  display: none;
}

#mainContainer {
  flex: 1;
  display: flex;
  flex-direction: column;
  min-width: 0;
}

/* === Toolbar === */
#toolbar {
  background: var(--toolbar-bg);
  border-bottom: 1px solid var(--chrome-border);
  padding: 8px 16px;
  display: flex;
  align-items: center;
  gap: 12px;
  flex-shrink: 0;
  font-size: 13px;
}

.toolbar-brand {
  font-weight: 700;
  font-size: 16px;
  color: var(--accent);
}

.toolbar-filename {
  color: var(--chrome-text-secondary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  flex: 1;
}

.toolbar-page-indicator {
  font-weight: 600;
  color: var(--chrome-text);
  flex-shrink: 0;
}

.toolbar-btn {
  background: none;
  border: 1px solid var(--chrome-border);
  padding: 4px 8px;
  border-radius: 4px;
  cursor: pointer;
  font-size: 14px;
  color: var(--chrome-text);
  line-height: 1;
}

.toolbar-btn:hover { background: var(--hover-bg); }

/* === Sidebar Toggle === */
#sidebarToggle {
  background: none;
  border: 1px solid var(--chrome-border);
  font-size: 16px;
  cursor: pointer;
  padding: 2px 8px;
  border-radius: 4px;
  color: var(--chrome-text);
  line-height: 1;
}

#sidebarToggle:hover { background: var(--hover-bg); }

/* === Sidebar Sections === */
.sidebar-section {
  padding: 12px;
  border-bottom: 1px solid var(--chrome-border);
}

.sidebar-heading {
  font-size: 11px;
  font-weight: 700;
  color: var(--chrome-text-secondary);
  text-transform: uppercase;
  letter-spacing: 1px;
  margin-bottom: 8px;
  border-bottom: 2px solid var(--accent);
  padding-bottom: 4px;
}

/* === Directory Tree === */
.tree-dir-header {
  padding: 6px 8px;
  border-radius: 3px;
  cursor: pointer;
  font-size: 13px;
  font-weight: 600;
  color: var(--chrome-text);
  user-select: none;
}

.tree-dir-header:hover { background: var(--hover-bg); }
.tree-item { font-weight: 400; font-size: 12px; }

.tree-toggle {
  display: inline-block;
  width: 14px;
  font-size: 10px;
  color: var(--chrome-text-secondary);
}

.pdf-item {
  padding: 6px 8px;
  border-radius: 3px;
  cursor: pointer;
  font-size: 13px;
  color: var(--chrome-text);
}

.pdf-item:hover { background: var(--hover-bg); }
.pdf-item.active { background: var(--accent); color: var(--accent-text); }
.pdf-item.has-progress { font-weight: 600; }

/* === TOC === */
.toc-item {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 8px;
  padding: 4px 8px;
  border-radius: 3px;
  cursor: pointer;
  font-size: 12px;
  color: var(--chrome-text);
}

.toc-item:hover { background: var(--hover-bg); }
.toc-item.active { background: var(--accent); color: var(--accent-text); }
.toc-title { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; flex: 1; }
.toc-page {
  flex-shrink: 0;
  font-size: 10px;
  color: var(--chrome-text-secondary);
}
.toc-item.active .toc-page { color: var(--accent-text); opacity: 0.7; }

/* === SFT Thumbnail Grid === */
.thumbnail-grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 4px;
}

.thumbnail-card {
  border: 2px solid transparent;
  border-radius: 3px;
  overflow: hidden;
  cursor: pointer;
  background: var(--badge-bg);
}

.thumbnail-card.active {
  border-color: var(--accent);
}

.thumbnail-card img {
  width: 100%;
  height: auto;
  display: block;
}

.thumbnail-label {
  font-size: 10px;
  text-align: center;
  padding: 2px;
  color: var(--chrome-text-secondary);
}

/* === Progress List === */
.progress-row {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 3px 0;
  font-size: 12px;
}

.progress-name {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  max-width: 120px;
}

.progress-bar-mini {
  width: 50px;
  height: 3px;
  background: var(--progress-bar-bg);
  border-radius: 2px;
  overflow: hidden;
  flex-shrink: 0;
}

.progress-bar-mini-fill {
  height: 100%;
  background: var(--progress-bar-fill);
  border-radius: 2px;
  transition: width 0.3s;
}

.progress-count {
  font-size: 10px;
  color: var(--chrome-text-secondary);
  flex-shrink: 0;
}

.empty-sidebar {
  color: var(--chrome-text-secondary);
  font-size: 13px;
  padding: 4px 0;
}

/* === Viewer Container === */
#viewerContainer {
  flex: 1;
  overflow-y: auto;
  padding: 24px 48px;
  transition: filter 0.2s ease-out;
}

/* Document theme filters */
#viewerContainer.doc-theme-normal { filter: none; }
#viewerContainer.doc-theme-sepia {
  filter: sepia(100%) brightness(90%) hue-rotate(10deg);
}
#viewerContainer.doc-theme-invert {
  filter: invert(0.92) hue-rotate(180deg);
}

/* === Page Segments === */
.page-segment {
  background: var(--page-bg);
  border-radius: 4px;
  padding: 40px 48px;
  box-shadow: var(--page-shadow);
  max-width: 750px;
  margin: 0 auto;
  line-height: 1.8;
  font-size: 16px;
}

.page-divider {
  max-width: 750px;
  margin: 16px auto;
  display: flex;
  align-items: center;
  gap: 16px;
}

.page-divider::before,
.page-divider::after {
  content: "";
  flex: 1;
  height: 1px;
  background: var(--divider-color);
}

.page-divider-text {
  font-size: 12px;
  font-weight: 700;
  color: var(--chrome-text-secondary);
  letter-spacing: 1px;
  white-space: nowrap;
}

.page-divider.active .page-divider-text {
  color: var(--accent);
  font-size: 14px;
}

.page-divider.active::before,
.page-divider.active::after {
  background: var(--accent);
  height: 2px;
}

/* Article typography */
.page-segment h1 {
  font-size: 26px; font-weight: 700; margin: 0 0 14px; line-height: 1.3;
}
.page-segment h2 {
  font-size: 20px; font-weight: 700; margin: 20px 0 10px; line-height: 1.4;
}
.page-segment h3 {
  font-size: 17px; font-weight: 700; margin: 16px 0 8px; line-height: 1.4;
}
.page-segment p { margin: 0 0 12px; }
.page-segment figure { margin: 16px 0; text-align: center; }
.page-segment figure img {
  max-width: 100%; height: auto; border-radius: 2px;
}

.page-loading-placeholder {
  max-width: 750px;
  margin: 0 auto;
  text-align: center;
  padding: 24px;
  color: var(--chrome-text-secondary);
  font-size: 13px;
}

.welcome-screen {
  display: flex;
  align-items: center;
  justify-content: center;
  height: 100%;
  font-size: 16px;
  color: var(--chrome-text-secondary);
}
```

- [ ] **Step 2: Commit**

```bash
git add static/style.css
git commit -m "refactor: dual-layer CSS with chrome variables and doc CSS filters"
```

---

### Task 4: HTML — Four-Container DOM Structure

**Files:**
- Rewrite: `templates/index.html`

- [ ] **Step 1: Read current template**

```bash
cat templates/index.html
```

(Check for existing Jinja blocks/template inheritance before replacing.)

- [ ] **Step 2: Write new index.html**

Write `templates/index.html`:

```html
<!DOCTYPE html>
<html lang="zh">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>PDF Reader</title>
<link rel="stylesheet" href="/static/style.css">
</head>
<body>

<div id="outerContainer">
  <div id="sidebarContainer">
    <div class="sidebar-section" id="file-tree-section">
      <div class="sidebar-heading">📂 目录</div>
      <div id="pdf-list"></div>
    </div>
    <div class="sidebar-section" id="toc-section">
      <div class="sidebar-heading">📑 大纲</div>
      <div id="toc-list"></div>
    </div>
    <div class="sidebar-section" id="thumbnail-section">
      <div class="sidebar-heading">🖼️ 页面</div>
      <div class="thumbnail-grid" id="thumbnail-grid"></div>
    </div>
    <div class="sidebar-section" id="progress-section">
      <div class="sidebar-heading">📊 进度</div>
      <div id="progress-list"></div>
    </div>
  </div>

  <div id="mainContainer">
    <div id="toolbar">
      <button id="sidebarToggle" title="切换侧边栏">☰</button>
      <span class="toolbar-brand">PDF Reader</span>
      <span class="toolbar-filename" id="toolbar-filename"></span>
      <span class="toolbar-page-indicator" id="toolbar-page"></span>
      <button class="toolbar-btn" id="btn-chrome-theme" title="界面主题">🌗</button>
      <button class="toolbar-btn" id="btn-doc-theme" title="文档主题">🎨</button>
    </div>

    <div id="viewerContainer" class="doc-theme-normal">
      <div class="welcome-screen" id="welcome">
        选择一个 PDF 文件开始阅读
      </div>
    </div>
  </div>
</div>

<script src="/static/js/store.js"></script>
<script src="/static/js/theme.js"></script>
<script src="/static/js/loader.js"></script>
<script src="/static/js/renderer.js"></script>
<script src="/static/js/scroller.js"></script>
<script src="/static/js/thumbnails.js"></script>
<script src="/static/js/sidebar.js"></script>
<script src="/static/js/app.js"></script>

</body>
</html>
```

- [ ] **Step 3: Verify HTML structure loads**

```bash
# Ensure app is running
curl -s http://127.0.0.1:5000/ | grep -o 'id="[^"]*"' | sort
```
Expected output includes: `outerContainer`, `sidebarContainer`, `mainContainer`, `toolbar`, `viewerContainer`

- [ ] **Step 4: Commit**

```bash
git add templates/index.html
git commit -m "refactor: four-container HTML with sidebar, toolbar, viewer"
```

---

### Task 5: JS Modules (1-4) — store, theme, loader, renderer

**Files:**
- Create: `static/js/store.js`
- Create: `static/js/theme.js`
- Create: `static/js/loader.js`
- Create: `static/js/renderer.js`

- [ ] **Step 1: Create js directory**

```bash
mkdir -p static/js
```

- [ ] **Step 2: Write store.js**

`static/js/store.js`:
```javascript
var Store = (function() {
  var PROGRESS_KEY = "pdf_reader_progress";
  var BOOKMARK_KEY = "pdf_reader_bookmark";

  var state = {
    currentPdf: null,
    totalPages: 0,
    currentPage: 1,
    toc: [],
    progress: loadJSON(PROGRESS_KEY, {}),
    bookmarks: loadJSON(BOOKMARK_KEY, {}),
    sidebarVisible: true,
    dirs: [],
    browseCache: {},
    pdfInfoCache: {}
  };

  function loadJSON(key, fallback) {
    try { var d = localStorage.getItem(key); return d ? JSON.parse(d) : fallback; }
    catch(e) { return fallback; }
  }

  function saveJSON(key, data) {
    localStorage.setItem(key, JSON.stringify(data));
  }

  function saveProgress() { saveJSON(PROGRESS_KEY, state.progress); }
  function saveBookmarks() { saveJSON(BOOKMARK_KEY, state.bookmarks); }

  function getBookmark(filename) { return state.bookmarks[filename] || 1; }
  function setBookmark(filename, n) { state.bookmarks[filename] = n; saveBookmarks(); }

  function markPageRead(filename, n) {
    if (!state.progress[filename]) state.progress[filename] = [];
    if (state.progress[filename].indexOf(n) === -1) {
      state.progress[filename].push(n);
      state.progress[filename].sort(function(a,b) { return a-b; });
      saveProgress();
    }
  }

  function getReadPages(filename) { return state.progress[filename] || []; }
  function getReadCount(filename) { return getReadPages(filename).length; }

  return {
    state: state,
    loadJSON: loadJSON, saveJSON: saveJSON,
    getBookmark: getBookmark, setBookmark: setBookmark,
    markPageRead: markPageRead, getReadPages: getReadPages, getReadCount: getReadCount
  };
})();
```

- [ ] **Step 3: Write theme.js**

`static/js/theme.js`:
```javascript
var ThemeManager = (function() {
  var CHROME_KEY = "pdf_reader_chrome_theme";
  var DOC_KEY = "pdf_reader_doc_theme";

  var chromeTheme = Store.loadJSON(CHROME_KEY, "light");
  var docTheme = Store.loadJSON(DOC_KEY, "normal");

  function applyChrome() {
    if (chromeTheme === "dark") {
      document.body.classList.add("chrome-dark");
    } else {
      document.body.classList.remove("chrome-dark");
    }
    Store.saveJSON(CHROME_KEY, chromeTheme);
    updateButtons();
  }

  function applyDoc() {
    var vc = document.getElementById("viewerContainer");
    if (!vc) return;
    vc.classList.remove("doc-theme-normal", "doc-theme-sepia", "doc-theme-invert");
    vc.classList.add("doc-theme-" + docTheme);
    Store.saveJSON(DOC_KEY, docTheme);
    updateButtons();
  }

  function toggleChrome() {
    chromeTheme = chromeTheme === "light" ? "dark" : "light";
    applyChrome();
  }

  function cycleDoc() {
    var themes = ["normal", "sepia", "invert"];
    var idx = themes.indexOf(docTheme);
    docTheme = themes[(idx + 1) % themes.length];
    applyDoc();
  }

  function updateButtons() {
    var cb = document.getElementById("btn-chrome-theme");
    var db = document.getElementById("btn-doc-theme");
    if (cb) cb.textContent = chromeTheme === "light" ? "☀️" : "🌙";
    if (db) {
      var labels = { normal: "📄", sepia: "📜", invert: "🌑" };
      db.textContent = labels[docTheme] || "🎨";
    }
  }

  function init() {
    applyChrome();
    applyDoc();
    var cb = document.getElementById("btn-chrome-theme");
    var db = document.getElementById("btn-doc-theme");
    if (cb) cb.addEventListener("click", toggleChrome);
    if (db) db.addEventListener("click", cycleDoc);
  }

  return {
    init: init, toggleChrome: toggleChrome, cycleDoc: cycleDoc,
    getChrome: function() { return chromeTheme; },
    getDoc: function() { return docTheme; }
  };
})();
```

- [ ] **Step 4: Write loader.js**

`static/js/loader.js`:
```javascript
var DocumentLoader = (function() {
  var pageCache = {};
  var infoCache = {};
  var pendingRequests = {};

  async function fetchJSON(url) {
    var res = await fetch(url);
    return res.json();
  }

  async function loadInfo(compound) {
    if (infoCache[compound]) return infoCache[compound];
    var data = await fetchJSON("/api/pdf/" + encodeURIComponent(compound) + "/info");
    if (data.error) throw new Error(data.error);
    infoCache[compound] = data;
    return data;
  }

  async function loadTOC(compound) {
    var data = await fetchJSON("/api/pdf/" + encodeURIComponent(compound) + "/toc");
    return data.toc || [];
  }

  async function loadPage(compound, pageNum) {
    var key = compound + ":" + pageNum;
    if (pageCache[key]) return pageCache[key];
    if (pendingRequests[key]) return pendingRequests[key];

    var promise = fetchJSON(
      "/api/pdf/" + encodeURIComponent(compound) + "/page/" + pageNum
    ).then(function(data) {
      if (data.error) throw new Error(data.error);
      pageCache[key] = data.html || "";
      delete pendingRequests[key];
      return pageCache[key];
    });

    pendingRequests[key] = promise;
    return promise;
  }

  function preFetch(compound, pageNums) {
    pageNums.forEach(function(n) {
      var key = compound + ":" + n;
      if (!pageCache[key] && !pendingRequests[key]) {
        loadPage(compound, n).catch(function(){});
      }
    });
  }

  async function loadThumbnails(compound, start, end) {
    var url = "/api/pdf/" + encodeURIComponent(compound) + "/thumbnails?start=" + start + "&end=" + end;
    return fetchJSON(url);
  }

  async function loadDirs() {
    var data = await fetchJSON("/api/dirs");
    return data.directories;
  }

  async function browseDir(dirKey, path) {
    var url = "/api/browse/" + dirKey + (path ? "/" + path : "");
    return fetchJSON(url);
  }

  return {
    loadInfo: loadInfo, loadTOC: loadTOC, loadPage: loadPage,
    preFetch: preFetch, loadThumbnails: loadThumbnails,
    loadDirs: loadDirs, browseDir: browseDir,
    pageCache: pageCache, infoCache: infoCache
  };
})();
```

- [ ] **Step 5: Write renderer.js**

`static/js/renderer.js`:
```javascript
var PageRenderer = (function() {
  var viewer = document.getElementById("viewerContainer");
  var renderedPages = {};

  function clearAll() {
    if (!viewer) return;
    Object.keys(renderedPages).forEach(function(pn) { removePage(parseInt(pn)); });
    renderedPages = {};
    var els = viewer.querySelectorAll(".page-loading-placeholder");
    els.forEach(function(el) { el.remove(); });
  }

  function renderPage(pageNum, html, isActive) {
    if (!viewer) return;
    removePage(pageNum);

    var divider = document.createElement("div");
    divider.className = "page-divider" + (isActive ? " active" : "");
    divider.dataset.page = pageNum;
    divider.innerHTML = '<span class="page-divider-text">── 第 ' + pageNum + ' 页 ──</span>';

    var segment = document.createElement("div");
    segment.className = "page-segment";
    segment.dataset.page = pageNum;
    segment.innerHTML = html;

    insertInOrder(pageNum, divider, segment);
    renderedPages[pageNum] = { divider: divider, segment: segment };
    return renderedPages[pageNum];
  }

  function insertInOrder(pageNum, divider, segment) {
    var dividers = viewer.querySelectorAll(".page-divider");
    for (var i = 0; i < dividers.length; i++) {
      var dp = parseInt(dividers[i].dataset.page);
      if (dp > pageNum) {
        viewer.insertBefore(divider, dividers[i]);
        viewer.insertBefore(segment, dividers[i]);
        return;
      }
    }
    viewer.appendChild(divider);
    viewer.appendChild(segment);
  }

  function removePage(pageNum) {
    var existing = renderedPages[pageNum];
    if (existing) {
      if (existing.divider.parentNode) existing.divider.parentNode.removeChild(existing.divider);
      if (existing.segment.parentNode) existing.segment.parentNode.removeChild(existing.segment);
      delete renderedPages[pageNum];
    }
  }

  function recyclePages(keepStart, keepEnd) {
    Object.keys(renderedPages).forEach(function(pn) {
      var n = parseInt(pn);
      if (n < keepStart || n > keepEnd) removePage(n);
    });
  }

  function scrollToPage(pageNum) {
    var existing = renderedPages[pageNum];
    if (existing) {
      existing.divider.scrollIntoView({ block: "start", behavior: "smooth" });
      return true;
    }
    return false;
  }

  function getRenderedPageNums() {
    return Object.keys(renderedPages).map(function(n) { return parseInt(n); });
  }

  return {
    clearAll: clearAll, renderPage: renderPage, removePage: removePage,
    recyclePages: recyclePages, scrollToPage: scrollToPage,
    getRenderedPageNums: getRenderedPageNums
  };
})();
```

- [ ] **Step 6: Verify all JS syntax**

```bash
for f in static/js/store.js static/js/theme.js static/js/loader.js static/js/renderer.js; do
  node --check "$f" && echo "$f: OK" || echo "$f: FAIL"
done
```
Expected: all OK

- [ ] **Step 7: Commit**

```bash
git add static/js/store.js static/js/theme.js static/js/loader.js static/js/renderer.js
git commit -m "feat: add Store, ThemeManager, DocumentLoader, PageRenderer modules"
```

---

### Task 6: JS Modules (5-7) — scroller, thumbnails, sidebar

**Files:**
- Create: `static/js/scroller.js`
- Create: `static/js/thumbnails.js`
- Create: `static/js/sidebar.js`

- [ ] **Step 1: Write scroller.js**

`static/js/scroller.js`:
```javascript
var ScrollController = (function() {
  var viewer = document.getElementById("viewerContainer");
  var observer = null;
  var onChangeCallback = null;
  var debounceTimer = null;

  function init(onChange) {
    onChangeCallback = onChange;
    if (!viewer) return;

    observer = new IntersectionObserver(function(entries) {
      var bestPage = null;
      var bestRatio = 0;
      entries.forEach(function(entry) {
        if (entry.isIntersecting && entry.intersectionRatio > bestRatio) {
          var pn = parseInt(entry.target.dataset.page);
          if (pn) { bestRatio = entry.intersectionRatio; bestPage = pn; }
        }
      });
      if (bestPage !== null && bestPage !== Store.state.currentPage) {
        Store.state.currentPage = bestPage;
        if (onChangeCallback) {
          clearTimeout(debounceTimer);
          debounceTimer = setTimeout(function() { onChangeCallback(bestPage); }, 50);
        }
      }
    }, { threshold: [0, 0.25, 0.5, 0.75] });

    observeAll();
  }

  function observeAll() {
    if (!observer || !viewer) return;
    viewer.querySelectorAll(".page-divider").forEach(function(el) {
      observer.observe(el);
    });
  }

  function observeElement(el) { if (observer) observer.observe(el); }

  function jumpToPage(pageNum) {
    Store.state.currentPage = pageNum;
    if (onChangeCallback) onChangeCallback(pageNum);
  }

  return {
    init: init, observeAll: observeAll, observeElement: observeElement,
    jumpToPage: jumpToPage
  };
})();
```

- [ ] **Step 2: Write thumbnails.js**

`static/js/thumbnails.js`:
```javascript
var ThumbnailPanel = (function() {
  var grid = document.getElementById("thumbnail-grid");
  var thumbData = [];
  var totalPages = 0;
  var currentHighlight = 0;
  var compound = null;

  async function load(compoundName) {
    compound = compoundName;
    thumbData = [];
    totalPages = 0;
    currentHighlight = 0;
    grid.innerHTML = "";

    try {
      var data = await DocumentLoader.loadThumbnails(compound, 1, 60);
      totalPages = data.total_pages;
      thumbData = data.thumbnails;
      renderVisible();
    } catch(e) {
      grid.innerHTML = '<div class="empty-sidebar">无法加载缩略图</div>';
    }
  }

  function renderVisible() {
    if (thumbData.length === 0) return;
    grid.innerHTML = "";

    for (var i = 0; i < Math.min(thumbData.length, 60); i++) {
      var t = thumbData[i];
      var card = document.createElement("div");
      card.className = "thumbnail-card";
      if (t.page === currentHighlight) card.classList.add("active");
      card.dataset.page = t.page;

      var img = document.createElement("img");
      img.src = t.image;
      img.alt = "Page " + t.page;
      img.loading = "lazy";
      card.appendChild(img);

      var label = document.createElement("div");
      label.className = "thumbnail-label";
      label.textContent = t.page;
      card.appendChild(label);

      (function(pageNum) {
        card.addEventListener("click", function() {
          if (!PageRenderer.scrollToPage(pageNum)) {
            Store.state.currentPage = pageNum;
            App.loadPagesAround(pageNum).then(function() {
              PageRenderer.scrollToPage(pageNum);
            });
          }
          highlight(pageNum);
        });
      })(t.page);

      grid.appendChild(card);
    }
  }

  function highlight(pageNum) {
    currentHighlight = pageNum;
    grid.querySelectorAll(".thumbnail-card").forEach(function(card) {
      card.classList.toggle("active", parseInt(card.dataset.page) === pageNum);
    });
  }

  function loadMoreIfNeeded() {
    if (thumbData.length >= totalPages) return;
    var nextStart = thumbData.length + 1;
    var nextEnd = Math.min(totalPages, nextStart + 59);
    DocumentLoader.loadThumbnails(compound, nextStart, nextEnd).then(function(data) {
      thumbData = thumbData.concat(data.thumbnails);
      renderVisible();
    });
  }

  var sidebar = document.getElementById("sidebarContainer");
  if (sidebar) {
    sidebar.addEventListener("scroll", function() {
      var nearBottom = sidebar.scrollTop + sidebar.clientHeight >= sidebar.scrollHeight - 200;
      if (nearBottom) loadMoreIfNeeded();
    });
  }

  return { load: load, highlight: highlight };
})();
```

- [ ] **Step 3: Write sidebar.js**

`static/js/sidebar.js`:
```javascript
var Sidebar = (function() {
  function escHtml(s) {
    var d = document.createElement("div");
    d.textContent = s;
    return d.innerHTML;
  }

  async function initDirs() {
    try {
      var dirs = await DocumentLoader.loadDirs();
      Store.state.dirs = dirs;
      renderFileTree();
    } catch(e) {
      document.getElementById("pdf-list").innerHTML = '<div class="empty-sidebar">加载目录失败</div>';
    }
  }

  function renderFileTree() {
    var listEl = document.getElementById("pdf-list");
    if (!listEl) return;
    listEl.innerHTML = "";
    if (Store.state.dirs.length === 0) {
      listEl.innerHTML = "<div class='empty-sidebar'>没有配置目录</div>";
      return;
    }
    Store.state.dirs.forEach(function(dir) {
      appendDirNode(listEl, dir.key, dir.dirname || dir.label, "");
    });
  }

  function appendDirNode(parentEl, dirKey, label, path) {
    var cacheKey = dirKey + ":" + path;
    var entry = Store.state.browseCache[cacheKey];
    var isExpanded = entry && entry.expanded;
    var data = entry && entry.data;

    var header = document.createElement("div");
    header.className = "tree-dir-header";
    header.innerHTML = '<span class="tree-toggle">' + (isExpanded ? "▼" : "▶") + "</span> " + escHtml(label);
    header.addEventListener("click", function() { toggleDir(dirKey, path); });
    parentEl.appendChild(header);

    if (isExpanded && data) {
      renderDirContents(parentEl, dirKey, path, data, 0);
    }
  }

  function renderDirContents(parentEl, dirKey, parentPath, data, depth) {
    var indent = 16 + depth * 16;

    data.dirs.forEach(function(subdir) {
      var subpath = parentPath ? parentPath + "/" + subdir : subdir;
      var cacheKey = dirKey + ":" + subpath;
      var entry = Store.state.browseCache[cacheKey];
      var isExpanded = entry && entry.expanded;

      var item = document.createElement("div");
      item.className = "tree-dir-header tree-item";
      item.style.paddingLeft = indent + "px";
      item.innerHTML = '<span class="tree-toggle">' + (isExpanded ? "▼" : "▶") + "</span> " + escHtml(subdir);
      item.addEventListener("click", function(e) {
        e.stopPropagation();
        toggleDir(dirKey, subpath);
      });
      parentEl.appendChild(item);

      if (isExpanded && entry && entry.data) {
        renderDirContents(parentEl, dirKey, subpath, entry.data, depth + 1);
      }
    });

    data.files.forEach(function(file) {
      var compound = dirKey + "/" + (parentPath ? parentPath + "/" + file.name : file.name);
      var item = document.createElement("div");
      item.className = "pdf-item";
      item.style.paddingLeft = indent + "px";
      item.textContent = file.name;
      if (compound === Store.state.currentPdf) item.classList.add("active");
      if (Store.getReadCount(compound) > 0) item.classList.add("has-progress");

      item.addEventListener("click", function() { App.selectPdf(compound); });
      parentEl.appendChild(item);
    });
  }

  async function toggleDir(dirKey, path) {
    var cacheKey = dirKey + ":" + path;
    var entry = Store.state.browseCache[cacheKey];

    if (entry && entry.expanded) { entry.expanded = false; renderFileTree(); return; }
    if (!entry) {
      try {
        var data = await DocumentLoader.browseDir(dirKey, path);
        Store.state.browseCache[cacheKey] = { expanded: true, data: data };
      } catch(e) {
        Store.state.browseCache[cacheKey] = { expanded: true, data: { dirs: [], files: [] } };
      }
    } else { entry.expanded = true; }
    renderFileTree();
  }

  function renderToc() {
    var el = document.getElementById("toc-list");
    if (!el) return;
    el.innerHTML = "";
    if (!Store.state.currentPdf || Store.state.toc.length === 0) {
      el.innerHTML = "<div class='empty-sidebar'>暂无目录</div>";
      return;
    }

    var activeIndex = -1;
    for (var i = Store.state.toc.length - 1; i >= 0; i--) {
      if (Store.state.toc[i].page <= Store.state.currentPage) { activeIndex = i; break; }
    }

    Store.state.toc.forEach(function(entry, i) {
      var item = document.createElement("div");
      item.className = "toc-item";
      if (i === activeIndex) item.classList.add("active");
      item.style.paddingLeft = (12 + (entry.level - 1) * 16) + "px";

      var title = document.createElement("span");
      title.className = "toc-title";
      title.textContent = entry.title;

      var pageNum = document.createElement("span");
      pageNum.className = "toc-page";
      pageNum.textContent = entry.page;

      item.appendChild(title);
      item.appendChild(pageNum);
      item.addEventListener("click", function() {
        Store.state.currentPage = entry.page;
        App.loadPagesAround(entry.page).then(function() {
          PageRenderer.scrollToPage(entry.page);
        });
      });
      el.appendChild(item);
    });

    if (activeIndex >= 0 && el.children[activeIndex]) {
      setTimeout(function() {
        el.children[activeIndex].scrollIntoView({ block: "center", behavior: "smooth" });
      }, 100);
    }
  }

  function renderProgressList() {
    var el = document.getElementById("progress-list");
    if (!el) return;
    el.innerHTML = "";
    var compounds = Object.keys(Store.state.progress).sort();
    if (compounds.length === 0) {
      el.innerHTML = "<div class='empty-sidebar'>暂无进度</div>";
      return;
    }

    compounds.forEach(function(compound) {
      var readCount = Store.getReadCount(compound);
      var displayName = compound.split("/").pop();
      var info = Store.state.pdfInfoCache[compound];

      var row = document.createElement("div");
      row.className = "progress-row";

      var nameEl = document.createElement("span");
      nameEl.className = "progress-name";
      nameEl.textContent = displayName;

      if (info && info.pages) {
        var pct = Math.round(readCount / info.pages * 100);
        var bar = document.createElement("div"); bar.className = "progress-bar-mini";
        var fill = document.createElement("div"); fill.className = "progress-bar-mini-fill";
        fill.style.width = pct + "%"; bar.appendChild(fill);
        var count = document.createElement("div"); count.className = "progress-count";
        count.textContent = readCount + "/" + info.pages;
        row.appendChild(nameEl); row.appendChild(bar); row.appendChild(count);
      } else {
        var count2 = document.createElement("div"); count2.className = "progress-count";
        count2.textContent = "已读 " + readCount + " 页";
        row.appendChild(nameEl); row.appendChild(count2);
      }
      el.appendChild(row);
    });
  }

  function renderAll() { renderFileTree(); renderToc(); renderProgressList(); }

  function toggleSidebar() {
    Store.state.sidebarVisible = !Store.state.sidebarVisible;
    var sidebar = document.getElementById("sidebarContainer");
    if (Store.state.sidebarVisible) { sidebar.classList.remove("collapsed"); }
    else { sidebar.classList.add("collapsed"); }
  }

  return {
    initDirs: initDirs, renderFileTree: renderFileTree,
    renderToc: renderToc, renderProgressList: renderProgressList,
    renderAll: renderAll, toggleSidebar: toggleSidebar
  };
})();
```

- [ ] **Step 4: Verify JS syntax**

```bash
for f in static/js/scroller.js static/js/thumbnails.js static/js/sidebar.js; do
  node --check "$f" && echo "$f: OK" || echo "$f: FAIL"
done
```
Expected: all OK

- [ ] **Step 5: Commit**

```bash
git add static/js/scroller.js static/js/thumbnails.js static/js/sidebar.js
git commit -m "feat: add ScrollController, ThumbnailPanel, Sidebar modules"
```

---

### Task 7: JS Module — app.js (Orchestration)

**Files:**
- Create: `static/js/app.js`

- [ ] **Step 1: Write app.js (wire everything)**

`static/js/app.js`:
```javascript
var App = (function() {
  async function init() {
    ThemeManager.init();
    await Sidebar.initDirs();
    document.getElementById("sidebarToggle").addEventListener("click", Sidebar.toggleSidebar);

    document.addEventListener("keydown", function(e) {
      if (!Store.state.currentPdf) return;
      if (e.target.tagName === "INPUT") return;
      if (e.key === "ArrowLeft") { e.preventDefault(); navigatePrev(); }
      else if (e.key === "ArrowRight") { e.preventDefault(); navigateNext(); }
    });

    ScrollController.init(onPageChanged);
  }

  async function selectPdf(compound) {
    Store.state.currentPdf = compound;
    Store.state.currentPage = Store.getBookmark(compound);

    var info = await DocumentLoader.loadInfo(compound);
    Store.state.totalPages = info.pages;
    Store.state.pdfInfoCache[compound] = { pages: info.pages };

    Store.state.toc = await DocumentLoader.loadTOC(compound);

    document.getElementById("toolbar-filename").textContent = compound.split("/").pop();
    document.getElementById("welcome").style.display = "none";

    ThumbnailPanel.load(compound);
    PageRenderer.clearAll();
    await loadPagesAround(Store.state.currentPage);
    PageRenderer.scrollToPage(Store.state.currentPage);

    Sidebar.renderAll();
    updateToolbar();
  }

  async function loadPagesAround(centerPage) {
    var compound = Store.state.currentPdf;
    if (!compound) return;
    var total = Store.state.totalPages;
    var buffer = 2;
    var start = Math.max(1, centerPage - buffer);
    var end = Math.min(total, centerPage + buffer);

    for (var n = start; n <= end; n++) {
      if (PageRenderer.getRenderedPageNums().indexOf(n) !== -1) continue;
      try {
        var html = await DocumentLoader.loadPage(compound, n);
        PageRenderer.renderPage(n, html, n === Store.state.currentPage);
        ScrollController.observeAll();
      } catch(err) { console.error("Failed to load page " + n, err); }
    }

    PageRenderer.recyclePages(start, end);

    var preFetchNums = [];
    for (var p = start - 3; p <= end + 3; p++) {
      if (p >= 1 && p <= total && PageRenderer.getRenderedPageNums().indexOf(p) === -1) {
        preFetchNums.push(p);
      }
    }
    DocumentLoader.preFetch(compound, preFetchNums);
  }

  function onPageChanged(pageNum) {
    Store.state.currentPage = pageNum;
    Store.markPageRead(Store.state.currentPdf, pageNum);
    Store.setBookmark(Store.state.currentPdf, pageNum);
    ThumbnailPanel.highlight(pageNum);
    Sidebar.renderToc();
    Sidebar.renderProgressList();
    updateToolbar();
    loadPagesAround(pageNum);
  }

  function updateToolbar() {
    document.getElementById("toolbar-page").textContent =
      "第 " + Store.state.currentPage + " / " + Store.state.totalPages + " 页";
  }

  function navigatePrev() {
    if (Store.state.currentPage > 1) {
      Store.state.currentPage--;
      if (!PageRenderer.scrollToPage(Store.state.currentPage)) {
        loadPagesAround(Store.state.currentPage).then(function() {
          PageRenderer.scrollToPage(Store.state.currentPage);
        });
      }
      onPageChanged(Store.state.currentPage);
    }
  }

  function navigateNext() {
    if (Store.state.currentPage < Store.state.totalPages) {
      Store.state.currentPage++;
      if (!PageRenderer.scrollToPage(Store.state.currentPage)) {
        loadPagesAround(Store.state.currentPage).then(function() {
          PageRenderer.scrollToPage(Store.state.currentPage);
        });
      }
      onPageChanged(Store.state.currentPage);
    }
  }

  return {
    init: init, selectPdf: selectPdf, loadPagesAround: loadPagesAround,
    navigatePrev: navigatePrev, navigateNext: navigateNext
  };
})();

document.addEventListener("DOMContentLoaded", function() { App.init(); });
```

- [ ] **Step 2: Verify syntax**

```bash
node --check static/js/app.js && echo "Syntax OK"
```

- [ ] **Step 3: Commit**

```bash
git add static/js/app.js
git commit -m "feat: add App orchestration module wiring all JS modules"
```

---

### Task 8: Integration — Run and Manual Verification

- [ ] **Step 1: Start the app**

```bash
CONFIG_PATH=config.json python3 app.py &
sleep 2
```

- [ ] **Step 2: Verify API + HTML + static files all load**

```bash
# API
curl -s http://127.0.0.1:5000/api/dirs | python3 -m json.tool | head -5

# HTML structure
curl -s http://127.0.0.1:5000/ | grep -c "outerContainer"

# JS files
for f in store theme loader renderer scroller thumbnails sidebar app; do
  code=$(curl -s -o /dev/null -w "%{http_code}" "http://127.0.0.1:5000/static/js/${f}.js")
  echo "js/${f}.js: HTTP $code"
done
```
Expected: all HTTP 200

- [ ] **Step 3: Manual browser test** — Open `http://127.0.0.1:5000/`

Checklist:
- [ ] Sidebar shows directory tree
- [ ] Clicking a PDF loads continuous-scroll pages in viewer
- [ ] SFT thumbnail grid appears in sidebar with page highlights
- [ ] Scrolling changes current page in: toolbar indicator, divider highlight, TOC highlight, thumbnail highlight
- [ ] Chrome theme toggle (🌗) switches only chrome dark/light
- [ ] Doc theme toggle (🎨) cycles only document normal/sepia/invert
- [ ] Keyboard left/right navigates pages

- [ ] **Step 4: Commit checkpoint**

```bash
git add -A
git commit -m "chore: integration verification checkpoint"
```

---

### Task 9: Run Tests and Final Cleanup

- [ ] **Step 1: Run all backend tests**

```bash
python3 -m pytest tests/ -v
```
Expected: 5 PASS

- [ ] **Step 2: Check for old CSS theme references**

```bash
grep -r "theme-classic\|theme-night\|theme-fresh" static/ templates/ 2>/dev/null
```
Expected: no output

- [ ] **Step 3: Check the old static/app.js is superseded by static/js/app.js**

```bash
ls -la static/app.js 2>/dev/null && echo "WARNING: old app.js still exists" || echo "OK: old app.js gone"
```

If old `static/app.js` still exists, remove it:
```bash
git rm static/app.js
```

- [ ] **Step 4: Final commit**

```bash
git add -A
git commit -m "chore: final cleanup — tests pass, no stale references"
```
