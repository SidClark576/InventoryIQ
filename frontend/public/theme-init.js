// Apply the saved theme before first paint (next-themes key "theme") so dark mode does not flash light. No saved theme = light.
// External file because the CSP has no 'unsafe-inline' for scripts.
try {
  var t = localStorage.getItem("theme");
  if (t === "dark" || (t === "system" && matchMedia("(prefers-color-scheme: dark)").matches)) {
    document.documentElement.classList.add("dark");
  }
} catch (e) {}
