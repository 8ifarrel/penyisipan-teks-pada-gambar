// JS vanilla pendukung tampilan: tombol salin, menu navigasi
// (hamburger) di mobile, dan nama file pada input unggah. Tidak ada
// logic yang berkomunikasi ke server di sini; form tetap submit secara
// normal (multipart/form-data).

document.addEventListener("DOMContentLoaded", function () {
  initCopyButtons();
  initNavToggle();
  initFileFields();
});

// --- Tombol "Salin" (kunci AES / teks hasil ekstraksi) --------------
//
// Tombol dengan atribut data-copy-target menyalin isi elemen yang
// ditunjuknya (input kunci AES atau textarea teks hasil ekstraksi),
// lalu label teksnya (.btn__label) diganti sementara sebagai feedback.

function initCopyButtons() {
  document.addEventListener("click", function (event) {
    const button = event.target.closest("[data-copy-target]");
    if (!button) {
      return;
    }

    const target = document.querySelector(
      button.getAttribute("data-copy-target")
    );
    if (!target) {
      return;
    }
    const text = "value" in target ? target.value : target.textContent;

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

    const fallbackCopy = function () {
      // Fallback bila Clipboard API tidak tersedia (mis. konteks
      // non-HTTPS).
      if (!target.select) {
        showFeedback(false);
        return;
      }
      target.select();
      try {
        document.execCommand("copy");
        showFeedback(true);
      } catch (err) {
        showFeedback(false);
      }
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

// --- Menu navigasi (hamburger di mobile) ----------------------------

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

// --- Nama file pada input unggah ------------------------------------
//
// Teks bawaan <input type="file"> mengikuti bahasa browser, jadi input
// aslinya disembunyikan dan nama file yang dipilih ditampilkan di sini
// dalam bahasa Indonesia.

function initFileFields() {
  document.querySelectorAll(".file-field").forEach(function (field) {
    const input = field.querySelector(".file-field__input");
    const nameEl = field.querySelector("[data-file-name]");
    if (!input || !nameEl) {
      return;
    }
    input.addEventListener("change", function () {
      const hasFile = Boolean(input.files && input.files.length);
      nameEl.textContent = hasFile
        ? input.files[0].name
        : "Tidak ada file dipilih";
    });
  });
}
