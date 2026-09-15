# Unit test untuk modul app.stego.lsb (penyisipan & ekstraksi payload dengan LSB).
#
# Mencakup:
#   - round-trip penyisipan lalu ekstraksi mengembalikan payload yang identik
#     (diuji end-to-end dengan payload sungguhan hasil AES-GCM + build_payload)
#   - exception muncul dengan benar saat kapasitas citra kurang
#   - exception muncul dengan benar saat citra bukan PNG/RGB 24-bit

import io

import numpy as np
import pytest
from PIL import Image

from app.crypto.aes_gcm import encrypt_text
from app.stego.lsb import (
  CapacityError,
  ImageValidationError,
  calculate_capacity,
  embed_payload,
  extract_payload,
)
from app.stego.payload import build_payload, parse_payload


def _make_png_image(width: int, height: int, mode: str = "RGB", seed: int = 0) -> Image.Image:
  """
  Membuat citra PNG RGB (atau mode lain) acak, lalu disimpan dan dibuka
  kembali sebagai PNG (melalui buffer BytesIO) agar atribut `.format`
  benar-benar bernilai "PNG", sama seperti citra yang diunggah pengguna
  lewat Image.open() pada file sungguhan.
  """
  rng = np.random.default_rng(seed)
  channels = len(mode) if mode != "P" else 1
  array = rng.integers(0, 256, size=(height, width, channels), dtype=np.uint8)
  if channels == 1:
    array = array.squeeze(-1)
  image = Image.fromarray(array, mode=mode)

  buffer = io.BytesIO()
  image.save(buffer, format="PNG")
  buffer.seek(0)
  return Image.open(buffer)


def _make_jpeg_image(width: int, height: int, seed: int = 0) -> Image.Image:
  rng = np.random.default_rng(seed)
  array = rng.integers(0, 256, size=(height, width, 3), dtype=np.uint8)
  image = Image.fromarray(array, mode="RGB")

  buffer = io.BytesIO()
  image.save(buffer, format="JPEG")
  buffer.seek(0)
  return Image.open(buffer)


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
    cover = _make_png_image(width=64, height=64, seed=1)

    stego = embed_payload(cover, payload)

    # Simpan & buka kembali sebagai PNG, meniru alur unduh/unggah citra
    # stego yang sesungguhnya.
    buffer = io.BytesIO()
    stego.save(buffer, format="PNG")
    buffer.seek(0)
    reopened_stego = Image.open(buffer)

    extracted_payload = extract_payload(reopened_stego)

    assert extracted_payload == payload

  def test_round_trip_with_explicit_key_decrypts_correctly(self):
    from app.crypto.aes_gcm import decrypt_ciphertext

    plaintext = "Teks pengujian round-trip penuh: enkripsi-sisip-ekstrak-dekripsi."
    encrypted = encrypt_text(plaintext)
    payload = build_payload(encrypted["nonce"], encrypted["tag"], encrypted["ciphertext"])

    cover = _make_png_image(width=128, height=128, seed=3)
    stego = embed_payload(cover, payload)

    buffer = io.BytesIO()
    stego.save(buffer, format="PNG")
    buffer.seek(0)
    reopened_stego = Image.open(buffer)

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
    cover = _make_png_image(width=32, height=32, seed=4)

    stego = embed_payload(cover, payload)

    cover_array = np.array(cover, dtype=np.uint8).reshape(-1)
    stego_array = np.array(stego, dtype=np.uint8).reshape(-1)

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
    tiny_cover = _make_png_image(width=2, height=2, seed=5)

    with pytest.raises(CapacityError, match="[Kk]apasitas"):
      embed_payload(tiny_cover, payload)

  def test_extract_raises_when_image_too_small_for_header(self):
    # Citra 1x1 RGB -> hanya 3 bit tersedia, tidak cukup untuk 32 bit header.
    tiny_image = _make_png_image(width=1, height=1, seed=6)

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
    cover = _make_png_image(width=side, height=side, seed=7)

    stego = embed_payload(cover, payload)
    stego_array = np.array(stego, dtype=np.uint8)

    # Potong citra stego menjadi 1x1 piksel (hanya 3 kanal tersisa),
    # sehingga header (yang menyatakan payload jauh lebih panjang) tidak
    # lagi bisa dipenuhi.
    truncated_array = stego_array[:1, :1, :]
    truncated_image = Image.fromarray(truncated_array, mode="RGB")

    buffer = io.BytesIO()
    truncated_image.save(buffer, format="PNG")
    buffer.seek(0)
    truncated_stego = Image.open(buffer)

    with pytest.raises(CapacityError):
      extract_payload(truncated_stego)


class TestImageValidation:
  def test_embed_raises_when_not_png(self):
    payload = _real_payload("x")
    jpeg_image = _make_jpeg_image(width=64, height=64, seed=8)

    with pytest.raises(ImageValidationError, match="PNG"):
      embed_payload(jpeg_image, payload)

  def test_embed_raises_when_not_rgb(self):
    payload = _real_payload("x")
    grayscale_image = _make_png_image(width=64, height=64, mode="L", seed=9)

    with pytest.raises(ImageValidationError, match="RGB"):
      embed_payload(grayscale_image, payload)

  def test_embed_raises_when_rgba(self):
    payload = _real_payload("x")
    rgba_image = _make_png_image(width=64, height=64, mode="RGBA", seed=10)

    with pytest.raises(ImageValidationError, match="RGB"):
      embed_payload(rgba_image, payload)

  def test_extract_raises_when_not_png(self):
    jpeg_image = _make_jpeg_image(width=64, height=64, seed=11)

    with pytest.raises(ImageValidationError, match="PNG"):
      extract_payload(jpeg_image)

  def test_extract_raises_when_not_rgb(self):
    grayscale_image = _make_png_image(width=64, height=64, mode="L", seed=12)

    with pytest.raises(ImageValidationError, match="RGB"):
      extract_payload(grayscale_image)
