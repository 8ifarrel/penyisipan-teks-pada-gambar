# Logic lengkap fitur "Sisipkan Teks": show_form() menampilkan form
# kosong (GET /sisipkan), handle_submit() memproses submit-nya
# (POST /sisipkan).

from flask import flash, render_template, request

from app.crypto.aes_gcm import encrypt_text
from app.metrics.quality import (
  calculate_mse,
  calculate_psnr,
  categorize_quality,
)
from app.stego.lsb import (
  ImageValidationError,
  calculate_capacity,
  embed_payload,
  validate_png_rgb24,
)
from app.stego.payload import build_payload
from app.utils.formatting import format_id_decimal
from app.utils.temp_files import (
  cleanup_old_temp_files,
  save_stego_image,
)
from app.utils.uploads import open_uploaded_image


def show_form():
  """Menampilkan form Sisipkan Teks kosong (GET /sisipkan)."""
  return render_template("embed.html")


def handle_submit():
  """Memproses submit form Sisipkan Teks (POST /sisipkan)."""
  cleanup_old_temp_files()

  # 1. Validasi input dasar (jangan percaya form begitu saja)
  cover_file = request.files.get("cover_image")
  text = (request.form.get("text") or "").strip()

  if not text:
    flash("Teks tidak boleh kosong.", "error")
    return render_template("embed.html"), 400

  cover_image = open_uploaded_image(cover_file)
  if cover_image is None:
    flash("Berkas citra tidak valid. Unggah citra PNG.", "error")
    return render_template("embed.html"), 400

  width, height = cover_image.size

  # 2. Validasi format PNG & model warna RGB 24-bit
  try:
    validate_png_rgb24(cover_image)
  except ImageValidationError as exc:
    flash(str(exc), "error")
    return render_template("embed.html"), 400

  # 3. Enkripsi teks dengan AES-GCM
  encrypted = encrypt_text(text)

  # 4. Bentuk payload
  payload = build_payload(
    encrypted["nonce"], encrypted["tag"], encrypted["ciphertext"]
  )

  # 5. Hitung kapasitas & periksa kecukupan
  capacity_bits = calculate_capacity(width, height)
  payload_bits_len = len(payload) * 8

  if capacity_bits < payload_bits_len:
    flash(
      "Proses enkripsi berhasil, tetapi proses penyisipan gagal "
      "karena kapasitas citra tidak cukup (kapasitas citra "
      f"{capacity_bits} bit, kebutuhan payload {payload_bits_len} "
      "bit). Gunakan citra berukuran lebih besar atau perpendek "
      "teks.",
      "error",
    )
    return render_template("embed.html"), 400

  # 6. Sisipkan payload dengan LSB
  stego_image = embed_payload(cover_image, payload)
  # embed_payload() mengembalikan objek citra baru (.info kosong), jadi
  # profil kompresi cover asli diteruskan manual di sini supaya
  # save_png() nanti tetap bisa menyesuaikan citra stego dengan citra
  # cover aslinya (lihat app/utils/png_io.py).
  stego_image.info.update(cover_image.info)

  # 7. Hitung MSE & PSNR, tentukan kategori kualitas
  mse = calculate_mse(cover_image, stego_image)
  psnr = calculate_psnr(mse)
  quality_category = categorize_quality(psnr)
  psnr_display = (
    "Tak terhingga (citra identik)"
    if psnr == float("inf")
    else format_id_decimal(psnr, 2) + " dB"
  )

  # 8. Simpan citra stego ke folder temporer untuk pratinjau & unduhan
  file_id = save_stego_image(stego_image)

  # 9. Output: citra stego, kategori kualitas, key, PSNR
  return render_template(
    "embed_result.html",
    file_id=file_id,
    quality_category=quality_category,
    psnr_display=psnr_display,
    key_hex=encrypted["key"].hex(),
  )
