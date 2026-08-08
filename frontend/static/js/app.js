const API = "/api";
let state = {
  cases: [],
  activeCase: null,
  images: [],
  activeImageId: null,
};

// ---------- helpers ----------
async function api(path, opts = {}) {
  const res = await fetch(`${API}${path}`, {
    headers: opts.body && !(opts.body instanceof FormData) ? { "Content-Type": "application/json" } : {},
    ...opts,
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ error: res.statusText }));
    throw new Error(err.error || "request failed");
  }
  return res.status === 204 ? null : res.json();
}

function toast(msg, isError = false) {
  const el = document.getElementById("toast");
  el.textContent = msg;
  el.style.borderColor = isError ? "var(--red)" : "var(--accent)";
  el.classList.remove("hidden");
  setTimeout(() => el.classList.add("hidden"), 3200);
}

// Every value that can originate from user input, EXIF/OCR content, or
// anything embedded in an uploaded image must be escaped before it's
// placed into innerHTML -- EXIF fields and OCR'd text are attacker-
// influenceable (a crafted image could carry "<img onerror=...>" as
// visible text) even though the platform itself is trusted.
function escapeHtml(str) {
  if (str === null || str === undefined) return "";
  return String(str)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

// Plain key/value rows -- both key and value are escaped as text.
function kv(rows) {
  if (!rows || rows.length === 0) return `<div class="empty-note">No data available.</div>`;
  return rows
    .map(([k, v]) => `<div class="kv-row"><div class="k">${escapeHtml(k)}</div><div class="v">${v === null || v === undefined ? "—" : escapeHtml(v)}</div></div>`)
    .join("");
}

function fmtBytes(n) {
  if (!n && n !== 0) return "—";
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`;
  return `${(n / 1024 / 1024).toFixed(2)} MB`;
}

// ---------- cases ----------
async function loadCases() {
  state.cases = await api("/cases");
  renderCaseList();
}

function renderCaseList() {
  const list = document.getElementById("caseList");
  if (state.cases.length === 0) {
    list.innerHTML = `<div class="empty-note">No cases yet.</div>`;
    return;
  }
  list.innerHTML = state.cases
    .map(
      (c) => `
    <div class="case-item ${state.activeCase && state.activeCase.id === c.id ? "active" : ""}" data-case-id="${c.id}">
      <div class="case-item-number">CASE #${escapeHtml(c.case_number)}</div>
      <div class="case-item-title">${escapeHtml(c.title)}</div>
      <div class="case-item-meta">${c.image_count} image(s) · ${escapeHtml(c.status)}</div>
    </div>`
    )
    .join("");
  list.querySelectorAll(".case-item").forEach((el) => {
    el.addEventListener("click", () => openCase(parseInt(el.dataset.caseId)));
  });
}

async function createCase() {
  const case_number = prompt("Case number (e.g. CC-2026-0041):");
  if (!case_number) return;
  const title = prompt("Case title:");
  if (!title) return;
  const investigator = prompt("Investigator name (optional):") || "";
  try {
    const c = await api("/cases", { method: "POST", body: JSON.stringify({ case_number, title, investigator }) });
    await loadCases();
    openCase(c.id);
    toast(`Case #${c.case_number} created`);
  } catch (e) {
    toast(e.message, true);
  }
}

async function openCase(caseId) {
  const c = await api(`/cases/${caseId}`);
  state.activeCase = c;
  state.images = c.images || [];
  state.activeImageId = state.images[0]?.id ?? null;

  document.getElementById("emptyState").classList.add("hidden");
  document.getElementById("caseWorkspace").classList.remove("hidden");
  renderCaseList();
  renderCaseHeader();
  renderOverview();
  renderImageGrid();
  populateImageSelectors();
  renderTimeline();
  renderNotes();
}

