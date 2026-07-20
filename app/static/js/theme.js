const THEME_KEY = "sizzle-theme";

function currentTheme() {
  return localStorage.getItem(THEME_KEY) || "dark";
}

function paintToggle(btn, theme) {
  btn.textContent = theme === "dark" ? "☀️" : "🌙";
}

const toggle = document.getElementById("theme-toggle");
if (toggle) {
  paintToggle(toggle, currentTheme());
  toggle.addEventListener("click", () => {
    const next = currentTheme() === "dark" ? "light" : "dark";
    localStorage.setItem(THEME_KEY, next);
    document.documentElement.setAttribute("data-theme", next);
    paintToggle(toggle, next);
  });
}
