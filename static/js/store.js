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
