/*
 * start_neighborhood.js — the geneNeighborhood submission form (page:
 * start_neighborhood.html). Ways to start an analysis:
 *   - from a completed cblaster job (derived job: cblaster_neighborhood), or
 *   - search a query against a database (job: neighborhood_search).
 * Each creates a job with a shareable id and redirects to its results viewer.
 */
(function () {
  "use strict";

  const $ = (id) => document.getElementById(id);
  const val = (id) => { const el = $(id); return el ? el.value : ""; };

  function showAlert(box, type, msg) {
    if (!box) return;
    box.className = "alert alert-" + type;
    box.textContent = msg;
  }
  function hideAlert(box) { if (box) box.className = "alert d-none"; }

  function submit(url, options, btn, spinner, alertBox) {
    btn.disabled = true;
    if (spinner) spinner.classList.remove("d-none");
    hideAlert(alertBox);
    fetch(url, options)
      .then((r) => r.json().then((b) => ({ ok: r.ok, b })))
      .then(({ ok, b }) => {
        if (ok) {
          if (window.CagecatJobs) CagecatJobs.store(b);
          window.location = "/results/" + b.id;
        } else {
          showAlert(alertBox, "danger", b.detail || "Submission failed.");
          btn.disabled = false;
          if (spinner) spinner.classList.add("d-none");
        }
      })
      .catch(() => {
        showAlert(alertBox, "danger", "Could not reach the server. Please try again.");
        btn.disabled = false;
        if (spinner) spinner.classList.add("d-none");
      });
  }

  document.addEventListener("DOMContentLoaded", function () {
    if (!$("gnCbSubmit")) return; // not the geneNeighborhood start page

    // Pre-fill the cblaster job id from ?from=<id> (link from cblaster results).
    const from = new URLSearchParams(window.location.search).get("from");
    if (from) $("gnCbJobId").value = from;

    // ── From a cblaster job (derived job) ──────────────────────────────────
    $("gnCbSubmit").addEventListener("click", function () {
      const alertBox = $("gnCbAlert");
      const jobId = val("gnCbJobId").trim();
      if (!jobId) { showAlert(alertBox, "danger", "Enter the cblaster job ID to analyse."); return; }
      const flankKb = parseFloat(val("gnCbFlank")) || 5;
      const fd = new FormData();
      const title = val("gnCbTitle").trim();
      if (title) fd.append("title", title);
      fd.append("flank", String(Math.round(flankKb * 1000)));
      submit(
        "/api/jobs/" + encodeURIComponent(jobId) + "/actions/cblaster_neighborhood",
        { method: "POST", body: fd },
        $("gnCbSubmit"), $("gnCbSpinner"), alertBox
      );
    });

    // ── Search query sequences against clusteredNR (primary job) ───────────
    $("gnSeSubmit").addEventListener("click", function () {
      const alertBox = $("gnSeAlert");
      const fileEl = $("gnSeFile");
      const file = fileEl && fileEl.files ? fileEl.files[0] : null;
      if (!file) { showAlert(alertBox, "danger", "Upload a query FASTA file to search."); return; }
      const flankKb = parseFloat(val("gnSeFlank")) || 5;
      const fd = new FormData();
      const title = val("gnSeTitle").trim();
      const email = val("gnSeEmail").trim();
      if (title) fd.append("title", title);
      if (email) fd.append("email", email);
      fd.append("database", val("gnSeDb") || "clusterednr");
      fd.append("flank", String(Math.round(flankKb * 1000)));
      fd.append("files", file);
      submit("/api/jobs/neighborhood_search", { method: "POST", body: fd },
             $("gnSeSubmit"), $("gnSeSpinner"), alertBox);
    });

    // ── Open an existing job ───────────────────────────────────────────────
    $("gnOpenExisting").addEventListener("click", function () {
      const id = val("gnExistingJobId").trim();
      if (id) window.location = "/results/" + id;
    });
  });
})();
