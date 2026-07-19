// Per-browser job history. Jobs are private to this browser (no login): their
// ids are kept in localStorage and rendered into the left sidebar. This mirrors
// the behaviour of CAGECAT v1.
(function () {
  const KEY = "cagecat_jobs";
  const MAX = 50;

  function all() {
    try {
      return JSON.parse(localStorage.getItem(KEY)) || [];
    } catch (e) {
      return [];
    }
  }

  function save(list) {
    localStorage.setItem(KEY, JSON.stringify(list.slice(0, MAX)));
  }

  function store(job) {
    if (!job || !job.id) return;
    const list = all().filter((j) => j.id !== job.id);
    list.unshift({
      id: job.id,
      label: job.label || job.tool || "",
      title: job.title || "",
      status: job.status || "",
      parent_id: job.parent_id || null,
      time: Date.now(),
    });
    save(list);
    render();
  }

  function badge(status) {
    const map = {
      completed: "success",
      failed: "danger",
      invalid: "danger",
      running: "info",
      queued: "secondary",
      pending: "secondary",
    };
    return map[status] || "secondary";
  }

  function escapeHtml(s) {
    return String(s).replace(/[&<>"]/g, (c) => ({
      "&": "&amp;",
      "<": "&lt;",
      ">": "&gt;",
      '"': "&quot;",
    })[c]);
  }

  function remove(id) {
    save(all().filter((j) => j.id !== id));
    render();
  }

  function clear() {
    localStorage.removeItem(KEY);
    render();
  }

  function render() {
    const el = document.getElementById("previousJobsOverview");
    if (!el) return;
    // Attach the delete-button click handler once (event delegation).
    if (!el.dataset.wired) {
      el.dataset.wired = "1";
      el.addEventListener("click", (ev) => {
        const btn = ev.target.closest("[data-del-id]");
        if (!btn) return;
        ev.preventDefault();
        ev.stopPropagation();
        remove(btn.dataset.delId);
      });
    }

    const list = all();
    if (!list.length) {
      el.innerHTML =
        '<li class="text-body-secondary small">No jobs yet on this browser.</li>';
      return;
    }
    el.innerHTML = "";
    list.forEach((j) => {
      const li = document.createElement("li");
      li.className = "mb-2 d-flex align-items-start justify-content-between";
      const label = j.title || j.label || j.id.slice(0, 8);
      li.innerHTML =
        '<a href="/results/' +
        j.id +
        '" class="text-decoration-none flex-grow-1 me-1">' +
        '<span class="badge text-bg-' +
        badge(j.status) +
        '">&nbsp;</span> ' +
        '<span class="small fw-semibold">' +
        escapeHtml(label) +
        "</span><br>" +
        '<span class="text-body-secondary" style="font-size:.72rem">' +
        escapeHtml(j.label) +
        " · " +
        j.id.slice(0, 8) +
        "</span></a>" +
        '<button type="button" class="btn btn-sm btn-link text-body-secondary p-0 lh-1" ' +
        'title="Remove from list" aria-label="Remove job" data-del-id="' +
        j.id +
        '"><i class="bi bi-x-lg"></i></button>';
      el.appendChild(li);
    });
  }

  // Refresh non-terminal jobs so the sidebar reflects completion.
  function refresh() {
    all().forEach((j) => {
      if (["completed", "failed", "invalid"].includes(j.status)) return;
      fetch("/api/jobs/" + j.id)
        .then((r) => (r.ok ? r.json() : null))
        .then((job) => {
          if (job) store(job);
        })
        .catch(() => {});
    });
  }

  window.CagecatJobs = { store, render, all, refresh, remove, clear };
  document.addEventListener("DOMContentLoaded", () => {
    render();
    refresh();
  });
})();
