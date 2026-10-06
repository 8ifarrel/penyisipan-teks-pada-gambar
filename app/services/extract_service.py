# Logic lengkap fitur "Ekstraksi Teks": show_form() menampilkan form
# kosong (GET /ekstraksi), handle_submit() memproses submit-nya
# (POST /ekstraksi).

import base64
import io

from flask import flash, render_template, request

from app.crypto.aes_gcm import (
  KEY_LEN_BYTES,
  AuthenticationError,
  decrypt_ciphertext,
)
from app.stego.lsb import (
  CapacityError,
  ImageValidationError,
  extract_payload,
  validate_png_rgb24,
)
from app.stego.payload import parse_payload
from app.utils.png_io import save_png
from app.utils.uploads import open_uploaded_image


def show_form():
  """Menampilkan form Ekstraksi Teks kosong (GET /ekstraksi)."""
  return render_template("extract.html")


def handle_submit():
  """Memproses submit form Ekstraksi Teks (POST /ekstraksi)."""
  # 1. Validasi input dasar
  stego_file = request.files.get("stego_image")
  key_hex = (request.form.get("key") or "").strip()

  stego_image = open_uploaded_image(stego_file)
  if stego_image is None:
    flash("Berkas citra tidak valid. Unggah citra PNG.", "error")
    return render_template("extract.html"), 400

  # 2. Validasi format PNG & model warna RGB 24-bit
  try:
    validate_png_rgb24(stego_image)
  except ImageValidationError as exc:
    flash(str(exc), "error")
    return render_template("extract.html"), 400

  # 3. Validasi panjang key AES
  if not key_hex:
    flash("Kunci AES tidak boleh kosong.", "error")
    return render_template("extract.html"), 400

  try:
    key = bytes.fromhex(key_hex)
  except ValueError:
    flash(
      "Kunci AES tidak valid: harus berupa string heksadesimal "
      f"({KEY_LEN_BYTES * 2} karakter, mis. hasil salinan dari "
      "halaman hasil penyisipan).",
      "error",
    )
    return render_template("extract.html"), 400

  if len(key) != KEY_LEN_BYTES:
    flash(
      f"Panjang kunci AES harus {KEY_LEN_BYTES * 8} bit "
      f"({KEY_LEN_BYTES * 2} karakter heksadesimal), diterima "
      f"{len(key) * 8} bit.",
      "error",
    )
    return render_template("extract.html"), 400

  # 4. Ekstraksi payload dari citra stego
  try:
    payload = extract_payload(stego_image)
  except CapacityError as exc:
    flash(f"Proses ekstraksi gagal: {exc}", "error")
    return render_template("extract.html"), 400

  # 5. Pisahkan komponen payload
  try:
    parsed = parse_payload(payload)
  except ValueError as exc:
    flash(
      "Proses ekstraksi gagal karena citra tidak memuat payload yang "
      "valid (kemungkinan bukan citra stego hasil penyisipan sistem "
      f"ini): {exc}",
      "error",
    )
    return render_template("extract.html"), 400

  # 6. Dekripsi ciphertext dengan AES-GCM
  try:
    plaintext = decrypt_ciphertext(
      key=key,
      nonce=parsed["nonce"],
      tag=parsed["tag"],
      ciphertext=parsed["ciphertext"],
    )
  except AuthenticationError:
    flash(
      "Proses ekstraksi berhasil, tetapi proses dekripsi gagal karena "
      "kunci AES salah atau data pada citra rusak.",
      "error",
    )
    return render_template("extract.html"), 400

  # 7. Output: preview citra stego (data URI, tanpa disimpan ke disk) &
  # teks hasil dekripsi.
  buffer = io.BytesIO()
  save_png(stego_image, buffer)
  encoded = base64.b64encode(buffer.getvalue()).decode("ascii")
  preview_data_uri = "data:image/png;base64," + encoded

  return render_template(
    "extract_result.html",
    plaintext=plaintext,
    preview_data_uri=preview_data_uri,
  )
