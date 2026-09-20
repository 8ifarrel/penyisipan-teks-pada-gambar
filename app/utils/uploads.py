# Pembacaan berkas upload dari form (mis. citra cover/stego yang diunggah
# lewat <input type="file">), terpisah dari logic route supaya routes.py
# bisa fokus pada alur request -> response saja.

import io
import os

from PIL import Image, UnidentifiedImageError

from app.utils.png_io import remember_source_compression_profile


def open_uploaded_image(file_storage):
  """
  Membuka file upload sebagai PIL.Image tanpa melempar exception ke
  caller. Mengembalikan None jika berkas tidak ada/kosong atau bukan
  citra yang bisa dibaca sama sekali (rusak/bukan format citra), sehingga
  route bisa menampilkan pesan error yang ramah alih-alih crash.

  Bytes mentahnya dibaca lebih dulu (bukan langsung diserahkan ke
  Image.open() dari stream) supaya ukuran kompresi PNG aslinya bisa
  direkam lewat remember_source_compression_profile(), dipakai save_png()
  nanti agar level kompresi citra stego mengikuti citra cover aslinya.
  """
  if file_storage is None or file_storage.filename == "":
    return None
  try:
    raw_bytes = file_storage.stream.read()
    file_storage.stream.seek(0)
    image = Image.open(io.BytesIO(raw_bytes))
    image.load()  # paksa dekode penuh sekarang agar berkas rusak terdeteksi di sini
    remember_source_compression_profile(image, raw_bytes)
    return image
  except (UnidentifiedImageError, OSError):
    return None


def file_size_bytes(file_storage) -> int:
  """
  Menghitung ukuran berkas upload dalam byte tanpa mengganggu posisi
  stream-nya, supaya Image.open() sesudah ini tetap membaca dari awal.
  """
  if file_storage is None:
    return 0
  stream = file_storage.stream
  pos = stream.tell()
  stream.seek(0, os.SEEK_END)
  size = stream.tell()
  stream.seek(pos)
  return size
