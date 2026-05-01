# Scraper Adnan - Dataset Review RS Hermina

Project ini berisi hasil scraping fase 1 untuk dataset:

`Pemetaan Distribusi Opini Publik Mengenai Pelayanan Rumah Sakit Hermina Dengan Hybrid Model Deep Learning`

## Status Final Fase 1

Scraping sudah dihentikan dan dataset final sudah dibuat.

- File utama untuk dipakai fase 2: `data/final/hermina_reviews_balanced_300_per_branch.csv`
- Total data final: `14.785` review
- Total cabang: `54`
- Cabang yang mencapai cap `300`: `40`
- Cabang yang mentok di bawah `300`: `14`
- Cap maksimal per cabang: `300`

Cabang yang di bawah `300` tetap dipakai apa adanya karena Google Maps sudah tidak memberi tambahan review teks unik yang cukup, atau cabangnya memang memiliki review teks publik lebih sedikit.

## Struktur Folder

```text
scraperadnan/
  data/
    final/
      hermina_reviews_balanced_300_per_branch.csv
      hermina_reviews_balanced_300_per_branch_summary.json
      branch_distribution_300_per_branch.csv
      final_dataset_status.json
    raw/
      hermina_google_maps_reviews_logged_in.csv
      hermina_jasaterdekat_reviews.csv
    metadata/
      hermina_official_branches.csv
      hermina_google_maps_metadata.csv
      fetch_summary.json
  scripts/
    fetch_hermina_google_maps_metadata.py
    scrape_google_maps_reviews_logged_in.py
    scrape_jasaterdekat_hermina_reviews.py
    build_balanced_hermina_reviews_dataset.py
    fetch_hermina_google_places_reviews.py
  logs/
    log run fokus 300 terakhir
  archive/
    output lama, log lama, dan browser profile/cache
```

## File Yang Dipakai Untuk Fase 2

Gunakan file ini:

```text
data/final/hermina_reviews_balanced_300_per_branch.csv
```

File ini sudah:

- dedupe berdasarkan `official_name + review_text` yang dinormalisasi
- menggabungkan sumber Google Maps browser scrape dan mirror publik
- membatasi cabang besar maksimal `300` review
- mempertahankan cabang kecil yang mentok di bawah `300`
- menyimpan metadata cabang, rating review, teks review, dan sumber data

Untuk melihat distribusi cabang:

```text
data/final/branch_distribution_300_per_branch.csv
```

## Cara Menjalankan Ulang Jika Perlu

Jalankan dari folder `scraperadnan`:

```powershell
cd "D:\Scraper adnan\scraperadnan"
```

Install dependency jika environment baru:

```powershell
pip install -r requirements.txt
python -m playwright install chromium
```

Ambil metadata cabang Hermina dan mapping Google Maps:

```powershell
python scripts\fetch_hermina_google_maps_metadata.py
```

Scrape Google Maps dengan target rata 300 per cabang:

```powershell
python -u scripts\scrape_google_maps_reviews_logged_in.py --target 21600 --coverage-min 300 --include-mirror-counts --delay-ms 900 --scroll-delay-ms 850 --max-scroll-rounds 240 --stagnant-rounds 10 --workers 4 --merge-interval 30
```

Bangun ulang dataset final cap 300 per cabang:

```powershell
python scripts\build_balanced_hermina_reviews_dataset.py --cap-per-branch 300
```

## Catatan Penting

- Jangan memakai file raw langsung untuk model, karena distribusi cabang belum dibatasi.
- Untuk fase 2 cleaning, mulai dari file final balanced.
- Kolom `review_text` adalah teks utama untuk cleaning NLP.
- Kolom `review_rating` bisa dipakai sebagai weak label awal sentimen.
- Kolom `official_name` dipakai untuk sentiment map per cabang.
- Kolom `official_province`, `latitude`, dan `longitude` belum lengkap untuk semua baris final; jika perlu peta geografis, join ulang dengan `data/metadata/hermina_official_branches.csv`.

## Rekomendasi Fase 2 Cleaning

Urutan cleaning yang disarankan:

1. Hapus baris dengan `review_text` kosong atau terlalu pendek.
2. Normalisasi huruf kecil.
3. Hapus URL, emoji, simbol, dan spasi berlebih.
4. Normalisasi slang/kata tidak baku bahasa Indonesia.
5. Buat label sentimen awal dari `review_rating`:
   - rating 1-2: negatif
   - rating 3: netral
   - rating 4-5: positif
6. Cek ulang manual sebagian data untuk validasi label.
7. Simpan hasil cleaning sebagai file baru, jangan menimpa file fase 1.
