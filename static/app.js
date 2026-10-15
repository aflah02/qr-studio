(() => {
  "use strict";
  const $ = id => document.getElementById(id);
  const fileInput = $("logo"), downloads = [$("download-png"), $("download-svg"), $("download-zip")];
  let logo = null, timer = null, serial = 0, controller = null, objectUrls = [];
  function revokeDownloads() {
    for (const url of objectUrls) URL.revokeObjectURL(url);
    objectUrls = [];
    for (const link of downloads) { link.removeAttribute("href"); link.classList.add("disabled"); link.setAttribute("aria-disabled", "true"); link.tabIndex = -1; }
  }
  function busy(value) {
    $("generate").disabled = value; $("spinner").hidden = !value;
    $("button-label").textContent = value ? "Creating your QR code" : "Create QR code";
    $("canvas").classList.toggle("updating", value); $("canvas").setAttribute("aria-busy", String(value));
  }
  function message(text, className = "") { $("status").textContent = text; $("status").className = className; }
  function invalidate() {
    serial += 1; if (controller) controller.abort(); clearTimeout(timer); revokeDownloads();
    for (const id of ["error", "adjustment", "scan-details", "preview-meta", "qr-preview"]) $(id).hidden = true;
    $("empty-state").hidden = false; busy(false);
  }
  function showError(text) { $("error").textContent = text; $("error").hidden = false; message("Check your input", "failed"); }
  function updateLogoMode() {
    const noLogo = $("logo-mode").value === "none";
    $("logo-upload-field").hidden = noLogo;
    $("bw-options").hidden = $("logo-mode").value !== "bw";
    fileInput.disabled = noLogo;
    for (const id of ["logo-percent", "padding", "auto-reduce"]) $(id).disabled = noLogo;
  }
  function schedule() {
    invalidate(); if (!$("url").value.trim()) { message("Ready when you are"); return; }
    message("Waiting for your changes…"); timer = setTimeout(generate, 700);
  }
  function setLogo(file) {
    if (file && file.size > 5 * 1024 * 1024) {
      logo = null; fileInput.value = ""; $("selected-file").hidden = true;
      invalidate(); showError("Choose a logo smaller than 5 MB."); return;
    }
    logo = file; $("selected-file").hidden = !file;
    $("file-name").textContent = file ? `${file.name} · ${Math.max(1, Math.round(file.size / 1024))} KB` : "";
    schedule();
  }
  function base64Bytes(value) { return Uint8Array.from(atob(value), char => char.charCodeAt(0)); }
  function download(link, bytes, type, filename) {
    const url = URL.createObjectURL(new Blob([bytes], {type})); objectUrls.push(url);
    link.href = url; link.download = filename; link.classList.remove("disabled"); link.setAttribute("aria-disabled", "false"); link.tabIndex = 0;
  }
  async function generate() {
    clearTimeout(timer); const url = $("url").value.trim();
    if (!url) { invalidate(); showError("Enter a URL to create a QR code."); return; }
    if (controller) controller.abort(); controller = new AbortController(); const request = ++serial;
    revokeDownloads(); $("error").hidden = true; busy(true); message("Creating and checking…");
    const mode = $("logo-mode").value;
    const data = new FormData(); data.set("url", url);
    data.set("logo_mode", mode === "none" ? "none" : "with_logo");
    data.set("monochrome", mode === "bw" ? "true" : "false");
    data.set("bw_threshold", $("bw-threshold").value);
    if (logo && mode !== "none") data.set("logo", logo, logo.name);
    data.set("logo_percent", $("logo-percent").value); data.set("padding_percent", $("padding").value);
    data.set("pixels", $("pixels").value); data.set("dpi", $("dpi").value); data.set("auto_reduce", $("auto-reduce").checked ? "true" : "false");
    try {
      const response = await fetch("/api/generate", {method: "POST", body: data, signal: controller.signal});
      const result = await response.json(); if (request !== serial) return;
      if (!response.ok) {
        const detail = Array.isArray(result.detail) ? result.detail.map(item => item.msg).join(". ") : result.detail;
        throw new Error(detail || "Your QR code could not be created. Please try again.");
      }
      $("qr-preview").src = "data:image/png;base64," + result.preview_base64; $("qr-preview").alt = "QR code for " + result.url;
      $("qr-preview").hidden = false; $("empty-state").hidden = true; $("preview-meta").hidden = false;
      $("dimensions").textContent = `${result.pixels.toLocaleString()} × ${result.pixels.toLocaleString()} px · ${result.dpi} dpi`;
      $("destination").textContent = result.url; $("destination").href = result.url;
      message(result.verified ? "✓ Scan check passed" : "Scan check did not pass", result.verified ? "passed" : "failed");
      $("adjustment").hidden = !result.logo_reduced && result.verified;
      if (!result.verified) $("adjustment").textContent = "Try a smaller logo or less space around it so the code is easier to scan.";
      else if (result.logo_reduced) $("adjustment").textContent = `Logo size adjusted from ${result.requested_logo_percent}% to ${result.used_logo_percent}% so the QR code scans.`;
      $("scan-details").hidden = false;
      $("scan-checks").replaceChildren(...result.checks.map(check => {
        const item = document.createElement("li"); item.className = check.passed ? "passed" : "failed";
        item.textContent = `${check.passed ? "✓" : "✗"} ${check.label} at ${check.pixels} px`; return item;
      }));
      download($("download-png"), base64Bytes(result.png_base64), "image/png", result.filename + ".png");
      download($("download-svg"), result.svg, "image/svg+xml", result.filename + ".svg");
      download($("download-zip"), base64Bytes(result.zip_base64), "application/zip", result.filename + ".zip");
    } catch (error) { if (error.name !== "AbortError" && request === serial) showError(error.message || "Could not reach the app. Please try again."); }
    finally { if (request === serial) busy(false); }
  }
  $("qr-form").addEventListener("submit", event => { event.preventDefault(); generate(); });
  $("url").addEventListener("input", schedule);
  $("logo-mode").addEventListener("change", () => { updateLogoMode(); schedule(); });
  $("bw-threshold").addEventListener("input", () => { $("bw-value").textContent = $("bw-threshold").value; schedule(); });
  for (const id of ["logo-percent", "padding", "pixels", "dpi", "auto-reduce"]) $(id).addEventListener("input", () => {
    $("logo-value").textContent = $("logo-percent").value + "%"; $("padding-value").textContent = $("padding").value + "%"; schedule();
  });
  fileInput.addEventListener("change", () => setLogo(fileInput.files[0] || null));
  $("remove-logo").addEventListener("click", () => { fileInput.value = ""; setLogo(null); });
  for (const event of ["dragenter", "dragover"]) $("dropzone").addEventListener(event, e => { e.preventDefault(); $("dropzone").classList.add("dragging"); });
  for (const event of ["dragleave", "drop"]) $("dropzone").addEventListener(event, e => { e.preventDefault(); $("dropzone").classList.remove("dragging"); });
  $("dropzone").addEventListener("drop", event => { if (event.dataTransfer.files.length) { fileInput.value = ""; setLogo(event.dataTransfer.files[0]); } });
  for (const link of downloads) link.addEventListener("click", event => { if (link.getAttribute("aria-disabled") === "true") event.preventDefault(); });
  window.addEventListener("beforeunload", () => { if (controller) controller.abort(); for (const url of objectUrls) URL.revokeObjectURL(url); });
  updateLogoMode();
})();
