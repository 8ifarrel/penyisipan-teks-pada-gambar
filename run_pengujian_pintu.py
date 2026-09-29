import os

from PIL import Image

from app.crypto.aes_gcm import (
  AuthenticationError,
  decrypt_ciphertext,
  encrypt_text,
)
from app.metrics.quality import (
  calculate_mse,
  calculate_psnr,
  categorize_quality,
)
from app.stego.lsb import (
  CapacityError,
  calculate_capacity,
  embed_payload,
  extract_payload,
)
from app.stego.payload import build_payload, parse_payload
from app.utils.formatting import (
  format_id_decimal,
  format_id_int,
  format_size,
)
from app.utils.png_io import remember_source_compression_profile, save_png

PENGUJIAN_DIR = r"C:\Users\Farrel Sirah\Documents\.Skripsi\pengujian"
IMG_DIR = os.path.join(PENGUJIAN_DIR, "img", "pintu")
TXT_DIR = os.path.join(PENGUJIAN_DIR, "txt")

COVERS = [
  (os.path.join(IMG_DIR, "pintu_128x.png"), "128x"),
  (os.path.join(IMG_DIR, "pintu_256x.png"), "256x"),
  (os.path.join(IMG_DIR, "pintu_512x.png"), "512x"),
  (os.path.join(IMG_DIR, "pintu_1024x.png"), "1024x"),
]

TEXTS = [
  (os.path.join(TXT_DIR, "teks-2000B_modified.txt"), "2KB"),
  (os.path.join(TXT_DIR, "teks-4000B_modified.txt"), "4KB"),
  (os.path.join(TXT_DIR, "teks-6000B_modified.txt"), "6KB"),
  (os.path.join(TXT_DIR, "teks-8000B_modified.txt"), "8KB"),
]

OUT_DIR = os.path.join(PENGUJIAN_DIR, "embeded", "pintu")

results = []
no = 0

for cover_path, res_label in COVERS:
  cover_image = Image.open(cover_path)
  cover_image.load()
  with open(cover_path, "rb") as f:
    remember_source_compression_profile(cover_image, f.read())
  width, height = cover_image.size
  cover_size_bytes = os.path.getsize(cover_path)
  capacity_bits = calculate_capacity(width, height)

  for text_path, payload_label in TEXTS:
    no += 1
    with open(text_path, encoding="utf-8") as f:
      text = f.read().strip()

    row = {
      "no": no,
      "citra_cover": f"pintu_{res_label}.png",
      "dimensi": (
        f"{format_id_int(width)} \u00d7 "
        f"{format_id_int(height)} piksel"
      ),
      "ukuran_cover": format_size(cover_size_bytes),
      "payload_label": payload_label,
    }

    encrypted = encrypt_text(text)
    payload = build_payload(
      encrypted["nonce"], encrypted["tag"], encrypted["ciphertext"]
    )
    payload_bits_len = len(payload) * 8

    row["kapasitas_cover"] = format_size(capacity_bits // 8)
    row["ukuran_payload"] = format_size(len(payload))
    row["status_enkripsi"] = "Berhasil"

    if capacity_bits < payload_bits_len:
      row["status_kapasitas"] = "Tidak Muat"
      row["status_penyisipan"] = "Gagal"
      row["ukuran_stego"] = "-"
      row["psnr"] = "-"
      row["kategori"] = "-"
      row["status_ekstraksi"] = "-"
      row["status_dekripsi"] = "-"
      row["catatan"] = "Kapasitas citra cover tidak cukup"
      row["file_stego"] = "-"
      results.append(row)
      continue

    row["status_kapasitas"] = "Muat"

    stego_image = embed_payload(cover_image, payload)
    stego_image.info.update(cover_image.info)
    row["status_penyisipan"] = "Berhasil"

    mse = calculate_mse(cover_image, stego_image)
    psnr = calculate_psnr(mse)
    quality_category = categorize_quality(psnr)
    psnr_display = (
      "Tak terhingga (citra identik)"
      if psnr == float("inf")
      else format_id_decimal(psnr, 2) + " dB"
    )
    row["psnr"] = psnr_display
    row["kategori"] = quality_category

    key_hex = encrypted["key"].hex()
    filename = f"pintu_{res_label}_{payload_label}_{key_hex}.png"
    out_path = os.path.join(OUT_DIR, filename)
    save_png(stego_image, out_path)
    stego_size_bytes = os.path.getsize(out_path)
    row["ukuran_stego"] = format_size(stego_size_bytes)
    row["file_stego"] = filename
    row["key_hex"] = key_hex

    # Uji ekstraksi ulang dari FILE yang benar-benar tersimpan di disk
    # (bukan dari objek stego_image di memori), supaya pengujian ini
    # benar-benar merepresentasikan alur nyata: unggah file -> ekstraksi.
    stego_reloaded = Image.open(out_path)
    stego_reloaded.load()
    try:
      extracted_payload = extract_payload(stego_reloaded)
      row["status_ekstraksi"] = "Berhasil"
    except CapacityError:
      row["status_ekstraksi"] = "Gagal"
      extracted_payload = None

    if extracted_payload is not None:
      parsed = parse_payload(extracted_payload)
      try:
        plaintext = decrypt_ciphertext(
          key=encrypted["key"],
          nonce=parsed["nonce"],
          tag=parsed["tag"],
          ciphertext=parsed["ciphertext"],
        )
        row["status_dekripsi"] = "Berhasil"
        row["catatan"] = (
          ""
          if plaintext == text
          else "PERINGATAN: teks hasil ekstraksi tidak cocok!"
        )
      except AuthenticationError:
        row["status_dekripsi"] = "Gagal"
        row["catatan"] = "PERINGATAN: dekripsi gagal saat verifikasi ulang!"
    else:
      row["status_dekripsi"] = "-"
      row["catatan"] = "PERINGATAN: ekstraksi ulang gagal!"

    results.append(row)

print("=" * 100)
for row in results:
  print(row)
print("=" * 100)

import json

with open(
  os.path.join(OUT_DIR, "_hasil_pengujian.json"),
  "w",
  encoding="utf-8",
) as f:
  json.dump(results, f, ensure_ascii=False, indent=2)

print("Selesai. Total baris:", len(results))
