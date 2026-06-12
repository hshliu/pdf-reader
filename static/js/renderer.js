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
