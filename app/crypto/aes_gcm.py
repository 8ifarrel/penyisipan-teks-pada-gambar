# Modul enkripsi & dekripsi AES-GCM.
#
# Parameter yang digunakan:
#   - Key       : 128 bit, dibentuk acak (CSPRNG) tiap proses enkripsi
#   - Nonce     : 96 bit (12 byte), dibentuk acak tiap proses enkripsi
#   - Auth tag  : 128 bit (16 byte)
#   - Encoding  : UTF-8
#
# Library yang digunakan: `cryptography` (cryptography.hazmat.primitives.ciphers.aead.AESGCM)
#
# Ciphertext dan authentication tag pada modul ini selalu berupa dua nilai
# bytes terpisah (bukan tergabung di akhir buffer seperti keluaran default
# AESGCM.encrypt()), karena payload penyisipan menyimpan nonce, tag, dan
# ciphertext sebagai tiga komponen berbeda. Keduanya digabungkan kembali
# hanya saat dipanggilkan ke AESGCM.encrypt()/decrypt().
#
# Verifikasi authentication tag dilakukan sepenuhnya oleh AESGCM.decrypt():
# jika tag tidak valid, library melempar cryptography.exceptions.InvalidTag,
# yang ditangkap di decrypt_ciphertext() dan dilempar ulang sebagai
# AuthenticationError.

import secrets

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

KEY_LEN_BYTES = 16   # 128 bit
NONCE_LEN_BYTES = 12  # 96 bit
TAG_LEN_BYTES = 16   # 128 bit


class AuthenticationError(Exception):
  """
  Dilempar ketika authentication tag (T) yang diberikan tidak sama dengan
  authentication tag pembanding (T') hasil verifikasi AES-GCM.

  Jika T != T', proses dekripsi tidak boleh dilanjutkan.
  """


def generate_key() -> bytes:
  """
  Membentuk key AES-128 secara acak menggunakan CSPRNG.

  Panjang key 128 bit (16 byte).

  Returns:
    bytes sepanjang KEY_LEN_BYTES (16 byte).
  """
  return secrets.token_bytes(KEY_LEN_BYTES)


def generate_nonce() -> bytes:
  """
  Membentuk nonce 96-bit (12 byte) secara acak menggunakan CSPRNG.

  Nonce hanya digunakan satu kali per proses enkripsi agar ciphertext
  berbeda walau plaintext sama.

  Returns:
    bytes sepanjang NONCE_LEN_BYTES (12 byte).
  """
  return secrets.token_bytes(NONCE_LEN_BYTES)


def encrypt_text(plaintext: str) -> dict:
  """
  Mengenkripsi teks dengan AES-128-GCM.

  Alur:
   1. Encode teks dengan UTF-8
   2. Tetapkan panjang key, nonce, authentication tag
   3. Bentuk key secara acak
   4. Bentuk nonce secara acak
   5. Enkripsi teks -> hasilkan ciphertext & authentication tag

  Args:
    plaintext: teks asli yang akan dienkripsi.

  Returns:
    dict dengan kunci "key", "nonce", "ciphertext", "tag", seluruhnya
    bytes terpisah (tag TIDAK menempel di ciphertext).
  """
  plaintext_bytes = plaintext.encode("utf-8")

  key = generate_key()
  nonce = generate_nonce()

  aesgcm = AESGCM(key)
  # AESGCM.encrypt() mengembalikan ciphertext dengan tag (16 byte)
  # menempel di akhir buffer, pisahkan secara eksplisit.
  ciphertext_with_tag = aesgcm.encrypt(nonce, plaintext_bytes, None)
  ciphertext = ciphertext_with_tag[:-TAG_LEN_BYTES]
  tag = ciphertext_with_tag[-TAG_LEN_BYTES:]

  return {
    "key": key,
    "nonce": nonce,
    "ciphertext": ciphertext,
    "tag": tag,
  }


def decrypt_ciphertext(key: bytes, nonce: bytes, tag: bytes, ciphertext: bytes) -> str:
  """
  Mendekripsi ciphertext dengan AES-128-GCM.

  Alur:
   1. Terima nonce, authentication tag, key, dan ciphertext
   2. Verifikasi authentication tag (T) terhadap tag pembanding (T'). Jika
    T != T', proses dihentikan dan AuthenticationError dilempar
   3. Jika T = T' -> dekripsi ciphertext dengan key & nonce
   4. Decode hasil dekripsi dari bytes ke teks dengan UTF-8

  Args:
    key: key AES-128 (16 byte).
    nonce: nonce yang digunakan saat enkripsi (12 byte).
    tag: authentication tag (T) hasil enkripsi (16 byte).
    ciphertext: ciphertext hasil enkripsi.

  Returns:
    Teks asli (plaintext) hasil dekripsi.

  Raises:
    AuthenticationError: jika authentication tag tidak valid (T != T'),
      artinya ciphertext/tag/key/nonce tidak konsisten atau data telah
      dimanipulasi.
  """
  aesgcm = AESGCM(key)
  ciphertext_with_tag = ciphertext + tag

  try:
    plaintext_bytes = aesgcm.decrypt(nonce, ciphertext_with_tag, None)
  except InvalidTag as exc:
    raise AuthenticationError(
      "Authentication tag tidak valid (T != T'): ciphertext, tag, "
      "key, atau nonce tidak konsisten sehingga dekripsi dibatalkan."
    ) from exc

  return plaintext_bytes.decode("utf-8")
