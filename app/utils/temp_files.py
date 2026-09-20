# Penyimpanan sementara citra stego di disk.
#
# Citra STEGO hasil penyisipan disimpan sebagai file PNG di folder temporer
# (`<instance_path>/tmp_stego/`) dengan nama acak (UUID4) agar bisa disajikan
# kembali lewat route pratinjau & unduh pada halaman hasil (butuh permintaan
# GET terpisah untuk <img> dan tombol unduh, sehingga tidak cukup hanya
# disimpan di memori selama satu request POST saja).
#
# Karena aplikasi ini tidak menjalankan scheduler/cron di latar belakang,
# file temporer dibersihkan secara "lazy": setiap kali route yang berpotensi
# membuat atau menyajikan file temporer dipanggil, file yang lebih tua dari
# TEMP_FILE_MAX_AGE_SECONDS dihapus terlebih dahulu. Ini cukup untuk
# skenario pemakaian skala kecil dan mencegah folder menumpuk tanpa batas.

import os
import re
import time
import uuid

from flask import abort, current_app

from app.utils.image_types import RgbImage
from app.utils.png_io import save_png

TEMP_DIR_NAME = "tmp_stego"
TEMP_FILE_MAX_AGE_SECONDS = 15 * 60  # 15 menit
STEGO_FILE_ID_PATTERN = re.compile(r"^[0-9a-f]{32}\.png$")


def temp_dir() -> str:
  path = os.path.join(current_app.instance_path, TEMP_DIR_NAME)
  os.makedirs(path, exist_ok=True)
  return path


def cleanup_old_temp_files() -> None:
  """
  Menghapus file citra stego sementara yang lebih tua dari
  TEMP_FILE_MAX_AGE_SECONDS, agar folder temporer tidak menumpuk seiring
  waktu.
  """
  directory = temp_dir()
  now = time.time()
  for filename in os.listdir(directory):
    file_path = os.path.join(directory, filename)
    try:
      if now - os.path.getmtime(file_path) > TEMP_FILE_MAX_AGE_SECONDS:
        os.remove(file_path)
    except OSError:
      pass  # file mungkin sudah terhapus proses lain; abaikan


def save_stego_image(stego_image: RgbImage) -> str:
  """Menyimpan citra stego ke folder temporer, mengembalikan file_id-nya."""
  file_id = f"{uuid.uuid4().hex}.png"
  save_png(stego_image, os.path.join(temp_dir(), file_id))
  return file_id


def resolve_temp_file_path(file_id: str) -> str:
  """
  Memvalidasi format file_id (mencegah path traversal, mis. "../../etc")
  dan mengembalikan path absolut file tersebut jika ada.

  Aborts:
    404: jika file_id berformat tidak valid atau file tidak ditemukan.
  """
  if not STEGO_FILE_ID_PATTERN.fullmatch(file_id):
    abort(404)
  file_path = os.path.join(temp_dir(), file_id)
  if not os.path.isfile(file_path):
    abort(404)
  return file_path
