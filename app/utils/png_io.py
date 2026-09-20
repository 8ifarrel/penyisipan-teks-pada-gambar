# Encoder/decoder PNG manual (tanpa Pillow), khusus PNG RGB 24-bit tanpa
# interlace: parsing chunk, unfilter/filter scanline (5 tipe filter sesuai
# spesifikasi PNG), dan kompresi/dekompresi lewat zlib (DEFLATE).
#
# Level kompresi zlib tidak pernah tersimpan sebagai field di file PNG mana
# pun (murni pengaturan encoder saat menyimpan), jadi ditebak lewat
# pick_compress_level() dengan membandingkan ukuran hasil kompresi di tiap
# level ke ukuran IDAT citra sumber, supaya citra stego mengikuti
# karakteristik kompresi encoder sumbernya.

import struct
import zlib

import numpy as np

from app.utils.image_types import RgbImage

PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
BYTES_PER_PIXEL = 3  # RGB 24-bit (8 bit x 3 kanal)

# Key pada image.info tempat ukuran total chunk IDAT citra cover asli
# disimpan oleh remember_source_compression_profile(), dibaca save_png()
# lewat pick_compress_level() untuk menyesuaikan level kompresi.
SOURCE_IDAT_TOTAL_BYTES_KEY = "_source_idat_total_bytes"

DEFAULT_COMPRESS_LEVEL = 6  # level kompresi zlib bawaan


class InvalidPngError(Exception):
  """Dilempar jika bytes bukan PNG valid, atau memakai fitur PNG yang tidak didukung."""


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


def _chunk_bytes(ctype: bytes, data: bytes) -> bytes:
  """Membungkus data jadi satu chunk PNG utuh: panjang + tipe + data + CRC32."""
  return struct.pack(">I", len(data)) + ctype + data + struct.pack(">I", zlib.crc32(ctype + data))


def _paeth_predictor(a: int, b: int, c: int) -> int:
  """Predictor filter Paeth: pilih di antara a (kiri), b (atas), c (kiri-atas)."""
  p = a + b - c
  pa, pb, pc = abs(p - a), abs(p - b), abs(p - c)
  if pa <= pb and pa <= pc:
    return a
  if pb <= pc:
    return b
  return c


