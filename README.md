# Samarupa

Aplikasi web steganografi yang menyisipkan teks rahasia ke dalam citra digital. Teks dienkripsi terlebih dahulu dengan **AES-128-GCM**, lalu payload hasil enkripsinya disisipkan ke citra menggunakan metode **Least Significant Bit (LSB)**.

Nama "Samarupa" berasal dari kata "samar" (tersembunyi) dan "rupa" (wujud/citra): wujud yang menyamarkan pesan di dalamnya.

## Fitur

- **Sisipkan Teks**: unggah citra PNG (RGB 24-bit) + tulis teks, sistem mengenkripsi teks dengan AES-GCM dan menyisipkan hasilnya ke citra lewat LSB. Kunci AES ditampilkan sekali di halaman hasil (hex, 32 karakter/128-bit) untuk disimpan sendiri oleh pengguna.
- **Ekstraksi Teks**: unggah citra stego + masukkan kunci AES, sistem mengekstraksi payload dari citra dan mendekripsinya kembali menjadi teks asli.
- **Ukur kualitas citra**: setiap penyisipan dihitung nilai MSE & PSNR-nya, lalu dikategorikan (baik / masih bisa diterima / menurun drastis).
- **Kunci AES tidak pernah disimpan di server** — hanya muncul sekali di response halaman hasil.
- Citra stego disimpan sementara di server (maksimal 15 menit) untuk keperluan pratinjau & unduhan, lalu dihapus otomatis.

## Cara kerja

1. **Enkripsi** — teks dienkripsi dengan AES-128-GCM menggunakan kunci acak sekali pakai (CSPRNG), menghasilkan ciphertext, nonce, dan authentication tag.
2. **Pembentukan payload** — nonce, tag, dan ciphertext digabung menjadi satu payload biner dengan header 4-byte (big-endian) penanda panjang total payload.
3. **Penyisipan LSB** — setiap bit payload disisipkan ke bit paling tidak signifikan tiap kanal warna (R, G, B) citra, dimulai dari piksel pertama.
4. **Ukur kualitas** — citra asli & citra hasil dibandingkan lewat MSE dan PSNR.
5. **Ekstraksi & dekripsi** — proses sebaliknya: bit LSB dibaca dari citra, payload disusun ulang, lalu didekripsi kembali menjadi teks asli menggunakan kunci AES yang sama.

## Teknologi

- **Backend**: Python, [Flask](https://flask.palletsprojects.com/)
- **Kriptografi**: [`cryptography`](https://cryptography.io/) (AES-GCM)
- **Pengolahan citra**: [Pillow](https://python-pillow.org/), [NumPy](https://numpy.org/) (operasi bit LSB tervectorisasi)
- **Frontend**: Jinja2, CSS murni (tanpa framework), vanilla JavaScript
- **Testing**: [pytest](https://pytest.org/)

## Struktur proyek

```
app/
  crypto/      modul enkripsi & dekripsi AES-GCM
  metrics/     modul penghitungan MSE, PSNR, kategori kualitas
  stego/       modul pembentukan payload & penyisipan/ekstraksi LSB
  static/      CSS & JavaScript
  templates/   halaman Jinja2 (beranda, sisipkan, ekstraksi, hasil, tentang)
  routes.py    endpoint Flask (menghubungkan semua modul di atas)
  __init__.py  application factory
tests/         unit test untuk tiap modul (pytest)
run.py         entry point menjalankan development server
```

## Instalasi & menjalankan

Butuh Python 3.10+.

```bash
# 1. Buat & aktifkan virtual environment
python -m venv venv
venv\Scripts\activate        # Windows
source venv/bin/activate     # macOS/Linux

# 2. Install dependency
pip install -r requirements-dev.txt   # termasuk pytest, untuk development
# atau
pip install -r requirements.txt       # hanya dependency untuk menjalankan aplikasi

# 3. Jalankan server
python run.py
```

Buka `http://127.0.0.1:5000` di browser.

## Menjalankan test

```bash
pytest tests/ -v
```

## Catatan keamanan

- Format kunci AES yang ditampilkan/diminta adalah **heksadesimal** (32 karakter untuk 16 byte), bukan base64 — supaya tidak ada karakter yang rawan rusak saat disalin lewat berbagai media.
- Kunci AES **tidak pernah** disimpan atau di-log di server.
- AES-GCM adalah skema AEAD: selain kerahasiaan, ia juga memverifikasi keaslian data — jika ciphertext/tag/citra stego dimanipulasi, proses dekripsi akan gagal alih-alih menghasilkan teks yang salah secara diam-diam.
