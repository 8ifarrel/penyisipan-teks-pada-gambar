# Unit test untuk modul app.stego.payload (pembentukan & pemisahan payload).

import struct

import pytest

from app.crypto.aes_gcm import NONCE_LEN_BYTES, TAG_LEN_BYTES
from app.stego.payload import (
  HEADER_LEN_BYTES,
  HEADER_STRUCT_FORMAT,
  build_payload,
  parse_payload,
)


def _sample_components(ciphertext_len: int = 20):
  nonce = bytes(range(NONCE_LEN_BYTES))
  tag = bytes(range(TAG_LEN_BYTES))
  ciphertext = bytes((i * 7) % 256 for i in range(ciphertext_len))
  return nonce, tag, ciphertext


class TestBuildPayload:
  def test_payload_structure_and_header_value(self):
    nonce, tag, ciphertext = _sample_components(ciphertext_len=20)
    payload = build_payload(nonce, tag, ciphertext)

    expected_length = HEADER_LEN_BYTES + NONCE_LEN_BYTES + TAG_LEN_BYTES + len(ciphertext)
    assert len(payload) == expected_length

    header = payload[:HEADER_LEN_BYTES]
    (header_value,) = struct.unpack(HEADER_STRUCT_FORMAT, header)
    assert header_value == expected_length

    assert payload[HEADER_LEN_BYTES : HEADER_LEN_BYTES + NONCE_LEN_BYTES] == nonce
    tag_start = HEADER_LEN_BYTES + NONCE_LEN_BYTES
    assert payload[tag_start : tag_start + TAG_LEN_BYTES] == tag
    assert payload[tag_start + TAG_LEN_BYTES :] == ciphertext

  def test_empty_ciphertext_is_allowed(self):
    nonce, tag, _ = _sample_components()
    payload = build_payload(nonce, tag, b"")
    assert len(payload) == HEADER_LEN_BYTES + NONCE_LEN_BYTES + TAG_LEN_BYTES

  def test_wrong_nonce_length_raises_value_error(self):
    _, tag, ciphertext = _sample_components()
    with pytest.raises(ValueError, match="nonce"):
      build_payload(b"\x00" * (NONCE_LEN_BYTES - 1), tag, ciphertext)

  def test_wrong_tag_length_raises_value_error(self):
    nonce, _, ciphertext = _sample_components()
    with pytest.raises(ValueError, match="tag"):
      build_payload(nonce, b"\x00" * (TAG_LEN_BYTES + 1), ciphertext)


class TestParsePayload:
  @pytest.mark.parametrize("ciphertext_len", [0, 1, 20, 5000])
  def test_round_trip_returns_original_components(self, ciphertext_len):
    nonce, tag, ciphertext = _sample_components(ciphertext_len=ciphertext_len)
    payload = build_payload(nonce, tag, ciphertext)

    parsed = parse_payload(payload)

    assert parsed["nonce"] == nonce
    assert parsed["tag"] == tag
    assert parsed["ciphertext"] == ciphertext

  def test_payload_too_short_raises_value_error(self):
    too_short = b"\x00" * (HEADER_LEN_BYTES + NONCE_LEN_BYTES)  # tanpa tag lengkap
    with pytest.raises(ValueError, match="terlalu pendek"):
      parse_payload(too_short)

  def test_header_length_mismatch_raises_value_error(self):
    nonce, tag, ciphertext = _sample_components(ciphertext_len=10)
    payload = build_payload(nonce, tag, ciphertext)

    # Rusak nilai header agar tidak sesuai panjang byte payload sebenarnya.
    corrupted_header = struct.pack(HEADER_STRUCT_FORMAT, 999999)
    corrupted_payload = corrupted_header + payload[HEADER_LEN_BYTES:]

    with pytest.raises(ValueError, match="tidak sesuai"):
      parse_payload(corrupted_payload)
