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
