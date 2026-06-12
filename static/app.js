const PROGRESS_KEY = "pdf_reader_progress";
const BOOKMARK_KEY = "pdf_reader_bookmark";
const THEME_KEY = "pdf_reader_theme";

const state = {
    currentPdf: null,
    totalPages: 0,
    currentPage: 1,
    toc: [],
    progress: loadProgress(),
    bookmarks: loadBookmarks(),
    sidebarOpen: false,
    theme: localStorage.getItem(THEME_KEY) || "theme-classic",

    // Directory tree browsing
    dirs: [],
    browseCache: {},     // "dirKey:path" -> {expanded, data: {dirs, files}}
    pdfInfoCache: {},    // "compound" -> {pages}
};

function loadProgress() {
    try {
        const data = localStorage.getItem(PROGRESS_KEY);
        return data ? JSON.parse(data) : {};
    } catch {
        return {};
    }
}

function saveProgress() {
    localStorage.setItem(PROGRESS_KEY, JSON.stringify(state.progress));
}

function loadBookmarks() {
    try {
        const data = localStorage.getItem(BOOKMARK_KEY);
        return data ? JSON.parse(data) : {};
    } catch {
        return {};
    }
}

function saveBookmarks() {
    localStorage.setItem(BOOKMARK_KEY, JSON.stringify(state.bookmarks));
}

function getBookmark(filename) {
    return state.bookmarks[filename] || 1;
}

function setBookmark(filename, pageNum) {
    state.bookmarks[filename] = pageNum;
    saveBookmarks();
}

function markPageRead(filename, pageNum) {
    if (!state.progress[filename]) state.progress[filename] = [];
    if (!state.progress[filename].includes(pageNum)) {
        state.progress[filename].push(pageNum);
        state.progress[filename].sort((a, b) => a - b);
        saveProgress();
    }
}

function getReadPages(filename) {
    return state.progress[filename] || [];
}

function getReadCount(filename) {
    return getReadPages(filename).length;
}

// === Theme ===

function applyTheme(theme) {
    state.theme = theme;
    localStorage.setItem(THEME_KEY, theme);
    document.body.className = theme;
    document.querySelectorAll(".theme-btn").forEach(btn => {
        btn.classList.toggle("active", btn.dataset.theme === theme);
    });
}

document.querySelectorAll(".theme-btn").forEach(btn => {
    btn.addEventListener("click", () => applyTheme(btn.dataset.theme));
});

applyTheme(state.theme);

// === Sidebar ===

function toggleSidebar() {
    state.sidebarOpen = !state.sidebarOpen;
    document.getElementById("sidebar-panel").classList.toggle("open", state.sidebarOpen);
    document.getElementById("sidebar-overlay").classList.toggle("visible", state.sidebarOpen);
}

function closeSidebar() {
    state.sidebarOpen = false;
    document.getElementById("sidebar-panel").classList.remove("open");
    document.getElementById("sidebar-overlay").classList.remove("visible");
}

document.getElementById("sidebar-toggle").addEventListener("click", toggleSidebar);
document.getElementById("sidebar-overlay").addEventListener("click", closeSidebar);

// === Directory Tree ===

async function init() {
    const res = await fetch("/api/dirs");
    const data = await res.json();
    state.dirs = data.directories;
    renderSidebar();
}

function renderSidebar() {
    renderFileTree();
    renderToc();
    renderProgressList();
}

function renderFileTree() {
    const listEl = document.getElementById("pdf-list");
    listEl.innerHTML = "";

    if (state.dirs.length === 0) {
        listEl.innerHTML = "<div class='empty-sidebar'>没有配置目录</div>";
        return;
    }

    for (const dir of state.dirs) {
        appendDirNode(listEl, dir.key, dir.dirname || dir.label, "");
    }
}

function appendDirNode(parentEl, dirKey, label, path) {
    const cacheKey = dirKey + ":" + path;
    const entry = state.browseCache[cacheKey];
    const isExpanded = entry && entry.expanded;
    const data = entry && entry.data;

    const header = document.createElement("div");
    header.className = "tree-dir-header";
    header.innerHTML = `<span class="tree-toggle">${isExpanded ? "&#9660;" : "&#9654;"}</span> ${escHtml(label)}`;
    header.addEventListener("click", () => toggleDir(dirKey, path));
    parentEl.appendChild(header);

    if (isExpanded && data) {
        renderDirContents(parentEl, dirKey, path, data, 0);
    }
}

