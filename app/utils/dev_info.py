# Helper kecil bersama untuk panel "Info Developer", dipakai baik oleh
# app/services/embed_service.py maupun app/services/extract_service.py.


def empty_dev_info(keys: list) -> dict:
  """Membuat dict Info Developer awal, seluruh field bernilai "-"."""
  return {key: "-" for key in keys}
