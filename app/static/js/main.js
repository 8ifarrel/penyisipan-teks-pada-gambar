// JS vanilla pendukung tampilan: tombol salin, menu navigasi (hamburger)
// di mobile, dan feedback visual pada area unggah drag-and-drop. Tidak ada
// logic yang berkomunikasi ke server di sini. Form tetap submit secara
// normal (multipart/form-data) lewat elemen <input type="file"> asli.

document.addEventListener("DOMContentLoaded", function () {
  initCopyButtons();
  initNavToggle();
  initDropzones();
});

// --- Tombol "Salin" (kunci AES / teks hasil ekstraksi) ---------------------

function initCopyButtons() {
  document.addEventListener("click", function (event) {
    const button = event.target.closest("[data-copy-target]");
    if (!button) {
      return;
    }

    const target = document.querySelector(button.getAttribute("data-copy-target"));
    if (!target) {
      return;
    }

    const text = "value" in target ? target.value : target.textContent;
    // Label teks disimpan di elemen terpisah (.btn__label) supaya ikon
    // SVG di dalam tombol tidak ikut hilang saat teks diganti sementara.
    const labelEl = button.querySelector(".btn__label") || button;
    const originalLabel = labelEl.textContent;

    const showFeedback = function (success) {
      labelEl.textContent = success ? "Tersalin!" : "Gagal menyalin";
      button.classList.toggle("btn--success", success);
      setTimeout(function () {
        labelEl.textContent = originalLabel;
        button.classList.remove("btn--success");
      }, 1500);
    };

    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(text).then(
        function () {
          showFeedback(true);
        },
        function () {
          if (target.select) {
            target.select();
          }
          showFeedback(false);
        }
      );
    } else if (target.select) {
      // Fallback bila Clipboard API tidak tersedia (mis. konteks non-HTTPS).
      target.select();
      try {
        document.execCommand("copy");
        showFeedback(true);
      } catch (err) {
        showFeedback(false);
      }
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
