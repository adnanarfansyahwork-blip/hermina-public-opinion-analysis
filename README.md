# Hermina Public Opinion Analysis (Scraper + Preprocessing)

Repo ini berisi:

- **`scraperadnan/`**: hasil scraping & script untuk membangun dataset review RS Hermina (fase 1).
- **`preprocessing/`**: hasil preprocessing/cleaning & notebook untuk menyiapkan data (fase 2).

## Struktur singkat

```text
.
  scraperadnan/
    data/
      final/      # dataset final siap dipakai fase 2
      raw/        # data mentah hasil scraping
      metadata/   # metadata cabang
    scripts/      # script scraping/build dataset
    requirements.txt
    README.md

  preprocessing/
    notebooks/    # notebook cleaning/sentiment-map
    data/
      interim/    # output tahap intermediate
      processed/  # output data bersih & siap model
    reports/      # ringkasan distribusi & laporan cleaning
```

## Dataset yang dipakai (utama)

- **Dataset final (fase 1, balanced cap 300/cabang):**
  - `scraperadnan/data/final/hermina_reviews_balanced_300_per_branch.csv`
- **Distribusi cabang:**
  - `scraperadnan/data/final/branch_distribution_300_per_branch.csv`

Output preprocessing (fase 2):

- `preprocessing/data/processed/data_clean.csv`
- `preprocessing/data/processed/data_model_ready.csv`

## Setup (jika mau menjalankan ulang script)

Disarankan pakai Python environment terpisah (venv).

```powershell
cd "D:\Scraper adnan\scraperadnan"
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python -m playwright install chromium
```

Catatan: repo ini punya `.gitignore` untuk menghindari folder yang besar/sensitif seperti `scraperadnan/archive/browser_profiles/` dan file log.

## Menjalankan ulang (opsional)

Semua command dijalankan dari folder `scraperadnan`.

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

## Preprocessing

Notebook utama ada di:

- `preprocessing/notebooks/01_data_cleaning_sentiment_map.ipynb`

Buka notebook tersebut di VS Code (Jupyter) dan jalankan cell berurutan. Input/output CSV ada di bawah `preprocessing/data/` dan ringkasannya di `preprocessing/reports/`.

## Referensi

- Dokumentasi detail fase 1: lihat `scraperadnan/README.md`
- Keterangan dataset: lihat `scraperadnan/data/README_DATASET.md`
