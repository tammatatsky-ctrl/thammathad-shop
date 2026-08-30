/* ThaiAddress — cascade picker: จังหวัด → อำเภอ → ตำบล → รหัสไปรษณีย์ (auto)
   ใช้ dataset: static/data/thai-address.json (77 จังหวัด / 928 อำเภอ / 7,436 ตำบล)
   สั่งใช้:  window.ThaiAddress.init({ province:'#id_province', district:'#id_district',
             subdistrict:'#id_subdistrict', zipcode:'#id_zipcode', dataUrl:'/static/data/...' })
   - fetch ครั้งเดียวแล้วแคช (cache) — ตัวอื่นเรียกใช้ตัวเดียวกันผ่าน pending promise.
   - อยาก "แก้ค่าตอนกลับมา edit" ใส่ data-selected ที่คอมป์ prov/dist/sub แล้ว restore ปิดท้าย. */
(function () {
    "use strict";

    var cache = null;
    var pending = null;

    /** loadData(url) — โหลด JSON หนึ่งครั้ง: ถ้าอยู่ใน cache คืนค่าทันที,
     *  ถ้ากำลังโหลดอยู่ (pending) รอ promise เดียวกัน — กัน fetch ซ้ำซ้อน.
     *  @param {string} url ตำแหน่ง thai-address.json
     *  @returns {Promise<Object>} ข้อมูล {p:[{n, d:[{n, t:[{n, z}]}]}]}
     */
    function loadData(url) {
        if (cache) return Promise.resolve(cache);
        if (!pending) {
            pending = fetch(url)
                .then(function (r) {
                    return r.json();
                })
                .then(function (j) {
                    cache = j;
                    return j;
                });
        }
        return pending;
    }

    /** fill(sel, options, selected, placeholder) — เติม <option> ลง select (พร้อม option placeholder ตัวแรก).
     *  @param {HTMLSelectElement} sel select ปลายทาง
     *  @param {string[]} options ตัวเลือก
     *  @param {string} selected ค่าที่อยาก select ไว้ (ตอน edit)
     *  @param {string} placeholder ข้อความตัวเลือกแรก
     */
    function fill(sel, options, selected, placeholder) {
        sel.innerHTML = "";
        var ph = document.createElement("option");
        ph.value = "";
        ph.textContent = placeholder;
        sel.appendChild(ph);
        options.forEach(function (name) {
            var o = document.createElement("option");
            o.value = name;
            o.textContent = name;
            if (selected && name === selected) o.selected = true;
            sel.appendChild(o);
        });
        sel.disabled = false;
    }

    window.ThaiAddress = {
        init: function (opts) {
            var pSel = document.querySelector(opts.province);
            var dSel = document.querySelector(opts.district);
            var tSel = document.querySelector(opts.subdistrict);
            var zInp = document.querySelector(opts.zipcode);
            if (!pSel || !dSel || !tSel || !zInp) return;

            var wantP = pSel.dataset.selected || "";
            var wantD = dSel.dataset.selected || "";
            var wantT = tSel.dataset.selected || "";

            function reset(sel, msg) {
                sel.innerHTML = '<option value="">' + msg + "</option>";
                sel.disabled = true;
            }

            loadData(opts.dataUrl)
                .then(function (data) {
                    /* province */
                    fill(
                        pSel,
                        data.p.map(function (x) {
                            return x.n;
                        }),
                        wantP,
                        "— เลือกจังหวัด —",
                    );

                    function onProvince() {
                        var pv = null;
                        data.p.forEach(function (x) {
                            if (x.n === pSel.value) pv = x;
                        });
                        if (!pv) {
                            reset(dSel, "— เลือกจังหวัดก่อน —");
                            reset(tSel, "— เลือกอำเภอก่อน —");
                            zInp.value = "";
                            return;
                        }
                        fill(
                            dSel,
                            pv.d.map(function (x) {
                                return x.n;
                            }),
                            wantD,
                            "— เลือกอำเภอ —",
                        );
                        onDistrict();
                    }
                    function onDistrict() {
                        var dv = null;
                        var pv = null;
                        data.p.forEach(function (x) {
                            if (x.n === pSel.value) pv = x;
                        });
                        if (pv)
                            pv.d.forEach(function (x) {
                                if (x.n === dSel.value) dv = x;
                            });
                        if (!dv) {
                            reset(tSel, "— เลือกอำเภอก่อน —");
                            zInp.value = "";
                            return;
                        }
                        fill(
                            tSel,
                            dv.t.map(function (x) {
                                return x.n;
                            }),
                            wantT,
                            "— เลือกตำบล —",
                        );
                        onSubdistrict();
                    }
                    function onSubdistrict() {
                        var tz = "";
                        var pv = null;
                        data.p.forEach(function (x) {
                            if (x.n === pSel.value) pv = x;
                        });
                        if (pv) {
                            pv.d.forEach(function (d) {
                                if (d.n !== dSel.value) return;
                                d.t.forEach(function (t) {
                                    if (t.n === tSel.value) tz = t.z;
                                });
                            });
                        }
                        zInp.value = tz;
                    }

                    pSel.addEventListener("change", function () {
                        wantD = "";
                        wantT = "";
                        onProvince();
                    });
                    dSel.addEventListener("change", function () {
                        wantT = "";
                        onDistrict();
                    });
                    tSel.addEventListener("change", onSubdistrict);

                    /* restore saved selection (edit mode) */
                    if (wantP) {
                        onProvince();
                        if (wantD && dSel.value === wantD) {
                            onDistrict();
                            if (wantT && tSel.value === wantT) onSubdistrict();
                        }
                    }
                })
                .catch(function () {
                    pSel.innerHTML =
                        '<option value="">โหลดข้อมูลที่อยู่ไม่สำเร็จ</option>';
                });
        },
    };
})();
