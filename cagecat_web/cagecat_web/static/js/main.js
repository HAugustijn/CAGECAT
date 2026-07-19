document.addEventListener("DOMContentLoaded", function () {
  const path = window.location.pathname;

  // Activate correct navbar link
  const navLinks = [
    { id: "nav-home", match: (path) => path === "/" },
    { id: "nav-docs", match: (path) => path.startsWith("/documentation") },
    { id: "nav-about", match: (path) => path.startsWith("/about") },
    { id: "nav-contact", match: (path) => path.startsWith("/contact") }
  ];

  navLinks.forEach(link => {
    const el = document.getElementById(link.id);
    if (el && link.match(path)) {
      el.classList.add("active");
    }
  });

  // Initialize tooltips
  const tooltipTriggerList = [].slice.call(document.querySelectorAll('[data-bs-toggle="tooltip"]'));
  tooltipTriggerList.forEach(function (tooltipTriggerEl) {
    new bootstrap.Tooltip(tooltipTriggerEl);
  });

  // Toggle sequence and HMM input sections
  const querySeqCheckbox = document.getElementById('querySeq');
  const queryHMMCheckbox = document.getElementById('queryHMM');
  const seqInputSection = document.getElementById('seqInputSection');
  const hmmInputSection = document.getElementById('hmmInputSection');

  function toggleSections() {
    seqInputSection.classList.toggle('d-none', !querySeqCheckbox.checked);
    hmmInputSection.classList.toggle('d-none', !queryHMMCheckbox.checked);
  }

  querySeqCheckbox.addEventListener('change', toggleSections);
  queryHMMCheckbox.addEventListener('change', toggleSections);
  toggleSections(); // Initial toggle

  // Toggle file upload div for sequence input
  const inputSeqRadio = document.getElementById("inputSeq");
  const inputNCBIRadio = document.getElementById("inputNCBI");
  const uploadDiv = document.getElementById("seqFileUpload");
  const hmmIdDiv = document.getElementById("hmmIdUpload");

  function toggleUploadDivs() {
    if (inputSeqRadio.checked) {
      uploadDiv.classList.remove('d-none');
      hmmIdDiv.classList.add('d-none');
    } else if (inputNCBIRadio.checked) {
      uploadDiv.classList.add('d-none');
      hmmIdDiv.classList.remove('d-none');
    }
  }

  inputSeqRadio.addEventListener("change", toggleUploadDivs);
  inputNCBIRadio.addEventListener("change", toggleUploadDivs);
  toggleUploadDivs(); // Initial toggle

  // Toggle intermediate genes settings
  const intermedGenesCheckbox = document.getElementById('IntermedGenes');
  const intermedSettings = document.getElementById('intermedSettings');

  function toggleIntermedSettings() {
    intermedSettings.classList.toggle('d-none', !intermedGenesCheckbox.checked);
  }

  intermedGenesCheckbox.addEventListener('change', toggleIntermedSettings);
  toggleIntermedSettings(); // Initial toggle

  // Toggle Advanced settings
  const toggleAdvancedBtn = document.getElementById('toggleAdvancedBtn');
  const toggleAdvancedIcon = document.getElementById('toggleAdvancedIcon');
  const advancedSettings = document.getElementById('advancedSettings');

  toggleAdvancedBtn.addEventListener('click', function () {
    advancedSettings.classList.toggle('d-none');
    if (advancedSettings.classList.contains('d-none')) {
      toggleAdvancedIcon.classList.remove('bi-dash-circle-fill');
      toggleAdvancedIcon.classList.add('bi-plus-circle-fill');
    } else {
      toggleAdvancedIcon.classList.remove('bi-plus-circle-fill');
      toggleAdvancedIcon.classList.add('bi-dash-circle-fill');
    }
  });

  // Toggle Filter settings
  const sections = [
    { btnId: "toggleFilterBtn", iconId: "toggleFilterIcon", textId: "toggleFilterText", targetId: "filterSettings" },
    { btnId: "toggleClusterBtn", iconId: "toggleClusterIcon", textId: "toggleClusterText", targetId: "clusterSettings" },
    { btnId: "toggleSummaryBtn", iconId: "toggleSummaryIcon", textId: "toggleSummaryText", targetId: "summarySettings" },
    { btnId: "toggleBinaryBtn", iconId: "toggleBinaryIcon", textId: "toggleBinaryText", targetId: "binarySettings" },
    { btnId: "toggleOtherBtn", iconId: "toggleOtherIcon", textId: "toggleOtherText", targetId: "otherSettings" }
  ];

  sections.forEach(section => {
    const btn = document.getElementById(section.btnId);
    const icon = document.getElementById(section.iconId);
    const text = document.getElementById(section.textId);
    const target = document.getElementById(section.targetId);

    function toggleSection() {
      target.classList.toggle("d-none");
      if (target.classList.contains("d-none")) {
        icon.classList.remove("bi-dash-circle-fill");
        icon.classList.add("bi-plus-circle-fill");
      } else {
        icon.classList.remove("bi-plus-circle-fill");
        icon.classList.add("bi-dash-circle-fill");
      }
    }

    btn.addEventListener("click", toggleSection);
    text.addEventListener("click", toggleSection);
  });
});

