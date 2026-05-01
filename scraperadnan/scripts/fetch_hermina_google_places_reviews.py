import argparse
import csv
import hashlib
import html
import os
import re
from datetime import datetime, timezone
from pathlib import Path

import requests


ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"
METADATA_CSV = DATA_DIR / "hermina_google_maps_metadata.csv"
OUTPUT_CSV = DATA_DIR / "hermina_google_maps_reviews.csv"
PLACES_DETAILS_URL = "https://maps.googleapis.com/maps/api/place/details/json"


def clean_review_text(value):
    if not value:
        return ""
    text = html.unescape(value)
    text = re.sub(r"<[^>]+>", " ", text)
    return " ".join(text.split())


def hash_author(value):
    if not value:
        return ""
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:16]


def epoch_to_iso(value):
    if value in (None, ""):
        return ""
    return datetime.fromtimestamp(int(value), tz=timezone.utc).isoformat()


def load_metadata():
    with METADATA_CSV.open(newline="", encoding="utf-8-sig") as handle:
        return list(csv.DictReader(handle))


def fetch_place_details(place_id, api_key, language, reviews_sort):
    params = {
        "place_id": place_id,
        "fields": "place_id,name,rating,user_ratings_total,reviews",
        "language": language,
        "reviews_sort": reviews_sort,
        "key": api_key,
    }
    response = requests.get(PLACES_DETAILS_URL, params=params, timeout=30)
    response.raise_for_status()
    payload = response.json()
    status = payload.get("status")
    if status != "OK":
        raise RuntimeError(f"{status}: {payload.get('error_message', 'no error message')}")
    return payload.get("result", {})


def write_rows(rows):
    fields = [
        "review_id",
        "official_name",
        "official_province",
        "google_place_id",
        "google_name",
        "place_rating",
        "place_user_ratings_total",
        "review_rating",
        "review_time_epoch",
        "review_time_iso_utc",
        "relative_time_description",
        "language",
        "original_language",
        "translated",
        "review_text",
        "reviewer_hash",
        "reviews_sort",
        "source_url",
        "collected_at_utc",
    ]
    with OUTPUT_CSV.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--language", default="id")
    parser.add_argument(
        "--reviews-sort",
        default="newest",
        choices=["newest", "most_relevant"],
        help="Google Places review ordering.",
    )
    args = parser.parse_args()

    api_key = os.environ.get("GOOGLE_MAPS_API_KEY")
    if not api_key:
        raise SystemExit(
            "Set GOOGLE_MAPS_API_KEY first, then rerun this script. "
            "Example: $env:GOOGLE_MAPS_API_KEY='YOUR_KEY'; python scripts\\fetch_hermina_google_places_reviews.py"
        )

    if not METADATA_CSV.exists():
        raise SystemExit(
            f"{METADATA_CSV} not found. Run scripts\\fetch_hermina_google_maps_metadata.py first."
        )

    collected_at = datetime.now(tz=timezone.utc).isoformat()
    rows = []

    for place in load_metadata():
        place_id = place.get("google_place_id")
        if not place_id:
            print(f"SKIP {place.get('official_name')}: missing google_place_id")
            continue

        try:
            details = fetch_place_details(place_id, api_key, args.language, args.reviews_sort)
        except Exception as exc:
            print(f"ERROR {place.get('official_name')}: {exc}")
            continue

        reviews = details.get("reviews") or []
        print(f"{place.get('official_name')}: {len(reviews)} reviews")

        for review in reviews:
            text = clean_review_text(review.get("text"))
            review_time = review.get("time")
            review_id_base = f"{place_id}|{review_time}|{review.get('rating')}|{text[:40]}"
            rows.append(
                {
                    "review_id": hashlib.sha256(review_id_base.encode("utf-8")).hexdigest()[:20],
                    "official_name": place.get("official_name"),
                    "official_province": place.get("official_province"),
                    "google_place_id": place_id,
                    "google_name": details.get("name") or place.get("google_name"),
                    "place_rating": details.get("rating"),
                    "place_user_ratings_total": details.get("user_ratings_total"),
                    "review_rating": review.get("rating"),
                    "review_time_epoch": review_time,
                    "review_time_iso_utc": epoch_to_iso(review_time),
                    "relative_time_description": review.get("relative_time_description"),
                    "language": review.get("language"),
                    "original_language": review.get("original_language"),
                    "translated": review.get("translated"),
                    "review_text": text,
                    "reviewer_hash": hash_author(review.get("author_name")),
                    "reviews_sort": args.reviews_sort,
                    "source_url": place.get("google_maps_url"),
                    "collected_at_utc": collected_at,
                }
            )

    write_rows(rows)
    print(f"Saved {len(rows)} reviews to {OUTPUT_CSV}")


if __name__ == "__main__":
    main()
