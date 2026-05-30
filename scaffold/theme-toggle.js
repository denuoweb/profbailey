const THEMES = ["light", "dark", "cyber"];
const PREFERENCES = ["system", ...THEMES];
const STORAGE_KEY = document.documentElement.dataset.themeStorageKey || "theme-preference";
const mediaQuery = window.matchMedia("(prefers-color-scheme: dark)");
const buttons = document.querySelectorAll("[data-theme-controls] button[data-theme]");

const normalizeTheme = (value) => (THEMES.includes(value) ? value : null);
const normalizePreference = (value) => (PREFERENCES.includes(value) ? value : null);
const getSystemTheme = () => (mediaQuery.matches ? "dark" : "light");

const readStoredPreference = () => {
  try {
    return normalizePreference(localStorage.getItem(STORAGE_KEY));
  } catch {
    return null;
  }
};

const writeStoredPreference = (preference) => {
  try {
    localStorage.setItem(STORAGE_KEY, preference);
  } catch {
    /* Ignore storage failures. */
  }
};

const resolvePreference = (preference) => {
  if (preference === "system") {
    return getSystemTheme();
  }
  return normalizeTheme(preference) ?? getSystemTheme();
};

let activePreference =
  readStoredPreference() ??
  normalizePreference(document.documentElement.dataset.themePreference) ??
  normalizePreference(document.documentElement.dataset.theme) ??
  "system";

const syncButtons = (preference) => {
  buttons.forEach((button) => {
    button.setAttribute("aria-pressed", String(button.dataset.theme === preference));
  });
};

const applyPreference = (preference) => {
  const nextPreference = normalizePreference(preference) ?? "system";
  const nextTheme = resolvePreference(nextPreference);
  document.documentElement.dataset.themePreference = nextPreference;
  document.documentElement.dataset.theme = nextTheme;
  syncButtons(nextPreference);
};

buttons.forEach((button) => {
  button.type = "button";
  button.addEventListener("click", () => {
    activePreference = normalizePreference(button.dataset.theme) ?? "system";
    writeStoredPreference(activePreference);
    applyPreference(activePreference);
  });
});

applyPreference(activePreference);

mediaQuery.addEventListener("change", () => {
  if (activePreference === "system") {
    applyPreference(activePreference);
  }
});
