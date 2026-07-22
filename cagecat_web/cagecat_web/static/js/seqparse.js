/*
 * CagecatSeq — shared, dependency-free sequence-annotation parsers.
 *
 * A single source of truth for reading GenBank, EMBL, GFF3(+FASTA) and FASTA in
 * the browser, used by both the plasmidViz and geneNeighborhood editors. Parsing
 * is multi-record: a file may contain several loci (e.g. an NCBI multi-record
 * GenBank download or a GFF with several sequence regions).
 *
 * Contract:
 *   CagecatSeq.parse(text, filename) -> { format, records: Record[] }
 *   Record  = { name, length, sequence, topology, features: Feature[] }
 *   Feature = { name, type, start, end, strand }   // 1-based inclusive; strand +1/-1/0
 */
(function () {
  "use strict";

  function cleanSeq(raw) {
    return (raw || "").replace(/[^A-Za-z]/g, "").toUpperCase();
  }

  function reverseComplement(seq) {
    const map = { A: "T", T: "A", G: "C", C: "G", N: "N",
                  a: "t", t: "a", g: "c", c: "g", n: "n" };
    let out = "";
    for (let i = seq.length - 1; i >= 0; i--) out += map[seq[i]] || "N";
    return out;
  }

  function detect(text) {
    const head = text.slice(0, 400);
    if (/^LOCUS\s/m.test(head) || head.startsWith("LOCUS")) return "genbank";
    if (/^ID\s{3}/.test(head) || /^ID\s+\w+;/.test(head)) return "embl";
    if (head.startsWith("##gff-version") || /^##gff/i.test(head)) return "gff";
    if (head.trimStart().startsWith(">")) return "fasta";
    const line = text.split(/\r?\n/).find((l) => l && !l.startsWith("#"));
    if (line && line.split("\t").length >= 8) return "gff";
    return "fasta";
  }

  function pickName(quals, type) {
    return quals.label || quals.gene || quals.product ||
           quals.locus_tag || quals.standard_name || quals.note || type;
  }

  function parseLocation(loc) {
    // Returns {start,end,strand} using 1-based inclusive coordinates.
    const strand = /complement/.test(loc) ? -1 : 1;
    const nums = (loc.match(/\d+/g) || []).map(Number);
    if (!nums.length) return null;
    return { start: Math.min(...nums), end: Math.max(...nums), strand };
  }

  // Shared GenBank/EMBL feature-table walker. `lines` are the raw table lines,
  // `keyIndent`/`qualIndent` the column at which keys and qualifiers begin.
  function featuresFromTable(lines, keyIndent, qualIndent) {
    const raw = [];
    let cur = null;
    let pendingQual = null;
    const flushQual = () => {
      if (cur && pendingQual) {
        const [k, v] = pendingQual;
        if (cur.quals[k] === undefined) cur.quals[k] = v;
      }
      pendingQual = null;
    };
    const push = () => { if (cur) { flushQual(); raw.push(cur); cur = null; } };

    for (const line of lines) {
      const key = line.slice(keyIndent).match(/^(\S+)\s+(.*)$/);
      const body = line.slice(qualIndent);
      const isFeatureStart = line.length > keyIndent && line[keyIndent] !== " " &&
                             line.slice(0, keyIndent).trim() === "" && key;
      if (isFeatureStart) {
        push();
        cur = { type: key[1], loc: key[2].trim(), quals: {} };
      } else if (cur && body.startsWith("/")) {
        flushQual();
        const m = body.match(/^\/(\w+)=?"?([^"]*)"?/);
        if (m) pendingQual = [m[1], m[2].trim()];
      } else if (cur && pendingQual && body.trim()) {
        pendingQual[1] += " " + body.trim().replace(/"$/, "");
      } else if (cur && !cur.loc.endsWith(")") && body.trim() && /^[\d.<>,()a-z]/i.test(body.trim())) {
        cur.loc += body.trim(); // continued location line
      }
    }
    push();

    const out = [];
    for (const f of raw) {
      if (f.type === "source") continue;
      const pos = parseLocation(f.loc);
      if (!pos) continue;
      out.push({
        name: pickName(f.quals, f.type),
        type: f.type,
        start: pos.start,
        end: pos.end,
        strand: pos.strand,
      });
    }
    return out;
  }

  // ── Per-format parsers (each returns Record[]) ──────────────────────────────
  function parseFasta(text) {
    const records = [];
    let name = "", seq = "";
    const flush = () => {
      if (name || seq) {
        const s = cleanSeq(seq);
        records.push({ name: name || "sequence", length: s.length, sequence: s,
                       topology: "circular", features: [] });
      }
    };
    for (const line of text.split(/\r?\n/)) {
      if (line.startsWith(">")) {
        flush();
        name = line.slice(1).trim().split(/\s+/)[0] || "sequence";
        seq = "";
      } else {
        seq += line.trim();
      }
    }
    flush();
    return records;
  }

  function splitBlocks(text) {
    // Split multi-record GenBank/EMBL on the // record terminator.
    return text.split(/^\/\/\s*$/m).map((b) => b.trim()).filter(Boolean);
  }

  function parseGenbankBlock(block) {
    const lines = block.split(/\r?\n/);
    let name = "", length = 0, topology = "circular";
    const locus = block.match(/^LOCUS\s+(\S+)\s+(\d+)\s*bp(.*)$/m);
    if (locus) {
      name = locus[1];
      length = parseInt(locus[2], 10);
      if (/linear/i.test(locus[3])) topology = "linear";
    }
    const ftStart = lines.findIndex((l) => l.startsWith("FEATURES"));
    const originIdx = lines.findIndex((l) => l.startsWith("ORIGIN"));
    const endIdx = originIdx === -1 ? lines.length : originIdx;
    const ftLines = ftStart === -1 ? [] : lines.slice(ftStart + 1, endIdx);
    const features = featuresFromTable(ftLines, 5, 21);

    let sequence = "";
    if (originIdx !== -1) sequence = cleanSeq(lines.slice(originIdx + 1).join(""));
    if (!length && sequence) length = sequence.length;
    if (!length && features.length) length = Math.max(...features.map((f) => f.end));
    return { name, length, sequence, topology, features };
  }

  function parseEmblBlock(block) {
    const lines = block.split(/\r?\n/);
    let name = "", length = 0, topology = "circular";
    const id = block.match(/^ID\s+(\S+?)[;\s]/m);
    if (id) name = id[1];
    const lenMatch = block.match(/(\d+)\s*BP\./);
    if (lenMatch) length = parseInt(lenMatch[1], 10);
    if (/linear/i.test(lines[0] || "")) topology = "linear";

    const ftLines = lines.filter((l) => l.startsWith("FT")).map((l) => "     " + l.slice(5));
    const features = featuresFromTable(ftLines, 5, 21);

    let sequence = "";
    const sqIdx = lines.findIndex((l) => l.startsWith("SQ"));
    if (sqIdx !== -1) sequence = cleanSeq(lines.slice(sqIdx + 1).join(""));
    if (!length && sequence) length = sequence.length;
    if (!length && features.length) length = Math.max(...features.map((f) => f.end));
    return { name, length, sequence, topology, features };
  }

  function parseGff(text) {
    // One record per seqid (GFF column 1); FASTA in a ##FASTA section is matched
    // back to its record by header.
    const lines = text.split(/\r?\n/);
    const bySeq = new Map();
    const regionLen = new Map();
    const fasta = new Map();
    let inFasta = false, fastaName = "";

    const rec = (seqid) => {
      if (!bySeq.has(seqid)) {
        bySeq.set(seqid, { name: seqid, length: 0, sequence: "", topology: "circular", features: [] });
      }
      return bySeq.get(seqid);
    };

    for (const line of lines) {
      if (inFasta) {
        if (line.startsWith(">")) fastaName = line.slice(1).trim().split(/\s+/)[0];
        else fasta.set(fastaName, (fasta.get(fastaName) || "") + line.trim());
        continue;
      }
      if (line.startsWith("##FASTA")) { inFasta = true; continue; }
      if (line.startsWith("##sequence-region")) {
        const p = line.split(/\s+/);
        if (p.length >= 4) regionLen.set(p[1], parseInt(p[3], 10) || 0);
        continue;
      }
      if (!line || line.startsWith("#")) continue;
      const c = line.split("\t");
      if (c.length < 8) continue;
      const type = c[2];
      if (type === "region" || type === "source") continue;
      const start = parseInt(c[3], 10);
      const end = parseInt(c[4], 10);
      if (!start || !end) continue;
      const strand = c[6] === "-" ? -1 : c[6] === "+" ? 1 : 0;
      const attrs = {};
      (c[8] || "").split(";").forEach((kv) => {
        const i = kv.indexOf("=");
        if (i > 0) attrs[kv.slice(0, i).trim().toLowerCase()] = decodeURIComponent(kv.slice(i + 1).trim());
      });
      const nm = attrs.name || attrs.gene || attrs.product || attrs.id || type;
      const r = rec(c[0]);
      r.features.push({ name: nm, type, start, end, strand });
      r.length = Math.max(r.length, end);
    }

    const records = [];
    for (const [seqid, r] of bySeq) {
      if (regionLen.has(seqid)) r.length = Math.max(r.length, regionLen.get(seqid));
      if (fasta.has(seqid)) {
        r.sequence = cleanSeq(fasta.get(seqid));
        r.length = Math.max(r.length, r.sequence.length);
      }
      records.push(r);
    }
    return records;
  }

  function parse(text, filename) {
    const format = detect(text);
    let records;
    if (format === "genbank") records = splitBlocks(text).map(parseGenbankBlock);
    else if (format === "embl") records = splitBlocks(text).map(parseEmblBlock);
    else if (format === "gff") records = parseGff(text);
    else records = parseFasta(text);

    records = records.filter((r) => r && (r.length || r.features.length));
    if (filename) {
      const base = filename.replace(/\.[^.]+$/, "");
      records.forEach((r, i) => {
        if (!r.name) r.name = records.length > 1 ? `${base}_${i + 1}` : base;
      });
    }
    return { format, records };
  }

  window.CagecatSeq = { parse, detect, reverseComplement };
})();
