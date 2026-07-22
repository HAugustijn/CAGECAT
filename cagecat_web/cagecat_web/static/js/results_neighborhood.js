/*
 * results_neighborhood.js — the geneNeighborhood results viewer (page:
 * results_neighborhood.html). Renders the EFI-GNT-style neighborhood diagram
 * from a finished job's neighborhood.json.
 *
 * Every locus is drawn as a to-scale arrow track, aligned on its query (anchor)
 * gene, with homologous genes sharing a colour across loci. The job (a cblaster
 * handoff or an upload) is built server-side by the neighborhood runner; this
 * script polls the job, loads its neighborhood.json and ingests it. SVG and
 * export helpers are shared with plasmidViz through CagecatViz. Activates only on
 * the results page (guards on #gnResultsRoot).
 */
(function () {
  "use strict";

  const $ = (id) => document.getElementById(id);
  const el = CagecatViz.svgEl;
  const esc = CagecatViz.escapeHtml;
  const clamp = (v, lo, hi) => Math.min(hi, Math.max(lo, v));

  // Distinct, print-friendly family palette (Tableau-10/20 derived).
  const PALETTE = [
    "#4E79A7", "#F28E2B", "#59A14F", "#E15759", "#B07AA1", "#76B7B2",
    "#EDC948", "#FF9DA7", "#9C755F", "#86BCB6", "#D37295", "#A0CBE8",
    "#FFBE7D", "#8CD17D", "#B6992D", "#499894", "#F1CE63", "#D4A6C8",
    "#79706E", "#BAB0AC",
  ];
  const NOFAMILY = "#c9ced4";

  let _uid = 0;
  const uid = (p) => (p || "x") + ++_uid;

  // The results page has no inline alert bar; surface export edge-cases quietly.
  const flash = (msg) => console.warn("[geneNeighborhood] " + msg);

  function GeneNeighborhood(root, tooltip) {
    const model = {
      source: null,
      loci: [],                 // in display order
      families: new Map(),      // key -> {label, color, count, hidden}
      anchorFamilies: new Set(),
      activeFamily: null,
      style: {
        rowHeight: 48, geneHeight: 22, gutterWidth: 240,
        geneLabels: "anchor",   // 'none' | 'anchor' | 'all'
        showScaleBar: true, showLegend: true,
        fontFamily: "Roboto, sans-serif", fontSize: 12, backbone: "#9AA5B1",
      },
      view: { windowKb: 10 },
    };
    const W = 1200;
    let svg = null;

    // ── Model building ─────────────────────────────────────────────────────
    function anchorCentre(genes, useAnchorFlag) {
      const anchors = useAnchorFlag ? genes.filter((g) => g.anchor) : [];
      const src = anchors.length ? anchors : genes;
      if (!src.length) return 0;
      const sum = src.reduce((a, g) => a + (g.start + g.end) / 2, 0);
      return sum / src.length;
    }

    // Ingest a stored neighborhood (the runner's neighborhood.json), whose loci
    // already carry label/sub and genes tagged with family/anchor.
    function ingest(data) {
      model.source = data.source || "cblaster";
      model.anchorFamilies = new Set();
      model.loci = (data.loci || []).map((L) => {
        const genes = (L.genes || [])
          .filter((g) => g.start != null && g.end != null)
          .map((g) => {
            if (g.anchor && g.family) model.anchorFamilies.add(g.family);
            return {
              id: uid("g"), name: g.name, start: g.start, end: g.end,
              strand: g.strand, family: g.family || null,
              identity: g.identity, anchor: !!g.anchor,
              product: g.product || null, proteinId: g.protein_id || null,
            };
          });
        return {
          id: uid("L"),
          label: L.label || "locus",
          sub: L.sub || "",
          score: L.score != null ? L.score : null,
          scaffold: L.scaffold || null,
          isQuery: !!L.is_query,
          visible: true, flip: false,
          genes, anchorBp: anchorCentre(genes, true),
        };
      }).filter((L) => L.genes.length);
      assignFamilies(data.queries || []);
      finishLoad();
    }

    // Assign colours to families: preferred order first, then by frequency. For
    // uploads, singleton families (a gene seen once) stay grey to reduce noise,
    // unless they are the anchor family.
    function assignFamilies(preferred) {
      const counts = new Map();
      for (const L of model.loci)
        for (const g of L.genes) if (g.family) counts.set(g.family, (counts.get(g.family) || 0) + 1);

      const ordered = [];
      for (const k of preferred) if (counts.has(k) && !ordered.includes(k)) ordered.push(k);
      [...model.anchorFamilies].forEach((k) => { if (counts.has(k) && !ordered.includes(k)) ordered.push(k); });
      [...counts.keys()].filter((k) => !ordered.includes(k))
        .sort((a, b) => counts.get(b) - counts.get(a)).forEach((k) => ordered.push(k));

      const fams = new Map();
      let ci = 0;
      for (const k of ordered) {
        const anchorFam = model.anchorFamilies.has(k);
        const rare = model.source === "upload" && counts.get(k) < 2 && !anchorFam;
        const color = rare ? NOFAMILY : PALETTE[ci++ % PALETTE.length];
        fams.set(k, { label: k, color, count: counts.get(k), hidden: false });
      }
      model.families = fams;
    }

    function finishLoad() {
      model.activeFamily = null;
      model.anchorFamily = null; // family the loci are currently aligned on
      autoFitWindow();
      applySort($("gnSort").value);
      render();
      renderInspector();
      renderTable();
      updateInfo();
    }

    // Keep the synthetic "Query" locus pinned to the top row.
    function pinQuery() {
      const q = model.loci.filter((L) => L.isQuery);
      if (q.length) model.loci = q.concat(model.loci.filter((L) => !L.isQuery));
    }

    // Fit the flanking window to cover ~95% of genes' distance from their anchor
    // (ignoring the synthetic query row, whose layout is arbitrary).
    function autoFitWindow() {
      const dists = [];
      for (const L of model.loci) {
        if (L.isQuery) continue;
        for (const g of L.genes)
          dists.push(Math.abs((g.start + g.end) / 2 - L.anchorBp));
      }
      if (!dists.length) return;
      dists.sort((a, b) => a - b);
      const p95 = dists[Math.floor(dists.length * 0.95)] || dists[dists.length - 1];
      const kb = clamp(Math.ceil((p95 * 1.1) / 1000), 1, 50);
      model.view.windowKb = kb;
      $("gnWindow").value = kb;
      $("gnWindowVal").textContent = kb;
    }

    // ── Geometry ───────────────────────────────────────────────────────────
    function metrics() {
      const st = model.style;
      const plotLeft = st.gutterWidth;
      const plotRight = W - 30;
      const plotW = plotRight - plotLeft;
      const xc = plotLeft + plotW / 2;
      const windowBp = model.view.windowKb * 1000;
      const scale = plotW / 2 / windowBp;
      return { plotLeft, plotRight, plotW, xc, windowBp, scale };
    }
    const visibleLoci = () => model.loci.filter((L) => L.visible);

    // ── Rendering ──────────────────────────────────────────────────────────
    function render() {
      // Remove any previous SVG (keep the empty-state + tooltip nodes).
      const old = root.querySelector("svg");
      if (old) old.remove();
      const loci = visibleLoci();
      const empty = $("gnEmptyState");
      if (!loci.length) { if (empty) empty.classList.remove("d-none"); return; }
      if (empty) empty.classList.add("d-none");

      const st = model.style;
      const m = metrics();
      const topPad = 26;
      const rowsH = loci.length * st.rowHeight;
      const scaleH = st.showScaleBar ? 44 : 12;
      const legendH = st.showLegend ? legendHeight() : 0;
      const H = topPad + rowsH + scaleH + legendH + 16;

      svg = el("svg", { viewBox: `0 0 ${W} ${H}`, width: W, height: H });
      const g = el("g", { class: "pv-view gn-view" });
      svg.appendChild(g);

      // Clip plot content to the plotting area (keeps arrows out of the gutter).
      const clipId = "gnClip" + Math.random().toString(36).slice(2, 7);
      const defs = el("defs");
      const clip = el("clipPath", { id: clipId });
      clip.appendChild(el("rect", { x: m.plotLeft, y: 0, width: m.plotW, height: rowsH + topPad + 6 }));
      defs.appendChild(clip);
      g.appendChild(defs);

      // Anchor alignment guide + label.
      const guideTop = topPad - 6, guideBot = topPad + rowsH + 4;
      g.appendChild(el("line", {
        x1: m.xc, y1: guideTop, x2: m.xc, y2: guideBot,
        stroke: "#50A57A", "stroke-width": 1.2, "stroke-dasharray": "5 4", opacity: 0.7,
      }));
      const gl = el("text", {
        x: m.xc, y: guideTop - 2, "text-anchor": "middle",
        "font-family": st.fontFamily, "font-size": 11, fill: "#50A57A",
      });
      gl.textContent = "query";
      g.appendChild(gl);

      const plot = el("g", { "clip-path": `url(#${clipId})` });
      g.appendChild(plot);

      loci.forEach((L, i) => {
        const y = topPad + i * st.rowHeight + st.rowHeight / 2;
        drawGutter(g, L, y);
        // backbone
        plot.appendChild(el("line", {
          x1: m.plotLeft, y1: y, x2: m.plotRight, y2: y,
          stroke: st.backbone, "stroke-width": 1.4, opacity: 0.7,
        }));
        for (const gene of L.genes) drawGene(plot, L, gene, y, m);
        if (st.geneLabels !== "none") for (const gene of L.genes) drawGeneLabel(plot, L, gene, y, m);
      });

      let yCursor = topPad + rowsH;
      if (st.showScaleBar) yCursor = drawScaleBar(g, m, yCursor + 6);
      if (st.showLegend) drawLegend(g, m, yCursor + 8);

      root.appendChild(svg);
      attachInteractions();
    }

    function truncate(s, n) { s = String(s); return s.length > n ? s.slice(0, n - 1) + "…" : s; }

    function drawGutter(g, L, y) {
      const st = model.style;
      const t1 = el("text", {
        x: 8, y: y - 3, "font-family": st.fontFamily, "font-size": st.fontSize,
        "font-weight": 600, fill: "var(--bs-body-color, #272727)",
      });
      t1.textContent = truncate(L.label, 34);
      g.appendChild(t1);
      if (L.sub) {
        const t2 = el("text", {
          x: 8, y: y + 12, "font-family": st.fontFamily, "font-size": 9.5,
          fill: "var(--bs-secondary-color, #6c757d)",
        });
        t2.textContent = truncate(L.sub, 44);
        g.appendChild(t2);
      }
    }

    function geneColor(gene) {
      if (!gene.family) return NOFAMILY;
      const fam = model.families.get(gene.family);
      return fam ? fam.color : NOFAMILY;
    }
    const familyHidden = (gene) => gene.family && model.families.get(gene.family) &&
                                   model.families.get(gene.family).hidden;

    function geneX(L, bp, m) {
      const f = L.flip ? -1 : 1;
      return m.xc + f * (bp - L.anchorBp) * m.scale;
    }

    function drawGene(plot, L, gene, y, m) {
      if (familyHidden(gene)) return;
      const st = model.style;
      const xa = geneX(L, gene.start - 1, m);
      const xb = geneX(L, gene.end, m);
      const left = Math.min(xa, xb), right = Math.max(xa, xb);
      if (right < m.plotLeft - 20 || left > m.plotRight + 20) return; // off-window
      const h = gene.anchor ? st.geneHeight + 4 : st.geneHeight;
      const top = y - h / 2, bot = y + h / 2;
      const dir = gene.strand * (L.flip ? -1 : 1);
      const head = Math.min((right - left) * 0.5, h * 0.85);
      let d;
      if (gene.strand === 0) {
        d = `M${left},${top} H${right} V${bot} H${left} Z`;
      } else if (dir >= 0) {
        d = `M${left},${top} H${right - head} L${right},${y} L${right - head},${bot} H${left} Z`;
      } else {
        d = `M${right},${top} H${left + head} L${left},${y} L${left + head},${bot} H${right} Z`;
      }
      const dim = model.activeFamily && gene.family !== model.activeFamily;
      const path = el("path", {
        d, fill: geneColor(gene), "fill-opacity": 0.95,
        stroke: gene.anchor ? "#2b2f33" : "#00000055",
        "stroke-width": gene.anchor ? 1.4 : 0.6,
        class: "gn-gene" + (dim ? " gn-dim" : ""),
      });
      path.dataset.gid = gene.id;
      path.dataset.lid = L.id;
      plot.appendChild(path);
    }

    function drawGeneLabel(plot, L, gene, y, m) {
      const st = model.style;
      if (st.geneLabels === "anchor" && !gene.anchor) return;
      if (familyHidden(gene)) return;
      const xa = geneX(L, gene.start - 1, m), xb = geneX(L, gene.end, m);
      const mid = (xa + xb) / 2;
      if (mid < m.plotLeft || mid > m.plotRight) return;
      const t = el("text", {
        x: mid, y: y - (gene.anchor ? st.geneHeight / 2 + 6 : st.geneHeight / 2 + 4),
        "text-anchor": "middle", "font-family": st.fontFamily,
        "font-size": gene.anchor ? st.fontSize : st.fontSize - 2,
        "font-weight": gene.anchor ? 600 : 400,
        fill: "var(--bs-body-color, #272727)",
      });
      t.textContent = truncate(gene.name, gene.anchor ? 22 : 16);
      t.style.pointerEvents = "none";
      plot.appendChild(t);
    }

    function niceBp(target) {
      const pow = Math.pow(10, Math.floor(Math.log10(target)));
      const frac = target / pow;
      const nice = frac >= 5 ? 5 : frac >= 2 ? 2 : 1;
      return nice * pow;
    }

    function drawScaleBar(g, m, y) {
      const st = model.style;
      const bp = niceBp(model.view.windowKb * 1000 * 0.5);
      const px = bp * m.scale;
      const x0 = m.plotLeft, x1 = m.plotLeft + px;
      g.appendChild(el("line", { x1: x0, y1: y + 12, x2: x1, y2: y + 12, stroke: "var(--bs-body-color, #272727)", "stroke-width": 1.4 }));
      g.appendChild(el("line", { x1: x0, y1: y + 8, x2: x0, y2: y + 16, stroke: "var(--bs-body-color, #272727)", "stroke-width": 1.4 }));
      g.appendChild(el("line", { x1: x1, y1: y + 8, x2: x1, y2: y + 16, stroke: "var(--bs-body-color, #272727)", "stroke-width": 1.4 }));
      const label = bp >= 1000 ? (bp / 1000) + " kb" : bp + " bp";
      const t = el("text", {
        x: x1 + 8, y: y + 16, "font-family": st.fontFamily, "font-size": 11,
        fill: "var(--bs-body-color, #272727)",
      });
      t.textContent = label;
      g.appendChild(t);
      return y + 28;
    }

    function coloredFamilies() {
      return [...model.families.entries()].filter(([, f]) => f.color !== NOFAMILY && !f.hidden);
    }
    function legendHeight() {
      const n = coloredFamilies().length + 1; // +1 for "other/flanking"
      const perRow = Math.max(1, Math.floor((W - 40) / 190));
      return 22 + Math.ceil(n / perRow) * 20;
    }
    function drawLegend(g, m, y) {
      const st = model.style;
      const title = el("text", {
        x: 8, y: y + 4, "font-family": st.fontFamily, "font-size": 12,
        "font-weight": 700, fill: "var(--bs-body-color, #272727)",
      });
      title.textContent = "Gene families";
      g.appendChild(title);
      const items = coloredFamilies().map(([, f]) => [f.color, f.label + " (" + f.count + ")"]);
      items.push([NOFAMILY, model.source === "cblaster" ? "flanking gene" : "other / singleton"]);
      const perRow = Math.max(1, Math.floor((W - 40) / 190));
      items.forEach(([color, label], i) => {
        const col = i % perRow, rowN = Math.floor(i / perRow);
        const x = 12 + col * 190, ly = y + 18 + rowN * 20;
        g.appendChild(el("rect", { x, y: ly, width: 14, height: 12, rx: 2, fill: color, stroke: "#00000055", "stroke-width": 0.5 }));
        const t = el("text", { x: x + 20, y: ly + 10, "font-family": st.fontFamily, "font-size": 11, fill: "var(--bs-body-color, #272727)" });
        t.textContent = truncate(label, 24);
        g.appendChild(t);
      });
    }

    // ── Interaction ────────────────────────────────────────────────────────
    function attachInteractions() {
      svg.addEventListener("mousemove", onHover);
      svg.addEventListener("mouseleave", () => tooltip.classList.add("d-none"));
      // Click a gene to align every locus on that family. Clicking empty space
      // deselects (clears the highlight) but keeps the alignment; the Reset
      // button restores the original layout.
      svg.addEventListener("click", (e) => {
        const t = e.target;
        if (t.classList && t.classList.contains("gn-gene")) {
          const gene = geneById(t.dataset.lid, t.dataset.gid);
          if (gene && gene.family) setAnchorFamily(gene.family);
        } else if (model.activeFamily) {
          model.activeFamily = null; // deselect: undim, alignment stays
          render();
          renderFamilyList();
        }
      });
    }

    // Click-to-align: re-anchor every locus on its gene of ``key`` so all genes
    // cblaster deemed the same line up under one another; loci that have the
    // family float to the top (under the pinned query row).
    function setAnchorFamily(key) {
      model.anchorFamily = key;
      model.activeFamily = key;
      const alignStrand = $("gnAutoFlip").checked;
      for (const L of model.loci) {
        const fam = L.genes.filter((g) => g.family === key);
        if (fam.length) {
          L.anchorBp = fam.reduce((a, g) => a + (g.start + g.end) / 2, 0) / fam.length;
          if (alignStrand) L.flip = fam[0].strand === -1;
        }
      }
      const withFam = model.loci.filter((L) => L.genes.some((g) => g.family === key));
      const without = model.loci.filter((L) => !L.genes.some((g) => g.family === key));
      model.loci = withFam.concat(without);
      pinQuery();
      render();
      renderLociList();
      renderFamilyList();
      renderTable();
    }

    // Restore the original layout: default anchors, orientation, order and window.
    function resetLayout() {
      model.anchorFamily = null;
      model.activeFamily = null;
      for (const L of model.loci) L.anchorBp = anchorCentre(L.genes, true);
      applyAutoFlip($("gnAutoFlip").checked);
      applySort($("gnSort").value);
      autoFitWindow();
      render();
      renderLociList();
      renderFamilyList();
      renderTable();
    }

    // Orient loci so the current anchor (a clicked family, else each locus'
    // query hit) points the same way.
    function applyAutoFlip(on) {
      for (const L of model.loci) {
        let g = null;
        if (model.anchorFamily) g = L.genes.find((x) => x.family === model.anchorFamily);
        if (!g) g = L.genes.find((x) => x.anchor);
        L.flip = on && g ? g.strand === -1 : false;
      }
    }

    function onHover(e) {
      const t = e.target;
      if (!t.classList || !t.classList.contains("gn-gene")) { tooltip.classList.add("d-none"); return; }
      const gene = geneById(t.dataset.lid, t.dataset.gid);
      if (!gene) return;
      const fam = gene.family && model.families.get(gene.family);
      const strand = gene.strand === 1 ? "+" : gene.strand === -1 ? "−" : "·";
      tooltip.innerHTML =
        `<div class="gn-tt-title">${esc(gene.name)}</div>` +
        (gene.product ? `<div class="gn-tt-meta">${esc(gene.product)}</div>` : "") +
        `<div class="gn-tt-meta">${gene.start.toLocaleString()}–${gene.end.toLocaleString()} (${strand})` +
        (gene.identity != null ? ` · ${gene.identity}% id` : "") + `</div>` +
        (fam ? `<div class="gn-tt-meta">family: ${esc(fam.label)}</div>` : "") +
        (gene.proteinId ? `<div class="gn-tt-meta">${esc(gene.proteinId)}</div>` : "") +
        (gene.anchor ? `<div class="gn-tt-meta">query anchor</div>` : "") +
        (gene.family ? `<div class="gn-tt-meta">click to align this family</div>` : "");
      const wrap = root.getBoundingClientRect();
      let x = e.clientX - wrap.left + root.scrollLeft + 12;
      let y = e.clientY - wrap.top + root.scrollTop + 12;
      tooltip.classList.remove("d-none");
      // Keep the tooltip inside the canvas.
      const tw = tooltip.offsetWidth, th = tooltip.offsetHeight;
      if (x + tw > root.clientWidth + root.scrollLeft) x -= tw + 24;
      if (y + th > root.clientHeight + root.scrollTop) y -= th + 24;
      tooltip.style.left = x + "px";
      tooltip.style.top = y + "px";
    }

    const locusById = (id) => model.loci.find((L) => L.id === id);
    function geneById(lid, gid) {
      const L = locusById(lid);
      return L && L.genes.find((g) => g.id === gid);
    }

    // ── Sorting / reordering ──────────────────────────────────────────────
    function applySort(mode) {
      if (mode === "name") model.loci.sort((a, b) => a.label.localeCompare(b.label));
      else if (mode === "size") model.loci.sort((a, b) => b.genes.length - a.genes.length);
      else model.loci.sort((a, b) => (b.score ?? 0) - (a.score ?? 0));
      pinQuery();
    }
    function moveLocus(fromId, toId, after) {
      const from = model.loci.findIndex((L) => L.id === fromId);
      if (from < 0 || model.loci[from].isQuery) return; // the query row stays put
      const [item] = model.loci.splice(from, 1);
      const to = model.loci.findIndex((L) => L.id === toId);
      if (to < 0) { model.loci.push(item); }
      else model.loci.splice(after ? to + 1 : to, 0, item);
      pinQuery();
    }

    // ── Inspector ──────────────────────────────────────────────────────────
    function renderInspector() { renderLociList(); renderFamilyList(); renderStyleForm(); }

    function renderLociList() {
      const list = $("gnLociList");
      $("gnLociCount").textContent = model.loci.length + (model.loci.length === 1 ? " locus" : " loci");
      list.innerHTML = "";
      model.loci.forEach((L) => {
        const li = document.createElement("li");
        li.className = "list-group-item gn-loci-item";
        li.draggable = !L.isQuery; // the query row is pinned to the top
        li.dataset.lid = L.id;
        const badge = L.isQuery
          ? ' <span class="badge text-bg-success" style="font-size:.6rem;vertical-align:middle;">query</span>'
          : "";
        li.innerHTML =
          `<span class="gn-loci-label"><span class="gn-loci-title">${esc(truncate(L.label, 30))}${badge}</span>` +
          `<br><span class="gn-loci-sub">${esc(truncate(L.sub || "", 40))}</span></span>` +
          `<button class="gn-icon-btn gn-flip" title="Flip orientation"><i class="bi bi-arrow-left-right"></i></button>` +
          `<button class="gn-icon-btn gn-vis" title="Show/hide"><i class="bi ${L.visible ? "bi-eye" : "bi-eye-slash"}"></i></button>`;
        li.querySelector(".gn-flip").addEventListener("click", (e) => {
          e.stopPropagation(); L.flip = !L.flip; render();
        });
        li.querySelector(".gn-vis").addEventListener("click", (e) => {
          e.stopPropagation(); L.visible = !L.visible; render(); renderLociList();
        });
        // Drag-and-drop reordering.
        li.addEventListener("dragstart", (e) => {
          li.classList.add("gn-dragging");
          e.dataTransfer.setData("text/plain", L.id);
          e.dataTransfer.effectAllowed = "move";
        });
        li.addEventListener("dragend", () => {
          li.classList.remove("gn-dragging");
          list.querySelectorAll(".gn-drop-above,.gn-drop-below")
            .forEach((n) => n.classList.remove("gn-drop-above", "gn-drop-below"));
        });
        li.addEventListener("dragover", (e) => {
          e.preventDefault();
          const below = e.offsetY > li.offsetHeight / 2;
          li.classList.toggle("gn-drop-below", below);
          li.classList.toggle("gn-drop-above", !below);
        });
        li.addEventListener("dragleave", () => li.classList.remove("gn-drop-above", "gn-drop-below"));
        li.addEventListener("drop", (e) => {
          e.preventDefault();
          const fromId = e.dataTransfer.getData("text/plain");
          const below = e.offsetY > li.offsetHeight / 2;
          if (fromId && fromId !== L.id) { moveLocus(fromId, L.id, below); render(); renderLociList(); }
        });
        list.appendChild(li);
      });
    }

    function renderFamilyList() {
      const list = $("gnFamilyList");
      list.innerHTML = "";
      const entries = [...model.families.entries()].filter(([, f]) => f.color !== NOFAMILY);
      if (!entries.length) {
        list.innerHTML = `<li class="list-group-item text-body-secondary small border-0">No coloured families.</li>`;
        return;
      }
      for (const [key, fam] of entries) {
        const li = document.createElement("li");
        li.className = "list-group-item" + (model.activeFamily === key ? " active" : "");
        li.innerHTML =
          `<input type="color" class="form-control form-control-sm form-control-color gn-fam-color" value="${CagecatViz.toHex(fam.color)}" title="Recolour family">` +
          `<input type="text" class="form-control form-control-sm gn-fam-name" value="${CagecatViz.escapeAttr(fam.label)}">` +
          `<span class="pv-feature-meta">${fam.count}</span>` +
          `<button class="pv-feat-toggle gn-fam-hide" title="Show/hide"><i class="bi ${fam.hidden ? "bi-eye-slash" : "bi-eye"}"></i></button>`;
        li.querySelector(".gn-fam-color").addEventListener("input", (e) => { fam.color = e.target.value; render(); });
        li.querySelector(".gn-fam-name").addEventListener("change", (e) => { fam.label = e.target.value; render(); });
        li.querySelector(".gn-fam-hide").addEventListener("click", (e) => {
          e.stopPropagation(); fam.hidden = !fam.hidden; render(); renderFamilyList();
        });
        li.addEventListener("click", (e) => {
          if (e.target.closest("input,button")) return;
          model.activeFamily = model.activeFamily === key ? null : key;
          render(); renderFamilyList();
        });
        list.appendChild(li);
      }
    }

    function fieldRow(label, html) {
      return `<div class="pv-field-row"><label>${label}</label>${html}</div>`;
    }
    function checkRow(id, label, checked) {
      return `<div class="form-check form-switch"><input class="form-check-input" type="checkbox" id="${id}" ${checked ? "checked" : ""}>` +
             `<label class="form-check-label small" for="${id}">${label}</label></div>`;
    }
    function renderStyleForm() {
      const st = model.style;
      const form = $("gnStyleForm");
      form.innerHTML =
        fieldRow(`Row height (<span id="gnRowVal">${st.rowHeight}</span>)`,
          `<input type="range" class="form-range" id="gnRowH" min="30" max="80" value="${st.rowHeight}">`) +
        fieldRow(`Gene height (<span id="gnGeneVal">${st.geneHeight}</span>)`,
          `<input type="range" class="form-range" id="gnGeneH" min="10" max="34" value="${st.geneHeight}">`) +
        fieldRow("Gene labels", `<select class="form-select form-select-sm" id="gnLabels">
            <option value="none" ${st.geneLabels === "none" ? "selected" : ""}>None</option>
            <option value="anchor" ${st.geneLabels === "anchor" ? "selected" : ""}>Anchor genes only</option>
            <option value="all" ${st.geneLabels === "all" ? "selected" : ""}>All genes</option>
          </select>`) +
        `<div class="row g-2 align-items-end">` +
          `<div class="col-7">${fieldRow(`Font size (<span id="gnFontVal">${st.fontSize}</span>)`, `<input type="range" class="form-range" id="gnFont" min="8" max="18" value="${st.fontSize}">`)}</div>` +
          `<div class="col-5">${fieldRow("Backbone", `<input type="color" class="form-control form-control-sm form-control-color w-100" id="gnBackbone" value="${CagecatViz.toHex(st.backbone)}">`)}</div>` +
        `</div>` +
        fieldRow("Label gutter width", `<input type="range" class="form-range" id="gnGutter" min="150" max="360" value="${st.gutterWidth}">`) +
        `<div class="mt-2">` + checkRow("gnScaleBar", "Show scale bar", st.showScaleBar) +
          checkRow("gnLegend", "Show legend", st.showLegend) + `</div>`;

      const bindRange = (id, valId, key, parse) => {
        $(id).addEventListener("input", (e) => {
          st[key] = parse(e.target.value);
          if (valId) $(valId).textContent = st[key];
          render();
        });
      };
      bindRange("gnRowH", "gnRowVal", "rowHeight", (v) => parseInt(v, 10));
      bindRange("gnGeneH", "gnGeneVal", "geneHeight", (v) => parseInt(v, 10));
      bindRange("gnFont", "gnFontVal", "fontSize", (v) => parseInt(v, 10));
      bindRange("gnGutter", null, "gutterWidth", (v) => parseInt(v, 10));
      $("gnLabels").addEventListener("change", (e) => { st.geneLabels = e.target.value; render(); });
      $("gnBackbone").addEventListener("input", (e) => { st.backbone = e.target.value; render(); });
      $("gnScaleBar").addEventListener("change", (e) => { st.showScaleBar = e.target.checked; render(); });
      $("gnLegend").addEventListener("change", (e) => { st.showLegend = e.target.checked; render(); });
    }

    function updateInfo() {
      const nLoci = model.loci.length;
      const nGenes = model.loci.reduce((a, L) => a + L.genes.length, 0);
      const nFam = coloredFamilies().length;
      $("gnInfo").textContent = nLoci
        ? `${nLoci} loci · ${nGenes} genes · ${nFam} families`
        : "No data loaded";
    }

    // ── Results table + NCBI out-links ─────────────────────────────────────
    function ncbiProteinLink(gene) {
      return gene.proteinId
        ? "https://www.ncbi.nlm.nih.gov/protein/" + encodeURIComponent(gene.proteinId)
        : null;
    }
    function ncbiRegionLink(locus, gene) {
      if (!locus.scaffold) return null;
      return "https://www.ncbi.nlm.nih.gov/nuccore/" + encodeURIComponent(locus.scaffold) +
        "?from=" + gene.start + "&to=" + gene.end;
    }

    function renderTable(filter) {
      const body = $("gnTableBody");
      if (!body) return;
      const f = (filter == null ? (($("gnTableFilter") || {}).value || "") : filter).toLowerCase();
      body.innerHTML = "";
      let rows = 0;
      for (const L of model.loci) {
        for (const g of [...L.genes].sort((a, b) => a.start - b.start)) {
          const hay = `${g.name} ${g.product || ""} ${g.family || ""} ${L.label}`.toLowerCase();
          if (f && !hay.includes(f)) continue;
          const fam = g.family && model.families.get(g.family);
          const swatch = fam
            ? `<span class="pv-feature-swatch d-inline-block me-1" style="background:${fam.color}"></span>`
            : "";
          const strand = g.strand === 1 ? "+" : g.strand === -1 ? "−" : "·";
          const pLink = ncbiProteinLink(g), rLink = ncbiRegionLink(L, g);
          let link = '<span class="text-body-secondary">—</span>';
          if (pLink) link = `<a href="${pLink}" target="_blank" rel="noopener">${esc(g.proteinId)}</a>`;
          else if (rLink) link = `<a href="${rLink}" target="_blank" rel="noopener">region</a>`;
          const tr = document.createElement("tr");
          tr.innerHTML =
            `<td>${esc(truncate(L.label, 28))}</td>` +
            `<td>${swatch}${esc(g.name)}${g.anchor ? ' <span class="badge text-bg-success">anchor</span>' : ""}</td>` +
            `<td>${fam ? esc(fam.label) : '<span class="text-body-secondary">—</span>'}</td>` +
            `<td>${strand}</td>` +
            `<td>${g.start.toLocaleString()}–${g.end.toLocaleString()}</td>` +
            `<td>${g.identity != null ? g.identity + "%" : "—"}</td>` +
            `<td>${g.product ? esc(g.product) : '<span class="text-body-secondary">—</span>'}</td>` +
            `<td>${link}</td>`;
          body.appendChild(tr);
          rows++;
        }
      }
      if (!rows) {
        body.innerHTML = '<tr><td colspan="8" class="text-body-secondary small p-3">No genes match the filter.</td></tr>';
      }
    }

    // ── Public API ─────────────────────────────────────────────────────────
    return {
      model, ingest, render, renderInspector, renderTable,
      setWindowKb(kb) { model.view.windowKb = kb; render(); },
      setSort(mode) { applySort(mode); render(); renderLociList(); },
      setAutoFlip(on) { applyAutoFlip(on); render(); },
      resetLayout,
      filterTable(q) { renderTable(q); },
      hasData: () => model.loci.length > 0,
      exportFig(kind) {
        if (!svg) return;
        const name = "gene_neighborhood";
        const opts = { landscape: true };
        if (kind === "svg") CagecatViz.exportSvg(svg, name, opts);
        else if (kind === "png") { try { CagecatViz.exportPng(svg, name, 3, opts); } catch (e) { flash("PNG export failed.", "danger"); } }
        else if (kind === "pdf") { if (!CagecatViz.exportPdf(svg, name, opts)) flash("Pop-up blocked — allow pop-ups to export as PDF.", "warning"); }
      },
    };
  }

  const TERMINAL = { completed: 1, failed: 1, invalid: 1 };

  // ── Bootstrap: results page. Poll the job, then load its neighborhood.json ──
  document.addEventListener("DOMContentLoaded", function () {
    const resultsRoot = $("gnResultsRoot");
    const root = $("gnCanvasWrap");
    if (!resultsRoot || !root) return; // not the geneNeighborhood results page
    const jobId = resultsRoot.dataset.jobId;
    const viewer = GeneNeighborhood(root, $("gnTooltip"));
    window.GeneNeighborhood = viewer;

    wireToolbar(viewer);

    const badge = $("gnStatusBadge");
    const setBadge = (status, cls) => {
      badge.textContent = status;
      badge.className = "badge text-bg-" + cls + " ms-2";
    };

    function showError(msg) {
      $("gnRunning").classList.add("d-none");
      const box = $("gnErrorPanel");
      box.textContent = msg;
      box.classList.remove("d-none");
    }

    function reveal() {
      $("gnStatusPanel").classList.add("d-none");
      $("gnViewer").classList.remove("d-none");
    }

    function loadResult() {
      fetch("/api/jobs/" + encodeURIComponent(jobId) + "/view/neighborhood.json")
        .then((r) => (r.ok ? r.json() : Promise.reject(new Error("result missing"))))
        .then((data) => {
          if (!data.loci || !data.loci.length) {
            showError("This analysis produced no gene clusters to visualise.");
            return;
          }
          reveal();
          viewer.ingest(data);
          viewer.setAutoFlip(true);
        })
        .catch(() => showError("The neighborhood result could not be loaded."));
    }

    // "What was run", with an expandable table of every parameter (like cblaster).
    let runInfoDone = false;
    function renderRunInfo(job) {
      if (runInfoDone) return;
      runInfoDone = true;
      const p = job.params || {};
      const files = job.input_files || [];
      const db = p.local_database || p.database || "";
      const parts = [`<strong>${esc(job.title || job.label || "geneNeighborhood")}</strong>`];
      if (files.length) parts.push("— " + esc(files.join(", ")));
      else if (p.clusters) parts.push("— cblaster clusters " + esc([].concat(p.clusters).join(" ")));
      if (db) parts.push("against <strong>" + esc(db) + "</strong>");
      if (p.mode) parts.push("(" + esc(p.mode) + ")");
      $("gnRunSummary").innerHTML = parts.join(" ");

      const rows = [];
      if (files.length) rows.push(["query file(s)", files.join(", ")]);
      Object.keys(p).forEach((k) => {
        const v = p[k];
        rows.push([k, Array.isArray(v) ? v.join(" ") : String(v)]);
      });
      $("gnRunTable").innerHTML = rows.map((r) =>
        `<tr><td class="text-body-secondary" style="width:12rem">${esc(r[0])}</td>` +
        `<td>${esc(r[1])}</td></tr>`).join("");
      $("gnRunInfo").classList.remove("d-none");
    }

    function poll() {
      fetch("/api/jobs/" + encodeURIComponent(jobId))
        .then((r) => {
          if (r.status === 404) { throw new Error("notfound"); }
          return r.json();
        })
        .then((job) => {
          if (window.CagecatJobs) CagecatJobs.store(job);
          renderRunInfo(job);
          if (!TERMINAL[job.status]) {
            setBadge(job.status, job.status === "running" ? "info" : "secondary");
            setTimeout(poll, 2500);
            return;
          }
          if (job.status === "completed") {
            setBadge("completed", "success");
            wireClinkerHandoff(job);
            loadResult();
          } else {
            setBadge(job.status, "danger");
            showError(job.error || "The analysis failed. See the job logs for details.");
          }
        })
        .catch((err) => {
          if (err.message === "notfound") {
            $("gnRunning").classList.add("d-none");
            $("gnNotFound").classList.remove("d-none");
            setBadge("not found", "secondary");
          } else {
            setTimeout(poll, 4000);
          }
        });
    }
    // Reveal "Align with clinker" only when the completed job offers the
    // clinker_clusters handoff (i.e. it produced GenBank cluster files).
    function wireClinkerHandoff(job) {
      const btn = $("gnToClinker");
      if (!btn) return;
      const available = (job.actions || []).some((a) => a.name === "clinker_clusters");
      if (!available) return;
      btn.classList.remove("d-none");
      btn.addEventListener("click", () => {
        btn.disabled = true;
        fetch("/api/jobs/" + encodeURIComponent(jobId) + "/actions/clinker_clusters", {
          method: "POST", body: new FormData(),
        })
          .then((r) => r.json().then((b) => ({ ok: r.ok, b })))
          .then(({ ok, b }) => {
            if (ok) {
              if (window.CagecatJobs) CagecatJobs.store(b);
              window.location = "/results/" + b.id;
            } else {
              alert(b.detail || "Could not start clinker.");
              btn.disabled = false;
            }
          })
          .catch(() => { btn.disabled = false; });
      }, { once: true });
    }

    poll();
  });

  function wireToolbar(viewer) {
    $("gnWindow").addEventListener("input", (e) => {
      const kb = parseInt(e.target.value, 10);
      $("gnWindowVal").textContent = kb;
      $("gnZoomLabel").textContent = Math.round((10 / kb) * 100) + "%";
      viewer.setWindowKb(kb);
    });
    const nudgeWindow = (factor) => {
      const cur = parseInt($("gnWindow").value, 10);
      const kb = clamp(Math.round(cur * factor), 1, 50);
      $("gnWindow").value = kb; $("gnWindowVal").textContent = kb;
      $("gnZoomLabel").textContent = Math.round((10 / kb) * 100) + "%";
      viewer.setWindowKb(kb);
    };
    $("gnZoomIn").addEventListener("click", () => nudgeWindow(0.8));
    $("gnZoomOut").addEventListener("click", () => nudgeWindow(1.25));
    $("gnZoomReset").addEventListener("click", () => {
      $("gnWindow").value = 10; $("gnWindowVal").textContent = 10;
      $("gnZoomLabel").textContent = "100%"; viewer.setWindowKb(10);
    });
    $("gnAutoFlip").addEventListener("change", (e) => viewer.setAutoFlip(e.target.checked));
    $("gnSort").addEventListener("change", (e) => viewer.setSort(e.target.value));
    const resetBtn = $("gnReset");
    if (resetBtn) resetBtn.addEventListener("click", () => viewer.resetLayout());

    document.querySelectorAll("[data-gnexport]").forEach((a) => {
      a.addEventListener("click", (e) => {
        e.preventDefault();
        if (!viewer.hasData()) return;
        viewer.exportFig(a.dataset.gnexport);
      });
    });

    const tableFilter = $("gnTableFilter");
    if (tableFilter) tableFilter.addEventListener("input", (e) => viewer.filterTable(e.target.value));
  }
})();