function renderDirContents(parentEl, dirKey, parentPath, data, depth) {
    const indent = 16 + depth * 16;

    for (const subdir of data.dirs) {
        const subpath = parentPath ? parentPath + "/" + subdir : subdir;
        const cacheKey = dirKey + ":" + subpath;
        const entry = state.browseCache[cacheKey];
        const isExpanded = entry && entry.expanded;
        const subData = entry && entry.data;

        const item = document.createElement("div");
        item.className = "tree-dir-header tree-item";
        item.style.paddingLeft = indent + "px";
        item.innerHTML = `<span class="tree-toggle">${isExpanded ? "&#9660;" : "&#9654;"}</span> ${escHtml(subdir)}`;
        item.addEventListener("click", (e) => {
            e.stopPropagation();
            toggleDir(dirKey, subpath);
        });
        parentEl.appendChild(item);

        if (isExpanded && subData) {
            renderDirContents(parentEl, dirKey, subpath, subData, depth + 1);
        }
    }

    for (const file of data.files) {
        const compound = dirKey + "/" + (parentPath ? parentPath + "/" + file.name : file.name);
        const item = document.createElement("div");
        item.className = "pdf-item";
        item.style.paddingLeft = indent + "px";
        item.textContent = file.name;
        if (compound === state.currentPdf) item.classList.add("active");
        if (getReadCount(compound) > 0) item.classList.add("has-progress");

        item.addEventListener("click", () => {
            selectPdf(compound);
            closeSidebar();
        });
        parentEl.appendChild(item);
    }
}

async function toggleDir(dirKey, path) {
    const cacheKey = dirKey + ":" + path;
    const entry = state.browseCache[cacheKey];

    if (entry && entry.expanded) {
        entry.expanded = false;
        renderFileTree();
        return;
    }

    if (!entry) {
        const url = "/api/browse/" + dirKey + (path ? "/" + path : "");
        try {
            const res = await fetch(url);
            const data = await res.json();
            state.browseCache[cacheKey] = { expanded: true, data: data };
        } catch {
            state.browseCache[cacheKey] = { expanded: true, data: { dirs: [], files: [] } };
        }
    } else {
        entry.expanded = true;
    }
    renderFileTree();
}

function escHtml(s) {
    const d = document.createElement("div");
    d.textContent = s;
    return d.innerHTML;
}

// === TOC ===

function renderToc() {
    const el = document.getElementById("toc-list");
    if (!el) return;
    el.innerHTML = "";

    if (!state.currentPdf || state.toc.length === 0) {
        el.innerHTML = "<div class='empty-sidebar'>暂无目录</div>";
        return;
    }

    let activeIndex = -1;
    for (let i = state.toc.length - 1; i >= 0; i--) {
        if (state.toc[i].page <= state.currentPage) {
            activeIndex = i;
            break;
        }
    }

    for (let i = 0; i < state.toc.length; i++) {
        const entry = state.toc[i];
        const item = document.createElement("div");
        item.className = "toc-item";
        if (i === activeIndex) item.classList.add("active");
        item.style.paddingLeft = (12 + (entry.level - 1) * 16) + "px";

        const title = document.createElement("span");
        title.className = "toc-title";
        title.textContent = entry.title;

        const pageNum = document.createElement("span");
        pageNum.className = "toc-page";
        pageNum.textContent = entry.page;

        item.appendChild(title);
        item.appendChild(pageNum);
        item.addEventListener("click", () => {
            if (state.currentPage !== entry.page) {
                state.currentPage = entry.page;
                loadPage();
            }
            closeSidebar();
        });
        el.appendChild(item);
    }

    if (activeIndex >= 0) {
        const activeEl = el.children[activeIndex];
        if (activeEl) {
            setTimeout(() => {
                activeEl.scrollIntoView({ block: "center", behavior: "smooth" });
            }, 100);
        }
    }
}

// === Progress ===

