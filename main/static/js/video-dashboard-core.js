const VideoDashboard = {

  /* ================= CONFIG ================= */

  API_URL: (window.APP_CONFIG?.API_BASE || "/api/v1") + "/videos/",
  FRAMES_API_URL: (window.APP_CONFIG?.API_BASE || "/api/v1") + "/video-frames/",

  S3_ENDPOINT: window.APP_CONFIG?.S3_ENDPOINT || "",
  S3_BUCKET: window.APP_CONFIG?.S3_BUCKET || "",


  /* ================= STATE ================= */

  state: {
    page: 1,
    size: 10,
    totalPages: 1,
    controller: null,
    selectedColumns: new Set(),
    columnOrder: [],
    frameCache: new Map(),
    categoryCache: null
  },

  CACHE_TTL_MS: 5 * 60 * 1000,


  /* ================= TABLE COLUMNS ================= */

  columns: [
    { key: "sno", label: "S No" },
    { key: "title", label: "Video Title" },
    { key: "category", label: "Category" },
    { key: "resolution", label: "Resolution" },
    { key: "orientation", label: "Orientation" },
    { key: "duration", label: "Duration" },
    { key: "fps", label: "Frame Rate (FPS)" },
    { key: "bitrate", label: "Video Bitrate" },
    { key: "video_codec", label: "Video Codec" },
    { key: "audio_codec", label: "Audio Codec" },
    { key: "audio_channels", label: "Audio Channels" },
    { key: "file_size", label: "File Size" },
    { key: "frame_count", label: "Frame Count" },
    { key: "pixel_format", label: "Pixel Format" },
    { key: "bit_depth", label: "Bit Depth" },
    { key: "container_format", label: "Container Format" },
    { key: "audio_sample_rate", label: "Audio Sample Rate" },
    { key: "audio_bitrate", label: "Audio Bitrate" },
    { key: "keyframes", label: "Key Frames" },
    { key: "thumbnail", label: "Thumbnail" }
  ],


  /* ================= INIT ================= */

  init() {
    this.cacheDom();
    this.loadPreferences();
    this.initDropdown();
    this.attachEvents();
    this.applyTheme();

    VideoDashboardTable.renderHeaders();
    VideoDashboardTable.loadVideos(1);

    this.loadCategories();
  },


  /* ================= DOM CACHE ================= */

  cacheDom() {

    this.tbody = document.getElementById("tbody");
    this.pageInfo = document.getElementById("pageInfo");

    this.searchBox = document.getElementById("searchBox");
    this.categoryFilter = document.getElementById("categoryFilter");
    this.orientationFilter = document.getElementById("orientationFilter");
    this.pageSizeSelect = document.getElementById("pageSizeSelect");

    this.dropdownMenu = document.getElementById("columnDropdown");

    this.exportLoader = document.getElementById("exportLoader");
    this.tableLoader = document.getElementById("tableLoader");
    this.errorBanner = document.getElementById("errorBanner");
    this.emptyState = document.getElementById("emptyState");

    /* Frame modal */
    this.frameModal = document.getElementById("frameModal");
    this.frameGrid = document.getElementById("frameGrid");
    this.frameModalTitle = document.getElementById("frameModalTitle");

    /* Thumbnail modal */
    this.thumbnailModal = document.getElementById("thumbnailModal");
    this.thumbnailModalImg = document.getElementById("thumbnailModalImg");
    this.thumbnailModalTitle = document.getElementById("thumbnailModalTitle");
    this.thumbnailMeta = document.getElementById("thumbnailMeta");
  },


  /* ================= EVENTS ================= */

  attachEvents() {

    document.addEventListener("click", (e) => {
      if (!e.target.closest(".column-box")) {
        this.dropdownMenu.style.display = "none";
      }
    });

    this.pageSizeSelect?.addEventListener("change", () => {
      this.state.size = Number(this.pageSizeSelect.value);
      VideoDashboardTable.loadVideos(1);
    });

    this.categoryFilter?.addEventListener("change", () => {
      VideoDashboardTable.loadVideos(1);
    });

    this.orientationFilter?.addEventListener("change", () => {
      VideoDashboardTable.loadVideos(1);
    });

    /* Search debounce */
    let searchTimer = null;

    this.searchBox?.addEventListener("input", () => {
      clearTimeout(searchTimer);
      searchTimer = setTimeout(() => {
        VideoDashboardTable.loadVideos(1);
      }, 350);
    });
  },


  /* ================= DROPDOWN ================= */

  toggleColumnDropdown() {
    this.dropdownMenu.style.display =
      this.dropdownMenu.style.display === "block" ? "none" : "block";
  },

  initDropdown() {

    if (!this.dropdownMenu) return;

    const frag = document.createDocumentFragment();

    this.columns.forEach(col => {

      const label = document.createElement("label");

      const cb = document.createElement("input");
      cb.type = "checkbox";
      cb.checked = this.state.selectedColumns.has(col.key);

      cb.addEventListener("change", () => {

        if (cb.checked) this.state.selectedColumns.add(col.key);
        else this.state.selectedColumns.delete(col.key);

        this.savePreferences();
        VideoDashboardTable.renderHeaders();
        VideoDashboardTable.loadVideos(1);
      });

      label.append(cb, document.createTextNode(" " + col.label));
      frag.appendChild(label);
    });

    this.dropdownMenu.innerHTML = "";
    this.dropdownMenu.appendChild(frag);
  },


  /* ================= THEME ================= */

  toggleTheme() {
    document.body.classList.toggle("dark-mode");

    localStorage.setItem(
      "vd_theme",
      document.body.classList.contains("dark-mode") ? "dark" : "light"
    );
  },

  applyTheme() {
    if (localStorage.getItem("vd_theme") === "dark") {
      document.body.classList.add("dark-mode");
    }
  },


  /* ================= QUERY ================= */

  buildQuery(page = 1, size = this.state.size) {

    let url = `${this.API_URL}?page=${page}&size=${size}`;

    if (this.searchBox?.value)
      url += `&search=${encodeURIComponent(this.searchBox.value)}`;

    if (this.categoryFilter?.value)
      url += `&category=${this.categoryFilter.value}`;

    if (this.orientationFilter?.value)
      url += `&orientation=${this.orientationFilter.value}`;

    return url;
  },


  /* ================= CATEGORY ================= */

  async loadCategories() {

    try {

      if (this.state.categoryCache) {
        this.renderCategories(this.state.categoryCache);
        return;
      }

      const url = (window.APP_CONFIG?.API_BASE || "/api/v1") + "/categories/";
      const data = await this.safeFetch(url);

      this.state.categoryCache = data;
      this.renderCategories(data);

    } catch (e) {
      console.error("Category load failed", e);
    }
  },

  renderCategories(data) {

    if (!this.categoryFilter) return;

    this.categoryFilter.innerHTML = `<option value="">All Categories</option>`;

    (data.results || []).forEach(cat => {

      const opt = document.createElement("option");
      opt.value = cat.id;
      opt.textContent = cat.name;

      this.categoryFilter.appendChild(opt);
    });
  },


  /* ================= FETCH ================= */

  async safeFetch(url, options = {}, retries = 1) {

    try {

      if (this.state.controller) this.state.controller.abort();

      this.state.controller = new AbortController();

      const res = await fetch(url, {
        ...options,
        signal: this.state.controller.signal
      });

      if (!res.ok) throw new Error("API failed");

      return await res.json();

    } catch (err) {

      if (retries > 0) {
        await new Promise(r => setTimeout(r, 300));
        return this.safeFetch(url, options, retries - 1);
      }

      throw err;
    }
  },


  /* ================= UI STATE ================= */

  setUIState(state) {

    const table = document.getElementById("videoTable");

    this.tableLoader?.classList.add("hidden");
    this.errorBanner?.classList.add("hidden");
    this.emptyState?.classList.add("hidden");
    table?.classList.remove("hidden");

    if (state === "loading") {
      this.tableLoader?.classList.remove("hidden");
      table?.classList.add("hidden");
    }

    if (state === "error") {
      this.errorBanner?.classList.remove("hidden");
      table?.classList.add("hidden");
    }

    if (state === "empty") {
      this.emptyState?.classList.remove("hidden");
      table?.classList.add("hidden");
    }
  },


  /* ================= LOCAL STORAGE ================= */

  loadPreferences() {

    try {

      const savedCols = JSON.parse(localStorage.getItem("vd_cols") || "null");
      const savedOrder = JSON.parse(localStorage.getItem("vd_order") || "null");

      this.state.selectedColumns = savedCols
        ? new Set(savedCols)
        : new Set(this.columns.map(c => c.key));

      this.state.columnOrder = savedOrder
        ? savedOrder
        : this.columns.map(c => c.key);

    } catch {

      this.state.selectedColumns = new Set(this.columns.map(c => c.key));
      this.state.columnOrder = this.columns.map(c => c.key);
    }
  },

  savePreferences() {

    localStorage.setItem(
      "vd_cols",
      JSON.stringify([...this.state.selectedColumns])
    );

    localStorage.setItem(
      "vd_order",
      JSON.stringify(this.state.columnOrder)
    );
  },


  /* ================= FRAME MODAL ================= */

  async openFrames(videoUrl, videoTitle = "Video Frames") {

    if (!this.frameModal || !this.frameGrid) return;

    this.frameModalTitle.textContent = videoTitle;
    this.frameGrid.innerHTML = "Loading frames...";
    this.frameModal.classList.remove("hidden");

    try {

      let cache = this.state.frameCache.get(videoUrl);

      if (cache && Date.now() - cache.ts < this.CACHE_TTL_MS) {
        return this.renderFrames(cache.data);
      }

      const data = await this.safeFetch(
        `${this.FRAMES_API_URL}?video_url=${encodeURIComponent(videoUrl)}`
      );

      this.state.frameCache.set(videoUrl, {
        data,
        ts: Date.now()
      });

      this.renderFrames(data);

    } catch (err) {

      console.error(err);
      this.frameGrid.innerHTML = "Failed to load frames";
    }
  },

  renderFrames(data) {

    if (!data.results?.length) {
      this.frameGrid.innerHTML = "No frames found";
      return;
    }

    const frag = document.createDocumentFragment();

    data.results.forEach(frame => {

      const wrapper = document.createElement("div");
      wrapper.className = "frame-item";

      const img = document.createElement("img");
      img.loading = "lazy";
      img.src = `${this.S3_ENDPOINT}/${this.S3_BUCKET}/${frame.frame_s3_key}`;

      const badge = document.createElement("div");
      badge.className = "frame-number";
      badge.innerText = `#${frame.frame_number}`;

      wrapper.append(img, badge);
      frag.appendChild(wrapper);
    });

    this.frameGrid.innerHTML = "";
    this.frameGrid.appendChild(frag);
  },

  closeFrameModal() {
    this.frameModal?.classList.add("hidden");
  },


  /* ================= THUMBNAIL MODAL ================= */

  openThumbnailModal(src, title = "Thumbnail Preview") {

    if (!this.thumbnailModal || !this.thumbnailModalImg) return;

    this.thumbnailModalImg.src = src;
    this.thumbnailModalTitle.textContent = title;

    const img = new Image();

    img.onload = () => {
      if (this.thumbnailMeta) {
        this.thumbnailMeta.innerText =
          `Resolution: ${img.naturalWidth} × ${img.naturalHeight}`;
      }
    };

    img.src = src;

    this.thumbnailModal.classList.remove("hidden");
  },

  closeThumbnailModal() {
    this.thumbnailModal?.classList.add("hidden");
  },


  /* ================= PAGINATION ================= */

  prevPage() {
    if (this.state.page > 1)
      VideoDashboardTable.loadVideos(this.state.page - 1);
  },

  nextPage() {
    if (this.state.page < this.state.totalPages)
      VideoDashboardTable.loadVideos(this.state.page + 1);
  }

};


/* ================= BOOT ================= */

document.addEventListener(
  "DOMContentLoaded",
  () => VideoDashboard.init()
);
