# README Dataset

## Dataset Final

File final fase 1:

```text
final/hermina_reviews_balanced_300_per_branch.csv
```

Jumlah data:

- `14.785` review final
- `54` cabang
- maksimal `300` review per cabang
- `40` cabang mencapai `300`
- `14` cabang mentok di bawah `300`

## File Pendukung

```text
final/branch_distribution_300_per_branch.csv
```

Berisi jumlah review final per cabang.

```text
final/final_dataset_status.json
```

Berisi ringkasan status final dalam format JSON.

```text
raw/hermina_google_maps_reviews_logged_in.csv
```

Raw hasil scrape Google Maps browser.

```text
raw/hermina_jasaterdekat_reviews.csv
```

Raw mirror publik yang dipakai sebagai tambahan stok review.

```text
metadata/hermina_official_branches.csv
metadata/hermina_google_maps_metadata.csv
```

Metadata cabang resmi dan mapping ke Google Maps.

## Kolom Penting

- `review_id`: ID dedupe final.
- `source`: asal data, direct Google Maps atau mirror publik.
- `official_name`: nama cabang resmi yang dipakai untuk grouping.
- `official_province`: provinsi dari metadata cabang.
- `google_name`: nama tempat di Google Maps.
- `google_rating`: rating Google Maps tempat.
- `reviewer_hash`: hash nama reviewer, bukan nama asli.
- `review_rating`: rating review individual.
- `review_time_text`: waktu relatif review dari Google Maps.
- `review_text`: teks review untuk fase cleaning dan model.
- `source_url`: URL Google Maps atau sumber mirror.

## Cabang Yang Mentok Di Bawah 300

Cabang ini tetap dipakai apa adanya karena hasil scrape sudah mentok atau review teks publiknya memang tidak cukup:

- Hermina Badung: 56
- Hermina Bogor: 73
- Hermina Karawang: 100
- Hermina Kendari: 100
- Hermina Nusantara: 113
- Hermina Salatiga: 181
- RS Hermina PIK Dua: 192
- RSU Hermina Aceh: 263
- Hermina Sukabumi: 273
- Hermina Serpong: 275
- Hermina Mutiara Bunda Salatiga: 276
- Hermina Madiun: 287
- Hermina Arcamanik: 298
- Hermina Pasteur: 298

## Untuk Fase 2 Cleaning

Gunakan file final balanced sebagai input:

```text
final/hermina_reviews_balanced_300_per_branch.csv
```

Jangan edit file ini langsung. Simpan output cleaning ke file baru, misalnya:

```text
clean/hermina_reviews_cleaned_phase2.csv
```