function renderCaseHeader() {
  const c = state.activeCase;
  // textContent, not innerHTML -- inherently safe regardless of content.
  document.getElementById("caseNumberLabel").textContent = `CASE #${c.case_number}`;
  document.getElementById("caseTitleLabel").textContent = c.title;
  document.getElementById("caseMetaLabel").textContent =
    `Investigator: ${c.investigator || "—"} · Status: ${c.status} · Opened: ${c.created_at}`;

  const btn = document.getElementById("btnToggleStatus");
  const isOpen = c.status === "open";
  btn.textContent = isOpen ? "Close Case" : "Reopen Case";
  btn.className = isOpen ? "btn-status btn-status-close" : "btn-status btn-status-reopen";
}

async function toggleCaseStatus() {
  const newStatus = state.activeCase.status === "open" ? "closed" : "open";
  try {
    const updated = await api(`/cases/${state.activeCase.id}`, {
      method: "PATCH",
      body: JSON.stringify({ status: newStatus }),
    });
    state.activeCase = { ...state.activeCase, ...updated };
    renderCaseHeader();
    renderCaseList();
    toast(newStatus === "closed" ? "Case closed" : "Case reopened");
  } catch (e) {
    toast(e.message, true);
  }
}

function renderOverview() {
  const c = state.activeCase;
  document.getElementById("overviewSummary").innerHTML = kv([
    ["Case Number", c.case_number],
    ["Title", c.title],
    ["Investigator", c.investigator || "—"],
    ["Description", c.description || "—"],
    ["Status", c.status],
    ["Created", c.created_at],
  ]);
  document.getElementById("overviewStats").innerHTML = `
    <div class="stat"><div class="stat-num">${state.images.length}</div><div class="stat-label">Evidence Images</div></div>
  `;
}

// ---------- images ----------
function renderImageGrid() {
  const grid = document.getElementById("imageGrid");
  if (state.images.length === 0) {
    grid.innerHTML = `<div class="empty-note">No evidence uploaded yet. Use "Upload Evidence" above.</div>`;
    return;
  }
  grid.innerHTML = state.images
    .map(
      (img) => `
    <div class="evidence-card" data-image-id="${img.id}">
      <button class="btn-remove-evidence" data-image-id="${img.id}" title="Remove this evidence">✕</button>
      <div class="evidence-thumb-wrap">
        <img class="evidence-thumb" src="${API}/images/${img.id}/file" loading="lazy" />
      </div>
      <div class="evidence-info">
        <div class="evidence-name">${escapeHtml(img.original_filename)}</div>
        <div class="evidence-hash">${escapeHtml(img.sha256)}</div>
        <div class="evidence-tag">EVIDENCE #${escapeHtml(img.image_uid)}</div>
      </div>
    </div>`
    )
    .join("");

  grid.querySelectorAll(".btn-remove-evidence").forEach((btn) => {
    btn.addEventListener("click", (e) => {
      e.stopPropagation();
      removeEvidence(parseInt(btn.dataset.imageId));
    });
  });

  applyTiltEffect(grid);
}

async function removeEvidence(imageId) {
  const img = state.images.find((i) => i.id === imageId);
  const label = img ? img.original_filename : "this evidence";
  if (!confirm(`Remove "${label}" from this case? This deletes the file and all analysis results for it. This cannot be undone.`)) {
    return;
  }
  try {
    await api(`/images/${imageId}`, { method: "DELETE" });
    await openCase(state.activeCase.id);
    toast("Evidence removed");
  } catch (e) {
    toast(e.message, true);
  }
}

// Subtle pointer-tracked 3D tilt on evidence cards -- purely cosmetic,
// degrades silently to a flat card if pointer events aren't available.
function applyTiltEffect(container) {
  container.querySelectorAll(".evidence-card").forEach((card) => {
    card.addEventListener("pointermove", (e) => {
      if (e.pointerType === "touch") return;
      const rect = card.getBoundingClientRect();
      const x = (e.clientX - rect.left) / rect.width - 0.5;
      const y = (e.clientY - rect.top) / rect.height - 0.5;
      card.style.transform = `perspective(700px) rotateY(${x * 8}deg) rotateX(${-y * 8}deg) translateZ(4px)`;
    });
    card.addEventListener("pointerleave", () => {
      card.style.transform = "";
    });
  });
}

