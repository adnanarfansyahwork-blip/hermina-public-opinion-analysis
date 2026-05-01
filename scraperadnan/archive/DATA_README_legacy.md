# Dataset Hermina Google Maps

Data dibuat pada 2026-04-29 untuk kebutuhan pemetaan distribusi opini publik layanan RS Hermina.

## File

- `data/hermina_official_branches.csv`
  - Daftar 54 cabang dari API publik Hermina Hospitals.
  - Berisi nama cabang, provinsi, alamat, koordinat resmi, dan deskripsi singkat.

- `data/hermina_google_maps_metadata.csv`
  - Daftar 54 cabang yang sudah dicocokkan ke Google Maps.
  - Berisi `google_place_id`, `google_feature_id`, `google_cid_decimal`, rating, kategori, alamat, koordinat Google Maps, URL Maps, dan jarak dari koordinat resmi.

- `data/fetch_summary.json`
  - Ringkasan hasil scraping dan diagnostik query.

- `data/hermina_google_maps_reviews_logged_in.csv`
  - Review yang diambil langsung dari Google Maps via browser automation.
  - Scraper berjalan mode round-robin agar cabang seimbang.

- `data/hermina_jasaterdekat_reviews.csv`
  - Mirror review Google Maps dari halaman publik JasaTerdekat.
  - Dipakai sebagai stok awal supaya cabang yang sudah punya banyak review tidak mendominasi jadwal scraping.

- `data/hermina_reviews_balanced_500_per_branch.csv`
  - Dataset gabungan yang sudah deduplicate dan dibatasi maksimal 500 review per cabang.

## Catatan Review Google Maps

Saat diakses tanpa login, Google Maps menampilkan mode terbatas dan tidak memunculkan teks review untuk halaman rumah sakit. Karena itu, file metadata sudah tersedia, tetapi teks review Google Maps belum bisa ditarik langsung dari browser tanpa akses terautentikasi atau Google Places API key.

Untuk mengambil review resmi dari Google Places API:

```powershell
$env:GOOGLE_MAPS_API_KEY="YOUR_KEY"
python scripts\fetch_hermina_google_places_reviews.py --reviews-sort newest
```

Output akan tersimpan ke:

```text
data/hermina_google_maps_reviews.csv
```

Skrip review menyimpan `reviewer_hash`, bukan nama reviewer, agar dataset lebih aman untuk penelitian.

## Balanced Scraping

Target ideal 500 review per 54 cabang adalah 27.000 review. Untuk menjaga distribusi, scraper dijalankan bertahap: semua cabang dikejar ke 50 review dulu, lalu 100, 150, dan seterusnya sampai 500.

```powershell
python -u scripts\scrape_google_maps_reviews_logged_in.py --target 27000 --coverage-min 500 --round-step 50 --include-mirror-counts --delay-ms 1800 --max-scroll-rounds 180 --stagnant-rounds 10
```

Bangun ulang dataset gabungan:

```powershell
python scripts\build_balanced_hermina_reviews_dataset.py --cap-per-branch 500
```

## Quality Check

Semua 54 cabang berhasil dipasangkan ke Google Maps. Ada 2 cabang dengan selisih koordinat lebih dari 1 km antara API Hermina dan Google Maps, sehingga sebaiknya dicek manual sebelum visualisasi final:

- Hermina Manado: 1.6863 km
- Hermina Periuk Tangerang: 1.0071 km

## Reproduce

```powershell
python scripts\fetch_hermina_google_maps_metadata.py
```

Sumber:

- Hermina Hospitals public API: `https://api.herminahospitals.com/api/v1/public/hospitals`
- Google Maps search metadata: `https://www.google.com/search?tbm=map`
- Google Places Details API untuk review: `https://maps.googleapis.com/maps/api/place/details/json`
