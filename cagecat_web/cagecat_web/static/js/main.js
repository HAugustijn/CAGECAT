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
