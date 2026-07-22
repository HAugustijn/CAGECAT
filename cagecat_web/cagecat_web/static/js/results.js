// Results page: polls a job's status, then renders its plot, downloads and the
// available downstream actions (gne, extract, recompute, ...).
(function () {
  let jobId;
  let maxExtract = 50;
  let maxClinker = 25;

  document.addEventListener("DOMContentLoaded", init);

  function init() {
    const root = document.getElementById("results-root");
    if (!root) return;
    jobId = root.dataset.jobId;
    maxExtract = parseInt(root.dataset.maxExtract, 10) || maxExtract;
    maxClinker = parseInt(root.dataset.maxClinker, 10) || maxClinker;
    wireActionForms();
    wireClusterVisualise();
    wireClusterNeighborhood();
    poll();
  }

  function el(id) {
    return document.getElementById(id);
  }

  function badge(s) {
    const m = {
      completed: "success",
      failed: "danger",
      invalid: "danger",
      running: "info",
      queued: "secondary",
      pending: "secondary",
    };
    return m[s] || "secondary";
  }

  function setHeader(job) {
    el("job-id").textContent = job.id;
    el("job-title").textContent = job.title || job.label;
    const b = el("job-status");
    b.textContent = job.status;
    b.className = "badge text-bg-" + badge(job.status);
    if (job.parent_id) {
      const pl = el("parent-link");
      pl.classList.remove("d-none");
      el("parent-link-a").href = "/results/" + job.parent_id;
    }
  }

  function poll() {
    fetch("/api/jobs/" + jobId)
      .then((r) => (r.status === 404 ? null : r.json()))
      .then((job) => {
        if (!job) {
          el("notfound-panel").classList.remove("d-none");
          el("status-panel").classList.add("d-none");
          return;
        }
        if (window.CagecatJobs) CagecatJobs.store(job);
        setHeader(job);
        if (["pending", "queued", "running"].includes(job.status)) {
          el("status-panel").classList.remove("d-none");
          setTimeout(poll, 2500);
        } else if (job.status === "completed") {
          el("status-panel").classList.add("d-none");
          loadResults(job);
        } else {
          el("status-panel").classList.add("d-none");
          el("error-panel").classList.remove("d-none");
          el("error-msg").textContent = job.error || "The job failed.";
          el("logs-link").href = "/api/jobs/" + jobId + "/logs/stderr.log";
        }
      })
      .catch(() => setTimeout(poll, 4000));
  }

  function fmtSize(n) {
    if (n < 1024) return n + " B";
    if (n < 1048576) return (n / 1024).toFixed(1) + " KB";
    return (n / 1048576).toFixed(1) + " MB";
  }

  function loadResults(job) {
    renderRunSummary(job);
    fetch("/api/jobs/" + jobId + "/results")
      .then((r) => r.json())
      .then((res) => {
        el("results-panel").classList.remove("d-none");

        // One button to download everything as a ZIP.
        if ((res.files || []).length) {
          const dl = el("downloadAll");
          dl.href = "/api/jobs/" + jobId + "/archive";
          dl.classList.remove("d-none");
        }

        // Plot: embedded on the page + "open in full screen" (new tab).
        if (res.plot) {
          const viewUrl =
            "/api/jobs/" + jobId + "/view/" + encodeURIComponent(res.plot);
          el("plot-frame").src = viewUrl;
          el("plot-panel").classList.remove("d-none");
          const fs = el("openFullscreen");
          fs.href = viewUrl;
          fs.classList.remove("d-none");
        }
        if (job.actions && job.actions.length) showActions(job.actions);
      });
    loadClusters();
  }

  function renderRunSummary(job) {
    const p = job.params || {};
    const files = job.input_files || [];
    let input = "";
    if (files.length) input = files.join(", ");
    else if (p.query_profiles) input = "profiles " + [].concat(p.query_profiles).join(" ");
    else if (p.query_ids) input = "NCBI ids " + [].concat(p.query_ids).join(" ");
    const db = p.local_database || p.hmm_database || p.database || "";
    const mode = p.mode || "";
    let line = "<strong>" + esc(job.label || job.tool) + "</strong>";
    if (input) line += " — " + esc(input);
    if (db) line += " against <strong>" + esc(db) + "</strong>";
    if (mode) line += " (" + esc(mode) + ")";
    el("run-summary-line").innerHTML = line;

    const rows = [];
    if (files.length) rows.push(["input file(s)", files.join(", ")]);
    Object.keys(p).forEach((k) => {
      const v = p[k];
      rows.push([k, Array.isArray(v) ? v.join(" ") : String(v)]);
    });
    el("run-summary-table").innerHTML = rows
      .map(
        (r) =>
          '<tr><td class="text-body-secondary" style="width:14rem">' +
          esc(r[0]) + "</td><td>" + esc(r[1]) + "</td></tr>"
      )
      .join("");
  }

  function esc(s) {
    return String(s == null ? "" : s).replace(/[&<>"]/g, (c) => ({
      "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;",
    })[c]);
  }

  function loadClusters() {
    fetch("/api/jobs/" + jobId + "/clusters")
      .then((r) => (r.ok ? r.json() : { clusters: [] }))
      .then((data) => {
        const clusters = data.clusters || [];
        if (!clusters.length) return;
        renderClusters(clusters, data.total || clusters.length, data.capped);
      })
      .catch(() => {});
  }

  function renderClusters(clusters, total, capped) {
    el("clusters-count").textContent = total;
    if (capped) {
      const note = el("clusters-cap-note");
      note.textContent =
        " Too many to list — showing the top " + clusters.length + " by score.";
      note.classList.remove("d-none");
    }
    const body = el("clustersBody");
    body.innerHTML = "";
    clusters.forEach((c) => {
      const tr = document.createElement("tr");
      const loc =
        c.start != null && c.end != null ? c.start + "–" + c.end : "";
      tr.innerHTML =
        '<td><input type="checkbox" class="form-check-input cluster-check" value="' +
        esc(c.number) + '"></td>' +
        "<td>" + esc(c.number) + "</td>" +
        "<td>" + esc(c.organism) + "</td>" +
        "<td>" + esc(c.scaffold) + "</td>" +
        "<td>" + esc(c.score) + "</td>" +
        "<td>" + esc(c.n_genes) + "</td>" +
        '<td class="text-nowrap">' + esc(loc) + "</td>";
      body.appendChild(tr);
    });

    const checks = () =>
      Array.from(document.querySelectorAll(".cluster-check"));
    const selected = () => checks().filter((c) => c.checked).map((c) => c.value);
    const updateCount = () => {
      const n = selected().length;
      el("clustersSelectedCount").textContent = n ? n + " selected" : "";
    };
    body.addEventListener("change", updateCount);
    el("clustersAll").addEventListener("click", () => {
      checks().forEach((c) => (c.checked = true));
      updateCount();
    });
    el("clustersNone").addEventListener("click", () => {
      checks().forEach((c) => (c.checked = false));
      el("clustersHeaderCheck").checked = false;
      updateCount();
    });
    el("clustersHeaderCheck").addEventListener("change", (ev) => {
      checks().forEach((c) => (c.checked = ev.target.checked));
      updateCount();
    });
    el("extractSelected").addEventListener("click", () => {
      const nums = selected();
      if (!nums.length) {
        alert("Select at least one cluster to download.");
        return;
      }
      if (
        nums.length > maxExtract &&
        !confirm(
          "You selected " + nums.length + " clusters. Extracting from a remote " +
          "search fetches each sequence from NCBI, so only the top " + maxExtract +
          " by score will be downloaded. Continue?"
        )
      ) {
        return;
      }
      const btn = el("extractSelected");
      const status = el("clustersSelectedCount");
      btn.disabled = true;
      status.textContent = "Preparing download…";
      const fd = new FormData();
      fd.append("clusters", nums.join(" "));
      fd.append("maximum_clusters", String(nums.length));
      fd.append("format", el("clustersFormat").value);
      // Runs as a background job that is deliberately NOT stored in the sidebar;
      // when it finishes we stream the results back as a single ZIP download.
      fetch("/api/jobs/" + jobId + "/actions/cblaster_extract_clusters", {
        method: "POST",
        body: fd,
      })
        .then((r) => r.json().then((b) => ({ ok: r.ok, b })))
        .then(({ ok, b }) => {
          if (!ok) {
            alert(b.detail || "Could not extract clusters.");
            btn.disabled = false;
            status.textContent = "";
            return;
          }
          pollThenDownloadZip(b.id, btn, status);
        })
        .catch(() => {
          btn.disabled = false;
          status.textContent = "";
        });
    });

    el("clusters-panel").classList.remove("d-none");
  }

  function showActions(actions) {
    el("actions-panel").classList.remove("d-none");
    const names = new Set(actions.map((a) => a.name));
    document.querySelectorAll("[data-action-card]").forEach((card) => {
      card.classList.toggle("d-none", !names.has(card.dataset.actionCard));
    });
  }

  function wireActionForms() {
    document.querySelectorAll("form[data-action]").forEach((form) => {
      form.addEventListener("submit", (ev) => {
        ev.preventDefault();
        const action = form.dataset.action;
        const inline = form.dataset.inline === "true";
        const btn = form.querySelector("button[type=submit]");
        if (btn) btn.disabled = true;
        fetch("/api/jobs/" + jobId + "/actions/" + action, {
          method: "POST",
          body: new FormData(form),
        })
          .then((r) => r.json().then((b) => ({ ok: r.ok, b })))
          .then(({ ok, b }) => {
            if (!ok) {
              alert(b.detail || "Could not start the analysis.");
              if (btn) btn.disabled = false;
              return;
            }
            if (inline) {
              // Inline utility jobs (GNE, extract sequences) are not added to
              // the "Your jobs" sidebar — they run and show results in place.
              runInline(form, b.id, btn);
            } else {
              if (window.CagecatJobs) CagecatJobs.store(b);
              window.location = "/results/" + b.id;
            }
          })
          .catch(() => {
            if (btn) btn.disabled = false;
          });
      });
    });
  }

  // Run a derived job without leaving the page: poll it and show its result
  // (downloads + any plot) in a container next to the form.
  function runInline(form, newJobId, btn) {
    let box = form.parentElement.querySelector(".inline-result");
    if (!box) {
      box = document.createElement("div");
      box.className = "inline-result mt-3";
      form.parentElement.appendChild(box);
    }
    box.innerHTML =
      '<div class="d-flex align-items-center gap-2 text-body-secondary small">' +
      '<div class="spinner-border spinner-border-sm" role="status"></div>' +
      "Running…</div>";

    const download = form.dataset.download === "true";
    const tick = () => {
      fetch("/api/jobs/" + newJobId)
        .then((r) => r.json())
        .then((job) => {
          // Deliberately NOT stored in CagecatJobs (no sidebar entry).
          if (["pending", "queued", "running"].includes(job.status)) {
            setTimeout(tick, 2500);
            return;
          }
          if (btn) btn.disabled = false;
          if (job.status !== "completed") {
            box.innerHTML =
              '<div class="alert alert-danger small mb-0">' +
              (job.error || "The analysis failed.") +
              ' <a href="/api/jobs/' + newJobId + '/logs/stderr.log" target="_blank">log</a></div>';
            return;
          }
          fetch("/api/jobs/" + newJobId + "/results")
            .then((r) => r.json())
            .then((res) => {
              renderInlineResult(box, newJobId, res);
              if (download && (res.files || []).length) {
                triggerDownload(newJobId, res.files[0].name);
              }
            });
        })
        .catch(() => setTimeout(tick, 4000));
    };
    tick();
  }

  function renderInlineResult(box, newJobId, res) {
    let html = "";
    if (res.plot) {
      html +=
        '<iframe src="/api/jobs/' + newJobId + "/view/" +
        encodeURIComponent(res.plot) +
        '" class="w-100 border rounded mb-2" style="height:55vh;background:#fff;"></iframe>';
    }
    const files = res.files || [];
    if (files.length) {
      html += '<div class="list-group small" style="max-width:520px;">';
      files.forEach((f) => {
        html +=
          '<a class="list-group-item list-group-item-action d-flex justify-content-between" href="/api/jobs/' +
          newJobId + "/results/" + encodeURIComponent(f.name) +
          '"><span>' + f.name + '</span><span class="text-body-secondary">' +
          fmtSize(f.size_bytes) + "</span></a>";
      });
      html += "</div>";
    } else {
      html += '<div class="text-body-secondary small">No output files were produced.</div>';
    }
    box.innerHTML = html;
  }

  function triggerDownload(newJobId, filename) {
    const a = document.createElement("a");
    a.href = "/api/jobs/" + newJobId + "/results/" + encodeURIComponent(filename);
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
  }

  // Poll a (non-stored) background job, then download all its files as one ZIP.
  function pollThenDownloadZip(newJobId, btn, statusEl) {
    const tick = () => {
      fetch("/api/jobs/" + newJobId)
        .then((r) => r.json())
        .then((job) => {
          if (["pending", "queued", "running"].includes(job.status)) {
            setTimeout(tick, 2000);
            return;
          }
          if (btn) btn.disabled = false;
          if (job.status !== "completed") {
            if (statusEl) statusEl.textContent = "Extraction failed.";
            return;
          }
          if (statusEl) statusEl.textContent = "Download started.";
          const a = document.createElement("a");
          a.href = "/api/jobs/" + newJobId + "/archive";
          document.body.appendChild(a);
          a.click();
          document.body.removeChild(a);
        })
        .catch(() => setTimeout(tick, 3000));
    };
    tick();
  }

  function wireClusterVisualise() {
    const btn = document.getElementById("visualiseSelected");
    if (!btn) return;
    btn.addEventListener("click", () => {
      const nums = Array.from(document.querySelectorAll(".cluster-check"))
        .filter((c) => c.checked)
        .map((c) => c.value);
      if (!nums.length) {
        alert("Select at least one cluster to visualise.");
        return;
      }
      if (
        nums.length > maxClinker &&
        !confirm(
          "You selected " + nums.length + " clusters. A clinker figure stays " +
          "readable up to about " + maxClinker + " clusters, so the top " +
          maxClinker + " by score will be used. Continue?"
        )
      ) {
        return;
      }
      btn.disabled = true;
      const fd = new FormData();
      fd.append("clusters", nums.join(" "));
      fd.append("maximum_clusters", String(nums.length));
      fetch("/api/jobs/" + jobId + "/actions/cblaster_clinker", {
        method: "POST",
        body: fd,
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
        .catch(() => {
          btn.disabled = false;
        });
    });
  }

  // Forward the selected clusters to geneNeighborhood, which fetches their
  // surrounding genes from NCBI. Only the selected clusters are sent.
  function wireClusterNeighborhood() {
    const btn = document.getElementById("neighborhoodSelected");
    if (!btn) return;
    btn.addEventListener("click", () => {
      const nums = Array.from(document.querySelectorAll(".cluster-check"))
        .filter((c) => c.checked)
        .map((c) => c.value);
      if (!nums.length) {
        alert("Select at least one cluster to view its neighborhood.");
        return;
      }
      btn.disabled = true;
      const fd = new FormData();
      fd.append("clusters", nums.join(" "));
      fetch("/api/jobs/" + jobId + "/actions/cblaster_neighborhood", {
        method: "POST",
        body: fd,
      })
        .then((r) => r.json().then((b) => ({ ok: r.ok, b })))
        .then(({ ok, b }) => {
          if (ok) {
            if (window.CagecatJobs) CagecatJobs.store(b);
            window.location = "/results/" + b.id;
          } else {
            alert(b.detail || "Could not start geneNeighborhood.");
            btn.disabled = false;
          }
        })
        .catch(() => {
          btn.disabled = false;
        });
    });
  }
})();
