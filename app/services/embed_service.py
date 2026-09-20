# Logic lengkap fitur "Sisipkan Teks": show_form() menampilkan form kosong
# (GET /sisipkan), handle_submit() memproses submit-nya (POST /sisipkan).

import os

from flask import current_app, flash, render_template, request

from app.crypto.aes_gcm import encrypt_text
from app.metrics.quality import calculate_mse, calculate_psnr, categorize_quality
from app.stego.lsb import (
  ImageValidationError,
  calculate_capacity,
  embed_payload,
  validate_png_rgb24,
)
from app.stego.payload import build_payload
from app.utils.dev_info import empty_dev_info
from app.utils.formatting import format_id_decimal, format_id_int, format_size
from app.utils.temp_files import cleanup_old_temp_files, save_stego_image, temp_dir
from app.utils.uploads import file_size_bytes, open_uploaded_image

# Daftar field "Info Developer" untuk halaman Sisipkan. Diisi progresif di
# handle_submit(); field yang belum sempat dihitung tetap "-".
_DEV_INFO_KEYS = [
  "cover_dimensions",
  "cover_size",
  "text_size",
  "payload_size",
  "capacity_bits",
  "capacity_status",
  "encryption_status",
  "embed_status",
  "stego_size",
  "psnr",
  "quality_category",
]


def show_form():
  """Menampilkan form Sisipkan Teks kosong (GET /sisipkan)."""
  # Panel Info Developer sudah tampil sejak kunjungan awal (seluruh field
  # "-"), diperbarui langsung di sisi klien lewat initDevInfoLive() di
  # main.js begitu pengguna memilih foto/mengetik teks.
  dev_info = empty_dev_info(_DEV_INFO_KEYS) if current_app.debug else None
  return render_template("embed.html", dev_info=dev_info)


def handle_submit():
  """Memproses submit form Sisipkan Teks (POST /sisipkan)."""
  cleanup_old_temp_files()

  # Info developer: rangkuman teknis tiap tahap proses (dimensi/ukuran
  # citra, ukuran payload, status tiap tahap, PSNR, kategori kualitas).
  # Dibentuk hanya saat mode debug aktif, diisi progresif seiring proses
  # berjalan sehingga field yang belum tercapai tetap "-".
  dev_info = None
  if current_app.debug:
    dev_info = empty_dev_info(_DEV_INFO_KEYS)

  # 1. Validasi input dasar (jangan percaya form begitu saja)
  cover_file = request.files.get("cover_image")
  text = (request.form.get("text") or "").strip()
  cover_size_bytes = file_size_bytes(cover_file)
  if dev_info is not None:
    dev_info["cover_size"] = format_size(cover_size_bytes)
    dev_info["text_size"] = format_size(len(text.encode("utf-8")))

  if not text:
    flash("Teks tidak boleh kosong.", "error")
    return render_template("embed.html", dev_info=dev_info), 400

  cover_image = open_uploaded_image(cover_file)
  if cover_image is None:
    flash("Berkas citra tidak valid. Unggah citra PNG.", "error")
    return render_template("embed.html", dev_info=dev_info), 400

  width, height = cover_image.size
  if dev_info is not None:
    dev_info["cover_dimensions"] = f"{format_id_int(width)} × {format_id_int(height)} piksel"

  # 2. Validasi format PNG & model warna RGB 24-bit
  try:
    validate_png_rgb24(cover_image)
  except ImageValidationError as exc:
    flash(str(exc), "error")
    return render_template("embed.html", dev_info=dev_info), 400

  # 3. Enkripsi teks dengan AES-GCM
  encrypted = encrypt_text(text)
  if dev_info is not None:
    dev_info["encryption_status"] = "Berhasil"

  # 4. Bentuk payload
  payload = build_payload(encrypted["nonce"], encrypted["tag"], encrypted["ciphertext"])
  if dev_info is not None:
    dev_info["payload_size"] = format_size(len(payload))

  # 5. Hitung kapasitas & periksa kecukupan
  capacity_bits = calculate_capacity(width, height)
  payload_bits_len = len(payload) * 8
  if dev_info is not None:
    # Ditampilkan dalam satuan KB (B), sama seperti field ukuran berkas lain.
    dev_info["capacity_bits"] = format_size(capacity_bits // 8)

  if capacity_bits < payload_bits_len:
    if dev_info is not None:
      dev_info["capacity_status"] = "Tidak Muat"
      dev_info["embed_status"] = "Gagal"
    flash(
      "Kapasitas citra tidak cukup untuk menyisipkan teks ini "
      f"(kapasitas citra {capacity_bits} bit, kebutuhan payload "
      f"{payload_bits_len} bit). Gunakan citra berukuran lebih besar "
      "atau perpendek teks.",
      "error",
    )
    return render_template("embed.html", dev_info=dev_info), 400

  if dev_info is not None:
    dev_info["capacity_status"] = "Muat"

  # 6. Sisipkan payload dengan LSB
  stego_image = embed_payload(cover_image, payload)
  if dev_info is not None:
    dev_info["embed_status"] = "Berhasil"

  # 7. Hitung MSE & PSNR, tentukan kategori kualitas
  mse = calculate_mse(cover_image, stego_image)
  psnr = calculate_psnr(mse)
  quality_category = categorize_quality(psnr)
  psnr_display = (
    "Tak terhingga (citra identik)"
    if psnr == float("inf")
    else format_id_decimal(psnr, 2) + " dB"
  )
  if dev_info is not None:
    dev_info["psnr"] = psnr_display
    dev_info["quality_category"] = quality_category

  # 8. Simpan citra stego ke folder temporer untuk pratinjau & unduhan
  file_id = save_stego_image(stego_image)
  if dev_info is not None:
    stego_size_bytes = os.path.getsize(os.path.join(temp_dir(), file_id))
    dev_info["stego_size"] = format_size(stego_size_bytes)

  # 9. Output: citra stego, kategori kualitas, key, PSNR
  return render_template(
    "embed_result.html",
    file_id=file_id,
    quality_category=quality_category,
    psnr_display=psnr_display,
    key_hex=encrypted["key"].hex(),
    dev_info=dev_info,
  )
