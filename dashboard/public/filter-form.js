(function () {
  var f = document.querySelector("[data-filter-form]");
  if (!f) return;
  f.addEventListener("submit", function (e) {
    e.preventDefault();
    var p = new URLSearchParams();
    new FormData(f).forEach(function (v, k) {
      if (v && v !== "all") p.set(k, String(v));
    });
    var qs = p.toString();
    window.location.href = qs ? "/?" + qs : "/";
  });
  f.querySelectorAll("[data-auto-submit]").forEach(function (el) {
    el.addEventListener("change", function () {
      f.requestSubmit();
    });
  });
})();