function populateImageSelectors() {
  const selectors = ["metadataImageSelect", "visualImageSelect", "searchImageSelect", "similarityImageSelect", "manipulationImageSelect", "reportImageSelect"];
  const options = state.images
    .map((img) => `<option value="${img.id}">${escapeHtml(img.original_filename)} (#${escapeHtml(img.image_uid)})</option>`)
    .join("");
  selectors.forEach((id) => {
    const el = document.getElementById(id);
    el.innerHTML = options || `<option value="">No images</option>`;
    if (state.activeImageId) el.value = state.activeImageId;
  });
}

async function handleUpload(file) {
  if (!state.activeCase) return;
  const form = new FormData();
  form.append("case_id", state.activeCase.id);
  form.append("file", file);
  try {
    toast("Uploading and hashing evidence...");
    await api("/images", { method: "POST", body: form });
    await openCase(state.activeCase.id);
    toast("Evidence uploaded and hashed");
  } catch (e) {
    toast(e.message, true);
  }
}

// ---------- metadata tab ----------
async function loadMetadata(imageId) {
  if (!imageId) return;
  const img = await api(`/images/${imageId}`);
  document.getElementById("fileProps").innerHTML = kv([
    ["Filename", img.original_filename],
    ["MIME Type", img.mime_type],
    ["File Size", fmtBytes(img.file_size)],
    ["Dimensions", `${img.width} × ${img.height}`],
    ["Color Mode", img.color_mode],
    ["SHA-256", img.sha256],
    ["MD5", img.md5],
    ["SHA-1", img.sha1],
    ["Perceptual Hash", img.phash],
  ]);

  const exifRows = img.metadata.filter((m) => m.category === "exif");
  document.getElementById("exifFindings").innerHTML = exifRows.length
    ? kv(exifRows.map((r) => [r.field_name, r.field_value]))
    : `<div class="empty-note">No EXIF metadata present in this file.</div>`;

  const gpsRows = img.metadata.filter((m) => m.category === "gps");
  if (gpsRows.length) {
    document.getElementById("gpsFindings").innerHTML = kv(gpsRows.map((r) => [r.field_name, r.field_value]));
    document.getElementById("gpsCaveat").textContent =
      "GPS metadata can be modified and should not, by itself, be treated as proof of where this image was captured.";
  } else {
    document.getElementById("gpsFindings").innerHTML = `<div class="empty-note">No GPS metadata present in this file.</div>`;
    document.getElementById("gpsCaveat").textContent = "";
  }
}

// ---------- visual / OCR / location tab ----------
async function runVisual(imageId) {
  toast("Running AI Visual Investigator...");
  const r = await api(`/analysis/${imageId}/visual`, { method: "POST" });
  document.getElementById("visualResults").innerHTML = kv([
    ["Faces Detected", r.faces_detected],
    ["Lighting", `${r.lighting.assessment} (brightness ${r.lighting.mean_brightness})`],
    ["Environment", r.color_environment.assessment],
  ]) + `<div class="caveat">${escapeHtml(r.note)}</div>`;
}

async function runOcr(imageId) {
  toast("Running OCR (English + Hindi + Gujarati)...");
  const r = await api(`/analysis/${imageId}/ocr`, { method: "POST" });
  const entityRows = Object.entries(r.entities || {}).map(([k, v]) => [k, v.join(", ")]);
  document.getElementById("ocrResults").innerHTML = `
    <div class="kv-grid">
      <div class="kv-row"><div class="k">Language mode</div><div class="v">${escapeHtml(r.language)}</div></div>
    </div>
    <div style="margin-top:10px; font-family: var(--mono); font-size:12px; white-space:pre-wrap; background: var(--bg-0); padding:10px; border-radius:4px; border:1px solid var(--border-soft);">
      ${r.extracted_text ? escapeHtml(r.extracted_text) : "No text detected."}
    </div>
    ${entityRows.length ? `<div class="kv-grid" style="margin-top:10px;">${kv(entityRows)}</div>` : ""}
  `;
}

