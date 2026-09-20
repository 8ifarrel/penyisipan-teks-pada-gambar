// JS vanilla pendukung tampilan: tombol salin, menu navigasi (hamburger)
// di mobile, dan feedback visual pada area unggah drag-and-drop. Tidak ada
// logic yang berkomunikasi ke server di sini. Form tetap submit secara
// normal (multipart/form-data) lewat elemen <input type="file"> asli.

document.addEventListener("DOMContentLoaded", function () {
  initCopyButtons();
  initNavToggle();
  initDropzones();
  initDevInfoLive();
});

// --- Tombol "Salin" (kunci AES / teks hasil ekstraksi) ---------------------

function initCopyButtons() {
  document.addEventListener("click", function (event) {
    const button = event.target.closest("[data-copy-target], [data-copy-value]");
    if (!button) {
      return;
    }

    // Dua varian tombol salin:
    //  - data-copy-target: menyalin isi elemen lain (mis. kunci AES),
    //    tombolnya punya label teks (.btn__label) yang diganti sementara.
    //  - data-copy-value: menyalin nilai literal pada atribut itu sendiri
    //    (dipakai tombol ikon-saja di panel Info Developer), feedbacknya
    //    lewat class CSS saja karena tombolnya tidak punya label teks.
    const isIconOnly = button.hasAttribute("data-copy-value");
    let text;
    let target = null;
    if (isIconOnly) {
      text = button.getAttribute("data-copy-value") || "";
    } else {
      target = document.querySelector(button.getAttribute("data-copy-target"));
      if (!target) {
        return;
      }
      text = "value" in target ? target.value : target.textContent;
    }

    const labelEl = isIconOnly ? null : button.querySelector(".btn__label") || button;
    const originalLabel = labelEl ? labelEl.textContent : null;

    const showFeedback = function (success) {
      if (isIconOnly) {
        button.classList.toggle("dev-info__copy--success", success);
        button.classList.toggle("dev-info__copy--error", !success);
        setTimeout(function () {
          button.classList.remove("dev-info__copy--success", "dev-info__copy--error");
        }, 1200);
        return;
      }
      labelEl.textContent = success ? "Tersalin!" : "Gagal menyalin";
      button.classList.toggle("btn--success", success);
      setTimeout(function () {
        labelEl.textContent = originalLabel;
        button.classList.remove("btn--success");
      }, 1500);
    };

    const fallbackCopy = function () {
      // Fallback bila Clipboard API tidak tersedia (mis. konteks non-HTTPS).
      if (target && target.select) {
        target.select();
        try {
          document.execCommand("copy");
          showFeedback(true);
        } catch (err) {
          showFeedback(false);
        }
        return;
      }
      // Tombol ikon-saja tidak menunjuk ke elemen input/textarea mana pun,
      // jadi butuh textarea sementara supaya document.execCommand("copy")
      // tetap bisa dipakai.
      const temp = document.createElement("textarea");
      temp.value = text;
      temp.style.position = "fixed";
      temp.style.opacity = "0";
      document.body.appendChild(temp);
      temp.select();
      try {
        document.execCommand("copy");
        showFeedback(true);
      } catch (err) {
        showFeedback(false);
      }
      document.body.removeChild(temp);
    };

    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(text).then(function () {
        showFeedback(true);
      }, fallbackCopy);
    } else {
      fallbackCopy();
    }
  });
}

// --- Menu navigasi (hamburger di mobile) ------------------------------------

function initNavToggle() {
  const toggle = document.getElementById("nav-toggle");
  const nav = document.getElementById("site-nav");
  if (!toggle || !nav) {
    return;
  }

  toggle.addEventListener("click", function () {
    const isOpen = nav.classList.toggle("is-open");
    toggle.classList.toggle("is-active", isOpen);
    toggle.setAttribute("aria-expanded", String(isOpen));
  });

  // Tutup menu setelah salah satu tautan navigasi dipilih.
  nav.querySelectorAll(".nav__link").forEach(function (link) {
    link.addEventListener("click", function () {
      nav.classList.remove("is-open");
      toggle.classList.remove("is-active");
      toggle.setAttribute("aria-expanded", "false");
    });
  });
}

