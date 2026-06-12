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
