/*
 * plasmidViz — interactive, client-side plasmid map editor for CAGECAT.
 *
 * Everything runs in the browser: sequences are parsed, annotated and rendered
 * locally, so no data is uploaded to the server. The module is a single IIFE
 * that only activates on the plasmidViz page (it guards on #pvCanvasWrap), so it
 * is safe to load site-wide.
 *
 * Public surface (attached to window.PlasmidViz) is intentionally small and
 * exists mainly to make the editor testable and debuggable from the console.
 */
(function () {
  "use strict";

  const SVG_NS = "http://www.w3.org/2000/svg";
  const VIEW = 1000; // logical viewBox size for the circular layout

  // ── Feature colour + type conventions ────────────────────────────────────
  const TYPE_COLORS = {
    CDS: "#6EB293",
    gene: "#6EB293",
    mRNA: "#8Fc9ab",
    tRNA: "#5B8DEF",
    rRNA: "#5B8DEF",
    ncRNA: "#5B8DEF",
    promoter: "#F0A03C",
    terminator: "#E4572E",
    RBS: "#3FB8AF",
    regulatory: "#3FB8AF",
    rep_origin: "#9B5DE5",
    origin: "#9B5DE5",
    oriT: "#9B5DE5",
    protein_bind: "#B5838D",
    primer_bind: "#9AA5B1",
    misc_feature: "#B7BFC9",
    misc_RNA: "#5B8DEF",
    source: "#CBD2D9",
    default: "#B7BFC9",
  };

  // Common resistance / reporter markers matched by name substring.
  const NAME_COLORS = [
    [/amp|bla|ampicillin/i, "#E4572E"],
    [/kan|neo|kanamycin/i, "#F0A03C"],
    [/chlor|cat|cam/i, "#9B5DE5"],
    [/tet|tetracycline/i, "#C05780"],
    [/spec|strep|aad/i, "#3FB8AF"],
    [/gfp|egfp|yfp|cfp|mcherry|rfp|fluor/i, "#5B8DEF"],
    [/lacz|laci|lac/i, "#6EB293"],
    [/ori|rep|pmb1|colE1/i, "#9B5DE5"],
  ];

  // Curated common restriction enzymes (recognition sequences, 5'->3').
  const ENZYMES = {
    EcoRI: "GAATTC", BamHI: "GGATCC", HindIII: "AAGCTT", NotI: "GCGGCCGC",
    XhoI: "CTCGAG", SalI: "GTCGAC", PstI: "CTGCAG", NcoI: "CCATGG",
    NdeI: "CATATG", XbaI: "TCTAGA", SpeI: "ACTAGT", KpnI: "GGTACC",
    SacI: "GAGCTC", SmaI: "CCCGGG", ApaI: "GGGCCC", BglII: "AGATCT",
    EcoRV: "GATATC", HpaI: "GTTAAC", ClaI: "ATCGAT", NheI: "GCTAGC",
  };

  const STOP_CODONS = new Set(["TAA", "TAG", "TGA"]);

  // ── Small helpers (SVG/colour/download/escape come from CagecatViz) ────────
  const $ = (id) => document.getElementById(id);
  const clamp = (v, lo, hi) => Math.min(hi, Math.max(lo, v));
  const el = CagecatViz.svgEl;
  const escapeHtml = CagecatViz.escapeHtml;
  const escapeAttr = CagecatViz.escapeHtml;
  const toHex = CagecatViz.toHex;
  let _uid = 0;
  const uid = () => "f" + ++_uid + "_" + Math.random().toString(36).slice(2, 7);

  function colorForFeature(type, name) {
    const nm = name || "";
    for (const [re, col] of NAME_COLORS) if (re.test(nm)) return col;
    return TYPE_COLORS[type] || TYPE_COLORS.default;
  }

  // Turn a bare CagecatSeq feature into a plasmidViz feature (adds id, colour,
  // visibility and label-override state).
  function decorateFeature(feat) {
    return {
      id: uid(),
      name: feat.name,
      type: feat.type,
      start: feat.start,
      end: feat.end,
      strand: feat.strand,
      color: colorForFeature(feat.type, feat.name),
      visible: true,
      label: null, // {lx, ly} override or null for auto placement
    };
  }

  // ── Auto-annotation ─────────────────────────────────────────────────────────
  const Annotate = {
    orfs(seq, length, minLen) {
      const found = [];
      const scan = (s, strand) => {
        for (let frame = 0; frame < 3; frame++) {
          let startPos = -1;
          for (let i = frame; i + 3 <= s.length; i += 3) {
            const codon = s.slice(i, i + 3);
            if (startPos === -1 && codon === "ATG") startPos = i;
            else if (startPos !== -1 && STOP_CODONS.has(codon)) {
              const orfLen = i + 3 - startPos;
              if (orfLen >= minLen) {
                // Convert to plus-strand 1-based coordinates.
                let gs, ge;
                if (strand === 1) { gs = startPos + 1; ge = i + 3; }
                else { gs = length - (i + 3) + 1; ge = length - startPos; }
                found.push({ start: gs, end: ge, strand, len: orfLen });
              }
              startPos = -1;
            }
          }
        }
      };
      scan(seq, 1);
      scan(CagecatSeq.reverseComplement(seq), -1);
      // Greedily keep the longest, dropping heavily overlapping ORFs.
      found.sort((a, b) => b.len - a.len);
      const kept = [];
      for (const o of found) {
        const overlaps = kept.some((k) => k.strand === o.strand &&
          Math.min(k.end, o.end) - Math.max(k.start, o.start) > 0.5 * Math.min(k.len, o.len));
        if (!overlaps) kept.push(o);
      }
      return kept.map((o, i) => ({
        id: uid(), name: "ORF" + (i + 1), type: "CDS",
        start: o.start, end: o.end, strand: o.strand,
        color: TYPE_COLORS.CDS, visible: true, label: null,
      }));
    },

    restrictionSites(seq, length, maxCuts) {
      const feats = [];
      const upper = seq.toUpperCase();
      for (const [name, site] of Object.entries(ENZYMES)) {
        const positions = [];
        let idx = upper.indexOf(site);
        while (idx !== -1) { positions.push(idx + 1); idx = upper.indexOf(site, idx + 1); }
        if (positions.length === 0 || positions.length > maxCuts) continue;
        for (const p of positions) {
          feats.push({
            id: uid(), name, type: "misc_feature",
            start: p, end: p + site.length - 1, strand: 0,
            color: "#6c757d", visible: true, label: null, enzyme: true,
          });
        }
      }
      return feats;
    },
  };

  // ── Editor ──────────────────────────────────────────────────────────────────
  function Editor(root) {
    const state = {
      name: "",
      length: 0,
      sequence: "",
      topology: "circular",
      features: [],
      selectedId: null,
      style: {
        featureThickness: 34,
        arrowStyle: "arrow", // 'arrow' | 'block'
        fontFamily: "Roboto, sans-serif",
        fontSize: 13,
        fontColor: "#333333",
        showLabels: true,
        showScale: true,
        showTitle: true,
        showGcContent: false,
        backboneColor: "#3c4045",
        outlineColor: "#00000055",
        outlineWidth: 0.6,
        opacity: 1,
        labelField: "name",
      },
      view: { zoom: 1, panX: 0, panY: 0 },
    };

    let svg = null, viewGroup = null;
    const history = [];
    let histIdx = -1;

    // ── History (undo/redo) ────────────────────────────────────────────────
    function snapshot() {
      return JSON.stringify({
        name: state.name, length: state.length, topology: state.topology,
        features: state.features, style: state.style, selectedId: state.selectedId,
      });
    }
    function pushHistory() {
      history.splice(histIdx + 1);
      history.push(snapshot());
      if (history.length > 60) history.shift();
      histIdx = history.length - 1;
      updateHistoryButtons();
    }
    function restore(snap) {
      const s = JSON.parse(snap);
      state.name = s.name; state.length = s.length; state.topology = s.topology;
      state.features = s.features; state.style = s.style; state.selectedId = s.selectedId;
      syncControlsFromState();
      render();
      renderInspector();
    }
    function undo() { if (histIdx > 0) { restore(history[--histIdx]); updateHistoryButtons(); } }
    function redo() { if (histIdx < history.length - 1) { restore(history[++histIdx]); updateHistoryButtons(); } }
    function updateHistoryButtons() {
      $("pvUndo").disabled = histIdx <= 0;
      $("pvRedo").disabled = histIdx >= history.length - 1;
    }

    // ── Loading data ─────────────────────────────────────────────────────────
    function loadParsed(parsed) {
      state.name = parsed.name || "plasmid";
      state.length = parsed.length || 0;
      state.sequence = parsed.sequence || "";
      state.topology = parsed.topology || "circular";
      state.features = parsed.features || [];
      state.selectedId = null;
      state.view = { zoom: 1, panX: 0, panY: 0 };
      if (!state.length) throw new Error("Could not determine sequence length from the file.");
      syncControlsFromState();
      history.length = 0; histIdx = -1;
      pushHistory();
      render();
      renderInspector();
      updateSeqInfo();
    }

    function syncControlsFromState() {
      $("pvName").value = state.name;
      $("pvTopology").value = state.topology;
    }

    function updateSeqInfo() {
      const info = $("pvSeqInfo");
      if (!state.length) { info.textContent = "No sequence loaded"; return; }
      const seqNote = state.sequence ? "" : " · sequence not provided";
      info.textContent = `${state.length.toLocaleString()} bp · ${state.features.length} features${seqNote}`;
    }

    // ── Geometry ───────────────────────────────────────────────────────────────
    const cx = VIEW / 2, cy = VIEW / 2;
    const R = 330; // backbone radius (circular)

    function polar(radius, frac) {
      const ang = frac * 2 * Math.PI - Math.PI / 2;
      return [cx + radius * Math.cos(ang), cy + radius * Math.sin(ang)];
    }
    const bpFrac = (bp) => (state.length ? (bp % state.length) / state.length : 0);

    // ── Rendering ──────────────────────────────────────────────────────────────
    function render() {
      root.innerHTML = "";
      if (!state.length) {
        const empty = document.createElement("div");
        empty.className = "pv-empty-state";
        empty.innerHTML =
          '<i class="bi bi-record-circle"></i>' +
          '<p class="mb-1 mt-3">No plasmid loaded yet.</p>' +
          '<p class="text-body-secondary small mb-0">Upload a file or load the sample to start editing.</p>';
        root.appendChild(empty);
        return;
      }
      svg = el("svg", { xmlns: SVG_NS });
      viewGroup = el("g", { class: "pv-view" });
      svg.appendChild(viewGroup);

      if (state.topology === "circular") {
        svg.setAttribute("viewBox", `0 0 ${VIEW} ${VIEW}`);
        renderCircular();
      } else {
        svg.setAttribute("viewBox", `0 0 ${VIEW} ${VIEW * 0.62}`);
        renderLinear();
      }
      applyViewTransform();
      root.appendChild(svg);
      attachCanvasInteractions();
    }

    function applyViewTransform() {
      const v = state.view;
      viewGroup.setAttribute(
        "transform",
        `translate(${v.panX} ${v.panY}) scale(${v.zoom})`
      );
    }

    function renderCircular() {
      const st = state.style;
      // Backbone
      viewGroup.appendChild(el("circle", {
        cx, cy, r: R, fill: "none",
        stroke: st.backboneColor, "stroke-width": 2.5,
      }));

      if (st.showScale) drawCircularScale();

      // Title / length in the centre
      if (st.showTitle) {
        const t1 = el("text", {
          x: cx, y: cy - 6, "text-anchor": "middle",
          "font-family": st.fontFamily, "font-size": 26, "font-weight": 700,
          fill: st.fontColor,
        });
        t1.textContent = state.name;
        viewGroup.appendChild(t1);
        const t2 = el("text", {
          x: cx, y: cy + 22, "text-anchor": "middle",
          "font-family": st.fontFamily, "font-size": 15, fill: st.fontColor,
        });
        t2.textContent = state.length.toLocaleString() + " bp";
        viewGroup.appendChild(t2);
      }

      const labels = [];
      for (const f of state.features) {
        if (!f.visible) continue;
        const shape = circularFeatureShape(f);
        viewGroup.appendChild(shape);
        if (st.showLabels) labels.push(f);
      }
      // Labels drawn after shapes so they sit on top.
      for (const f of labels) drawCircularLabel(f);
    }

    function drawCircularScale() {
      const st = state.style;
      const ticks = 12;
      const rTickOut = R - 6, rTickIn = R - 16;
      for (let i = 0; i < ticks; i++) {
        const frac = i / ticks;
        const [x1, y1] = polar(rTickOut, frac);
        const [x2, y2] = polar(rTickIn, frac);
        viewGroup.appendChild(el("line", {
          x1, y1, x2, y2, stroke: st.backboneColor, "stroke-width": 1, opacity: 0.55,
        }));
        const bp = Math.round(frac * state.length);
        const [tx, ty] = polar(rTickIn - 12, frac);
        const t = el("text", {
          x: tx, y: ty, "text-anchor": "middle", "dominant-baseline": "middle",
          "font-family": st.fontFamily, "font-size": 9, fill: st.backboneColor, opacity: 0.7,
        });
        t.textContent = bp ? (bp / 1000).toFixed(1) + "k" : "0";
        viewGroup.appendChild(t);
      }
    }

    function circularFeatureShape(f) {
      const st = state.style;
      const t = st.featureThickness;
      // Offset strands slightly in/out of the backbone ring.
      const mid = R + (f.strand === -1 ? -t * 0.55 : f.strand === 1 ? t * 0.55 : 0) * 0;
      const rm = R;
      const ri = rm - t / 2, ro = rm + t / 2;
      let f0 = bpFrac(f.start - 1), f1 = bpFrac(f.end);
      if (f1 <= f0) f1 += 1; // wrap across origin
      const span = f1 - f0;
      const useArrow = st.arrowStyle === "arrow" && f.strand !== 0 && span > 0.004;
      const headFrac = Math.min(span * 0.5, 0.012 + span * 0.15);

      const P = (r, fr) => polar(r, fr).map((n) => n.toFixed(2)).join(",");
      const large = (a) => (a > 0.5 ? 1 : 0);
      let d;
      if (!useArrow) {
        d = `M${P(ro, f0)} A${ro},${ro} 0 ${large(span)},1 ${P(ro, f1)}` +
            ` L${P(ri, f1)} A${ri},${ri} 0 ${large(span)},0 ${P(ri, f0)} Z`;
      } else if (f.strand === 1) {
        const fb = f1 - headFrac;
        d = `M${P(ro, f0)} A${ro},${ro} 0 ${large(fb - f0)},1 ${P(ro, fb)}` +
            ` L${P(rm, f1)} L${P(ri, fb)}` +
            ` A${ri},${ri} 0 ${large(fb - f0)},0 ${P(ri, f0)} Z`;
      } else {
        const fb = f0 + headFrac;
        d = `M${P(rm, f0)} L${P(ro, fb)}` +
            ` A${ro},${ro} 0 ${large(f1 - fb)},1 ${P(ro, f1)}` +
            ` L${P(ri, f1)} A${ri},${ri} 0 ${large(f1 - fb)},0 ${P(ri, fb)} Z`;
      }
      const path = el("path", {
        d, fill: f.color, "fill-opacity": st.opacity,
        stroke: st.outlineColor, "stroke-width": st.outlineWidth,
        class: "pv-feature-shape" + (f.id === state.selectedId ? " pv-selected" : ""),
      });
      path.dataset.fid = f.id;
      return path;
    }

    function labelAnchorCircular(f) {
      let f0 = bpFrac(f.start - 1), f1 = bpFrac(f.end);
      if (f1 <= f0) f1 += 1;
      const mid = ((f0 + f1) / 2) % 1;
      const [ax, ay] = polar(R + state.style.featureThickness / 2, mid);
      return { mid, ax, ay };
    }

    function drawCircularLabel(f) {
      const st = state.style;
      const { mid, ax, ay } = labelAnchorCircular(f);
      let lx, ly;
      if (f.label) { lx = f.label.lx; ly = f.label.ly; }
      else {
        const [px, py] = polar(R + st.featureThickness / 2 + 34, mid);
        lx = px; ly = py;
      }
      const anchor = lx < cx - 4 ? "end" : lx > cx + 4 ? "start" : "middle";
      // Leader line
      viewGroup.appendChild(el("line", {
        x1: ax.toFixed(2), y1: ay.toFixed(2), x2: lx.toFixed(2), y2: ly.toFixed(2),
        stroke: st.fontColor, "stroke-width": 0.6, opacity: 0.5,
        class: "pv-leader", "data-fid": f.id,
      }));
      const text = el("text", {
        x: lx.toFixed(2), y: ly.toFixed(2), "text-anchor": anchor,
        "dominant-baseline": "middle", "font-family": st.fontFamily,
        "font-size": st.fontSize, fill: st.fontColor, class: "pv-label",
      });
      text.dataset.fid = f.id;
      text.textContent = labelText(f);
      viewGroup.appendChild(text);
    }

    function labelText(f) {
      const field = state.style.labelField;
      if (field === "type") return f.type;
      if (field === "range") return `${f.start}–${f.end}`;
      return f.name;
    }

    // Linear layout
    function renderLinear() {
      const st = state.style;
      const W = VIEW, H = VIEW * 0.62;
      const marginX = 70, baseY = H * 0.55;
      const usable = W - 2 * marginX;
      const xOf = (bp) => marginX + (bp / state.length) * usable;

      if (st.showTitle) {
        const t = el("text", {
          x: W / 2, y: 46, "text-anchor": "middle", "font-family": st.fontFamily,
          "font-size": 24, "font-weight": 700, fill: st.fontColor,
        });
        t.textContent = `${state.name}  ·  ${state.length.toLocaleString()} bp`;
        viewGroup.appendChild(t);
      }

      // Backbone line
      viewGroup.appendChild(el("line", {
        x1: marginX, y1: baseY, x2: W - marginX, y2: baseY,
        stroke: st.backboneColor, "stroke-width": 2.5,
      }));

      if (st.showScale) {
        const ticks = 10;
        for (let i = 0; i <= ticks; i++) {
          const bp = Math.round((i / ticks) * state.length);
          const x = xOf(bp);
          viewGroup.appendChild(el("line", {
            x1: x, y1: baseY + 4, x2: x, y2: baseY + 12,
            stroke: st.backboneColor, "stroke-width": 1, opacity: 0.6,
          }));
          const t = el("text", {
            x, y: baseY + 26, "text-anchor": "middle", "font-family": st.fontFamily,
            "font-size": 10, fill: st.backboneColor, opacity: 0.75,
          });
          t.textContent = bp.toLocaleString();
          viewGroup.appendChild(t);
        }
      }

      const labels = [];
      for (const f of state.features) {
        if (!f.visible) continue;
        viewGroup.appendChild(linearFeatureShape(f, xOf, baseY));
        if (st.showLabels) labels.push(f);
      }
      for (const f of labels) drawLinearLabel(f, xOf, baseY);
    }

    function linearFeatureShape(f, xOf, baseY) {
      const st = state.style;
      const t = st.featureThickness;
      const x0 = xOf(f.start - 1), x1 = xOf(f.end);
      const w = Math.max(1, x1 - x0);
      const top = baseY - t / 2, bot = baseY + t / 2;
      const head = Math.min(w * 0.5, 14);
      const useArrow = st.arrowStyle === "arrow" && f.strand !== 0 && w > 6;
      let d;
      if (!useArrow) {
        d = `M${x0},${top} H${x1} V${bot} H${x0} Z`;
      } else if (f.strand === 1) {
        d = `M${x0},${top} H${x1 - head} L${x1},${baseY} L${x1 - head},${bot} H${x0} Z`;
      } else {
        d = `M${x1},${top} H${x0 + head} L${x0},${baseY} L${x0 + head},${bot} H${x1} Z`;
      }
      const path = el("path", {
        d, fill: f.color, "fill-opacity": st.opacity,
        stroke: st.outlineColor, "stroke-width": st.outlineWidth,
        class: "pv-feature-shape" + (f.id === state.selectedId ? " pv-selected" : ""),
      });
      path.dataset.fid = f.id;
      return path;
    }

    function drawLinearLabel(f, xOf, baseY) {
      const st = state.style;
      const xmid = (xOf(f.start - 1) + xOf(f.end)) / 2;
      const anchorY = baseY - st.featureThickness / 2;
      let lx, ly;
      if (f.label) { lx = f.label.lx; ly = f.label.ly; }
      else { lx = xmid; ly = anchorY - 26; }
      viewGroup.appendChild(el("line", {
        x1: xmid, y1: anchorY, x2: lx, y2: ly + 4,
        stroke: st.fontColor, "stroke-width": 0.6, opacity: 0.5,
        class: "pv-leader", "data-fid": f.id,
      }));
      const text = el("text", {
        x: lx, y: ly, "text-anchor": "middle", "font-family": st.fontFamily,
        "font-size": st.fontSize, fill: st.fontColor, class: "pv-label",
      });
      text.dataset.fid = f.id;
      text.textContent = labelText(f);
      viewGroup.appendChild(text);
    }

    // ── Canvas interaction: select, pan, zoom, drag labels ────────────────────
    function clientToView(evt) {
      const ctm = viewGroup.getScreenCTM();
      if (!ctm) return { x: 0, y: 0 };
      const pt = svg.createSVGPoint();
      pt.x = evt.clientX; pt.y = evt.clientY;
      const p = pt.matrixTransform(ctm.inverse());
      return { x: p.x, y: p.y };
    }

    function attachCanvasInteractions() {
      let mode = null; // 'pan' | 'label'
      let dragFid = null;
      let start = null;

      svg.addEventListener("pointerdown", (e) => {
        const target = e.target;
        if (target.classList.contains("pv-label")) {
          mode = "label";
          dragFid = target.dataset.fid;
          start = clientToView(e);
          svg.setPointerCapture(e.pointerId);
          e.preventDefault();
          return;
        }
        if (target.classList.contains("pv-feature-shape")) {
          selectFeature(target.dataset.fid);
          return;
        }
        // Background → pan / deselect
        mode = "pan";
        start = { x: e.clientX, y: e.clientY, panX: state.view.panX, panY: state.view.panY };
        svg.setPointerCapture(e.pointerId);
      });

      svg.addEventListener("pointermove", (e) => {
        if (mode === "pan") {
          state.view.panX = start.panX + (e.clientX - start.x);
          state.view.panY = start.panY + (e.clientY - start.y);
          applyViewTransform();
        } else if (mode === "label") {
          const p = clientToView(e);
          const f = featureById(dragFid);
          if (f) {
            f.label = { lx: p.x, ly: p.y };
            redrawLabelsOnly();
          }
        }
      });

      const endDrag = (e) => {
        if (mode === "label") pushHistory();
        if (mode === "pan" && start && (Math.abs(e.clientX - start.x) < 3 && Math.abs(e.clientY - start.y) < 3)) {
          selectFeature(null); // treat as a click on empty space
        }
        mode = null; dragFid = null; start = null;
      };
      svg.addEventListener("pointerup", endDrag);
      svg.addEventListener("pointercancel", endDrag);

      svg.addEventListener("wheel", (e) => {
        e.preventDefault();
        const factor = e.deltaY < 0 ? 1.12 : 1 / 1.12;
        zoomAt(e, factor);
      }, { passive: false });
    }

    function redrawLabelsOnly() {
      // Cheap re-render for smooth label dragging.
      render();
    }

    function zoomAt(evt, factor) {
      const before = clientToView(evt);
      state.view.zoom = clamp(state.view.zoom * factor, 0.3, 8);
      applyViewTransform();
      const after = clientToView(evt);
      state.view.panX += (after.x - before.x) * state.view.zoom;
      state.view.panY += (after.y - before.y) * state.view.zoom;
      applyViewTransform();
      $("pvZoomLabel").textContent = Math.round(state.view.zoom * 100) + "%";
    }
    function zoomBy(factor) {
      state.view.zoom = clamp(state.view.zoom * factor, 0.3, 8);
      applyViewTransform();
      $("pvZoomLabel").textContent = Math.round(state.view.zoom * 100) + "%";
    }
    function resetView() {
      state.view = { zoom: 1, panX: 0, panY: 0 };
      if (viewGroup) applyViewTransform();
      $("pvZoomLabel").textContent = "100%";
    }

    // ── Feature helpers ────────────────────────────────────────────────────────
    const featureById = (id) => state.features.find((f) => f.id === id);
    function selectFeature(id) {
      state.selectedId = id;
      render();
      renderInspector();
      if (id) {
        const tab = bootstrap.Tab.getOrCreateInstance($("pvTabSelected-btn"));
        tab.show();
      }
    }

    // ── Inspector UI ───────────────────────────────────────────────────────────
    function renderInspector() {
      renderFeatureList();
      renderSelectedForm();
      renderStyleForm();
      $("pvFeatureCount").textContent =
        state.features.length + (state.features.length === 1 ? " feature" : " features");
      updateSeqInfo();
    }

    function renderFeatureList() {
      const list = $("pvFeatureList");
      const filter = ($("pvFeatureSearch").value || "").toLowerCase();
      list.innerHTML = "";
      const sorted = [...state.features].sort((a, b) => a.start - b.start);
      for (const f of sorted) {
        if (filter && !(f.name.toLowerCase().includes(filter) || f.type.toLowerCase().includes(filter))) continue;
        const li = document.createElement("li");
        li.className = "list-group-item" + (f.id === state.selectedId ? " active" : "");
        li.dataset.fid = f.id;
        const strandGlyph = f.strand === 1 ? "▶" : f.strand === -1 ? "◀" : "■";
        li.innerHTML =
          `<span class="pv-feature-swatch" style="background:${f.color}"></span>` +
          `<span class="pv-feature-name" title="${escapeHtml(f.name)}">${escapeHtml(f.name)}</span>` +
          `<span class="pv-feature-meta">${strandGlyph} ${f.start}–${f.end}</span>` +
          `<button class="pv-feat-toggle" title="Show/hide" aria-label="Toggle visibility">` +
          `<i class="bi ${f.visible ? "bi-eye" : "bi-eye-slash"}"></i></button>`;
        li.addEventListener("click", (e) => {
          if (e.target.closest(".pv-feat-toggle")) {
            f.visible = !f.visible;
            pushHistory(); render(); renderFeatureList(); return;
          }
          selectFeature(f.id);
        });
        list.appendChild(li);
      }
      if (!list.children.length) {
        const li = document.createElement("li");
        li.className = "list-group-item text-body-secondary small border-0";
        li.textContent = state.features.length ? "No features match the filter." : "No features yet.";
        list.appendChild(li);
      }
    }

    function fieldRow(label, controlHtml) {
      return `<div class="pv-field-row"><label>${label}</label>${controlHtml}</div>`;
    }

    function renderSelectedForm() {
      const noSel = $("pvNoSelection");
      const form = $("pvSelectedForm");
      const f = featureById(state.selectedId);
      if (!f) { noSel.classList.remove("d-none"); form.classList.add("d-none"); return; }
      noSel.classList.add("d-none");
      form.classList.remove("d-none");
      const typeOptions = Object.keys(TYPE_COLORS).filter((t) => t !== "default")
        .map((t) => `<option value="${t}" ${t === f.type ? "selected" : ""}>${t}</option>`).join("");
      form.innerHTML =
        fieldRow("Name", `<input type="text" class="form-control form-control-sm" id="pvfName" value="${escapeAttr(f.name)}">`) +
        fieldRow("Type", `<select class="form-select form-select-sm" id="pvfType">${typeOptions}</select>`) +
        `<div class="row g-2">` +
          `<div class="col-6">${fieldRow("Start", `<input type="number" min="1" class="form-control form-control-sm" id="pvfStart" value="${f.start}">`)}</div>` +
          `<div class="col-6">${fieldRow("End", `<input type="number" min="1" class="form-control form-control-sm" id="pvfEnd" value="${f.end}">`)}</div>` +
        `</div>` +
        fieldRow("Strand", `<select class="form-select form-select-sm" id="pvfStrand">
            <option value="1" ${f.strand === 1 ? "selected" : ""}>Forward (+)</option>
            <option value="-1" ${f.strand === -1 ? "selected" : ""}>Reverse (−)</option>
            <option value="0" ${f.strand === 0 ? "selected" : ""}>None</option>
          </select>`) +
        `<div class="row g-2 align-items-end">` +
          `<div class="col-7">${fieldRow("Colour", `<input type="color" class="form-control form-control-sm form-control-color w-100" id="pvfColor" value="${toHex(f.color)}">`)}</div>` +
          `<div class="col-5">${fieldRow("Visible", `<div class="form-check form-switch mt-1"><input class="form-check-input" type="checkbox" id="pvfVisible" ${f.visible ? "checked" : ""}></div>`)}</div>` +
        `</div>` +
        `<div class="d-flex gap-2 mt-2">` +
          `<button class="btn btn-sm btn-outline-secondary flex-fill" id="pvfResetLabel"><i class="bi bi-arrow-repeat me-1"></i>Reset label</button>` +
          `<button class="btn btn-sm btn-outline-danger flex-fill" id="pvfDelete"><i class="bi bi-trash me-1"></i>Delete</button>` +
        `</div>`;

      const commit = (mutate) => { mutate(); pushHistory(); render(); renderFeatureList(); };
      const live = (mutate) => { mutate(); render(); };

      $("pvfName").addEventListener("input", (e) => live(() => { f.name = e.target.value; }));
      $("pvfName").addEventListener("change", () => pushHistory());
      $("pvfType").addEventListener("change", (e) => commit(() => { f.type = e.target.value; }));
      $("pvfStart").addEventListener("change", (e) => commit(() => {
        f.start = clamp(parseInt(e.target.value, 10) || 1, 1, state.length);
      }));
      $("pvfEnd").addEventListener("change", (e) => commit(() => {
        f.end = clamp(parseInt(e.target.value, 10) || 1, 1, state.length);
      }));
      $("pvfStrand").addEventListener("change", (e) => commit(() => { f.strand = parseInt(e.target.value, 10); }));
      $("pvfColor").addEventListener("input", (e) => live(() => { f.color = e.target.value; }));
      $("pvfColor").addEventListener("change", () => { pushHistory(); renderFeatureList(); });
      $("pvfVisible").addEventListener("change", (e) => commit(() => { f.visible = e.target.checked; }));
      $("pvfResetLabel").addEventListener("click", () => commit(() => { f.label = null; }));
      $("pvfDelete").addEventListener("click", () => {
        state.features = state.features.filter((x) => x.id !== f.id);
        state.selectedId = null;
        pushHistory(); render(); renderInspector();
      });
    }

    function renderStyleForm() {
      const st = state.style;
      const form = $("pvStyleForm");
      form.innerHTML =
        fieldRow(`Feature thickness (<span id="pvThickVal">${st.featureThickness}</span>)`,
          `<input type="range" class="form-range" id="pvThickness" min="10" max="70" value="${st.featureThickness}">`) +
        fieldRow("Arrow style", `<select class="form-select form-select-sm" id="pvArrowStyle">
            <option value="arrow" ${st.arrowStyle === "arrow" ? "selected" : ""}>Arrows (show strand)</option>
            <option value="block" ${st.arrowStyle === "block" ? "selected" : ""}>Blocks</option>
          </select>`) +
        fieldRow(`Feature opacity (<span id="pvOpacityVal">${st.opacity.toFixed(2)}</span>)`,
          `<input type="range" class="form-range" id="pvOpacity" min="0.2" max="1" step="0.05" value="${st.opacity}">`) +
        `<div class="row g-2">` +
          `<div class="col-6">${fieldRow("Outline", `<input type="color" class="form-control form-control-sm form-control-color w-100" id="pvOutline" value="${toHex(st.outlineColor)}">`)}</div>` +
          `<div class="col-6">${fieldRow(`Outline w. (<span id="pvOutlineWVal">${st.outlineWidth}</span>)`, `<input type="range" class="form-range" id="pvOutlineW" min="0" max="3" step="0.2" value="${st.outlineWidth}">`)}</div>` +
        `</div>` +
        `<hr class="my-2">` +
        fieldRow("Label field", `<select class="form-select form-select-sm" id="pvLabelField">
            <option value="name" ${st.labelField === "name" ? "selected" : ""}>Name</option>
            <option value="type" ${st.labelField === "type" ? "selected" : ""}>Type</option>
            <option value="range" ${st.labelField === "range" ? "selected" : ""}>Coordinates</option>
          </select>`) +
        fieldRow("Label font", `<select class="form-select form-select-sm" id="pvFontFamily">
            <option value="Roboto, sans-serif" ${st.fontFamily.startsWith("Roboto") ? "selected" : ""}>Roboto (sans)</option>
            <option value="Arial, Helvetica, sans-serif" ${st.fontFamily.startsWith("Arial") ? "selected" : ""}>Arial</option>
            <option value="Georgia, serif" ${st.fontFamily.startsWith("Georgia") ? "selected" : ""}>Georgia (serif)</option>
            <option value="'Courier New', monospace" ${st.fontFamily.includes("Courier") ? "selected" : ""}>Courier (mono)</option>
          </select>`) +
        `<div class="row g-2 align-items-end">` +
          `<div class="col-7">${fieldRow(`Font size (<span id="pvFontSizeVal">${st.fontSize}</span>)`, `<input type="range" class="form-range" id="pvFontSize" min="8" max="24" value="${st.fontSize}">`)}</div>` +
          `<div class="col-5">${fieldRow("Colour", `<input type="color" class="form-control form-control-sm form-control-color w-100" id="pvFontColor" value="${toHex(st.fontColor)}">`)}</div>` +
        `</div>` +
        `<div class="row g-2">` +
          `<div class="col-6">${fieldRow("Backbone", `<input type="color" class="form-control form-control-sm form-control-color w-100" id="pvBackbone" value="${toHex(st.backboneColor)}">`)}</div>` +
        `</div>` +
        `<div class="mt-2">` +
          checkRow("pvShowLabels", "Show labels", st.showLabels) +
          checkRow("pvShowScale", "Show scale / ruler", st.showScale) +
          checkRow("pvShowTitle", "Show title", st.showTitle) +
        `</div>`;

      const commit = () => { pushHistory(); render(); };
      const bindRange = (id, valId, key, parse, fmt) => {
        const input = $(id);
        input.addEventListener("input", (e) => {
          st[key] = parse(e.target.value);
          if (valId) $(valId).textContent = fmt ? fmt(st[key]) : st[key];
          render();
        });
        input.addEventListener("change", commit);
      };
      bindRange("pvThickness", "pvThickVal", "featureThickness", (v) => parseInt(v, 10));
      bindRange("pvOpacity", "pvOpacityVal", "opacity", parseFloat, (v) => v.toFixed(2));
      bindRange("pvOutlineW", "pvOutlineWVal", "outlineWidth", parseFloat);
      bindRange("pvFontSize", "pvFontSizeVal", "fontSize", (v) => parseInt(v, 10));

      $("pvArrowStyle").addEventListener("change", (e) => { st.arrowStyle = e.target.value; commit(); });
      $("pvOutline").addEventListener("input", (e) => { st.outlineColor = e.target.value; render(); });
      $("pvOutline").addEventListener("change", commit);
      $("pvLabelField").addEventListener("change", (e) => { st.labelField = e.target.value; commit(); });
      $("pvFontFamily").addEventListener("change", (e) => { st.fontFamily = e.target.value; commit(); });
      $("pvFontColor").addEventListener("input", (e) => { st.fontColor = e.target.value; render(); });
      $("pvFontColor").addEventListener("change", commit);
      $("pvBackbone").addEventListener("input", (e) => { st.backboneColor = e.target.value; render(); });
      $("pvBackbone").addEventListener("change", commit);
      $("pvShowLabels").addEventListener("change", (e) => { st.showLabels = e.target.checked; commit(); });
      $("pvShowScale").addEventListener("change", (e) => { st.showScale = e.target.checked; commit(); });
      $("pvShowTitle").addEventListener("change", (e) => { st.showTitle = e.target.checked; commit(); });
    }

    function checkRow(id, label, checked) {
      return `<div class="form-check form-switch"><input class="form-check-input" type="checkbox" id="${id}" ${checked ? "checked" : ""}>` +
             `<label class="form-check-label small" for="${id}">${label}</label></div>`;
    }

    // ── Add feature manually ───────────────────────────────────────────────────
    function addFeature() {
      if (!state.length) { flash("Load a sequence first.", "warning"); return; }
      const mid = Math.round(state.length / 2);
      const f = {
        id: uid(), name: "New feature", type: "misc_feature",
        start: Math.max(1, mid - Math.round(state.length * 0.05)),
        end: Math.min(state.length, mid + Math.round(state.length * 0.05)),
        strand: 1, color: TYPE_COLORS.default, visible: true, label: null,
      };
      state.features.push(f);
      state.selectedId = f.id;
      pushHistory(); render(); renderInspector();
      bootstrap.Tab.getOrCreateInstance($("pvTabSelected-btn")).show();
    }

    // ── Auto-annotate ──────────────────────────────────────────────────────────
    function autoAnnotate() {
      if (!state.sequence) {
        flash("Auto-annotation needs a nucleotide sequence (GenBank/EMBL with ORIGIN, GFF+FASTA, or a FASTA file).", "warning");
        return;
      }
      const minLen = Math.max(150, Math.round(state.length * 0.02));
      const orfs = Annotate.orfs(state.sequence, state.length, minLen);
      const sites = Annotate.restrictionSites(state.sequence, state.length, 2);
      // Avoid duplicating ORFs that overlap an existing CDS.
      const existing = state.features.filter((f) => f.type === "CDS" || f.type === "gene");
      const newOrfs = orfs.filter((o) => !existing.some((e) =>
        o.strand === e.strand && Math.min(o.end, e.end) - Math.max(o.start, e.start) > 0));
      state.features.push(...newOrfs, ...sites);
      pushHistory(); render(); renderInspector();
      flash(`Added ${newOrfs.length} ORF(s) and ${sites.length} restriction site(s).`, "success");
    }

    // ── Export (SVG/PNG/PDF via the shared CagecatViz helpers) ─────────────────
    function exportSvg() { CagecatViz.exportSvg(svg, safeName()); }
    function exportPng(scale) {
      try { CagecatViz.exportPng(svg, safeName(), scale); }
      catch (e) { flash("PNG export failed.", "danger"); }
    }
    function exportPdf() {
      if (!CagecatViz.exportPdf(svg, safeName())) {
        flash("Pop-up blocked — allow pop-ups to export as PDF.", "warning");
      }
    }

    function exportJson() {
      const proj = {
        format: "plasmidviz/1",
        name: state.name, length: state.length, topology: state.topology,
        sequence: state.sequence, features: state.features, style: state.style,
      };
      CagecatViz.download(
        new Blob([JSON.stringify(proj, null, 2)], { type: "application/json" }),
        safeName() + ".json");
    }

    function loadProject(proj) {
      loadParsed({
        name: proj.name, length: proj.length, topology: proj.topology,
        sequence: proj.sequence || "", features: proj.features || [],
      });
      if (proj.style) { Object.assign(state.style, proj.style); render(); renderInspector(); }
    }

    const safeName = () => (state.name || "plasmid").replace(/[^\w.-]+/g, "_");

    // ── Public control wiring ──────────────────────────────────────────────────
    return {
      state, loadParsed, loadProject,
      render, renderInspector, renderFeatureList,
      addFeature, autoAnnotate, undo, redo,
      zoomBy, resetView,
      exportSvg, exportPng, exportPdf, exportJson,
      setName(n) { state.name = n; render(); },
      setTopology(t) { state.topology = t; resetView(); render(); renderInspector(); },
      showAll(v) { state.features.forEach((f) => (f.visible = v)); pushHistory(); render(); renderFeatureList(); },
    };
  }

  // Transient alert in the plasmidViz source bar (delegates to CagecatViz).
  const flash = (msg, type) => CagecatViz.flash("pvAlert", msg, type);

  // ── Sample plasmid (a compact synthetic construct with a real sequence) ────────
  function sampleData() {
    // Build a ~2.7 kb sequence with a couple of embedded ORFs so auto-annotate
    // and restriction detection have something to work with.
    const bases = "ACGT";
    let seq = "";
    const rng = mulberry32(42);
    for (let i = 0; i < 2686; i++) seq += bases[Math.floor(rng() * 4)];
    return {
      name: "pUC19-demo",
      length: seq.length,
      sequence: seq,
      topology: "circular",
      features: [
        mkFeat("lacZα", "CDS", 146, 469, -1),
        mkFeat("MCS", "misc_feature", 400, 455, 0),
        mkFeat("lac promoter", "promoter", 480, 510, -1),
        mkFeat("ori", "rep_origin", 867, 1455, 1),
        mkFeat("AmpR", "CDS", 1626, 2486, -1),
        mkFeat("AmpR promoter", "promoter", 2487, 2591, -1),
      ],
    };
  }
  function mkFeat(name, type, start, end, strand) {
    return { id: uid(), name, type, start, end, strand,
             color: colorForFeature(type, name), visible: true, label: null };
  }
  function mulberry32(a) {
    return function () {
      a |= 0; a = (a + 0x6D2B79F5) | 0;
      let t = Math.imul(a ^ (a >>> 15), 1 | a);
      t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
      return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
    };
  }

  // ── Bootstrap the page ─────────────────────────────────────────────────────────
  document.addEventListener("DOMContentLoaded", function () {
    const canvas = $("pvCanvasWrap");
    if (!canvas) return; // not the plasmidViz page

    const editor = Editor(canvas);
    window.PlasmidViz = editor;

    // File upload
    $("pvFile").addEventListener("change", (e) => {
      const file = e.target.files && e.target.files[0];
      if (!file) return;
      const reader = new FileReader();
      reader.onload = () => {
        try {
          const text = String(reader.result);
          if (file.name.endsWith(".json")) {
            editor.loadProject(JSON.parse(text));
          } else {
            const { records } = CagecatSeq.parse(text, file.name);
            const rec = records[0];
            if (!rec) throw new Error("no sequence records found in the file.");
            editor.loadParsed({
              name: rec.name, length: rec.length, sequence: rec.sequence,
              topology: rec.topology, features: rec.features.map(decorateFeature),
            });
            if (rec.features.length === 0 && rec.sequence) {
              flash("No annotations found in the file — use “Auto-annotate” to detect features.", "info");
            }
          }
        } catch (err) {
          flash("Could not read file: " + err.message, "danger");
        }
      };
      reader.onerror = () => flash("Failed to read the file.", "danger");
      reader.readAsText(file);
    });

    $("pvSampleBtn").addEventListener("click", () => {
      editor.loadParsed(sampleData());
      $("pvName").value = editor.state.name;
    });

    $("pvName").addEventListener("input", (e) => editor.setName(e.target.value));
    $("pvTopology").addEventListener("change", (e) => editor.setTopology(e.target.value));

    $("pvUndo").addEventListener("click", editor.undo);
    $("pvRedo").addEventListener("click", editor.redo);
    $("pvZoomIn").addEventListener("click", () => editor.zoomBy(1.2));
    $("pvZoomOut").addEventListener("click", () => editor.zoomBy(1 / 1.2));
    $("pvZoomReset").addEventListener("click", () => editor.resetView());
    $("pvAddFeature").addEventListener("click", editor.addFeature);
    $("pvAutoAnnotate").addEventListener("click", editor.autoAnnotate);
    $("pvShowAll").addEventListener("click", () => editor.showAll(true));
    $("pvHideAll").addEventListener("click", () => editor.showAll(false));
    $("pvFeatureSearch").addEventListener("input", editor.renderFeatureList);

    document.querySelectorAll("[data-export]").forEach((a) => {
      a.addEventListener("click", (e) => {
        e.preventDefault();
        if (!editor.state.length) { flash("Load a plasmid before exporting.", "warning"); return; }
        const kind = a.dataset.export;
        if (kind === "svg") editor.exportSvg();
        else if (kind === "png") editor.exportPng(3);
        else if (kind === "pdf") editor.exportPdf();
        else if (kind === "json") editor.exportJson();
      });
    });

    // Keyboard: undo / redo when not typing in an input.
    document.addEventListener("keydown", (e) => {
      const typing = /^(INPUT|TEXTAREA|SELECT)$/.test((e.target.tagName || ""));
      if (typing) return;
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "z") {
        e.preventDefault();
        if (e.shiftKey) editor.redo(); else editor.undo();
      }
    });
  });
})();
