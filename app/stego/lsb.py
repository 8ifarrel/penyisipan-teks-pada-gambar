# Modul penyisipan & ekstraksi payload dengan metode LSB (1-bit paling rendah).
# 
# Aturan penyisipan:
#   - Disisipkan pada bit ke-0 tiap kanal warna (R, G, B) secara berurutan,
#     dimulai dari piksel pertama hingga piksel terakhir.
#   - Kapasitas maksimum: C = W x H x c  (c = 3 kanal warna). Karena k=1
#     (satu bit LSB per kanal), kapasitas dalam satuan "kanal" persis sama
#     dengan kapasitas dalam satuan bit.
#   - Penggantian bit LSB untuk k=1:
#         x'_i = x_i - (x_i mod 2) + m_i
#     yang secara bitwise setara dengan: x'_i = (x_i & ~1) | m_i
#
# Library yang digunakan: numpy untuk operasi bit secara vectorized (penting
# agar tetap efisien pada citra berukuran besar). Baca/tulis PNG ditangani
# encoder/decoder manual di app/utils/png_io.py, tidak dipakai langsung di
# sini agar modul ini tidak bergantung pada urusan encoding PNG.

import struct

import numpy as np

from app.stego.payload import HEADER_LEN_BYTES, HEADER_STRUCT_FORMAT
from app.utils.image_types import RgbImage

CHANNELS = 3  # RGB
BITS_PER_BYTE = 8
LSB_MASK = 0xFE  # ...11111110, untuk menghapus bit ke-0 (bit paling rendah)


class ImageValidationError(Exception):
  """Dilempar jika citra bukan berformat PNG dan/atau bukan RGB 24-bit."""


class CapacityError(Exception):
  """Dilempar jika kapasitas citra tidak cukup untuk menampung payload."""


def validate_png_rgb24(image: RgbImage) -> None:
  """
  Memvalidasi bahwa array piksel citra bermodel warna RGB 24-bit
  (3 kanal warna, 8 bit per kanal).

  Raises:
    ImageValidationError: jika salah satu syarat di atas tidak terpenuhi.
  """
  pixels = image.pixels
  if pixels.dtype != np.uint8 or pixels.ndim != 3 or pixels.shape[2] != CHANNELS:
    raise ImageValidationError(
      "Citra harus berformat PNG dan bermodel warna RGB 24-bit."
    )


def calculate_capacity(width: int, height: int, channels: int = CHANNELS) -> int:
  """
  Menghitung kapasitas penyisipan maksimum suatu citra (dalam bit).

  Rumus: C = W x H x c

  Args:
    width: lebar citra dalam piksel.
    height: tinggi citra dalam piksel.
    channels: jumlah kanal warna pada piksel (default 3, RGB).

  Returns:
    Kapasitas penyisipan maksimum dalam bit (karena k=1 bit LSB per kanal).
  """
  return width * height * channels


def embed_payload(cover_image: RgbImage, payload: bytes) -> RgbImage:
  """
  Menyisipkan payload ke dalam citra cover menggunakan metode LSB.

  Alur:
   1. Validasi format PNG & model warna RGB 24-bit
   2. Hitung kapasitas citra cover & panjang payload dalam bit
   3. Periksa kecukupan kapasitas
   4. Baca citra cover sebagai deret kanal warna berurutan (R, G, B, R, G, B, ...)
   5. Ubah payload menjadi deret bit (MSB-first per byte)
   6. Ganti bit ke-0 tiap kanal warna secara berurutan dengan tiap bit payload (k=1)
   7. Susun ulang array menjadi citra stego

  Args:
    cover_image: RgbImage berisi array piksel PNG RGB 24-bit.
    payload: bytes payload (hasil app.stego.payload.build_payload).

  Returns:
    RgbImage berisi citra stego.

  Raises:
    ImageValidationError: jika citra bukan PNG dan/atau bukan RGB 24-bit.
    CapacityError: jika kapasitas citra cover tidak cukup untuk payload.
  """
  validate_png_rgb24(cover_image)

  width, height = cover_image.size
  capacity_bits = calculate_capacity(width, height, CHANNELS)
  payload_bits_len = len(payload) * BITS_PER_BYTE

  if capacity_bits < payload_bits_len:
    raise CapacityError(
      f"Kapasitas citra tidak cukup untuk menyisipkan payload ini "
      f"(kapasitas {capacity_bits} bit, payload {payload_bits_len} bit)."
    )

  pixel_array = cover_image.pixels  # shape: (H, W, 3)
  flat_channels = pixel_array.reshape(-1).copy()  # deret kanal R,G,B,R,G,B,...

  # MSB-first per byte agar konsisten dengan urutan pada extract_payload().
  payload_bits = np.unpackbits(np.frombuffer(payload, dtype=np.uint8))

  n = payload_bits.shape[0]
  # k=1: x'_i = x_i - (x_i mod 2) + m_i  <=>  (x_i & ~1) | m_i
  flat_channels[:n] = (flat_channels[:n] & LSB_MASK) | payload_bits

  stego_array = flat_channels.reshape(pixel_array.shape)
  return RgbImage(stego_array)


def extract_payload(stego_image: RgbImage) -> bytes:
  """
  Mengekstraksi payload dari citra stego menggunakan metode LSB.

  Alur:
   1. Validasi format PNG & model warna RGB 24-bit
   2. Baca citra stego sebagai deret kanal warna berurutan
   3. Ekstraksi 32 bit LSB pertama (4 byte) -> rekonstruksi header (panjang payload)
   4. Ekstraksi bit LSB sejumlah (panjang_payload_total x 8) bit, termasuk
    32 bit header yang sudah diambil di awal
   5. Rekonstruksi seluruh bit menjadi bytes payload lengkap

  Args:
    stego_image: RgbImage berisi array piksel PNG RGB 24-bit.

  Returns:
    bytes payload lengkap (header + nonce + tag + ciphertext).

  Raises:
    ImageValidationError: jika citra bukan PNG dan/atau bukan RGB 24-bit.
    CapacityError: jika citra terlalu kecil untuk memuat header atau
      payload sepanjang yang dinyatakan pada header.
  """
  validate_png_rgb24(stego_image)

  pixel_array = stego_image.pixels
  flat_channels = pixel_array.reshape(-1)

  header_bits_len = HEADER_LEN_BYTES * BITS_PER_BYTE  # 32 bit
  if flat_channels.shape[0] < header_bits_len:
    raise CapacityError("Citra terlalu kecil untuk memuat header payload.")

  header_bits = (flat_channels[:header_bits_len] & 1).astype(np.uint8)
  header_bytes = np.packbits(header_bits).tobytes()
  (payload_length,) = struct.unpack(HEADER_STRUCT_FORMAT, header_bytes)

  payload_bits_len = payload_length * BITS_PER_BYTE
  if flat_channels.shape[0] < payload_bits_len:
    raise CapacityError(
      "Citra tidak memuat cukup data untuk payload sepanjang yang "
      "dinyatakan pada header (kemungkinan citra stego rusak atau "
      "bukan hasil penyisipan yang valid)."
    )

  payload_bits = (flat_channels[:payload_bits_len] & 1).astype(np.uint8)
  payload_bytes = np.packbits(payload_bits).tobytes()

  return payload_bytes