async function runLocation(imageId) {
  toast("Correlating location clues...");
  const r = await api(`/analysis/${imageId}/location`);
  const clueHtml = r.clues.length
    ? r.clues
        .map(
          (c) =>
            `<div class="kv-row"><div class="k">${escapeHtml(c.label)}</div><div class="v">${escapeHtml(c.detail)}${
              c.caveat ? `<div class="caveat">${escapeHtml(c.caveat)}</div>` : ""
            }</div></div>`
        )
        .join("")
    : `<div class="empty-note">No location-relevant clues found.</div>`;
  document.getElementById("locationResults").innerHTML = `
    <div class="assessment-banner">${escapeHtml(r.narrative)}</div>
    <div class="kv-grid">${clueHtml}</div>
  `;
}

// ---------- search tab ----------
async function loadSearchLinks(imageId) {
  const r = await api(`/analysis/${imageId}/reverse-search-links`);
  const links = { ...r };
  const note = links.note;
  const imageUrl = links.image_url;
  delete links.note;
  delete links.image_url;

  document.getElementById("searchLinks").innerHTML = Object.entries(links)
    .map(([k, v]) => `<a href="${encodeURI(v)}" target="_blank" rel="noopener">${escapeHtml(k.replace(/_/g, " "))}</a>`)
    .join("");
  document.getElementById("searchNote").textContent = note;

  const previewEl = document.getElementById("searchPreview");
  previewEl.innerHTML = `
    <div class="search-preview-row">
      <img id="searchPreviewImg" class="search-preview-thumb" src="${encodeURI(imageUrl)}" />
      <div class="search-preview-info">
        <div class="search-preview-status" id="searchPreviewStatus">Loading preview…</div>
        <div class="search-preview-url">${escapeHtml(imageUrl)}</div>
        <button class="btn-action" id="btnCopyPublicLink">Copy Link</button>
      </div>
    </div>
  `;
  const img = document.getElementById("searchPreviewImg");
  const status = document.getElementById("searchPreviewStatus");
  img.onload = () => {
    status.textContent = "✓ Reachable — this is what search providers will fetch.";
    status.className = "search-preview-status search-preview-ok";
  };
  img.onerror = () => {
    status.textContent = "✗ This URL did not load. Reverse search will fail until this is reachable from outside your network — check your host's public URL/HTTPS setup.";
    status.className = "search-preview-status search-preview-fail";
  };
  document.getElementById("btnCopyPublicLink").addEventListener("click", async () => {
    try {
      await navigator.clipboard.writeText(imageUrl);
      toast("Link copied");
    } catch {
      toast("Could not copy — select and copy the URL manually", true);
    }
  });
}

// ---------- similarity tab ----------
async function runSimilarity(imageId) {
  toast("Scanning case for duplicates/similar images...");
  const r = await api(`/analysis/${imageId}/similarity`);
  document.getElementById("exactDuplicates").innerHTML = r.exact_duplicates.length
    ? kv(r.exact_duplicates.map((d) => [d.original_filename, `SHA-256 match`]))
    : `<div class="empty-note">No exact duplicates found in this case.</div>`;
  document.getElementById("similarImages").innerHTML = r.similar_images.length
    ? kv(r.similar_images.map((s) => [s.original_filename, `${s.similarity_pct}% similar (Hamming distance ${s.hamming_distance})`]))
    : `<div class="empty-note">No visually similar images found in this case.</div>`;
}

