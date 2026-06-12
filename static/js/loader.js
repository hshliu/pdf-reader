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
