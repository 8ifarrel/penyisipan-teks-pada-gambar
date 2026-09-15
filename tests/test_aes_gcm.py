# Unit test untuk modul app.crypto.aes_gcm (AES-128-GCM).
#
# Mencakup:
#   (a) round-trip enkripsi-dekripsi menghasilkan teks yang sama persis
#   (b) dekripsi dengan authentication tag yang salah gagal dengan benar
#   (c) panjang key dan nonce yang dihasilkan selalu benar (16 byte, 12 byte)

import pytest

from app.crypto.aes_gcm import (
  KEY_LEN_BYTES,
  NONCE_LEN_BYTES,
  TAG_LEN_BYTES,
  AuthenticationError,
  decrypt_ciphertext,
  encrypt_text,
  generate_key,
  generate_nonce,
)


class TestGenerateKey:
  def test_key_length_is_16_bytes(self):
    key = generate_key()
    assert len(key) == KEY_LEN_BYTES == 16

  def test_key_is_bytes(self):
    assert isinstance(generate_key(), bytes)

  def test_keys_are_random_each_call(self):
    keys = {generate_key() for _ in range(20)}
    assert len(keys) == 20  # sangat kecil kemungkinan tabrakan


class TestGenerateNonce:
  def test_nonce_length_is_12_bytes(self):
    nonce = generate_nonce()
    assert len(nonce) == NONCE_LEN_BYTES == 12

  def test_nonce_is_bytes(self):
    assert isinstance(generate_nonce(), bytes)

  def test_nonces_are_random_each_call(self):
    nonces = {generate_nonce() for _ in range(20)}
    assert len(nonces) == 20


class TestEncryptText:
  @pytest.mark.parametrize(
    "plaintext",
    [
      "Halo, dunia!",
      "",
      "Teks dengan karakter unicode: 你好, éàü, emoji 🔐🖼️",
      "A" * 5000,  # teks panjang
    ],
  )
  def test_encrypt_produces_correctly_sized_components(self, plaintext):
    result = encrypt_text(plaintext)

    assert len(result["key"]) == KEY_LEN_BYTES
    assert len(result["nonce"]) == NONCE_LEN_BYTES
    assert len(result["tag"]) == TAG_LEN_BYTES
    # ciphertext (AES-GCM adalah stream cipher) panjangnya = panjang plaintext (bytes)
    assert len(result["ciphertext"]) == len(plaintext.encode("utf-8"))

  def test_ciphertext_does_not_contain_tag_appended(self):
    # Memastikan tag benar-benar dipisahkan, bukan menempel di ciphertext.
    result = encrypt_text("contoh teks rahasia")
    assert not result["ciphertext"].endswith(result["tag"])

  def test_two_encryptions_use_different_key_and_nonce(self):
    result_a = encrypt_text("teks yang sama")
    result_b = encrypt_text("teks yang sama")

    assert result_a["key"] != result_b["key"]
    assert result_a["nonce"] != result_b["nonce"]
    # Ciphertext & tag pun berbeda walau plaintext sama, karena key/nonce beda.
    assert result_a["ciphertext"] != result_b["ciphertext"]
    assert result_a["tag"] != result_b["tag"]


class TestRoundTrip:
  @pytest.mark.parametrize(
    "plaintext",
    [
      "Halo, dunia!",
      "",
      "Teks dengan karakter unicode: 你好, éàü, emoji 🔐🖼️",
      "Baris pertama\nBaris kedua\tdengan tab",
      "A" * 5000,
    ],
  )
  def test_decrypt_returns_original_plaintext(self, plaintext):
    encrypted = encrypt_text(plaintext)

    decrypted = decrypt_ciphertext(
      key=encrypted["key"],
      nonce=encrypted["nonce"],
      tag=encrypted["tag"],
      ciphertext=encrypted["ciphertext"],
    )

    assert decrypted == plaintext


class TestAuthenticationFailure:
  def _encrypt_sample(self):
    return encrypt_text("pesan rahasia yang harus terjaga integritasnya")

  def test_wrong_tag_raises_authentication_error(self):
    encrypted = self._encrypt_sample()

    # Rusak satu byte pertama pada tag agar T != T'
    corrupted_tag = bytes([encrypted["tag"][0] ^ 0xFF]) + encrypted["tag"][1:]

    with pytest.raises(AuthenticationError):
      decrypt_ciphertext(
        key=encrypted["key"],
        nonce=encrypted["nonce"],
        tag=corrupted_tag,
        ciphertext=encrypted["ciphertext"],
      )

  def test_wrong_key_raises_authentication_error(self):
    encrypted = self._encrypt_sample()
    wrong_key = generate_key()

    with pytest.raises(AuthenticationError):
      decrypt_ciphertext(
        key=wrong_key,
        nonce=encrypted["nonce"],
        tag=encrypted["tag"],
        ciphertext=encrypted["ciphertext"],
      )

  def test_wrong_nonce_raises_authentication_error(self):
    encrypted = self._encrypt_sample()
    wrong_nonce = generate_nonce()

    with pytest.raises(AuthenticationError):
      decrypt_ciphertext(
        key=encrypted["key"],
        nonce=wrong_nonce,
        tag=encrypted["tag"],
        ciphertext=encrypted["ciphertext"],
      )

  def test_tampered_ciphertext_raises_authentication_error(self):
    encrypted = self._encrypt_sample()
    tampered_ciphertext = (
      bytes([encrypted["ciphertext"][0] ^ 0xFF]) + encrypted["ciphertext"][1:]
    )

    with pytest.raises(AuthenticationError):
      decrypt_ciphertext(
        key=encrypted["key"],
        nonce=encrypted["nonce"],
        tag=encrypted["tag"],
        ciphertext=tampered_ciphertext,
      )

  def test_authentication_error_message_mentions_tag_mismatch(self):
    encrypted = self._encrypt_sample()
    corrupted_tag = bytes([encrypted["tag"][0] ^ 0xFF]) + encrypted["tag"][1:]

    with pytest.raises(AuthenticationError, match="Authentication tag"):
      decrypt_ciphertext(
        key=encrypted["key"],
        nonce=encrypted["nonce"],
        tag=corrupted_tag,
        ciphertext=encrypted["ciphertext"],
      )
