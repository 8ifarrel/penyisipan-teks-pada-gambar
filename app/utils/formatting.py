# Format angka untuk tampilan (halaman hasil).
#
# Konvensi Indonesia dipakai di modul ini: titik (.) sebagai pemisah
# ribuan, koma (,) sebagai pemisah desimal, kebalikan dari konvensi
# Python/Inggris bawaan (f"{x:,}").


def format_id_decimal(value: float, decimals: int) -> str:
  """
  Format bilangan desimal mengikuti konvensi penulisan angka Indonesia:
  titik (.) sebagai pemisah ribuan, koma (,) sebagai pemisah desimal
  (mis. 12300.232 -> "12.300,232").
  """
  formatted = f"{value:,.{decimals}f}"
  swapped = formatted.replace(",", "X").replace(".", ",")
  return swapped.replace("X", ".")
