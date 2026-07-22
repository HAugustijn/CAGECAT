/*
 * CagecatViz — shared helpers for the client-side visualisation editors
 * (plasmidViz, geneNeighborhood): SVG element creation, colour utilities, a file
 * downloader, transient alerts, and self-contained SVG/PNG/PDF export.
 *
 * Keeping export in one place means both editors produce identical, dependency-
 * free, offline-capable figures (vector SVG/PDF, high-resolution raster PNG).
 */
(function () {
  "use strict";

  const SVG_NS = "http://www.w3.org/2000/svg";

  function svgEl(tag, attrs) {
    const node = document.createElementNS(SVG_NS, tag);
    if (attrs) for (const k in attrs) node.setAttribute(k, attrs[k]);
    return node;
  }

  function escapeHtml(s) {
    return String(s).replace(/[&<>"]/g, (c) =>
      ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
  }

  function toHex(color) {
    // Normalise #rgb / #rrggbb / #rrggbbaa to #rrggbb for <input type=color>.
    if (!color) return "#888888";
    if (color[0] === "#") {
      if (color.length === 4) return "#" + [1, 2, 3].map((i) => color[i] + color[i]).join("");
      return "#" + color.slice(1, 7);
    }
    return "#888888";
  }

  function download(blob, filename) {
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    a.remove();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  }

  const _flashTimers = new WeakMap();
  function flash(box, msg, type) {
    if (typeof box === "string") box = document.getElementById(box);
    if (!box) return;
    box.className = "alert alert-" + (type || "info") + " mt-3 mb-0";
    box.textContent = msg;
    clearTimeout(_flashTimers.get(box));
    _flashTimers.set(box, setTimeout(() => (box.className = "alert d-none mt-3 mb-0"), 6000));
  }

  // Clone an SVG for export: strip the interactive pan/zoom transform and any
  // selection styling, add a solid background, and return the standalone node.
  function standaloneSvg(svg, opts) {
    opts = opts || {};
    const clone = svg.cloneNode(true);
    const view = clone.querySelector(opts.viewSelector || ".pv-view");
    if (view) view.removeAttribute("transform");
    clone.querySelectorAll(".pv-selected").forEach((n) => n.classList.remove("pv-selected"));
    clone.setAttribute("xmlns", SVG_NS);
    clone.setAttribute("xmlns:xlink", "http://www.w3.org/1999/xlink");
    const vb = (clone.getAttribute("viewBox") || "0 0 1000 1000").split(/\s+/).map(Number);
    const bg = svgEl("rect", { x: vb[0], y: vb[1], width: vb[2], height: vb[3],
                               fill: opts.background || "#ffffff" });
    clone.insertBefore(bg, clone.firstChild);
    return { node: clone, x: vb[0], y: vb[1], width: vb[2], height: vb[3] };
  }

  function exportSvg(svg, filename, opts) {
    const { node } = standaloneSvg(svg, opts);
    const data = new XMLSerializer().serializeToString(node);
    download(new Blob([data], { type: "image/svg+xml" }), filename + ".svg");
  }

  function exportPng(svg, filename, scale, opts) {
    const { node, width, height } = standaloneSvg(svg, opts);
    const data = new XMLSerializer().serializeToString(node);
    const url = URL.createObjectURL(new Blob([data], { type: "image/svg+xml" }));
    const img = new Image();
    img.onload = () => {
      const canvas = document.createElement("canvas");
      canvas.width = Math.round(width * scale);
      canvas.height = Math.round(height * scale);
      const ctx = canvas.getContext("2d");
      ctx.fillStyle = (opts && opts.background) || "#ffffff";
      ctx.fillRect(0, 0, canvas.width, canvas.height);
      ctx.drawImage(img, 0, 0, canvas.width, canvas.height);
      URL.revokeObjectURL(url);
      canvas.toBlob((blob) => download(blob, filename + ".png"), "image/png");
    };
    img.onerror = () => { URL.revokeObjectURL(url); throw new Error("PNG export failed"); };
    img.src = url;
  }

  function exportPdf(svg, filename, opts) {
    // Vector PDF via the browser's print dialog ("Save as PDF") — no PDF library,
    // works offline, keeps the figure fully scalable.
    const { node } = standaloneSvg(svg, opts);
    const data = new XMLSerializer().serializeToString(node);
    const win = window.open("", "_blank");
    if (!win) return false;
    const landscape = opts && opts.landscape ? " landscape" : "";
    win.document.write(
      `<!doctype html><html><head><title>${escapeHtml(filename)}</title>` +
      `<style>@page{margin:12mm;size:auto${landscape};}html,body{margin:0;height:100%;}` +
      `svg{width:100%;height:auto;max-height:100vh;display:block;}</style></head>` +
      `<body>${data}<script>window.onload=function(){setTimeout(function(){window.print();},250);};<\/script></body></html>`
    );
    win.document.close();
    return true;
  }

  window.CagecatViz = {
    SVG_NS, svgEl, escapeHtml, escapeAttr: escapeHtml, toHex,
    download, flash, standaloneSvg, exportSvg, exportPng, exportPdf,
  };
})();
