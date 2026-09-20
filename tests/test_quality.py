# Unit test untuk modul app.metrics.quality (MSE, PSNR, kategori kualitas).
#
# Nilai ekspektasi pada test MSE/PSNR dihitung manual (dengan tangan atau
# rumus MSE/PSNR langsung via `math`), bukan dengan memanggil ulang fungsi
# yang diuji, agar benar-benar independen dari implementasi.

import math

import numpy as np
import pytest
from PIL import Image

from app.metrics.quality import (
  MAX_PIXEL_VALUE,
  calculate_mse,
  calculate_psnr,
  categorize_quality,
)


def _image_from_array(array: np.ndarray) -> Image.Image:
  return Image.fromarray(array.astype(np.uint8), mode="RGB")


class TestCalculateMse:
  def test_identical_images_have_zero_mse(self):
    array = np.array([[[10, 20, 30], [40, 50, 60]]], dtype=np.uint8)
    cover = _image_from_array(array)
    stego = _image_from_array(array.copy())

    assert calculate_mse(cover, stego) == 0.0

  def test_manual_single_channel_difference(self):
    # Citra 1x2 piksel (m=1, n=2), RGB -> 6 elemen total.
    # Hanya kanal R piksel pertama berbeda sebesar 10; sisanya identik.
    cover_array = np.array([[[0, 0, 0], [0, 0, 0]]], dtype=np.uint8)
    stego_array = np.array([[[10, 0, 0], [0, 0, 0]]], dtype=np.uint8)

    cover = _image_from_array(cover_array)
    stego = _image_from_array(stego_array)

    # Perhitungan manual: sum((I-K)^2) = 10^2 = 100, dibagi 6 elemen.
    expected_mse = 100 / 6
    assert calculate_mse(cover, stego) == pytest.approx(expected_mse)

  def test_manual_max_difference(self):
    # Cover seluruhnya 0, stego seluruhnya 255 -> beda maksimum tiap elemen.
    cover_array = np.zeros((2, 2, 3), dtype=np.uint8)
    stego_array = np.full((2, 2, 3), 255, dtype=np.uint8)

    cover = _image_from_array(cover_array)
    stego = _image_from_array(stego_array)

    expected_mse = 255**2  # setiap elemen menyumbang (255-0)^2 = 65025
    assert calculate_mse(cover, stego) == pytest.approx(expected_mse)

  def test_uint8_subtraction_does_not_wrap_around(self):
    # Uji khusus regresi: jika pengurangan dilakukan pada tipe uint8
    # (bukan float) sebelum dikuadratkan, 0 - 255 akan wrap-around
    # menjadi 1 (bukan -255), sehingga (1)^2 = 1, BUKAN 255^2 = 65025.
    cover_array = np.zeros((1, 1, 3), dtype=np.uint8)
    stego_array = np.full((1, 1, 3), 255, dtype=np.uint8)

    cover = _image_from_array(cover_array)
    stego = _image_from_array(stego_array)

    mse = calculate_mse(cover, stego)
    assert mse == pytest.approx(255**2)
    assert mse != pytest.approx(1.0)

  def test_shape_mismatch_raises_value_error(self):
    cover = _image_from_array(np.zeros((4, 4, 3), dtype=np.uint8))
    stego = _image_from_array(np.zeros((8, 8, 3), dtype=np.uint8))

    with pytest.raises(ValueError, match="[Dd]imensi"):
      calculate_mse(cover, stego)


class TestCalculatePsnr:
  def test_zero_mse_returns_infinity(self):
    assert calculate_psnr(0.0) == float("inf")

  def test_manual_mse_matches_direct_formula(self):
    mse = 100 / 6
    expected_psnr = 10 * math.log10((MAX_PIXEL_VALUE**2) / mse)
    assert calculate_psnr(mse) == pytest.approx(expected_psnr)

  def test_exact_zero_db_boundary(self):
    # MAX^2 / mse = 1 ketika mse = MAX^2 -> psnr = 10*log10(1) = 0 dB.
    mse = MAX_PIXEL_VALUE**2
    assert calculate_psnr(mse) == pytest.approx(0.0, abs=1e-9)

  def test_exact_20db_boundary(self):
    # 65025 / 650.25 = 100 -> 10*log10(100) = 20 dB persis.
    mse = (MAX_PIXEL_VALUE**2) / 100
    assert calculate_psnr(mse) == pytest.approx(20.0)

  def test_exact_30db_boundary(self):
    # 65025 / 65.025 = 1000 -> 10*log10(1000) = 30 dB persis.
    mse = (MAX_PIXEL_VALUE**2) / 1000
    assert calculate_psnr(mse) == pytest.approx(30.0)

  def test_negative_mse_raises_value_error(self):
    with pytest.raises(ValueError, match="negatif"):
      calculate_psnr(-1.0)


class TestCategorizeQuality:
  @pytest.mark.parametrize(
    "psnr,expected_category",
    [
      (0.0, "Kualitas citra stego menurun drastis"),
      (10.0, "Kualitas citra stego menurun drastis"),
      (19.999, "Kualitas citra stego menurun drastis"),
      (20.0, "Kualitas citra stego masih bisa diterima"),  # batas bawah, inklusif
      (25.0, "Kualitas citra stego masih bisa diterima"),
      (30.0, "Kualitas citra stego masih bisa diterima"),  # batas atas, inklusif
      (30.0001, "Kualitas citra stego baik"),
      (35.0, "Kualitas citra stego baik"),
      (float("inf"), "Kualitas citra stego baik"),  # citra identik sempurna
    ],
  )
  def test_category_thresholds(self, psnr, expected_category):
    assert categorize_quality(psnr) == expected_category


class TestEndToEnd:
  def test_identical_images_are_categorized_as_good_with_infinite_psnr(self):
    array = np.random.default_rng(0).integers(0, 256, size=(16, 16, 3), dtype=np.uint8)
    cover = _image_from_array(array)
    stego = _image_from_array(array.copy())

    mse = calculate_mse(cover, stego)
    psnr = calculate_psnr(mse)
    category = categorize_quality(psnr)

    assert mse == 0.0
    assert psnr == float("inf")
    assert category == "Kualitas citra stego baik"

  def test_lsb_embedding_typically_yields_high_psnr(self):
    # Perubahan hanya pada bit LSB (beda maksimum 1 per elemen) harus
    # menghasilkan PSNR yang jauh di atas 30 dB (kualitas "baik"),
    # merepresentasikan skenario nyata penyisipan LSB.
    rng = np.random.default_rng(1)
    cover_array = rng.integers(0, 256, size=(32, 32, 3), dtype=np.uint8)
    # Simulasikan penyisipan LSB: ganti bit ke-0 tiap elemen (beda maks 1).
    lsb_bits = rng.integers(0, 2, size=cover_array.shape, dtype=np.uint8)
    stego_array = (cover_array & 0xFE) | lsb_bits

    cover = _image_from_array(cover_array)
    stego = _image_from_array(stego_array)

    mse = calculate_mse(cover, stego)
    psnr = calculate_psnr(mse)

    assert mse <= 1.0  # beda maksimum 1 per elemen -> MSE maksimum 1
    assert psnr > 30.0
    assert categorize_quality(psnr) == "Kualitas citra stego baik"