// --- Area unggah drag-and-drop -----------------------------------------------
//
// Elemen <input type="file"> pada .dropzone sengaja tetap ada dan berfungsi
// penuh (diposisikan menutupi seluruh area lewat CSS). Drag-and-drop file
// ke atasnya sudah didukung langsung oleh browser tanpa JS tambahan. Skrip
// ini hanya menambahkan feedback visual (highlight saat drag, nama file
// terpilih) supaya area tersebut terasa interaktif.

function initDropzones() {
  document.querySelectorAll(".dropzone").forEach(function (dropzone) {
    const input = dropzone.querySelector(".dropzone__input");
    const filenameEl = dropzone.querySelector("[data-dropzone-filename]");
    if (!input) {
      return;
    }

    ["dragenter", "dragover"].forEach(function (eventName) {
      input.addEventListener(eventName, function () {
        dropzone.classList.add("is-dragover");
      });
    });

    ["dragleave", "drop"].forEach(function (eventName) {
      input.addEventListener(eventName, function () {
        dropzone.classList.remove("is-dragover");
      });
    });

    // Highlight area saat input difokus lewat keyboard (Tab), karena
    // input-nya sendiri transparan (opacity: 0) sehingga fokus tidak
    // terlihat tanpa ini.
    input.addEventListener("focus", function () {
      dropzone.classList.add("is-focused");
    });
    input.addEventListener("blur", function () {
      dropzone.classList.remove("is-focused");
    });

    input.addEventListener("change", function () {
      const hasFile = Boolean(input.files && input.files.length);
      if (filenameEl) {
        filenameEl.textContent = hasFile ? input.files[0].name : "";
        filenameEl.hidden = !hasFile;
      }
      dropzone.classList.toggle("has-file", hasFile);
    });
  });
}

// --- Panel "Info Developer": info langsung sebelum form disubmit -----------
//
// Sebagian field pada panel Info Developer (ukuran & dimensi foto, ukuran
// teks, perkiraan ukuran payload, kapasitas citra) dihitung di sisi klien
// begitu pengguna memilih foto/mengetik teks, tanpa perlu menunggu form
// disubmit ke server. Elemen dengan id="dev-..." di _dev_info.html adalah
// target pembaruannya.

// Overhead payload tetap: header (4 byte) + nonce (12 byte) + authentication
// tag (16 byte) AES-GCM, mengikuti struktur payload pada app/stego/payload.py.
const DEV_INFO_PAYLOAD_OVERHEAD_BYTES = 32;

// SVG identik dengan macro icon_copy() di _icons.html, dipakai ulang di sini
// karena tombol salin pada field yang diperbarui live dibuat lewat JS
// (innerHTML), bukan dirender Jinja.
const DEV_INFO_COPY_ICON_SVG =
  '<svg class="icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" ' +
  'stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round" ' +
  'aria-hidden="true"><rect x="9" y="9" width="11" height="11" rx="2" />' +
  '<path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1" /></svg>';

function escapeHtml(str) {
  return String(str)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

// Format bilangan bulat/desimal mengikuti konvensi penulisan angka
// Indonesia (titik pemisah ribuan, koma pemisah desimal), setara dengan
// format_id_int()/format_id_decimal() di app/utils/formatting.py.
function formatIdInt(value) {
  return value.toLocaleString("id-ID");
}

function formatIdDecimal(value, decimals) {
  return value.toLocaleString("id-ID", {
    minimumFractionDigits: decimals,
    maximumFractionDigits: decimals,
  });
}

function formatSizeLive(numBytes) {
  const kbStr = formatIdDecimal(numBytes / 1000, 3) + " KB";
  return `${kbStr} (${formatIdInt(numBytes)} B)`;
}

// Menampilkan satu nilai Info Developer lengkap dengan tombol salin
// (ikon saja), menyamai perilaku macro _dev_value() di _dev_info.html.
// Nilai berformat "A (B)" (hasil formatSizeLive()) dipecah jadi dua
// bagian yang masing-masing punya tombol salin sendiri.
function devCopyButtonHtml(value) {
  const escaped = escapeHtml(value);
  return (
    `<button type="button" class="dev-info__copy" data-copy-value="${escaped}" ` +
    `title="Salin ${escaped}" aria-label="Salin ${escaped}">${DEV_INFO_COPY_ICON_SVG}</button>`
  );
}

function renderDevValue(text) {
  if (text === "-") {
    return "-";
  }
  const match = text.match(/^(.*) \(([^)]*)\)$/);
  if (match) {
    const primary = match[1];
    const secondary = match[2];
    return (
      `${escapeHtml(primary)}${devCopyButtonHtml(primary)} ` +
      `(${escapeHtml(secondary)}${devCopyButtonHtml(secondary)})`
    );
  }
  return `${escapeHtml(text)}${devCopyButtonHtml(text)}`;
}

