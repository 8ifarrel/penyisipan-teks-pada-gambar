# Modul pembentukan & pemisahan payload.
# 
# Struktur payload (urutan byte tetap):
#   1. Header              (4 byte, unsigned integer, big-endian)
#   2. Nonce               (12 byte)
#   3. Authentication tag  (16 byte)
#   4. Ciphertext          (panjang plaintext UTF-8)
# 
# Header disimpan/dibaca menggunakan modul `struct` Python, dengan format
# karakter unsigned integer 4 byte big-endian (">I") agar deterministik
# terlepas dari byte order platform yang menjalankan sistem.

import struct

from app.crypto.aes_gcm import NONCE_LEN_BYTES, TAG_LEN_BYTES

HEADER_LEN_BYTES = 4
HEADER_STRUCT_FORMAT = ">I"  # unsigned integer, 4 byte, big-endian


def build_payload(nonce: bytes, tag: bytes, ciphertext: bytes) -> bytes:
  """
  Membentuk payload dari komponen hasil enkripsi AES-GCM.

  Alur:
   1. Hitung panjang ciphertext
   2. Hitung panjang payload = |header| + |nonce| + |tag| + |ciphertext|
   3. Bentuk header (unsigned integer, 4 byte) berisi panjang payload
   4. Satukan header, nonce, authentication tag, dan ciphertext

  Args:
    nonce: nonce AES-GCM (harus NONCE_LEN_BYTES byte).
    tag: authentication tag AES-GCM (harus TAG_LEN_BYTES byte).
    ciphertext: ciphertext hasil enkripsi.

  Returns:
    bytes payload lengkap, siap disisipkan ke citra cover dengan LSB.

  Raises:
    ValueError: jika panjang nonce atau tag tidak sesuai ukuran yang
      ditetapkan (12 byte dan 16 byte), karena offset pemisahan pada
      parse_payload() bergantung penuh pada ukuran tetap ini.
  """
  if len(nonce) != NONCE_LEN_BYTES:
    raise ValueError(
      f"Panjang nonce harus {NONCE_LEN_BYTES} byte, diterima {len(nonce)} byte."
    )
  if len(tag) != TAG_LEN_BYTES:
    raise ValueError(
      f"Panjang authentication tag harus {TAG_LEN_BYTES} byte, "
      f"diterima {len(tag)} byte."
    )

  payload_length = HEADER_LEN_BYTES + NONCE_LEN_BYTES + TAG_LEN_BYTES + len(ciphertext)
  header = struct.pack(HEADER_STRUCT_FORMAT, payload_length)

  return header + nonce + tag + ciphertext


def parse_payload(payload: bytes) -> dict:
  """
  Memisahkan payload menjadi komponen nonce, authentication tag, dan ciphertext.

  Alur:
   1. Baca 4 byte pertama sebagai header -> panjang total payload
   2. Ambil 12 byte berikutnya sebagai nonce
   3. Ambil 16 byte berikutnya sebagai authentication tag
   4. Hitung panjang ciphertext = panjang_payload - header - nonce - tag
   5. Ambil sisa byte sebagai ciphertext

  Args:
    payload: bytes payload lengkap (mis. hasil ekstraksi LSB dari citra
      stego), minimal sepanjang header + nonce + tag.

  Returns:
    dict berisi "nonce", "tag", "ciphertext" (bytes).

  Raises:
    ValueError: jika payload terlalu pendek untuk memuat header, nonce,
      dan authentication tag, atau jika panjang pada header tidak
      konsisten dengan panjang byte payload yang diberikan.
  """
  min_length = HEADER_LEN_BYTES + NONCE_LEN_BYTES + TAG_LEN_BYTES
  if len(payload) < min_length:
    raise ValueError(
      f"Payload terlalu pendek: minimal {min_length} byte, "
      f"diterima {len(payload)} byte."
    )

  (payload_length,) = struct.unpack(
    HEADER_STRUCT_FORMAT, payload[:HEADER_LEN_BYTES]
  )
  if payload_length != len(payload):
    raise ValueError(
      f"Panjang payload pada header ({payload_length} byte) tidak "
      f"sesuai dengan panjang byte payload yang diberikan ({len(payload)} byte)."
    )

  nonce_start = HEADER_LEN_BYTES
  tag_start = nonce_start + NONCE_LEN_BYTES
  ciphertext_start = tag_start + TAG_LEN_BYTES

  nonce = payload[nonce_start:tag_start]
  tag = payload[tag_start:ciphertext_start]
  ciphertext = payload[ciphertext_start:]

  return {"nonce": nonce, "tag": tag, "ciphertext": ciphertext}
