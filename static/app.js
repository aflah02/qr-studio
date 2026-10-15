(() => {
  "use strict";
  const $ = id => document.getElementById(id);
  const fileInput = $("logo"), buttons = [$("download-file"), $("download-zip")];
  let logo = null, timer = null, serial = 0, controller = null, exportController = null, result = null;
  function busy(value) {
    $("generate").disabled = value; $("spinner").hidden = !value;
    $("button-label").textContent = value ? "Creating your QR code" : "Create QR code";
    $("canvas").classList.toggle("updating", value); $("canvas").setAttribute("aria-busy", String(value));
  }
  function exportLabel() { $("download-file").textContent = "Download " + $("export-format").selectedOptions[0].textContent; }
  function message(text, className = "") { $("status").textContent = text; $("status").className = className; }
  function invalidate() {
    serial += 1; if (controller) controller.abort(); if (exportController) exportController.abort();
    clearTimeout(timer); result = null; buttons.forEach(button => { button.disabled = true; });
    exportLabel(); $("download-zip").textContent = "Download all formats as ZIP";
    for (const id of ["error", "adjustment", "scan-details", "preview-meta", "qr-preview"]) $(id).hidden = true;
    $("empty-state").hidden = false; busy(false);
    $("canvas").style.aspectRatio = "1";
  }
  function showError(text) { $("error").textContent = text; $("error").hidden = false; message("Check your input", "failed"); }
  function updateOptions() {
    const noLogo = $("logo-mode").value === "none";
    $("logo-upload-field").hidden = noLogo; $("bw-options").hidden = $("logo-mode").value !== "bw";
    fileInput.disabled = noLogo;
    for (const id of ["logo-percent", "padding", "auto-reduce"]) $(id).disabled = noLogo;
    const custom = $("pixels").value === "custom";
    $("custom-dimensions").hidden = !custom; $("custom-size-hint").hidden = !custom;
  }
  function schedule() {
    updateOptions(); invalidate();
    if (!$("url").value.trim()) { message("Ready when you are"); return; }
    message("Waiting for your changes…"); timer = setTimeout(generate, 700);
  }
  function setLogo(file) {
    if (file && file.size > 5 * 1024 * 1024) {
      logo = null; fileInput.value = ""; $("selected-file").hidden = true;
      invalidate(); showError("Choose a logo smaller than 5 MB."); return;
    }
    logo = file; $("selected-file").hidden = !file;
    $("file-name").textContent = file ? file.name + " · " + Math.max(1,Math.round(file.size/1024)) + " KB" : "";
    schedule();
  }
  function formData() {
    const mode = $("logo-mode").value, custom = $("pixels").value === "custom";
    const data = new FormData(); data.set("url", $("url").value.trim());
    data.set("logo_mode", mode === "none" ? "none" : "with_logo");
    data.set("monochrome", mode === "bw" ? "true" : "false"); data.set("bw_threshold", $("bw-threshold").value);
    if (logo && mode !== "none") data.set("logo", logo, logo.name);
    data.set("logo_percent", $("logo-percent").value); data.set("padding_percent", $("padding").value);
    data.set("pixels", custom ? "4096" : $("pixels").value);
    if (custom) { data.set("width", $("custom-width").value); data.set("height", $("custom-height").value); }
    data.set("dpi", $("dpi").value); data.set("auto_reduce", $("auto-reduce").checked ? "true" : "false");
    data.set("module_style", $("module-style").value); data.set("canvas_shape", $("canvas-shape").value);
    return data;
  }
  function base64Bytes(value) { return Uint8Array.from(atob(value), char => char.charCodeAt(0)); }
  function saveBlob(blob, filename) {
    const url = URL.createObjectURL(blob), link = document.createElement("a");
    link.href = url; link.download = filename; document.body.append(link); link.click(); link.remove();
    setTimeout(() => URL.revokeObjectURL(url), 30000);
  }
  async function responseError(response) {
    let payload = null;
    try { payload = await response.json(); } catch (_) {}
    const detail = payload && payload.detail;
    return Array.isArray(detail) ? detail.map(item => item.msg).join(". ") : detail || "The request could not be completed. Please try again.";
  }
  async function generate() {
    clearTimeout(timer);
    if (!$("url").value.trim()) { invalidate(); showError("Enter a URL to create a QR code."); return; }
    if (controller) controller.abort(); controller = new AbortController(); const request = ++serial;
    result = null; buttons.forEach(button => { button.disabled = true; });
    $("error").hidden = true; busy(true); message("Creating and checking…");
    try {
      const response = await fetch("/api/generate", {method:"POST",body:formData(),signal:controller.signal});
      if (!response.ok) throw new Error(await responseError(response));
      const data = await response.json(); if (request !== serial) return;
      result = data;
      $("qr-preview").src = "data:image/png;base64," + data.preview_base64; $("qr-preview").alt = "QR code for " + data.url;
      $("qr-preview").hidden = false; $("empty-state").hidden = true; $("preview-meta").hidden = false;
      $("canvas").style.aspectRatio = data.width + " / " + data.height;
      $("dimensions").textContent = data.width.toLocaleString() + " × " + data.height.toLocaleString() + " px · " + data.dpi + " dpi · " + (data.width*25.4/data.dpi).toFixed(1) + " × " + (data.height*25.4/data.dpi).toFixed(1) + " mm";
      $("destination").textContent = data.url; $("destination").href = data.url;
      message(data.verified ? "✓ Scan check passed" : "Scan check did not pass",data.verified ? "passed" : "failed");
      $("adjustment").hidden = !data.logo_reduced && data.verified;
      if (!data.verified) $("adjustment").textContent = "Try a smaller logo, a simpler style or a higher output resolution so the code is easier to scan.";
      else if (data.logo_reduced) $("adjustment").textContent = "Logo size adjusted from " + data.requested_logo_percent + "% to " + data.used_logo_percent + "% so the QR code scans.";
      $("scan-details").hidden = false;
      $("scan-checks").replaceChildren(...data.checks.map(check => {
        const item = document.createElement("li"); item.className = check.passed ? "passed" : "failed";
        item.textContent = (check.passed ? "✓" : "✗") + " " + check.label + " at " + check.pixels + " px"; return item;
      }));
      buttons.forEach(button => { button.disabled = false; }); exportLabel();
    } catch (error) {
      if (error.name !== "AbortError" && request === serial) showError(error.message || "Could not reach the app. Please try again.");
    } finally { if (request === serial) busy(false); }
  }
  async function exportFile(kind) {
    if (!result) return;
    if (kind === "png") { saveBlob(new Blob([base64Bytes(result.png_base64)],{type:"image/png"}),result.filename+".png"); return; }
    if (kind === "svg") { saveBlob(new Blob([result.svg],{type:"image/svg+xml"}),result.filename+".svg"); return; }
    const request = serial, stem = result.filename, data = formData(); data.set("format",kind);
    if (exportController) exportController.abort(); exportController = new AbortController();
    buttons.forEach(button => { button.disabled = true; }); $("error").hidden = true;
    const button = kind === "zip" ? $("download-zip") : $("download-file");
    button.textContent = "Preparing " + kind.toUpperCase() + "…";
    try {
      const response = await fetch("/api/export",{method:"POST",body:data,signal:exportController.signal});
      if (!response.ok) throw new Error(await responseError(response));
      const blob = await response.blob();
      if (request === serial && result) saveBlob(blob,stem+"."+kind);
    } catch (error) {
      if (error.name !== "AbortError" && request === serial) showError(error.message || "Download could not be prepared.");
    } finally {
      if (request === serial) { buttons.forEach(item => { item.disabled = !result; }); exportLabel(); $("download-zip").textContent = "Download all formats as ZIP"; }
    }
  }
  $("qr-form").addEventListener("submit", event => { event.preventDefault(); generate(); });
  $("url").addEventListener("input",schedule);
  $("logo-mode").addEventListener("change",schedule);
  $("bw-threshold").addEventListener("input",() => { $("bw-value").textContent = $("bw-threshold").value; schedule(); });
  for (const id of ["logo-percent","padding","pixels","dpi","auto-reduce","custom-width","custom-height","module-style","canvas-shape"]) $(id).addEventListener("input",() => {
    $("logo-value").textContent = $("logo-percent").value + "%"; $("padding-value").textContent = $("padding").value + "%"; schedule();
  });
  $("export-format").addEventListener("change",exportLabel);
  $("download-file").addEventListener("click",() => exportFile($("export-format").value));
  $("download-zip").addEventListener("click",() => exportFile("zip"));
  fileInput.addEventListener("change",() => setLogo(fileInput.files[0] || null));
  $("remove-logo").addEventListener("click",() => { fileInput.value = ""; setLogo(null); });
  for (const event of ["dragenter","dragover"]) $("dropzone").addEventListener(event,e => { e.preventDefault(); $("dropzone").classList.add("dragging"); });
  for (const event of ["dragleave","drop"]) $("dropzone").addEventListener(event,e => { e.preventDefault(); $("dropzone").classList.remove("dragging"); });
  $("dropzone").addEventListener("drop",event => { if (event.dataTransfer.files.length) { fileInput.value = ""; setLogo(event.dataTransfer.files[0]); } });
  window.addEventListener("beforeunload",() => { if (controller) controller.abort(); if (exportController) exportController.abort(); });
  updateOptions(); exportLabel();
})();

