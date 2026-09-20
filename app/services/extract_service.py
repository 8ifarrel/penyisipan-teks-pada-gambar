# Logic lengkap fitur "Ekstraksi Teks": show_form() menampilkan form kosong
# (GET /ekstraksi), handle_submit() memproses submit-nya (POST /ekstraksi).

import base64
import io

from flask import current_app, flash, render_template, request

from app.crypto.aes_gcm import KEY_LEN_BYTES, AuthenticationError, decrypt_ciphertext
from app.stego.lsb import (
  CapacityError,
  ImageValidationError,
  extract_payload,
  validate_png_rgb24,
)
from app.stego.payload import parse_payload
from app.utils.dev_info import empty_dev_info
from app.utils.formatting import format_id_int, format_size
from app.utils.png_io import save_png
from app.utils.uploads import file_size_bytes, open_uploaded_image

# Daftar field "Info Developer" untuk halaman Ekstraksi.
_DEV_INFO_KEYS = [
  "stego_dimensions",
  "stego_size",
  "payload_size",
  "extraction_status",
  "decryption_status",
  "text_size",
]


def show_form():
  """Menampilkan form Ekstraksi Teks kosong (GET /ekstraksi)."""
  dev_info = empty_dev_info(_DEV_INFO_KEYS) if current_app.debug else None
  return render_template("extract.html", dev_info=dev_info)


def handle_submit():
  """Memproses submit form Ekstraksi Teks (POST /ekstraksi)."""
  # Info developer: rangkuman teknis tiap tahap proses. Dibentuk hanya saat
  # mode debug aktif, diisi progresif sehingga field yang belum tercapai
  # tetap "-".
  dev_info = None
  if current_app.debug:
    dev_info = empty_dev_info(_DEV_INFO_KEYS)

  # 1. Validasi input dasar
  stego_file = request.files.get("stego_image")
  key_hex = (request.form.get("key") or "").strip()
  stego_size_bytes = file_size_bytes(stego_file)
  if dev_info is not None:
    dev_info["stego_size"] = format_size(stego_size_bytes)

  stego_image = open_uploaded_image(stego_file)
  if stego_image is None:
    flash("Berkas citra tidak valid. Unggah citra PNG.", "error")
    return render_template("extract.html", dev_info=dev_info), 400

  if dev_info is not None:
    stego_width, stego_height = stego_image.size
    dev_info["stego_dimensions"] = (
      f"{format_id_int(stego_width)} × {format_id_int(stego_height)} piksel"
    )

  # 2. Validasi format PNG & model warna RGB 24-bit
  try:
    validate_png_rgb24(stego_image)
  except ImageValidationError as exc:
    flash(str(exc), "error")
    return render_template("extract.html", dev_info=dev_info), 400

  # 3. Validasi panjang key AES
  if not key_hex:
    flash("Kunci AES tidak boleh kosong.", "error")
    return render_template("extract.html", dev_info=dev_info), 400

  try:
    key = bytes.fromhex(key_hex)
  except ValueError:
    flash(
      "Kunci AES tidak valid: harus berupa string heksadesimal "
      f"({KEY_LEN_BYTES * 2} karakter, mis. hasil salinan dari halaman "
      "hasil penyisipan).",
      "error",
    )
    return render_template("extract.html", dev_info=dev_info), 400

  if len(key) != KEY_LEN_BYTES:
    flash(
      f"Panjang kunci AES harus {KEY_LEN_BYTES * 8} bit "
      f"({KEY_LEN_BYTES * 2} karakter heksadesimal), diterima "
      f"{len(key) * 8} bit.",
      "error",
    )
    return render_template("extract.html", dev_info=dev_info), 400

  # 4. Ekstraksi payload dari citra stego
  try:
    payload = extract_payload(stego_image)
  except CapacityError as exc:
    if dev_info is not None:
      dev_info["extraction_status"] = "Gagal"
    flash(f"Ekstraksi gagal: {exc}", "error")
    return render_template("extract.html", dev_info=dev_info), 400

  if dev_info is not None:
    dev_info["payload_size"] = format_size(len(payload))

  # 5. Pisahkan komponen payload
  try:
    parsed = parse_payload(payload)
  except ValueError as exc:
    if dev_info is not None:
      dev_info["extraction_status"] = "Gagal"
    flash(
      "Citra tidak memuat payload yang valid (kemungkinan bukan citra "
      f"stego hasil penyisipan sistem ini): {exc}",
      "error",
    )
    return render_template("extract.html", dev_info=dev_info), 400

  if dev_info is not None:
    dev_info["extraction_status"] = "Berhasil"

  # 6. Dekripsi ciphertext dengan AES-GCM
  try:
    plaintext = decrypt_ciphertext(
      key=key,
      nonce=parsed["nonce"],
      tag=parsed["tag"],
      ciphertext=parsed["ciphertext"],
    )
  except AuthenticationError:
    if dev_info is not None:
      dev_info["decryption_status"] = "Gagal"
    flash("Ekstraksi gagal: kunci AES salah atau data pada citra rusak.", "error")
    return render_template("extract.html", dev_info=dev_info), 400

  if dev_info is not None:
    dev_info["decryption_status"] = "Berhasil"
    dev_info["text_size"] = format_size(len(plaintext.encode("utf-8")))

  # 7. Output: preview citra stego (data URI, tanpa disimpan ke disk) &
  # teks hasil dekripsi.
  buffer = io.BytesIO()
  save_png(stego_image, buffer)
  preview_data_uri = "data:image/png;base64," + base64.b64encode(buffer.getvalue()).decode(
    "ascii"
  )

  return render_template(
    "extract_result.html",
    plaintext=plaintext,
    preview_data_uri=preview_data_uri,
    dev_info=dev_info,
  )
