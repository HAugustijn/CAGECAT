const toggleButton = document.getElementById('theme-toggle');
const themeIcon = document.getElementById('theme-icon');
const html = document.documentElement;

const savedTheme = localStorage.getItem('theme');

// If a saved theme exists, use it
if (savedTheme) {
  html.setAttribute('data-bs-theme', savedTheme);
}

// Sync icon with current theme
const currentTheme = html.getAttribute('data-bs-theme');
themeIcon.classList.remove('bi-sun', 'bi-moon-stars');
themeIcon.classList.add(currentTheme === 'dark' ? 'bi-moon-stars' : 'bi-sun');

// Theme toggle logic
toggleButton.addEventListener('click', () => {
  const current = html.getAttribute('data-bs-theme');
  const next = current === 'dark' ? 'light' : 'dark';
  html.setAttribute('data-bs-theme', next);
  localStorage.setItem('theme', next);

  themeIcon.classList.remove('bi-sun', 'bi-moon-stars');
  themeIcon.classList.add(next === 'dark' ? 'bi-moon-stars' : 'bi-sun');
});
