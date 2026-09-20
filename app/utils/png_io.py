# Penyimpanan PNG yang menyesuaikan (adaptif) karakteristik encoder citra
# cover aslinya, bukan dipukul rata ke satu profil tertentu:
#   - Level kompresi zlib: tidak pernah tersimpan sebagai field di file PNG
#     mana pun (murni pengaturan encoder saat menyimpan), jadi ditebak lewat
#     pick_compress_level() dengan membandingkan ukuran hasil kompresi di
#     tiap level ke ukuran total IDAT citra sumber.
#   - Ukuran potongan (chunking) IDAT: encoder berbeda memecah data hasil
#     kompresi jadi beberapa chunk IDAT dengan ukuran buffer internal yang
#     berbeda-beda (mis. Pillow 65536 byte, libpng 8192 byte). Ukuran ini
#     dideteksi dari citra sumber lewat remember_source_compression_profile()
#     dan diterapkan ulang saat menyimpan lewat _idat_chunk_size(), supaya
#     jumlah/ukuran chunk IDAT citra hasil mengikuti citra sumbernya.

import contextlib
import io
import struct

from PIL import Image, ImageFile

PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"

# Key pada image.info tempat ukuran total chunk IDAT citra cover asli
# disimpan oleh remember_source_compression_profile(), dibaca save_png()
# lewat pick_compress_level() untuk menyesuaikan level kompresi.
SOURCE_IDAT_TOTAL_BYTES_KEY = "_source_idat_total_bytes"

# Key pada image.info tempat ukuran buffer IDAT citra cover asli disimpan,
# dibaca save_png() untuk menyesuaikan ukuran potongan chunk IDAT.
SOURCE_IDAT_CHUNK_SIZE_KEY = "_source_idat_chunk_size"

DEFAULT_COMPRESS_LEVEL = 6  # level kompresi zlib bawaan Pillow


def _iter_chunks(png_bytes: bytes):
  """
  Iterasi tiap chunk pada bytes mentah sebuah file PNG, menghasilkan
  (tipe chunk, panjang data chunk, offset awal chunk). Tidak menghasilkan
  apa-apa jika bytes bukan diawali signature PNG yang valid.
  """
  if png_bytes[:8] != PNG_SIGNATURE:
    return
  pos = 8
  while pos + 8 <= len(png_bytes):
    (length,) = struct.unpack(">I", png_bytes[pos : pos + 4])
    ctype = png_bytes[pos + 4 : pos + 8]
    yield ctype, length, pos
    pos += 8 + length + 4
    if ctype == b"IEND":
      return


def remember_source_compression_profile(image: Image.Image, raw_bytes: bytes) -> None:
  """
  Merekam profil kompresi PNG citra asli ke image.info, dibaca save_png()
  supaya citra hasil mengikuti karakteristik encoder sumbernya:
    - SOURCE_IDAT_TOTAL_BYTES_KEY: ukuran total seluruh chunk IDAT, dipakai
      pick_compress_level() untuk menyesuaikan level kompresi.
    - SOURCE_IDAT_CHUNK_SIZE_KEY: ukuran buffer chunk IDAT (byte terbesar
      di antara seluruh chunk IDAT), dipakai _idat_chunk_size() untuk
      menyesuaikan jumlah/ukuran potongan chunk IDAT. Hanya diisi jika
      citra sumber punya lebih dari satu chunk IDAT (ukuran buffer encoder
      sumber tidak bisa disimpulkan dari satu chunk saja).
  Tidak melakukan apa-apa jika raw_bytes bukan PNG valid.
  """
  idat_lengths = [length for ctype, length, _ in _iter_chunks(raw_bytes) if ctype == b"IDAT"]
  idat_total_bytes = sum(idat_lengths)
  if idat_total_bytes:
    image.info[SOURCE_IDAT_TOTAL_BYTES_KEY] = idat_total_bytes
  if len(idat_lengths) > 1:
    image.info[SOURCE_IDAT_CHUNK_SIZE_KEY] = max(idat_lengths)


