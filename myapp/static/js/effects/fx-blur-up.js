/* ===== FX MOD: blur-up (ภาพโหลด เบลอ→ชัด) ===== */
/**
 * FX mod id: 'blur-up' — รูปสินค้า/avatar ค่อยๆ blur→ชัดเมื่อโหลดเสร็จ.
 * เอาเฉพาะ IMG ที่ยังโหลดไม่จบ (img.complete + naturalWidth) มาใส่ .img-blur-up
 * แล้วเมื่อ 'load'/'error' เพิ่ม .img-loaded → CSS เบลอ→ชัด (ขอบด้านภาพ).
 * ctx ที่ใช้: (ไม่ต้องใช้ engine — จบใน boot ทันที)
 */
FX.register({
  id: "blur-up",
  boot: function (ctx) {
    /* ---- Image blur-up ---- */
    document
      .querySelectorAll(
        ".product-img, .cart-thumb, .product-detail-image, .table-avatar, .placeholder-avatar",
      )
      .forEach(function (img) {
        if (img.tagName !== "IMG" || (img.complete && img.naturalWidth)) return;
        img.classList.add("img-blur-up");
        var done = function () {
          img.classList.add("img-loaded");
        };
        img.addEventListener("load", done);
        img.addEventListener("error", done);
      });
  },
});