function initDevInfoLive() {
  initEmbedDevInfoLive();
  initExtractDevInfoLive();
}

function initEmbedDevInfoLive() {
  const fileInput = document.getElementById("cover_image");
  const textInput = document.getElementById("text");
  const dimEl = document.getElementById("dev-cover-dimensions");
  if (!fileInput || !textInput || !dimEl) {
    return;
  }

  const sizeEl = document.getElementById("dev-cover-size");
  const textSizeEl = document.getElementById("dev-text-size");
  const payloadEl = document.getElementById("dev-payload-size");
  const capacityEl = document.getElementById("dev-capacity-bits");
  const statusEl = document.getElementById("dev-capacity-status");

  let capacityBits = null;
  let payloadBits = null;

  function updateCapacityStatus() {
    if (capacityBits === null || payloadBits === null || !statusEl) {
      return;
    }
    const status = capacityBits >= payloadBits ? "Muat" : "Tidak Muat";
    statusEl.innerHTML = renderDevValue(status);
  }

  fileInput.addEventListener("change", function () {
    const file = fileInput.files && fileInput.files[0];
    if (!file) {
      return;
    }
    if (sizeEl) {
      sizeEl.innerHTML = renderDevValue(formatSizeLive(file.size));
    }

    const objectUrl = URL.createObjectURL(file);
    const img = new Image();
    img.onload = function () {
      dimEl.innerHTML = renderDevValue(
        `${formatIdInt(img.naturalWidth)} × ${formatIdInt(img.naturalHeight)} piksel`
      );
      capacityBits = img.naturalWidth * img.naturalHeight * 3;
      if (capacityEl) {
        // Kapasitas ditampilkan dalam satuan KB (B), sama seperti ukuran
        // berkas lain, bukan bit, supaya konsisten dengan sisi server
        // (lihat format_size(capacity_bits // 8) di embed_service.py).
        capacityEl.innerHTML = renderDevValue(formatSizeLive(Math.floor(capacityBits / 8)));
      }
      updateCapacityStatus();
      URL.revokeObjectURL(objectUrl);
    };
    img.src = objectUrl;
  });

  textInput.addEventListener("input", function () {
    const textBytes = new TextEncoder().encode(textInput.value).length;
    if (textSizeEl) {
      textSizeEl.innerHTML = renderDevValue(formatSizeLive(textBytes));
    }

    const payloadBytes = DEV_INFO_PAYLOAD_OVERHEAD_BYTES + textBytes;
    if (payloadEl) {
      payloadEl.innerHTML = renderDevValue(formatSizeLive(payloadBytes));
    }
    payloadBits = payloadBytes * 8;
    updateCapacityStatus();
  });
}

function initExtractDevInfoLive() {
  const fileInput = document.getElementById("stego_image");
  const dimEl = document.getElementById("dev-stego-dimensions");
  if (!fileInput || !dimEl) {
    return;
  }

  const sizeEl = document.getElementById("dev-stego-size");

  fileInput.addEventListener("change", function () {
    const file = fileInput.files && fileInput.files[0];
    if (!file) {
      return;
    }
    if (sizeEl) {
      sizeEl.innerHTML = renderDevValue(formatSizeLive(file.size));
    }

    const objectUrl = URL.createObjectURL(file);
    const img = new Image();
    img.onload = function () {
      dimEl.innerHTML = renderDevValue(
        `${formatIdInt(img.naturalWidth)} × ${formatIdInt(img.naturalHeight)} piksel`
      );
      URL.revokeObjectURL(objectUrl);
    };
    img.src = objectUrl;
  });
}
