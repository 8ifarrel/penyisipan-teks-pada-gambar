# Routes/Blueprint Flask.
#
# Menangani seluruh endpoint sistem: halaman beranda, fitur penyisipan teks,
# dan fitur ekstraksi teks.
#
# --- Format input kunci AES (keputusan desain) -----------------------------
# Kunci AES-128 (16 byte) ditampilkan/diminta dalam bentuk HEX (32 karakter
# heksadesimal), BUKAN base64. Alasan:
#   - Hex hanya terdiri atas karakter [0-9a-f], sehingga tidak mengandung
#     simbol yang rawan salah salin/rusak saat copy-paste lewat berbagai
#     media (mis. '+', '/', '=' pada base64 yang kadang di-encode ulang
#     secara tidak sengaja oleh sistem lain, seperti pada URL atau editor).
#   - Panjangnya tetap dan mudah divalidasi (persis 32 karakter untuk 16 byte).
#   - `bytes.hex()` / `bytes.fromhex()` sudah tersedia langsung di Python
#     tanpa perlu import tambahan (berbeda dengan base64 yang perlu modul
#     `base64` terpisah), sehingga lebih sederhana untuk lapisan presentasi.
#
# --- Penyimpanan file temporer ----------------------------------------------
# Citra STEGO hasil penyisipan disimpan sebagai file PNG di folder temporer
# (`<instance_path>/tmp_stego/`) dengan nama acak (UUID4) agar bisa disajikan
# kembali lewat route pratinjau & unduh pada halaman hasil (butuh permintaan
# GET terpisah untuk <img> dan tombol unduh, sehingga tidak cukup hanya
# disimpan di memori selama satu request POST saja).
#
# Key AES TIDAK PERNAH disimpan ke file/session di server, hanya
# disisipkan langsung ke HTML halaman hasil sekali saat response dikirim
# (pengguna diharapkan menyalin & menyimpannya sendiri).
#
# Karena aplikasi ini tidak menjalankan scheduler/cron di latar belakang,
# file temporer dibersihkan secara "lazy": setiap kali route yang berpotensi
# membuat atau menyajikan file temporer dipanggil, file yang lebih tua dari
# TEMP_FILE_MAX_AGE_SECONDS dihapus terlebih dahulu. Ini cukup untuk
# skenario pemakaian skala kecil dan mencegah folder menumpuk tanpa batas.

import base64
import io
import os
import re
import time
import uuid

from flask import (
  Blueprint,
  abort,
  current_app,
  flash,
  render_template,
  request,
  send_file,
)
from PIL import Image, UnidentifiedImageError

from app.crypto.aes_gcm import (
  KEY_LEN_BYTES,
  AuthenticationError,
  decrypt_ciphertext,
  encrypt_text,
)
from app.metrics.quality import calculate_mse, calculate_psnr, categorize_quality
from app.stego.lsb import (
  CapacityError,
  ImageValidationError,
  calculate_capacity,
  embed_payload,
  extract_payload,
  validate_png_rgb24,
)
from app.stego.payload import build_payload, parse_payload

main_bp = Blueprint("main", __name__)

TEMP_DIR_NAME = "tmp_stego"
TEMP_FILE_MAX_AGE_SECONDS = 15 * 60  # 15 menit
STEGO_FILE_ID_PATTERN = re.compile(r"^[0-9a-f]{32}\.png$")


# --- Util internal (penyimpanan sementara & validasi upload) --------------


def _temp_dir() -> str:
  path = os.path.join(current_app.instance_path, TEMP_DIR_NAME)
  os.makedirs(path, exist_ok=True)
  return path


def _cleanup_old_temp_files() -> None:
  """
  Menghapus file citra stego sementara yang lebih tua dari
  TEMP_FILE_MAX_AGE_SECONDS, agar folder temporer tidak menumpuk seiring
  waktu. Lihat catatan desain di bagian atas modul ini.
  """
  directory = _temp_dir()
  now = time.time()
  for filename in os.listdir(directory):
    file_path = os.path.join(directory, filename)
    try:
      if now - os.path.getmtime(file_path) > TEMP_FILE_MAX_AGE_SECONDS:
        os.remove(file_path)
    except OSError:
      pass  # file mungkin sudah terhapus proses lain; abaikan


def _open_uploaded_image(file_storage):
  """
  Membuka file upload sebagai PIL.Image tanpa melempar exception ke
  caller. Mengembalikan None jika berkas tidak ada/kosong atau bukan
  citra yang bisa dibaca sama sekali (rusak/bukan format citra), sehingga
  route bisa menampilkan pesan error yang ramah alih-alih crash.
  """
  if file_storage is None or file_storage.filename == "":
    return None
  try:
    image = Image.open(file_storage.stream)
    image.load()  # paksa dekode penuh sekarang agar berkas rusak terdeteksi di sini
    return image
  except (UnidentifiedImageError, OSError):
    return None


def _save_stego_image(stego_image: Image.Image) -> str:
  """Menyimpan citra stego ke folder temporer, mengembalikan file_id-nya."""
  file_id = f"{uuid.uuid4().hex}.png"
  stego_image.save(os.path.join(_temp_dir(), file_id), format="PNG")
  return file_id


