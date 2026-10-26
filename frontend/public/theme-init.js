// Applies the saved theme before the page is painted, so a person who chose a theme that differs from
// their system setting does not see the other one flash first. It only reads the saved choice; with no
// choice, the page follows the system setting through CSS. Keep the key in step with src/theme.ts.
(function () {
  try {
    var saved = window.localStorage.getItem("securescope-theme");
    if (saved === "light" || saved === "dark") {
      document.documentElement.setAttribute("data-theme", saved);
      var meta = document.querySelector('meta[name="theme-color"]');
      if (meta)
        meta.setAttribute("content", saved === "light" ? "#eef3f8" : "#050505");
    }
  } catch (e) {
    /* storage can be blocked; the app then follows the system setting */
  }
})();
