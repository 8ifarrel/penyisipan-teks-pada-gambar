# Unit test untuk modul app.stego.lsb (penyisipan & ekstraksi payload dengan LSB).
#
# Mencakup:
#   - round-trip penyisipan lalu ekstraksi mengembalikan payload yang identik
#     (diuji end-to-end dengan payload sungguhan hasil AES-GCM + build_payload,
#     dan lewat encode/decode PNG asli agar meniru alur unduh/unggah nyata)
#   - exception muncul dengan benar saat kapasitas citra kurang
#   - exception muncul dengan benar saat array piksel citra bukan RGB 24-bit

import numpy as np
import pytest

from app.crypto.aes_gcm import encrypt_text
from app.stego.lsb import (
  CapacityError,
  ImageValidationError,
  calculate_capacity,
  embed_payload,
  extract_payload,
)
from app.stego.payload import build_payload, parse_payload
from app.utils.image_types import RgbImage
from app.utils.png_io import decode_png, encode_png


def _make_cover(width: int, height: int, seed: int = 0) -> RgbImage:
  rng = np.random.default_rng(seed)
  pixels = rng.integers(0, 256, size=(height, width, 3), dtype=np.uint8)
  return RgbImage(pixels)


def _roundtrip_through_png(image: RgbImage) -> RgbImage:
  """Encode lalu decode ulang lewat PNG, meniru alur unduh/unggah citra sungguhan."""
  return decode_png(encode_png(image, compress_level=6))


def _real_payload(plaintext: str = "pesan rahasia untuk pengujian LSB") -> bytes:
  encrypted = encrypt_text(plaintext)
  return build_payload(encrypted["nonce"], encrypted["tag"], encrypted["ciphertext"])


class TestCalculateCapacity:
  def test_capacity_formula(self):
    # Rumus kapasitas: C = W x H x c
    assert calculate_capacity(width=10, height=5, channels=3) == 150

  def test_default_channels_is_3(self):
    assert calculate_capacity(width=4, height=4) == 4 * 4 * 3


class TestEmbedExtractRoundTrip:
  def test_round_trip_returns_identical_payload(self):
    payload = _real_payload()
    cover = _make_cover(width=64, height=64, seed=1)

    stego = embed_payload(cover, payload)
    reopened_stego = _roundtrip_through_png(stego)

    extracted_payload = extract_payload(reopened_stego)

    assert extracted_payload == payload

  def test_round_trip_with_explicit_key_decrypts_correctly(self):
    from app.crypto.aes_gcm import decrypt_ciphertext

    plaintext = "Teks pengujian round-trip penuh: enkripsi-sisip-ekstrak-dekripsi."
    encrypted = encrypt_text(plaintext)
    payload = build_payload(encrypted["nonce"], encrypted["tag"], encrypted["ciphertext"])

    cover = _make_cover(width=128, height=128, seed=3)
    stego = embed_payload(cover, payload)
    reopened_stego = _roundtrip_through_png(stego)

    extracted_payload = extract_payload(reopened_stego)
    parsed = parse_payload(extracted_payload)

    decrypted = decrypt_ciphertext(
      key=encrypted["key"],
      nonce=parsed["nonce"],
      tag=parsed["tag"],
      ciphertext=parsed["ciphertext"],
    )

    assert decrypted == plaintext

  def test_embedding_only_modifies_lsb_of_used_channels(self):
    payload = _real_payload("x")  # payload pendek
    cover = _make_cover(width=32, height=32, seed=4)

    stego = embed_payload(cover, payload)

    cover_array = cover.pixels.reshape(-1)
    stego_array = stego.pixels.reshape(-1)

    # Setiap kanal warna paling banter berbeda 1 (hanya bit LSB yang berubah).
    diff = np.abs(cover_array.astype(np.int16) - stego_array.astype(np.int16))
    assert np.all(diff <= 1)

    # Kanal yang tidak dipakai payload harus identik persis dengan cover.
    payload_bits_len = len(payload) * 8
    assert np.array_equal(
      cover_array[payload_bits_len:], stego_array[payload_bits_len:]
    )


class TestCapacityError:
  def test_embed_raises_when_capacity_insufficient(self):
    payload = _real_payload("payload yang jauh lebih panjang dari kapasitas citra kecil")
    # Citra 2x2 RGB -> kapasitas 2*2*3 = 12 bit = 1.5 byte, jauh di bawah
    # kebutuhan payload (header saja sudah 4 byte = 32 bit).
    tiny_cover = _make_cover(width=2, height=2, seed=5)

    with pytest.raises(CapacityError, match="[Kk]apasitas"):
      embed_payload(tiny_cover, payload)

  def test_extract_raises_when_image_too_small_for_header(self):
    # Citra 1x1 RGB -> hanya 3 bit tersedia, tidak cukup untuk 32 bit header.
    tiny_image = _make_cover(width=1, height=1, seed=6)

    with pytest.raises(CapacityError, match="header"):
      extract_payload(tiny_image)

  def test_extract_raises_when_header_claims_more_than_available(self):
    # Sisipkan payload valid ke citra pas-pasan, lalu potong citra stego
    # (memangkas piksel) sehingga header menyatakan panjang payload yang
    # tidak lagi bisa dipenuhi oleh sisa data pada citra.
    payload = _real_payload("p")
    payload_bits_len = len(payload) * 8
    # Kapasitas hanya cukup untuk payload ini persis (tanpa piksel lebih).
    num_channels_needed = payload_bits_len
    side = int(np.ceil(np.sqrt(num_channels_needed / 3))) + 1
    cover = _make_cover(width=side, height=side, seed=7)

    stego = embed_payload(cover, payload)

    # Potong citra stego menjadi 1x1 piksel (hanya 3 kanal tersisa),
    # sehingga header (yang menyatakan payload jauh lebih panjang) tidak
    # lagi bisa dipenuhi.
    truncated_image = RgbImage(stego.pixels[:1, :1, :])
    truncated_stego = _roundtrip_through_png(truncated_image)

    with pytest.raises(CapacityError):
      extract_payload(truncated_stego)


class TestImageValidation:
  def test_embed_raises_when_pixels_wrong_dtype(self):
    payload = _real_payload("x")
    bad_image = RgbImage(np.zeros((8, 8, 3), dtype=np.float32))

    with pytest.raises(ImageValidationError, match="PNG"):
      embed_payload(bad_image, payload)

  def test_embed_raises_when_grayscale(self):
    payload = _real_payload("x")
    grayscale_image = RgbImage(np.zeros((8, 8, 1), dtype=np.uint8))

    with pytest.raises(ImageValidationError, match="RGB"):
      embed_payload(grayscale_image, payload)

  def test_embed_raises_when_rgba(self):
    payload = _real_payload("x")
    rgba_image = RgbImage(np.zeros((8, 8, 4), dtype=np.uint8))

    with pytest.raises(ImageValidationError, match="RGB"):
      embed_payload(rgba_image, payload)

  def test_extract_raises_when_pixels_wrong_dtype(self):
    bad_image = RgbImage(np.zeros((8, 8, 3), dtype=np.float32))

    with pytest.raises(ImageValidationError, match="PNG"):
      extract_payload(bad_image)

  def test_extract_raises_when_grayscale(self):
    grayscale_image = RgbImage(np.zeros((8, 8, 1), dtype=np.uint8))

    with pytest.raises(ImageValidationError, match="RGB"):
      extract_payload(grayscale_image)
