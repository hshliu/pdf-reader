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
