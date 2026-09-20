# Penyimpanan PNG yang menyesuaikan gaya penulisan citra stego dengan
# karakteristik encoder citra cover aslinya, apa pun encoder itu (bukan
# dipukul rata ke satu gaya tertentu): level kompresi, ukuran chunk IDAT,
# urutan chunk ancillary, dan chunk mana saja yang ada/tidak ada, semuanya
# dideteksi dari citra sumber lewat remember_source_png_profile().

import contextlib
import io
import struct
from datetime import datetime, timezone

from PIL import Image, ImageFile
from PIL.PngImagePlugin import PngInfo

# Key pada image.info yang bukan chunk teks PNG, ditangani png_save_kwargs()
# lewat argumen khusus (icc_profile/dpi/exif) alih-alih dibungkus sebagai
# chunk teks lewat PngInfo.
PNG_NON_TEXT_INFO_KEYS = frozenset(
  {
    "icc_profile",
    "dpi",
    "exif",
    "gamma",
    "transparency",
    "aspect",
    "chromaticity",
    "srgb",
    "_source_chunk_order",
    "_source_idat_chunk_size",
    "_source_idat_total_bytes",
    "_source_has_time",
  }
)

PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"

# Key pada image.info tempat profil encoder citra cover asli disimpan oleh
# remember_source_png_profile(), dibaca save_png() untuk menyesuaikan gaya
# penulisan citra stego.
SOURCE_CHUNK_ORDER_KEY = "_source_chunk_order"
SOURCE_IDAT_CHUNK_SIZE_KEY = "_source_idat_chunk_size"
SOURCE_IDAT_TOTAL_BYTES_KEY = "_source_idat_total_bytes"
SOURCE_HAS_TIME_KEY = "_source_has_time"

DEFAULT_MAXBLOCK = ImageFile.MAXBLOCK  # ukuran buffer IDAT bawaan Pillow
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


def parse_chunk_order(png_bytes: bytes) -> list:
  """
  Membaca urutan tipe chunk (IHDR, eXIf, iCCP, pHYs, tIME, tEXt, IDAT, dst.)
  dari bytes mentah sebuah file PNG.

  Returns:
    List berisi tipe chunk (bytes 4 karakter) sesuai urutan pada file.
    List kosong jika bytes bukan PNG valid.
  """
  return [ctype for ctype, _, _ in _iter_chunks(png_bytes)]


def remember_source_png_profile(image: Image.Image, raw_bytes: bytes) -> None:
  """
  Merekam profil encoder PNG citra asli ke image.info: urutan chunk,
  ukuran chunk IDAT yang dipakai, dan ada/tidaknya chunk tIME. Ikut
  terbawa ke citra stego lewat stego_image.info.update(cover_image.info)
  di embed_payload(), dan dibaca save_png() supaya gaya penulisan PNG
  citra stego mengikuti karakteristik encoder sumbernya. Tidak melakukan
  apa-apa jika raw_bytes bukan PNG valid.
  """
  order = []
  idat_lengths = []
  for ctype, length, _ in _iter_chunks(raw_bytes):
    order.append(ctype)
    if ctype == b"IDAT":
      idat_lengths.append(length)

  if not order:
    return

  image.info[SOURCE_CHUNK_ORDER_KEY] = order
  image.info[SOURCE_HAS_TIME_KEY] = b"tIME" in order
  if idat_lengths:
    # Chunk IDAT terakhir umumnya lebih pendek (sisa data), jadi ukuran
    # buffer yang sebenarnya dipakai encoder adalah nilai terbesarnya.
    image.info[SOURCE_IDAT_CHUNK_SIZE_KEY] = max(idat_lengths)
    image.info[SOURCE_IDAT_TOTAL_BYTES_KEY] = sum(idat_lengths)


def reorder_ancillary_chunks(png_bytes: bytes, reference_order: list) -> bytes:
  """
  Menyusun ulang urutan chunk ancillary (semua chunk di antara IHDR dan
  IDAT pertama, mis. iCCP/eXIf/pHYs/tEXt/tIME) pada bytes PNG agar sama
  dengan reference_order. IHDR tetap chunk pertama, IDAT..IEND tetap di
  posisi belakang tanpa disentuh. Chunk yang tipenya tidak ada di
  reference_order ditaruh setelah seluruh chunk yang dikenali, urutan
  relatifnya sendiri tidak berubah.

  Args:
    png_bytes: bytes PNG lengkap.
    reference_order: urutan tipe chunk acuan (lihat parse_chunk_order()).

  Returns:
    bytes PNG dengan urutan chunk ancillary baru. Dikembalikan tanpa
    perubahan jika strukturnya tidak sesuai dugaan (tidak diawali IHDR
    atau tidak ada IDAT).
  """
  chunks = [
    (ctype, png_bytes[pos : pos + 8 + length + 4])
    for ctype, length, pos in _iter_chunks(png_bytes)
  ]

  idat_index = next((i for i, (ctype, _) in enumerate(chunks) if ctype == b"IDAT"), None)
  if idat_index is None or not chunks or chunks[0][0] != b"IHDR":
    return png_bytes  # struktur tak terduga, jangan diotak-atik sama sekali

  ihdr = chunks[0]
  ancillary = chunks[1:idat_index]
  tail = chunks[idat_index:]  # IDAT (bisa berkali-kali) sampai IEND, urutan asli dipertahankan

  def sort_key(item):
    ctype, _ = item
    try:
      return (0, reference_order.index(ctype))
    except ValueError:
      return (1, 0)  # tipe baru yang tidak ada di cover asli, ditaruh di akhir

  ancillary.sort(key=sort_key)

  reordered = [ihdr, *ancillary, *tail]
  return PNG_SIGNATURE + b"".join(raw for _, raw in reordered)


