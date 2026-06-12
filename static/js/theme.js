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
