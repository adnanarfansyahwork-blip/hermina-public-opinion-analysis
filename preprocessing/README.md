# Preprocessing Data Ulasan RS Hermina

Tahap ini menyiapkan dataset agar sesuai dengan tujuan project **Sentiment Map RS Hermina**:

- mengklasifikasikan sentimen ulasan menjadi positif, netral, dan negatif;
- memetakan sentimen per cabang;
- mendeteksi aspek pelayanan yang dibahas;
- menentukan masalah dominan per cabang;
- menyiapkan data untuk priority score dan dashboard aplikasi.

## Input

File utama:

```text
preprocessing/data_fix.csv
```

Kolom input:

- `review_id`
- `official_name`
- `official_province`
- `google_name`
- `review_rating`
- `review_time_text`
- `review_text`

## Cara Menjalankan

```powershell
cd "D:\Scraper adnan\preprocessing"
python .\01_clean_data.py
```

## Output Utama

```text
preprocessing/data/processed/data_clean.csv
preprocessing/data/processed/data_model_ready.csv
preprocessing/reports/sentiment_map_branch_ready.csv
preprocessing/reports/aspect_summary.csv
preprocessing/reports/branch_aspect_summary.csv
preprocessing/reports/cleaning_summary.json
```

## Isi Output

- `data_clean.csv`: dataset bersih lengkap dengan teks bersih, label sentimen, dan flag aspek.
- `data_model_ready.csv`: dataset siap tahap modeling.
- `sentiment_map_branch_ready.csv`: ringkasan sentimen per cabang untuk peta dan priority score.
- `aspect_summary.csv`: ringkasan aspek pelayanan secara keseluruhan.
- `branch_aspect_summary.csv`: aspek positif/negatif dominan per cabang.
- `cleaning_summary.json`: audit hasil cleaning.

## Label Awal Sentimen

Label awal dibuat dari rating:

- rating 1-2 = `negatif`
- rating 3 = `netral`
- rating 4-5 = `positif`

Label ini masih bisa divalidasi manual pada tahap modeling agar lebih akurat.

## Aspek Pelayanan

Aspek awal yang dideteksi:

- antrean
- dokter
- perawat
- administrasi
- farmasi
- fasilitas
- biaya/BPJS
- kebersihan
- komunikasi