def _unfilter_scanlines(raw: bytes, width: int, height: int) -> np.ndarray:
  """
  Membalik filter scanline PNG (reconstruct), mengembalikan array piksel
  (height, width, 3). Setiap scanline diawali 1 byte tipe filter, diikuti
  width*3 byte data terfilter.

  Tipe filter None (0) dan Up (2) dihitung vektorisasi penuh (tidak
  bergantung pada piksel di baris yang sama). Tipe Sub (1), Average (3),
  dan Paeth (4) butuh nilai piksel kiri yang baru direkonstruksi, sehingga
  dihitung berurutan per kolom dalam baris tersebut.
  """
  stride = width * BYTES_PER_PIXEL
  recon = np.zeros((height, stride), dtype=np.uint8)
  pos = 0
  for y in range(height):
    filter_type = raw[pos]
    pos += 1
    row = np.frombuffer(raw, dtype=np.uint8, count=stride, offset=pos).astype(np.int16)
    pos += stride
    above = recon[y - 1].astype(np.int16) if y > 0 else np.zeros(stride, dtype=np.int16)

    if filter_type == 0:
      recon[y] = row.astype(np.uint8)
    elif filter_type == 2:
      recon[y] = ((row + above) % 256).astype(np.uint8)
    elif filter_type in (1, 3, 4):
      out = np.empty(stride, dtype=np.uint8)
      bpp = BYTES_PER_PIXEL
      for x in range(stride):
        left = int(out[x - bpp]) if x >= bpp else 0
        up = int(above[x])
        if filter_type == 1:
          out[x] = (row[x] + left) % 256
        elif filter_type == 3:
          out[x] = (row[x] + (left + up) // 2) % 256
        else:
          up_left = int(above[x - bpp]) if x >= bpp else 0
          out[x] = (row[x] + _paeth_predictor(left, up, up_left)) % 256
      recon[y] = out
    else:
      raise InvalidPngError(f"Tipe filter scanline tidak dikenal: {filter_type}.")

  return recon.reshape(height, width, BYTES_PER_PIXEL)


def _filter_scanlines(pixels: np.ndarray) -> bytes:
  """
  Menerapkan filter scanline PNG ke array piksel (height, width, 3), memilih
  tipe filter per baris secara adaptif dengan heuristik "minimum sum of
  absolute differences" (dipakai libpng): tipe filter yang membuat baris
  hasil filter paling mendekati nol dianggap paling ramah dikompresi zlib.

  Berbeda dengan unfilter, proses filter (encode) tidak punya dependensi
  berantai (hanya butuh nilai piksel ASLI di kiri/atas/kiri-atas, yang
  semuanya sudah diketahui di awal), sehingga bisa dihitung vektorisasi
  penuh untuk kelima tipe filter sekaligus.
  """
  height, _width, _channels = pixels.shape
  img = pixels.astype(np.int16)

  left = np.zeros_like(img)
  left[:, 1:, :] = img[:, :-1, :]
  above = np.zeros_like(img)
  above[1:, :, :] = img[:-1, :, :]
  upper_left = np.zeros_like(img)
  upper_left[1:, 1:, :] = img[:-1, :-1, :]

  p = left + above - upper_left
  pa, pb, pc = np.abs(p - left), np.abs(p - above), np.abs(p - upper_left)
  paeth_pred = np.where((pa <= pb) & (pa <= pc), left, np.where(pb <= pc, above, upper_left))

  candidates = {
    0: img,
    1: (img - left) % 256,
    2: (img - above) % 256,
    3: (img - (left + above) // 2) % 256,
    4: (img - paeth_pred) % 256,
  }

  def signed_abs_sum(arr: np.ndarray) -> np.ndarray:
    signed = np.where(arr >= 128, arr - 256, arr)
    return np.abs(signed).reshape(height, -1).sum(axis=1)

  scores = np.stack([signed_abs_sum(candidates[t]) for t in range(5)], axis=1)  # (height, 5)
  chosen = np.argmin(scores, axis=1)

  rows = []
  for y in range(height):
    ftype = int(chosen[y])
    rows.append(bytes([ftype]))
    rows.append(candidates[ftype][y].astype(np.uint8).tobytes())
  return b"".join(rows)


def decode_png(raw_bytes: bytes) -> RgbImage:
  """
  Mendekode bytes mentah PNG menjadi RgbImage. Hanya mendukung PNG RGB
  24-bit (bit depth 8, color type truecolor) tanpa interlace.

  Raises:
    InvalidPngError: jika bytes bukan PNG valid, atau memakai bit
      depth/color type/interlace yang tidak didukung.
  """
  if raw_bytes[:8] != PNG_SIGNATURE:
    raise InvalidPngError("Bukan berkas PNG (signature tidak cocok).")

  ihdr_data = None
  idat_parts = []
  for ctype, length, offset in _iter_chunks(raw_bytes):
    data = raw_bytes[offset + 8 : offset + 8 + length]
    if ctype == b"IHDR":
      ihdr_data = data
    elif ctype == b"IDAT":
      idat_parts.append(data)

  if ihdr_data is None or len(ihdr_data) != 13:
    raise InvalidPngError("Chunk IHDR tidak ditemukan atau tidak valid.")

  width, height, bit_depth, color_type, _compression, _filter_method, interlace_method = (
    struct.unpack(">IIBBBBB", ihdr_data)
  )
  if bit_depth != 8 or color_type != 2 or interlace_method != 0:
    raise InvalidPngError(
      "Hanya mendukung PNG RGB 24-bit (bit depth 8, truecolor, tanpa interlace)."
    )
  if not idat_parts:
    raise InvalidPngError("Chunk IDAT tidak ditemukan.")

  try:
    raw = zlib.decompress(b"".join(idat_parts))
  except zlib.error as exc:
    raise InvalidPngError(f"Gagal mendekompresi data IDAT: {exc}") from exc

  expected_len = height * (1 + width * BYTES_PER_PIXEL)
  if len(raw) != expected_len:
    raise InvalidPngError("Panjang data hasil dekompresi tidak sesuai dimensi citra.")

  pixels = _unfilter_scanlines(raw, width, height)
  return RgbImage(pixels)


def remember_source_compression_profile(image: RgbImage, raw_bytes: bytes) -> None:
  """
  Merekam ukuran total chunk IDAT citra asli ke
  image.info[SOURCE_IDAT_TOTAL_BYTES_KEY]. Dibaca pick_compress_level()
  untuk menyesuaikan level kompresi citra hasil dengan citra sumbernya.
  Tidak melakukan apa-apa jika raw_bytes bukan PNG valid.
  """
  idat_total_bytes = sum(length for ctype, length, _ in _iter_chunks(raw_bytes) if ctype == b"IDAT")
  if idat_total_bytes:
    image.info[SOURCE_IDAT_TOTAL_BYTES_KEY] = idat_total_bytes


def pick_compress_level(raw: bytes, target_idat_bytes) -> int:
  """
  Mencari level kompresi zlib (0-9) yang menghasilkan ukuran IDAT paling
  mendekati target_idat_bytes (ukuran IDAT citra cover asli), lewat binary
  search (ukuran hasil kompresi zlib monoton turun/tetap seiring level
  naik), alih-alih mencoba seluruh 10 level satu per satu.

  Args:
    raw: bytes hasil filter scanline (sebelum dikompresi), sama untuk
      semua level karena filter tidak bergantung pada level kompresi.
    target_idat_bytes: ukuran total IDAT citra sumber dalam byte, atau
      None jika tidak diketahui. Jika None, DEFAULT_COMPRESS_LEVEL
      dikembalikan langsung tanpa pencarian.

  Returns:
    Level kompresi 0-9 dengan ukuran IDAT paling mendekati target.
  """
  if target_idat_bytes is None:
    return DEFAULT_COMPRESS_LEVEL

  sizes = {}

  def size_at(level: int) -> int:
    if level not in sizes:
      sizes[level] = len(zlib.compress(raw, level))
    return sizes[level]

  lo, hi = 0, 9
  while lo < hi:
    mid = (lo + hi) // 2
    if size_at(mid) > target_idat_bytes:
      lo = mid + 1
    else:
      hi = mid

  candidates = [lo] if lo == 0 else [lo - 1, lo]
  return min(candidates, key=lambda level: abs(size_at(level) - target_idat_bytes))


def encode_png(image: RgbImage, compress_level: int) -> bytes:
  """Mengencode RgbImage menjadi bytes PNG utuh (signature + IHDR + IDAT + IEND)."""
  height, width, _ = image.pixels.shape
  raw = _filter_scanlines(image.pixels)
  compressed = zlib.compress(raw, compress_level)
  ihdr = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
  return (
    PNG_SIGNATURE
    + _chunk_bytes(b"IHDR", ihdr)
    + _chunk_bytes(b"IDAT", compressed)
    + _chunk_bytes(b"IEND", b"")
  )


def save_png(image: RgbImage, destination) -> None:
  """
  Menyimpan citra sebagai PNG dengan level kompresi yang disesuaikan
  dengan citra cover asli (lihat pick_compress_level()) jika
  image.info[SOURCE_IDAT_TOTAL_BYTES_KEY] tersedia (lihat
  remember_source_compression_profile()). Jika tidak, dipakai
  DEFAULT_COMPRESS_LEVEL.

  Args:
    destination: path (str/os.PathLike) atau objek mirip file yang
      punya method write() (mis. io.BytesIO).
  """
  raw = _filter_scanlines(image.pixels)
  target_idat_bytes = image.info.get(SOURCE_IDAT_TOTAL_BYTES_KEY)
  compress_level = pick_compress_level(raw, target_idat_bytes)

  height, width, _ = image.pixels.shape
  compressed = zlib.compress(raw, compress_level)
  ihdr = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
  data = (
    PNG_SIGNATURE
    + _chunk_bytes(b"IHDR", ihdr)
    + _chunk_bytes(b"IDAT", compressed)
    + _chunk_bytes(b"IEND", b"")
  )

  if hasattr(destination, "write"):
    destination.write(data)
  else:
    with open(destination, "wb") as f:
      f.write(data)
