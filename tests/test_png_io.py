# Unit test untuk modul app.utils.png_io (encoder/decoder PNG manual).
#
# Mencakup:
#   - round-trip encode -> decode mengembalikan array piksel yang identik,
#     di berbagai level kompresi dan bentuk citra (acak, solid, 1x1)
#   - decode_png menolak bytes yang bukan PNG valid/tidak didukung
#   - pick_compress_level (lewat save_png) memilih level yang menghasilkan
#     ukuran IDAT identik dengan citra acuan

import numpy as np
import pytest

from app.utils.image_types import RgbImage
from app.utils.png_io import InvalidPngError, decode_png, encode_png, remember_source_compression_profile, save_png


def _random_image(width: int, height: int, seed: int = 0) -> RgbImage:
  rng = np.random.default_rng(seed)
  pixels = rng.integers(0, 256, size=(height, width, 3), dtype=np.uint8)
  return RgbImage(pixels)


class TestRoundTrip:
  def test_encode_then_decode_returns_identical_pixels(self):
    image = _random_image(37, 23, seed=1)
    decoded = decode_png(encode_png(image, compress_level=6))
    assert np.array_equal(decoded.pixels, image.pixels)

  def test_round_trip_at_every_compress_level(self):
    image = _random_image(16, 16, seed=2)
    for level in range(10):
      decoded = decode_png(encode_png(image, compress_level=level))
      assert np.array_equal(decoded.pixels, image.pixels)

  def test_round_trip_single_pixel(self):
    image = _random_image(1, 1, seed=3)
    decoded = decode_png(encode_png(image, compress_level=6))
    assert np.array_equal(decoded.pixels, image.pixels)

  def test_round_trip_solid_color_image(self):
    # Citra warna solid: baris pertama & baris berikutnya identik, menguji
    # jalur filter Up/None yang divektorisasi penuh (tanpa loop per kolom).
    image = RgbImage(np.full((20, 20, 3), 128, dtype=np.uint8))
    decoded = decode_png(encode_png(image, compress_level=6))
    assert np.array_equal(decoded.pixels, image.pixels)

  def test_round_trip_gradient_image(self):
    # Citra gradien: nilai piksel berubah teratur antar kolom/baris,
    # menguji jalur filter Sub/Average/Paeth (butuh loop per kolom saat decode).
    x = np.arange(30, dtype=np.uint8)
    y = np.arange(25, dtype=np.uint8)
    pixels = np.stack(
      [np.tile(x, (25, 1)), np.tile(y[:, None], (1, 30)), np.full((25, 30), 200, dtype=np.uint8)],
      axis=-1,
    ).astype(np.uint8)
    image = RgbImage(pixels)
    decoded = decode_png(encode_png(image, compress_level=6))
    assert np.array_equal(decoded.pixels, image.pixels)


class TestInvalidPng:
  def test_decode_raises_on_bad_signature(self):
    with pytest.raises(InvalidPngError, match="signature"):
      decode_png(b"bukan berkas PNG sama sekali")

  def test_decode_raises_when_idat_missing(self):
    image = _random_image(4, 4, seed=4)
    data = encode_png(image, compress_level=6)
    # Signature (8) + chunk IHDR utuh (4+4+13+4=25) = 33 byte, tanpa IDAT.
    truncated = data[:33]
    with pytest.raises(InvalidPngError, match="IDAT"):
      decode_png(truncated)


def _gradient_image(width: int, height: int) -> RgbImage:
  # Citra gradien (bukan derau acak) supaya ukuran IDAT-nya benar-benar
  # bervariasi antar level kompresi, sehingga pick_compress_level punya
  # target yang bisa dibedakan.
  x = np.linspace(0, 255, width, dtype=np.uint8)
  y = np.linspace(0, 255, height, dtype=np.uint8)
  pixels = np.stack(
    [np.tile(x, (height, 1)), np.tile(y[:, None], (1, width)), np.full((height, width), 100, dtype=np.uint8)],
    axis=-1,
  ).astype(np.uint8)
  return RgbImage(pixels)


class TestCompressionProfile:
  def test_save_png_matches_source_compression_level(self, tmp_path):
    image = _gradient_image(64, 64)
    reference_bytes = encode_png(image, compress_level=3)

    stego = RgbImage(image.pixels.copy())
    remember_source_compression_profile(stego, reference_bytes)

    out_path = tmp_path / "out.png"
    save_png(stego, str(out_path))

    # Ukuran berkas harus sama persis (bisa saja levelnya sendiri berbeda,
    # karena beberapa level kompresi zlib bisa menghasilkan ukuran output
    # yang identik untuk data yang sama, tanpa memengaruhi kebenaran).
    assert len(out_path.read_bytes()) == len(reference_bytes)

  def test_save_png_without_profile_uses_default_level(self, tmp_path):
    image = _random_image(8, 8, seed=6)
    out_path = tmp_path / "out.png"
    save_png(image, str(out_path))
    decoded = decode_png(out_path.read_bytes())
    assert np.array_equal(decoded.pixels, image.pixels)

  def test_save_png_writes_to_file_like_object(self):
    import io

    image = _random_image(8, 8, seed=7)
    buffer = io.BytesIO()
    save_png(image, buffer)
    decoded = decode_png(buffer.getvalue())
    assert np.array_equal(decoded.pixels, image.pixels)
