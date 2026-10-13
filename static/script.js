const up = document.getElementById("upform");
if (up) up.addEventListener("submit", () => {
  const b = document.getElementById("upbtn");
  b.disabled = true;
  b.textContent = "Analyzing... this can take up to a minute";
});
document.querySelectorAll("form[data-confirm]").forEach((f) =>
  f.addEventListener("submit", (e) => { if (!confirm(f.dataset.confirm)) e.preventDefault(); }));