def _resolve_temp_file_path(file_id: str) -> str:
  """
  Memvalidasi format file_id (mencegah path traversal, mis. "../../etc")
  dan mengembalikan path absolut file tersebut jika ada.

  Aborts:
    404: jika file_id berformat tidak valid atau file tidak ditemukan.
  """
  if not STEGO_FILE_ID_PATTERN.fullmatch(file_id):
    abort(404)
  file_path = os.path.join(_temp_dir(), file_id)
  if not os.path.isfile(file_path):
    abort(404)
  return file_path


# --- Halaman ----------------------------------------------------------------


@main_bp.route("/")
def index():
  return render_template("index.html")


@main_bp.route("/tentang")
def tentang():
  return render_template("tentang.html")


@main_bp.route("/sisipkan", methods=["GET", "POST"])
def sisipkan():
  if request.method == "GET":
    return render_template("embed.html")

  _cleanup_old_temp_files()

  # 1. Validasi input dasar (jangan percaya form begitu saja)
  cover_file = request.files.get("cover_image")
  text = (request.form.get("text") or "").strip()

  if not text:
    flash("Teks tidak boleh kosong.", "error")
    return render_template("embed.html"), 400

  cover_image = _open_uploaded_image(cover_file)
  if cover_image is None:
    flash("Berkas citra tidak valid. Unggah citra PNG.", "error")
    return render_template("embed.html"), 400

  # 2. Validasi format PNG & model warna RGB 24-bit
  try:
    validate_png_rgb24(cover_image)
  except ImageValidationError as exc:
    flash(str(exc), "error")
    return render_template("embed.html"), 400

  # 3. Enkripsi teks dengan AES-GCM
  encrypted = encrypt_text(text)

  # 4. Bentuk payload
  payload = build_payload(encrypted["nonce"], encrypted["tag"], encrypted["ciphertext"])

  # 5. Hitung kapasitas & periksa kecukupan
  width, height = cover_image.size
  capacity_bits = calculate_capacity(width, height)
  payload_bits_len = len(payload) * 8

  if capacity_bits < payload_bits_len:
    flash(
      "Kapasitas citra tidak cukup untuk menyisipkan teks ini "
      f"(kapasitas citra {capacity_bits} bit, kebutuhan payload "
      f"{payload_bits_len} bit). Gunakan citra berukuran lebih besar "
      "atau perpendek teks.",
      "error",
    )
    return render_template("embed.html"), 400

  # 6. Sisipkan payload dengan LSB
  stego_image = embed_payload(cover_image, payload)

  # 7. Hitung MSE & PSNR, tentukan kategori kualitas
  mse = calculate_mse(cover_image, stego_image)
  psnr = calculate_psnr(mse)
  quality_category = categorize_quality(psnr)
  psnr_display = "Tak terhingga (citra identik)" if psnr == float("inf") else f"{psnr:.2f} dB"

  # 8. Simpan citra stego ke folder temporer untuk pratinjau & unduhan
  file_id = _save_stego_image(stego_image)

  # 9. Output: citra stego, kategori kualitas, key, PSNR
  return render_template(
    "embed_result.html",
    file_id=file_id,
    quality_category=quality_category,
    psnr_display=psnr_display,
    key_hex=encrypted["key"].hex(),
  )


@main_bp.route("/pratinjau/<file_id>")
def pratinjau_stego(file_id):
  """Menyajikan citra stego untuk ditampilkan (bukan diunduh) di halaman hasil."""
  _cleanup_old_temp_files()
  file_path = _resolve_temp_file_path(file_id)
  return send_file(file_path, mimetype="image/png")


@main_bp.route("/unduh/<file_id>")
def unduh_stego(file_id):
  """Menyajikan citra stego sebagai unduhan (Content-Disposition: attachment)."""
  _cleanup_old_temp_files()
  file_path = _resolve_temp_file_path(file_id)
  return send_file(
    file_path,
    mimetype="image/png",
    as_attachment=True,
    download_name="citra_stego.png",
  )


@main_bp.route("/ekstraksi", methods=["GET", "POST"])
def ekstraksi():
  if request.method == "GET":
    return render_template("extract.html")

  # 1. Validasi input dasar
  stego_file = request.files.get("stego_image")
  key_hex = (request.form.get("key") or "").strip()

  stego_image = _open_uploaded_image(stego_file)
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
      f"({KEY_LEN_BYTES * 2} karakter, mis. hasil salinan dari halaman "
      "hasil penyisipan).",
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
    flash(f"Ekstraksi gagal: {exc}", "error")
    return render_template("extract.html"), 400

  # 5. Pisahkan komponen payload
  try:
    parsed = parse_payload(payload)
  except ValueError as exc:
    flash(
      "Citra tidak memuat payload yang valid (kemungkinan bukan citra "
      f"stego hasil penyisipan sistem ini): {exc}",
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
    flash("Ekstraksi gagal: kunci AES salah atau data pada citra rusak.", "error")
    return render_template("extract.html"), 400

  # 7. Output: preview citra stego & teks hasil dekripsi.
  # Preview disisipkan sebagai data URI (tidak perlu disimpan ke disk --
  # berbeda dari alur /sisipkan, di sini citra sumbernya sendiri sudah
  # diunggah pengguna, tidak perlu disajikan ulang lewat route terpisah).
  buffer = io.BytesIO()
  stego_image.save(buffer, format="PNG")
  preview_data_uri = "data:image/png;base64," + base64.b64encode(buffer.getvalue()).decode(
    "ascii"
  )

  return render_template(
    "extract_result.html",
    plaintext=plaintext,
    preview_data_uri=preview_data_uri,
  )
