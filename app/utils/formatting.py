# Format angka & ukuran untuk tampilan (Info Developer, halaman hasil).
#
# Konvensi Indonesia dipakai di seluruh modul ini: titik (.) sebagai
# pemisah ribuan, koma (,) sebagai pemisah desimal, kebalikan dari
# konvensi Python/Inggris bawaan (f"{x:,}").


def format_id_int(value: int) -> str:
  """
  Format bilangan bulat dengan titik (.) sebagai pemisah ribuan, mengikuti
  konvensi penulisan angka Indonesia (mis. 12300 -> "12.300").
  """
  return f"{value:,}".replace(",", ".")


def format_id_decimal(value: float, decimals: int) -> str:
  """
  Format bilangan desimal mengikuti konvensi penulisan angka Indonesia:
  titik (.) sebagai pemisah ribuan, koma (,) sebagai pemisah desimal
  (mis. 12300.232 -> "12.300,232").
  """
  formatted = f"{value:,.{decimals}f}"
  return formatted.replace(",", "X").replace(".", ",").replace("X", ".")


def format_size(num_bytes: int) -> str:
  """
  Format ukuran byte sekaligus dalam dua satuan dengan urutan TETAP "KB (B)"
  berapa pun besarnya, mis. "123,000 KB (123.000 B)" atau "0,012 KB (12 B)",
  supaya kedua angka selalu tersedia untuk dokumentasi pengujian tanpa
  perlu dihitung ulang manual.

  1 KB = 1000 byte (desimal/SI, sesuai lembar pencatatan hasil pengujian),
  BUKAN 1024 byte (biner/KiB).
  """
  kb_str = format_id_decimal(num_bytes / 1000, 3) + " KB"
  return f"{kb_str} ({format_id_int(num_bytes)} B)"
