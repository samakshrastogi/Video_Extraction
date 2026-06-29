const VideoDashboardTable = {

  /* ================= COLUMN MAP ================= */

  columnMap: null,

  initColumnMap() {

    if (this.columnMap) return;

    this.columnMap = {};

    VideoDashboard.columns.forEach(col => {
      this.columnMap[col.key] = col;
    });
  },


  /* ================= TABLE HEADER ================= */

  renderColGroup() {

    const colGroup = document.getElementById("tableColGroup");
    if (!colGroup) return;

    const selected = VideoDashboard.state.selectedColumns;
    const order = VideoDashboard.state.columnOrder;

    let html = "";

    for (let i = 0; i < order.length; i++) {
      if (selected.has(order[i])) html += "<col>";
    }

    colGroup.innerHTML = html;
  },


  renderHeaders() {

    this.initColumnMap();
    this.renderColGroup();

    const head = document.getElementById("tableHeader");
    if (!head) return;

    const selected = VideoDashboard.state.selectedColumns;
    const order = VideoDashboard.state.columnOrder;

    let html = "";

    for (let i = 0; i < order.length; i++) {

      const key = order[i];
      if (!selected.has(key)) continue;

      html += `<th>${this.columnMap[key]?.label || key}</th>`;
    }

    head.innerHTML = html;
  },


  /* ================= FORMATTERS ================= */

  formatDuration(ms) {
    if (!ms) return "";
    const sec = Math.floor(ms / 1000);
    return `${Math.floor(sec / 60)} min ${sec % 60} sec`;
  },

  formatBitrate(b) {
    if (!b) return "";
    return (b / 1_000_000).toFixed(2) + " Mbps";
  },

  formatSize(b) {
    if (!b) return "";
    return (b / 1024 / 1024).toFixed(2) + " MB";
  },


  /* ================= LOAD VIDEOS ================= */

  async loadVideos(page = 1) {

    const VD = VideoDashboard;

    VD.state.page = page;

    if (!VD.tbody) return;

    VD.setUIState("loading");

    try {

      const url = VD.buildQuery(page);
      const data = await VD.safeFetch(url);

      const total = data.total || 0;
      const size = data.size || VD.state.size;

      const totalRowsEl = document.getElementById("totalRows");
      if (totalRowsEl) totalRowsEl.innerText = `Total Rows: ${total}`;

      VD.state.totalPages = Math.max(1, Math.ceil(total / size));

      if (!data.results?.length) {
        VD.tbody.innerHTML = "";
        VD.setUIState("empty");
        return;
      }

      this.renderTable(data.results);
      this.initRowEvents();

      VD.setUIState("table");

      if (VD.pageInfo) {
        VD.pageInfo.innerText =
          `Page ${VD.state.page} / ${VD.state.totalPages}`;
      }

      this.prefetchNextPage();

    } catch (err) {

      console.error(err);
      VideoDashboard.setUIState("error");
    }
  },


  /* ================= PREFETCH ================= */

  async prefetchNextPage() {

    const VD = VideoDashboard;

    if (VD.state.page >= VD.state.totalPages) return;

    try {

      const nextUrl = VD.buildQuery(VD.state.page + 1);
      fetch(nextUrl).catch(() => { });

    } catch { }
  },


  /* ================= TABLE RENDER ================= */

  renderTable(rows) {

    const VD = VideoDashboard;

    const selected = VD.state.selectedColumns;
    const order = VD.state.columnOrder;

    let html = "";

    const baseIndex = (VD.state.page - 1) * VD.state.size;

    for (let i = 0; i < rows.length; i++) {

      const v = rows[i];
      const serial = baseIndex + i + 1;

      const durationMs =
        v.duration ??
        (v.duration_seconds != null ? v.duration_seconds * 1000 : null);

      const thumbnailUrl = v.thumbnail_s3_key
        ? `${VD.S3_ENDPOINT}/${VD.S3_BUCKET}/${v.thumbnail_s3_key}`
        : null;

      const map = {

        sno: serial,
        title: v.title || "",
        category: v.category || "",
        resolution: v.resolution || "",
        orientation: v.orientation || "",
        duration: this.formatDuration(durationMs),
        fps: v.fps ?? "",
        bitrate: this.formatBitrate(v.bitrate),
        video_codec: v.video_codec || "",
        audio_codec: v.audio_codec || "",
        audio_channels: v.audio_channels ?? "",
        file_size: this.formatSize(v.file_size),
        frame_count: v.frame_count ?? "",
        pixel_format: v.pixel_format ?? "",
        bit_depth: v.bit_depth ?? "",
        container_format: v.container_format || "",
        audio_sample_rate: v.audio_sample_rate ?? "",
        audio_bitrate: this.formatBitrate(v.audio_bitrate),

        /* Thumbnail clickable */
        thumbnail: thumbnailUrl
          ? `<div class="thumb-cell">
                <div class="thumb-wrapper">
                  <img
                    class="thumb-click"
                    src="${thumbnailUrl}"
                    loading="lazy"
                    data-title="${(v.title || "").replace(/"/g, "&quot;")}"
                    onerror="this.style.display='none'"
                  />
                </div>
             </div>`
          : "",

        keyframes:
          `<button type="button" class="btn-secondary open-frame-btn">
            Open
          </button>`
      };

      html += `<tr 
                data-video-url="${v.video_url || ""}"
                data-video-title="${(v.title || "").replace(/"/g, "&quot;")}"
              >`;

      for (let j = 0; j < order.length; j++) {

        const key = order[j];
        if (!selected.has(key)) continue;

        html += `<td>${map[key] ?? ""}</td>`;
      }

      html += "</tr>";
    }

    VD.tbody.innerHTML = html;
  },


  /* ================= ROW EVENTS ================= */

  initRowEvents() {

    const tbody = VideoDashboard.tbody;
    if (!tbody || tbody.dataset.bound) return;

    tbody.dataset.bound = "1";

    tbody.addEventListener("click", (e) => {

      /* ===== FRAME BUTTON ===== */
      const frameBtn = e.target.closest(".open-frame-btn");

      if (frameBtn) {

        const tr = frameBtn.closest("tr");
        if (!tr) return;

        const url = tr.dataset.videoUrl;
        const title = tr.dataset.videoTitle || "Video Frames";

        if (url) VideoDashboard.openFrames(url, title);

        return;
      }


      /* ===== THUMBNAIL CLICK ===== */
      const thumb = e.target.closest(".thumb-click");

      if (thumb) {

        const src = thumb.src;
        const title = thumb.dataset.title || "Thumbnail";

        VideoDashboard.openThumbnailModal(src, title);
      }
    });
  }

};