// ---------- manipulation tab ----------
async function runManipulation(imageId) {
  toast("Running Error Level Analysis and compression heuristics...");
  const r = await api(`/analysis/${imageId}/manipulation`, { method: "POST" });
  document.getElementById("manipulationSummary").textContent = r.summary;
  document.getElementById("manipulationIndicators").innerHTML = r.indicators.length
    ? r.indicators
        .map(
          (i) => `
      <div class="kv-row">
        <div class="k">${escapeHtml(i.indicator)}</div>
        <div class="v"><span class="severity-${escapeHtml(i.severity)}">[${escapeHtml(i.severity.toUpperCase())}]</span> ${escapeHtml(i.detail)}</div>
      </div>`
        )
        .join("")
    : `<div class="empty-note">No indicators surfaced.</div>`;
  await loadDerivatives(imageId);
}

async function runSynthetic(imageId) {
  toast("Running synthetic-media screening...");
  const r = await api(`/analysis/${imageId}/synthetic`, { method: "POST" });
  document.getElementById("syntheticResults").innerHTML =
    kv([
      ["Assessment", r.assessment],
      ["Confidence", r.confidence],
      ["Frequency Ratio", r.frequency_ratio],
    ]) + `<div class="caveat">${escapeHtml(r.disclaimer)}</div>`;
}

async function applyPreset(imageId, preset) {
  toast(`Applying preset: ${preset.replace(/_/g, " ")}...`);
  await api(`/images/${imageId}/enhance`, { method: "POST", body: JSON.stringify({ preset }) });
  await loadDerivatives(imageId);
  toast("Derivative created and hashed");
}

async function loadDerivatives(imageId) {
  const img = await api(`/images/${imageId}`);
  document.getElementById("derivativesList").innerHTML = img.derivatives.length
    ? img.derivatives
        .map(
          (d) => `
      <div class="derivative-item">
        <img src="${API}/images/derivatives/${d.id}/file" />
        <div class="label">${escapeHtml(d.label)}</div>
        <div class="hash">${escapeHtml(d.sha256)}</div>
      </div>`
        )
        .join("")
    : `<div class="empty-note">No derivatives generated yet.</div>`;
}

// ---------- timeline / notes ----------
async function renderTimeline() {
  const events = await api(`/cases/${state.activeCase.id}/timeline`);
  document.getElementById("timelineList").innerHTML = events.length
    ? events
        .map(
          (e) => `
      <div class="timeline-item">
        <div class="timeline-time">${escapeHtml(e.event_time || "Timestamp unknown")}</div>
        <div class="timeline-label">${escapeHtml(e.event_label)}</div>
        <div class="timeline-source">Source: ${escapeHtml(e.source_field || "—")}</div>
      </div>`
        )
        .join("")
    : `<div class="empty-note">No timeline events yet.</div>`;
}

async function renderNotes() {
  const notes = await api(`/cases/${state.activeCase.id}/notes`);
  document.getElementById("notesList").innerHTML = notes.length
    ? notes.map((n) => `<div class="note-item">${escapeHtml(n.note)}<div class="note-time">${escapeHtml(n.created_at)}</div></div>`).join("")
    : `<div class="empty-note">No notes yet.</div>`;
}

async function addNote() {
  const input = document.getElementById("noteInput");
  const note = input.value.trim();
  if (!note) return;
  await api(`/cases/${state.activeCase.id}/notes`, { method: "POST", body: JSON.stringify({ note }) });
  input.value = "";
  renderNotes();
}

// ---------- report tab ----------
async function generateReport(imageId) {
  toast("Generating forensic report PDF...");
  const r = await api(`/reports/${imageId}/generate`, { method: "POST" });
  document.getElementById("reportStatus").innerHTML = `
    Report generated successfully.
    <a href="${encodeURI(r.download_url)}" style="color: var(--accent-hi); margin-left: 8px;">Download PDF</a>
  `;
}