function renderProgressList() {
    const el = document.getElementById("progress-list");
    el.innerHTML = "";

    const compounds = Object.keys(state.progress).sort();
    if (compounds.length === 0) {
        el.innerHTML = "<div class='empty-sidebar'>暂无进度</div>";
        return;
    }

    for (const compound of compounds) {
        const readCount = getReadCount(compound);
        const displayName = compound.split("/").pop();
        const info = state.pdfInfoCache[compound];

        const row = document.createElement("div");
        row.className = "progress-row";

        const nameEl = document.createElement("span");
        nameEl.className = "progress-name";
        nameEl.textContent = displayName;

        if (info && info.pages) {
            const pct = Math.round(readCount / info.pages * 100);
            const bar = document.createElement("div");
            bar.className = "progress-bar-mini";
            const fill = document.createElement("div");
            fill.className = "progress-bar-mini-fill";
            fill.style.width = pct + "%";
            bar.appendChild(fill);
            const count = document.createElement("div");
            count.className = "progress-count";
            count.textContent = readCount + "/" + info.pages;
            row.appendChild(nameEl);
            row.appendChild(bar);
            row.appendChild(count);
        } else {
            const count = document.createElement("div");
            count.className = "progress-count";
            count.textContent = "已读 " + readCount + " 页";
            row.appendChild(nameEl);
            row.appendChild(count);
        }

        el.appendChild(row);
    }
}

// === Reader ===

async function selectPdf(filename) {
    state.currentPdf = filename;
    state.currentPage = getBookmark(filename);

    const res = await fetch("/api/pdf/" + encodeURIComponent(filename) + "/info");
    const info = await res.json();
    if (info.error) {
        alert("无法打开: " + info.error);
        return;
    }
    state.totalPages = info.pages;
    state.pdfInfoCache[filename] = { pages: info.pages };

    const tocRes = await fetch("/api/pdf/" + encodeURIComponent(filename) + "/toc");
    const tocData = await tocRes.json();
    state.toc = tocData.toc || [];

    document.getElementById("welcome").style.display = "none";
    document.getElementById("reader").style.display = "flex";

    updateBreadcrumb();
    renderSidebar();
    await loadPage();
}

function updateBreadcrumb() {
    const bc = document.getElementById("header-breadcrumb");
    const displayName = state.currentPdf ? state.currentPdf.split("/").pop() : "";
    bc.textContent = displayName + "  >  第 " + state.currentPage + " 页";
}

function updateHeaderProgress() {
    if (!state.currentPdf) return;
    const readCount = getReadCount(state.currentPdf);
    const pct = Math.round(readCount / state.totalPages * 100);
    document.getElementById("header-progress").textContent = `${readCount}/${state.totalPages} 页 (${pct}%)`;
}

async function loadPage() {
    const article = document.getElementById("page-article");
    const loading = document.getElementById("page-loading");

    article.innerHTML = "";
    article.style.display = "none";
    loading.style.display = "block";

    const res = await fetch(`/api/pdf/${encodeURIComponent(state.currentPdf)}/page/${state.currentPage}`);
    const data = await res.json();

    if (data.error) {
        loading.textContent = "加载失败: " + data.error;
        return;
    }

    loading.style.display = "none";
    article.style.display = "block";

    if (data.has_content) {
        article.innerHTML = data.html;
    } else {
        article.innerHTML = "<p style='color:#999;text-align:center;padding:40px'>此页无内容</p>";
    }

    markPageRead(state.currentPdf, state.currentPage);
    setBookmark(state.currentPdf, state.currentPage);
    renderSidebar();
    updateHeaderProgress();
    updateBreadcrumb();

    document.getElementById("page-indicator").textContent =
        `第 ${state.currentPage} 页 / 共 ${state.totalPages} 页`;

    document.getElementById("btn-prev").disabled = state.currentPage <= 1;
    document.getElementById("btn-next").disabled = state.currentPage >= state.totalPages;

    window.scrollTo(0, 0);
}

function navigatePrev() {
    if (state.currentPage > 1) {
        state.currentPage--;
        loadPage();
    }
}

function navigateNext() {
    if (state.currentPage < state.totalPages) {
        state.currentPage++;
        loadPage();
    }
}

function jumpToPage() {
    const input = document.getElementById("jump-input");
    const num = parseInt(input.value);
    if (num >= 1 && num <= state.totalPages) {
        state.currentPage = num;
        input.value = "";
        loadPage();
    }
}

document.getElementById("btn-prev").addEventListener("click", navigatePrev);
document.getElementById("btn-next").addEventListener("click", navigateNext);
document.getElementById("btn-jump").addEventListener("click", jumpToPage);

document.addEventListener("keydown", (e) => {
    if (!state.currentPdf) return;
    if (e.target.tagName === "INPUT") return;
    if (e.key === "ArrowLeft") { e.preventDefault(); navigatePrev(); }
    else if (e.key === "ArrowRight") { e.preventDefault(); navigateNext(); }
});

init();