// --- cblaster search submission --------------------------------------------
// Kept in its own listener (and fully null-guarded) so it runs on every page
// regardless of the page-specific setup above.
document.addEventListener("DOMContentLoaded", function () {
  const submitBtn = document.getElementById("cblasterSubmit");
  if (submitBtn) submitBtn.addEventListener("click", submitCblasterSearch);

  const openBtn = document.getElementById("openExistingJob");
  if (openBtn) {
    openBtn.addEventListener("click", function () {
      const input = document.getElementById("existingJobId");
      const id = (input && input.value ? input.value : "").trim();
      if (id) window.location = "/results/" + id;
    });
  }
});

const CBLASTER_BINARY_KEY = { KeyFucLen: "len", KeyFucSum: "sum", KeyFucMax: "max" };
const CBLASTER_BINARY_ATTR = {
  HitAttIdent: "identity",
  HitAttCov: "coverage",
  HitAttBit: "bitscore",
  HitAttEval: "evalue",
};

function submitCblasterSearch() {
  const alertBox = document.getElementById("cblasterAlert");
  const btn = document.getElementById("cblasterSubmit");
  const spinner = document.getElementById("cblasterSubmitSpinner");
  const val = (id) => {
    const el = document.getElementById(id);
    return el ? el.value : "";
  };
  const checked = (id) => {
    const el = document.getElementById(id);
    return !!(el && el.checked);
  };
  const appendIf = (fd, name, value) => {
    if (value !== "" && value != null) fd.append(name, value);
  };

  const fd = new FormData();
  appendIf(fd, "title", val("inputJobTitle"));
  appendIf(fd, "email", val("inputEmail"));

  const useSeq = checked("querySeq");
  const useHMM = checked("queryHMM");

  if (useSeq && useHMM) {
    showAlert(alertBox, "danger",
      "Combined (sequence + HMM) search is not supported yet — choose either sequences or HMM profiles.");
    return;
  }

  if (useHMM) {
    // HMM search: Pfam profiles against a local database, no query file.
    fd.append("mode", "hmm");
    const profiles = val("inputHMMs").trim();
    if (!profiles) {
      showAlert(alertBox, "danger", "Enter at least one Pfam profile identifier (e.g. PF00005).");
      return;
    }
    fd.append("query_profiles", profiles);
    const db = val("selectOrg");
    if (!db) {
      showAlert(alertBox, "danger", "No HMM search database is available on the server.");
      return;
    }
    fd.append("hmm_database", db);
  } else if (useSeq) {
    // Remote search: uploaded query file, or NCBI accessions.
    fd.append("mode", "remote");
    const useNCBI = checked("inputNCBI");
    const fileEl = document.getElementById("SeqInputFile");
    const hasFile = fileEl && fileEl.files && fileEl.files.length;
    const ncbiIds = val("hmmIdInput").trim();
    if (hasFile) {
      fd.append("files", fileEl.files[0]);
    } else if (useNCBI && ncbiIds) {
      fd.append("query_ids", ncbiIds);
    } else {
      showAlert(alertBox, "danger", "Please upload a query file or enter NCBI accessions.");
      return;
    }
    fd.append("database", val("selectDb") || "nr");
    appendIf(fd, "entrez_query", val("inputSpeciesLabel"));
    appendIf(fd, "hitlist_size", val("inputMaxHits"));
    appendIf(fd, "max_evalue", val("inputMaxEval"));
    appendIf(fd, "min_identity", val("inputMinIdent"));
    appendIf(fd, "min_coverage", val("inputMinCov"));
  } else {
    showAlert(alertBox, "danger", "Select a query type: input sequences or HMM profiles.");
    return;
  }

  // Clustering options apply to every mode.
  appendIf(fd, "gap", val("inputMaxIntGap"));
  appendIf(fd, "unique", val("inputMinUniqueHits"));
  appendIf(fd, "min_hits", val("inputMinHitsClust"));
  appendIf(fd, "percentage", val("inputMinPerc"));
  if (checked("IntermedGenes")) {
    fd.append("intermediate_genes", "on");
    appendIf(fd, "max_distance", val("inputMaxDist"));
  }
  if (checked("checkSortCLust")) fd.append("sort_clusters", "on");
  const bkey = CBLASTER_BINARY_KEY[val("inputKefFunc")];
  if (bkey) fd.append("binary_key", bkey);
  const battr = CBLASTER_BINARY_ATTR[val("inputHitAtt")];
  if (battr) fd.append("binary_attr", battr);
  appendIf(fd, "require", val("inputReqSeq"));

  btn.disabled = true;
  if (spinner) spinner.classList.remove("d-none");
  hideAlert(alertBox);

  fetch("/api/jobs/cblaster", { method: "POST", body: fd })
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

function showAlert(box, type, msg) {
  if (!box) return;
  box.className = "alert alert-" + type;
  box.textContent = msg;
}

function hideAlert(box) {
  if (box) box.className = "alert d-none";
}

// --- clinker submission ----------------------------------------------------
document.addEventListener("DOMContentLoaded", function () {
  const submitBtn = document.getElementById("clinkerSubmit");
  if (submitBtn) submitBtn.addEventListener("click", submitClinker);

  const advBtn = document.getElementById("toggleClinkerAdvancedBtn");
  const advIcon = document.getElementById("toggleClinkerAdvancedIcon");
  const advSection = document.getElementById("clinkerAdvancedSettings");
  if (advBtn && advSection) {
    advBtn.addEventListener("click", function () {
      advSection.classList.toggle("d-none");
      if (advIcon) {
        advIcon.classList.toggle("bi-plus-circle-fill");
        advIcon.classList.toggle("bi-dash-circle-fill");
      }
    });
  }
});

function submitClinker() {
  const alertBox = document.getElementById("clinkerAlert");
  const btn = document.getElementById("clinkerSubmit");
  const spinner = document.getElementById("clinkerSubmitSpinner");
  const val = (id) => {
    const el = document.getElementById(id);
    return el ? el.value : "";
  };
  const checked = (id) => {
    const el = document.getElementById(id);
    return !!(el && el.checked);
  };
  const appendIf = (fd, name, value) => {
    if (value !== "" && value != null) fd.append(name, value);
  };

  const fileEl = document.getElementById("clinkerFiles");
  const files = fileEl && fileEl.files ? fileEl.files : [];
  if (!files.length) {
    showAlert(alertBox, "danger", "Please upload at least one gene cluster file.");
    return;
  }

  const fd = new FormData();
  appendIf(fd, "title", val("clinkerJobTitle"));
  appendIf(fd, "email", val("clinkerEmail"));
  for (let i = 0; i < files.length; i++) fd.append("files", files[i]);
  appendIf(fd, "identity", val("clinkerIdentity"));
  appendIf(fd, "delimiter", val("clinkerDelimiter"));
  appendIf(fd, "decimals", val("clinkerDecimals"));
  if (checked("clinkerAsSeparate")) fd.append("as_separate_clusters", "on");
  if (checked("clinkerNoAlign")) fd.append("no_align", "on");
  if (checked("clinkerUseFileOrder")) fd.append("use_file_order", "on");
  if (checked("clinkerHideLinkHeaders")) fd.append("hide_link_headers", "on");
  if (checked("clinkerHideAlnHeaders")) fd.append("hide_aln_headers", "on");

  btn.disabled = true;
  if (spinner) spinner.classList.remove("d-none");
  hideAlert(alertBox);

  fetch("/api/jobs/clinker", { method: "POST", body: fd })
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