// ---------- tabs ----------
function initTabs() {
  document.querySelectorAll(".tab").forEach((tab) => {
    tab.addEventListener("click", () => {
      document.querySelectorAll(".tab").forEach((t) => t.classList.remove("active"));
      document.querySelectorAll(".tab-panel").forEach((p) => p.classList.remove("active"));
      tab.classList.add("active");
      document.getElementById(`panel-${tab.dataset.tab}`).classList.add("active");
    });
  });
}

// ---------- mobile nav ----------
function initMobileNav() {
  const sidebar = document.getElementById("sidebar");
  const overlay = document.getElementById("sidebarOverlay");
  const menuBtn = document.getElementById("btnMobileMenu");

  const open = () => { sidebar.classList.add("open"); overlay.classList.add("visible"); };
  const close = () => { sidebar.classList.remove("open"); overlay.classList.remove("visible"); };

  menuBtn.addEventListener("click", () => {
    sidebar.classList.contains("open") ? close() : open();
  });
  overlay.addEventListener("click", close);

  // auto-close after picking a case on mobile
  sidebar.addEventListener("click", (e) => {
    if (e.target.closest(".case-item") && window.innerWidth <= 900) close();
  });
}

// ---------- wire up ----------
function init() {
  initTabs();
  initMobileNav();
  loadCases();

  document.getElementById("btnNewCase").addEventListener("click", createCase);
  document.getElementById("btnToggleStatus").addEventListener("click", toggleCaseStatus);

  document.getElementById("fileInput").addEventListener("change", (e) => {
    if (e.target.files[0]) handleUpload(e.target.files[0]);
  });

  document.getElementById("btnAddNote").addEventListener("click", addNote);

  document.getElementById("metadataImageSelect").addEventListener("change", (e) => loadMetadata(e.target.value));

  document.getElementById("btnRunVisual").addEventListener("click", () => {
    const id = document.getElementById("visualImageSelect").value;
    if (id) runVisual(id);
  });
  document.getElementById("btnRunOcr").addEventListener("click", () => {
    const id = document.getElementById("visualImageSelect").value;
    if (id) runOcr(id);
  });
  document.getElementById("btnRunLocation").addEventListener("click", () => {
    const id = document.getElementById("visualImageSelect").value;
    if (id) runLocation(id);
  });

  document.getElementById("btnGetSearchLinks").addEventListener("click", () => {
    const id = document.getElementById("searchImageSelect").value;
    if (id) loadSearchLinks(id);
  });

  document.getElementById("btnRunSimilarity").addEventListener("click", () => {
    const id = document.getElementById("similarityImageSelect").value;
    if (id) runSimilarity(id);
  });

  document.getElementById("btnRunManipulation").addEventListener("click", () => {
    const id = document.getElementById("manipulationImageSelect").value;
    if (id) runManipulation(id);
  });
  document.getElementById("btnRunSynthetic").addEventListener("click", () => {
    const id = document.getElementById("manipulationImageSelect").value;
    if (id) runSynthetic(id);
  });
  document.querySelectorAll(".btn-preset").forEach((btn) => {
    btn.addEventListener("click", () => {
      const id = document.getElementById("manipulationImageSelect").value;
      if (id) applyPreset(id, btn.dataset.preset);
    });
  });
  document.getElementById("manipulationImageSelect").addEventListener("change", (e) => {
    if (e.target.value) loadDerivatives(e.target.value);
  });

  document.getElementById("btnGenerateReport").addEventListener("click", () => {
    const id = document.getElementById("reportImageSelect").value;
    if (id) generateReport(id);
  });

  // auto-load metadata for the selected image when the metadata tab opens
  document.querySelector('.tab[data-tab="metadata"]').addEventListener("click", () => {
    const id = document.getElementById("metadataImageSelect").value;
    if (id) loadMetadata(id);
  });
  document.querySelector('.tab[data-tab="manipulation"]').addEventListener("click", () => {
    const id = document.getElementById("manipulationImageSelect").value;
    if (id) loadDerivatives(id);
  });
}

document.addEventListener("DOMContentLoaded", init);
