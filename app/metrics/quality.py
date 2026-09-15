# Modul penghitungan MSE, PSNR, dan kategori kualitas citra stego.
#
# Rumus MSE:
#   MSE = (1 / (m*n)) * sum_i sum_j (I(i,j) - K(i,j))^2
#
# Rumus PSNR:
#   PSNR = 10 * log10(MAX^2 / MSE)
#   MAX = nilai maksimum komponen warna (255 untuk 8-bit per kanal)
#
# Kategori kualitas citra stego berdasarkan nilai PSNR:
#   PSNR < 20 dB           -> "Kualitas citra stego menurun drastis"
#   20 dB <= PSNR <= 30 dB -> "Kualitas citra stego masih bisa diterima"
#   PSNR > 30 dB           -> "Kualitas citra stego baik"
#
# Catatan pilihan perhitungan MSE pada citra RGB:
# Rumus MSE di atas menulis I(i,j) dan K(i,j) tanpa indeks kanal warna
# eksplisit, dan pembagi berupa m x n (jumlah piksel spasial, bukan jumlah
# elemen array RGB yang sudah dikali 3 kanal). Pada praktiknya, untuk citra
# berwarna terdapat dua pendekatan yang umum dipakai di literatur:
#   (1) hitung MSE per kanal (R, K, G masing-masing sebagai "citra" m x n
#       tersendiri), lalu rata-ratakan MSE ketiga kanal tersebut; atau
#   (2) hitung satu MSE atas seluruh elemen array RGB (m x n x 3 elemen)
#       sekaligus, yaitu sum_i sum_j sum_c (I-K)^2 dibagi (m*n*3).
# Karena tiap kanal memiliki jumlah piksel m x n yang identik, kedua
# pendekatan tersebut MATEMATIS EKUIVALEN (rata-rata dari rata-rata dengan
# bobot sama = rata-rata gabungan). Modul ini memilih pendekatan (2), yaitu
# menghitung langsung pada seluruh elemen array RGB via np.mean(), karena
# lebih ringkas, tervectorisasi penuh oleh numpy tanpa perlu iterasi per
# kanal, dan hasilnya identik dengan pendekatan (1).

import math

import numpy as np

MAX_PIXEL_VALUE = 255


def calculate_mse(cover_image, stego_image) -> float:
  """
  Menghitung nilai MSE antara citra cover dan citra stego.

  Rumus: MSE = (1/(m*n)) * sum_i sum_j (I(i,j) - K(i,j))^2

  Lihat catatan pilihan perhitungan di bagian atas modul ini mengenai
  penerapan rumus tersebut pada citra RGB (3 kanal warna).

  Args:
    cover_image: objek PIL.Image (mode RGB), sebagai citra I.
    stego_image: objek PIL.Image (mode RGB) dengan dimensi yang sama
      dengan cover_image, sebagai citra K.

  Returns:
    Nilai MSE (float). Bernilai 0.0 jika kedua citra identik persis.

  Raises:
    ValueError: jika dimensi/bentuk array kedua citra tidak sama,
      karena MSE piksel-demi-piksel hanya terdefinisi untuk citra
      dengan ukuran yang sama.
  """
  # Konversi ke float64 SEBELUM dikurangkan, karena piksel PIL bertipe uint8
  # (0-255), sehingga pengurangan langsung pada tipe uint8 akan underflow
  # (wrap-around) alih-alih menghasilkan nilai negatif yang benar.
  cover_array = np.asarray(cover_image, dtype=np.float64)
  stego_array = np.asarray(stego_image, dtype=np.float64)

  if cover_array.shape != stego_array.shape:
    raise ValueError(
      "Dimensi citra cover dan citra stego harus sama untuk "
      f"menghitung MSE (cover: {cover_array.shape}, stego: {stego_array.shape})."
    )

  squared_diff = (cover_array - stego_array) ** 2
  return float(np.mean(squared_diff))


def calculate_psnr(mse: float) -> float:
  """
  Menghitung nilai PSNR dari MSE.

  Rumus: PSNR = 10 * log10(MAX^2 / MSE), dengan MAX = 255.

  Kasus khusus MSE = 0 (citra cover dan citra stego identik piksel demi
  piksel) ditangani secara eksplisit agar tidak terjadi pembagian dengan
  nol: PSNR dianggap tak terhingga (float("inf")), merepresentasikan
  kualitas "identik sempurna".

  Args:
    mse: nilai Mean Square Error (harus >= 0).

  Returns:
    Nilai PSNR dalam desibel (dB), atau float("inf") jika mse == 0.

  Raises:
    ValueError: jika mse bernilai negatif (tidak valid secara matematis).
  """
  if mse < 0:
    raise ValueError(f"MSE tidak boleh negatif, diterima: {mse}.")

  if mse == 0:
    return float("inf")

  return 10 * math.log10((MAX_PIXEL_VALUE ** 2) / mse)


def categorize_quality(psnr: float) -> str:
  """
  Menentukan kategori kualitas citra stego berdasarkan nilai PSNR.

  Kategori:
    PSNR < 20 dB           -> "Kualitas citra stego menurun drastis"
    20 dB <= PSNR <= 30 dB -> "Kualitas citra stego masih bisa diterima"
    PSNR > 30 dB           -> "Kualitas citra stego baik"

  Args:
    psnr: nilai PSNR dalam dB (bisa float("inf") untuk citra identik).

  Returns:
    Deskripsi kategori kualitas citra stego.
  """
  if psnr < 20:
    return "Kualitas citra stego menurun drastis"
  if psnr <= 30:
    return "Kualitas citra stego masih bisa diterima"
  return "Kualitas citra stego baik"
