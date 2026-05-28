const THEMES = ["light", "dark", "cyber"];
const STORAGE_KEY = document.documentElement.dataset.themeStorageKey || "theme-preference";
const mediaQuery = window.matchMedia("(prefers-color-scheme: dark)");
const buttons = document.querySelectorAll("[data-theme-controls] button[data-theme]");

const normalizeTheme = (value) => (THEMES.includes(value) ? value : null);
const getSystemTheme = () => (mediaQuery.matches ? "dark" : "light");

const readStoredTheme = () => {
  try {
    return normalizeTheme(localStorage.getItem(STORAGE_KEY));
  } catch {
    return null;
  }
};

const writeStoredTheme = (theme) => {
  try {
    localStorage.setItem(STORAGE_KEY, theme);
  } catch {
    /* Ignore storage failures. */
  }
};

let explicitTheme = readStoredTheme() ?? normalizeTheme(document.documentElement.dataset.theme);

const syncButtons = (theme) => {
  buttons.forEach((button) => {
    button.setAttribute("aria-pressed", String(button.dataset.theme === theme));
  });
};

const applyTheme = (theme) => {
  const nextTheme = normalizeTheme(theme) ?? getSystemTheme();
  document.documentElement.dataset.theme = nextTheme;
  syncButtons(nextTheme);
};

buttons.forEach((button) => {
  button.type = "button";
  button.addEventListener("click", () => {
    explicitTheme = button.dataset.theme;
    writeStoredTheme(explicitTheme);
    applyTheme(explicitTheme);
  });
});

applyTheme(explicitTheme ?? getSystemTheme());

mediaQuery.addEventListener("change", () => {
  if (!explicitTheme) {
    applyTheme(getSystemTheme());
  }
});
