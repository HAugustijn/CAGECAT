// Results page: polls a job's status, then renders its plot, downloads and the
// available downstream actions (gne, extract, recompute, ...).
(function () {
  let jobId;

  document.addEventListener("DOMContentLoaded", init);

  function init() {
    const root = document.getElementById("results-root");
    if (!root) return;
    jobId = root.dataset.jobId;
    wireActionForms();
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
    fetch("/api/jobs/" + jobId + "/results")
      .then((r) => r.json())
      .then((res) => {
        const dl = el("downloads");
        dl.innerHTML = "";
        (res.files || []).forEach((f) => {
          const a = document.createElement("a");
          a.href =
            "/api/jobs/" + jobId + "/results/" + encodeURIComponent(f.name);
          a.className =
            "list-group-item list-group-item-action d-flex justify-content-between";
          a.innerHTML =
            "<span>" +
            f.name +
            '</span><span class="text-body-secondary small">' +
            fmtSize(f.size_bytes) +
            "</span>";
          dl.appendChild(a);
        });
        if (!(res.files || []).length) {
          dl.innerHTML =
            '<div class="list-group-item text-body-secondary small">No output files were produced.</div>';
        }
        el("results-panel").classList.remove("d-none");

        if (res.plot) {
          el("plot-frame").src =
            "/api/jobs/" + jobId + "/view/" + encodeURIComponent(res.plot);
          el("plot-panel").classList.remove("d-none");
        }
        if (job.actions && job.actions.length) showActions(job.actions);
      });
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
        const btn = form.querySelector("button[type=submit]");
        if (btn) btn.disabled = true;
        fetch("/api/jobs/" + jobId + "/actions/" + action, {
          method: "POST",
          body: new FormData(form),
        })
          .then((r) => r.json().then((b) => ({ ok: r.ok, b })))
          .then(({ ok, b }) => {
            if (ok) {
              if (window.CagecatJobs) CagecatJobs.store(b);
              window.location = "/results/" + b.id;
            } else {
              alert(b.detail || "Could not start the analysis.");
              if (btn) btn.disabled = false;
            }
          })
          .catch(() => {
            if (btn) btn.disabled = false;
          });
      });
    });
  }
})();
