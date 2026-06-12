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