def png_save_kwargs(image: Image.Image, compress_level: int, include_time: bool) -> dict:
  """
  Membentuk kwargs untuk Image.save() dari metadata pada image.info.
  Pillow hanya membaca icc_profile secara otomatis dari image.info saat
  menyimpan PNG; dpi, exif, dan chunk teks custom wajib diteruskan
  eksplisit lewat argumen, jika tidak akan hilang meski sudah ada di
  image.info.

  Args:
    compress_level: level kompresi zlib (0-9) yang dipakai.
    include_time: jika True, tambahkan chunk tIME berisi waktu sekarang.
  """
  kwargs = {"compress_level": compress_level}
  if "icc_profile" in image.info:
    kwargs["icc_profile"] = image.info["icc_profile"]
  if "dpi" in image.info:
    kwargs["dpi"] = image.info["dpi"]
  if "exif" in image.info:
    kwargs["exif"] = image.info["exif"]

  pnginfo = PngInfo()
  for key, value in image.info.items():
    if key in PNG_NON_TEXT_INFO_KEYS or not isinstance(value, str):
      continue
    pnginfo.add_text(key, value)

  if include_time:
    now = datetime.now(timezone.utc)
    pnginfo.add(
      b"tIME",
      struct.pack(">HBBBBB", now.year, now.month, now.day, now.hour, now.minute, now.second),
    )
  kwargs["pnginfo"] = pnginfo

  return kwargs


@contextlib.contextmanager
def idat_chunk_size(max_block: int):
  """
  Mengatur ukuran buffer IDAT PNG yang dipakai Pillow saat menyimpan
  (lewat ImageFile.MAXBLOCK), alih-alih memakai nilai bawaannya.

  ImageFile.MAXBLOCK adalah pengaturan global di Pillow (bukan per-file),
  jadi dikembalikan ke nilai semula setelah dipakai lewat context manager
  ini agar tidak memengaruhi proses simpan citra lain.
  """
  original_max_block = ImageFile.MAXBLOCK
  ImageFile.MAXBLOCK = max_block
  try:
    yield
  finally:
    ImageFile.MAXBLOCK = original_max_block


def _idat_bytes_at_level(image: Image.Image, compress_level: int, max_block: int) -> int:
  """Menghitung total ukuran byte seluruh chunk IDAT pada level kompresi tertentu."""
  buffer = io.BytesIO()
  with idat_chunk_size(max_block):
    image.save(buffer, format="PNG", compress_level=compress_level)
  return sum(length for ctype, length, _ in _iter_chunks(buffer.getvalue()) if ctype == b"IDAT")


def pick_compress_level(image: Image.Image, target_idat_bytes, max_block: int) -> int:
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
    max_block: ukuran buffer IDAT yang akan dipakai saat menyimpan
      (memengaruhi jumlah chunk, bukan ukuran datanya, tapi tetap
      dipakai konsisten di tiap percobaan level).

  Returns:
    Level kompresi 0-9 dengan ukuran IDAT paling mendekati target.
  """
  if target_idat_bytes is None:
    return DEFAULT_COMPRESS_LEVEL

  sizes = {}

  def size_at(level: int) -> int:
    if level not in sizes:
      sizes[level] = _idat_bytes_at_level(image, level, max_block)
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
  Menyimpan citra sebagai PNG. Jika image.info menyimpan profil encoder
  citra cover asli (lihat remember_source_png_profile()), gaya penulisan
  citra hasil disesuaikan mengikuti profil tersebut: level kompresi
  (lihat pick_compress_level()), ukuran chunk IDAT, ada/tidaknya chunk
  tIME, dan urutan chunk ancillary (lihat reorder_ancillary_chunks()).
  Jika tidak ada profil (mis. citra bukan berasal dari upload PNG asli),
  dipakai pengaturan bawaan Pillow.

  Args:
    destination: path (str/os.PathLike) atau objek mirip file yang
      punya method write() (mis. io.BytesIO).
  """
  reference_order = image.info.get(SOURCE_CHUNK_ORDER_KEY)
  max_block = image.info.get(SOURCE_IDAT_CHUNK_SIZE_KEY) or DEFAULT_MAXBLOCK
  target_idat_bytes = image.info.get(SOURCE_IDAT_TOTAL_BYTES_KEY)
  include_time = bool(image.info.get(SOURCE_HAS_TIME_KEY))

  compress_level = pick_compress_level(image, target_idat_bytes, max_block)

  buffer = io.BytesIO()
  with idat_chunk_size(max_block):
    image.save(buffer, format="PNG", **png_save_kwargs(image, compress_level, include_time))
  data = buffer.getvalue()

  if reference_order:
    data = reorder_ancillary_chunks(data, reference_order)

  if hasattr(destination, "write"):
    destination.write(data)
  else:
    with open(destination, "wb") as f:
      f.write(data)
