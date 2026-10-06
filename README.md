# Data Pengujian

Branch ini berisi data pengujian skripsi **Penyisipan Teks pada
Gambar** (AES-GCM dan steganografi LSB) oleh Muhammad Farrel Sirah
(NIM 2209106138), Program Studi S-1 Informatika, Universitas
Mulawarman.

Branch ini hanya berisi data dan **tidak memuat kode aplikasi**.
Kode aplikasi ada di branch `main`.

## Struktur folder

| Folder | Isi |
|---|---|
| `1_mentah/` | Bahan asli sebelum diolah: foto `kucing_ori.jpg` dan `pintu_ori.jpg`, serta teks sumber `teks_8KB_ori.txt` (8 KB). |
| `2_siap_uji/` | Bahan yang langsung dipakai untuk pengujian: citra cover PNG RGB 24-bit (`img/kucing/`, `img/pintu/`) dan teks uji (`txt/`). |
| `3_hasil/` | Citra stego hasil penyisipan, dikelompokkan per objek (`kucing/`, `pintu/`). |

## Bahan uji

- **Citra cover:** dua objek (`pintu` dan `kucing`) dengan empat
  resolusi: 128x, 256x, 512x, dan 1024x (persegi, PNG RGB 24-bit).
  Contoh nama file: `pintu_128x.png`.
- **Teks uji:** empat ukuran, yaitu 2 KB, 4 KB, 6 KB, dan 8 KB
  (`teks_2KB_modified.txt` dan seterusnya).
- **Kombinasi:** 2 objek x 4 resolusi x 4 ukuran teks = 32 pengujian.
  Urutan pencatatan: `pintu` (nomor 1-16), lalu `kucing` (nomor
  17-32).

## Hasil

Rekap lengkap seluruh pengujian (32 baris) dicatat pada spreadsheet
berikut:
[Pencatatan Hasil Pengujian Skripsi](https://docs.google.com/spreadsheets/d/1jAHLK298xYfTonicSSep1OiYDAIqJD8YHR2758-3PZU).

Nama file citra stego di `3_hasil/` berformat:

```
objek_resolusi_ukuranteks_key.png
```

Contoh: `kucing_128x_2KB_3815ef4f500b04c2ec2aba5dc3978a0f.png`.
Bagian `key` adalah kunci AES-128 (32 karakter heksadesimal) yang
dibutuhkan untuk mengekstraksi teks dari citra tersebut.

Dua kombinasi tidak menghasilkan citra stego karena kapasitas citra
tidak cukup: `pintu_128x` dan `kucing_128x` dengan teks 8 KB.
Karena itu, tiap objek memiliki 15 citra stego (bukan 16).
