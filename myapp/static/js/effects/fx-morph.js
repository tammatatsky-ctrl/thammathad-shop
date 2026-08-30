/* ===== FX MOD: morph (การ์ดขยายเป็น modal) ===== */
/**
 * FX mod id: 'morph' — คลิกการ์ด .card-expand[data-expand] → ขยายเป็น modal กลางจอ
 * ด้วยเทคนิค shared-element morph: จับ rect ของการ์ดเดิม → animate ไปรวบกลางจอ (is-morph-open).
 * โครงสร้าง modal สร้างจากเนื้อหาในตัวการ์ดเอง (img/ชื่อ/desc/ราคา/ลิงก์ data-detail-url).
 * IMPORTANT: นี่คือ interaction feedback (เหมือน lightbox) → ห้าม gate ด้วย Motion.reduced()
 * หรือ OS prefers-reduced-motion — ต้อง morph ทำงานเสมอ (AGENTS.md recipe #3).
 * ctx ที่ใช้: FX.api.bindCardLight (แสงกล่องไฟไล่เมาส์จาก core).
 */
FX.register({
  id: "morph",
  boot: function (ctx) {
    /* ---- Card expand modal: คลิกการ์ด → ขยายเป็น modal ---- */
    document.addEventListener("click", function (e) {
      var tile = e.target.closest(".card-expand[data-expand]");
      if (!tile) return;
      if (e.target.closest("a[href], button, .btn")) return;
      e.preventDefault();
      openCardExpand(tile);
    });
    /** openCardExpand(tile) — สร้าง backdrop + modal จากเนื้อหาของการ์ดที่คลิก แล้ว morph ขึ้นกลางจอ.
     *  เงื่อนไขข้าม: คลิกที่ a[href]/button/.btn ภายใน → ปล่อยทำงานตามปกติ (ไม่เปิด modal).
     *  @param {HTMLElement} tile การ์ดตัวแม่ (.card-expand[data-expand])
     */
    function openCardExpand(tile) {
      var backdrop = document.createElement("div");
      backdrop.className = "island-backdrop";
      var wrap = document.createElement("div");
      wrap.className = "card-expand-wrap";
      var img = tile.querySelector("img");
      var link =
        tile.querySelector(".product-link") || tile.querySelector("a[href]");
      var desc =
        tile.querySelector(".product-description") || tile.querySelector("p");
      var price = tile.querySelector(".product-price--emphasis");
      var detailUrl =
        tile.getAttribute("data-detail-url") ||
        (link && link.getAttribute("href")) ||
        "";
      var src = (img && img.currentSrc) || (img && img.src) || "";
      var imgHtml = src
        ? '<img src="' + src + '" alt="" class="card-expand-img">'
        : "";
      var nameHtml =
        (link ? link.textContent.trim() : "") || "รายละเอียดสินค้า";
      var descHtml = desc
        ? '<p class="card-expand-desc">' + desc.textContent.trim() + "</p>"
        : "";
      var priceHtml = price
        ? '<p class="card-expand-price">' + price.textContent.trim() + "</p>"
        : "";
      wrap.innerHTML =
        '<div class="card-expand-card" role="dialog" aria-modal="true">' +
        '<button type="button" class="card-expand-close" aria-label="ปิด"><i class="bi bi-x-lg"></i></button>' +
        imgHtml +
        '<div class="card-expand-body">' +
        '<h4 class="card-expand-title">' +
        nameHtml +
        "</h4>" +
        descHtml +
        priceHtml +
        '<a href="' +
        detailUrl +
        '" class="btn btn-primary w-100 card-expand-link mt-3"><i class="bi bi-arrow-right me-1"></i>ดูรายละเอียด</a>' +
        "</div></div>";
      document.body.appendChild(backdrop);
      document.body.appendChild(wrap);
      var card = wrap.querySelector(".card-expand-card");
      var offLight = (
        FX.api.bindCardLight ||
        function () {
          return function () {};
        }
      )(card);

      /* ---- Apple shared-element morph: ขยายจากตำแหน่งการ์ดที่คลิก
               เป็น interaction feedback (เหมือน lightbox) → ไม่ขึ้นกับ ⚡ toggle หรือ OS reduce ---- */
      {
        var r = tile.getBoundingClientRect();
        var vw = window.innerWidth,
          vh = window.innerHeight;
        var cardW = Math.min(520, Math.max(280, vw - 48));
        var cardH = Math.min(440, Math.max(200, vh - 72));
        var x0 = Math.min(Math.max(r.left, 12), vw - cardW - 12);
        var y0 = Math.min(Math.max(r.top, 12), vh - cardH - 12);
        card.style.position = "fixed";
        card.style.left = x0 + "px";
        card.style.top = y0 + "px";
        card.style.width = r.width + "px";
        card.style.height = r.height + "px";
        card.style.margin = "0";
        card.style.zIndex = "9999";
        card.classList.add("is-morph");
        document.body.offsetHeight;
        requestAnimationFrame(function () {
          card.classList.add("is-morph-open");
          card.style.left = (vw - cardW) / 2 + "px";
          card.style.top = (vh - cardH) / 2 + "px";
          card.style.width = cardW + "px";
          card.style.height = cardH + "px";
          requestAnimationFrame(function () {
            backdrop.classList.add("show");
          });
        });
      }
      function close() {
        if (card.dataset.closing) return;
        card.dataset.closing = "1";
        if (offLight) offLight();
        card.classList.add("is-closing");
        card.classList.remove("is-morph-open");
        card.classList.remove("show");
        backdrop.classList.remove("show");
        setTimeout(function () {
          if (wrap.parentNode) wrap.parentNode.removeChild(wrap);
          if (backdrop.parentNode) backdrop.parentNode.removeChild(backdrop);
        }, 520);
      }
      card.querySelector(".card-expand-close").addEventListener("click", close);
      backdrop.addEventListener("click", close);
      document.addEventListener(
        "keydown",
        function esc(e) {
          if (e.key === "Escape") {
            close();
            document.removeEventListener("keydown", esc, true);
          }
        },
        true,
      );
    }
    window.openCardExpand = openCardExpand;
  },
});
