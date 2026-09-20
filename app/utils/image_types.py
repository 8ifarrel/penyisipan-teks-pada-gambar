# Wadah data citra RGB 24-bit: array piksel numpy + metadata opsional
# (mis. profil kompresi sumber, lihat app/utils/png_io.py). Dipakai sebagai
# tipe citra bersama antara app/stego/ dan app/utils/png_io.py tanpa membuat
# kedua modul itu saling bergantung satu sama lain.

import numpy as np


class RgbImage:
  def __init__(self, pixels: np.ndarray):
    self.pixels = pixels  # array uint8, shape (height, width, 3)
    self.info = {}

  @property
  def size(self) -> tuple[int, int]:
    height, width = self.pixels.shape[:2]
    return (width, height)