@contextlib.contextmanager
def _idat_chunk_size(chunk_size):
  """
  Mengganti sementara ukuran buffer yang dipakai Pillow untuk memecah data
  IDAT terkompresi menjadi beberapa chunk saat menyimpan PNG (dikembalikan
  ke nilai semula setelah blok `with` selesai, termasuk jika terjadi error).
  """
  original = ImageFile.MAXBLOCK
  ImageFile.MAXBLOCK = chunk_size
  try:
    yield
  finally:
    ImageFile.MAXBLOCK = original


def _idat_bytes_at_level(image: Image.Image, compress_level: int) -> int:
  """Menghitung total ukuran byte seluruh chunk IDAT pada level kompresi tertentu."""
  buffer = io.BytesIO()
  image.save(buffer, format="PNG", compress_level=compress_level)
  return sum(length for ctype, length, _ in _iter_chunks(buffer.getvalue()) if ctype == b"IDAT")


def pick_compress_level(image: Image.Image, target_idat_bytes) -> int:
  """
  Mencari level kompresi zlib Pillow (0-9) yang menghasilkan ukuran total
  chunk IDAT paling mendekati target_idat_bytes (ukuran IDAT citra cover
  asli), supaya ukuran citra stego mengikuti karakteristik kompresi
  encoder sumbernya, bukan dipukul rata ke satu level tertentu.

  Args:
    target_idat_bytes: ukuran total IDAT citra sumber dalam byte, atau
      None jika tidak diketahui (mis. citra tidak berasal dari upload
      PNG asli). Jika None, DEFAULT_COMPRESS_LEVEL dikembalikan langsung
      tanpa pencarian.

  Returns:
    Level kompresi 0-9 dengan ukuran IDAT paling mendekati target.
  """
  if target_idat_bytes is None:
    return DEFAULT_COMPRESS_LEVEL

  sizes = {}

  def size_at(level: int) -> int:
    if level not in sizes:
      sizes[level] = _idat_bytes_at_level(image, level)
    return sizes[level]

  # Ukuran hasil kompresi zlib monoton turun (atau tetap) seiring level
  # naik, jadi level dengan ukuran paling mendekati target bisa dicari
  # lewat binary search (maks. ~4 percobaan simpan) alih-alih mencoba
  # seluruh 10 level satu per satu.
  lo, hi = 0, 9
  while lo < hi:
    mid = (lo + hi) // 2
    if size_at(mid) > target_idat_bytes:
      lo = mid + 1
    else:
      hi = mid

  # lo = level terkecil dengan ukuran <= target. Level tepat di bawahnya
  # (kompresi lebih longgar, ukuran lebih besar) bisa saja justru lebih
  # dekat ke target, jadi keduanya dibandingkan.
  candidates = [lo] if lo == 0 else [lo - 1, lo]
  return min(candidates, key=lambda level: abs(size_at(level) - target_idat_bytes))


def save_png(image: Image.Image, destination) -> None:
  """
  Menyimpan citra sebagai PNG dengan level kompresi dan ukuran potongan
  chunk IDAT yang disesuaikan dengan citra cover asli (lihat
  pick_compress_level() dan _idat_chunk_size()) jika profilnya tersedia
  di image.info (lihat remember_source_compression_profile()). Jika
  tidak, dipakai pengaturan bawaan Pillow.

  Args:
    destination: path (str/os.PathLike) atau objek mirip file yang
      punya method write() (mis. io.BytesIO).
  """
  target_idat_bytes = image.info.get(SOURCE_IDAT_TOTAL_BYTES_KEY)
  compress_level = pick_compress_level(image, target_idat_bytes)
  chunk_size = image.info.get(SOURCE_IDAT_CHUNK_SIZE_KEY)

  buffer = io.BytesIO()
  if chunk_size:
    with _idat_chunk_size(chunk_size):
      image.save(buffer, format="PNG", compress_level=compress_level)
  else:
    image.save(buffer, format="PNG", compress_level=compress_level)
  data = buffer.getvalue()

  if hasattr(destination, "write"):
    destination.write(data)
  else:
    with open(destination, "wb") as f:
      f.write(data)
