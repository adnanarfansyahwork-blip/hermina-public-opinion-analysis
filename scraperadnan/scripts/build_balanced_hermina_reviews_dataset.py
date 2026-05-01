import argparse
import csv
import hashlib
import json
import re
from collections import defaultdict
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"
DIRECT_CSV = DATA_DIR / "hermina_google_maps_reviews_logged_in.csv"
MIRROR_CSV = DATA_DIR / "hermina_jasaterdekat_reviews.csv"
DEFAULT_OUTPUT_TEMPLATE = "hermina_reviews_balanced_{cap}_per_branch.csv"
DEFAULT_SUMMARY_TEMPLATE = "hermina_reviews_balanced_{cap}_per_branch_summary.json"


FIELDS = [
    "review_id",
    "source",
    "source_url",
    "official_name",
    "official_province",
    "google_place_id",
    "google_name",
    "google_rating",
    "latitude",
    "longitude",
    "reviewer_hash",
    "review_rating",
    "review_date",
    "review_time_text",
    "review_text",
    "collected_at_utc",
]


def normalize_text(value):
    value = (value or "").lower()
    value = re.sub(r"\s+", " ", value)
    value = re.sub(r"[^\w\s]", "", value)
    return value.strip()


def read_csv(path):
    if not path.exists():
        return []
    with path.open(newline="", encoding="utf-8-sig") as handle:
        return list(csv.DictReader(handle))


def normalize_row(row, fallback_source):
    official_name = row.get("official_name") or ""
    review_text = " ".join((row.get("review_text") or "").split())
    if not official_name or len(review_text) < 8:
        return None

    # Keep the final training dataset strict: identical review text in the same
    # branch is treated as a duplicate even if source/date/rating differs.
    review_key = "|".join([official_name, normalize_text(review_text)])
    review_id = hashlib.sha256(review_key.encode("utf-8")).hexdigest()[:20]
    return {
        "review_id": review_id,
        "source": row.get("source") or fallback_source,
        "source_url": row.get("source_url") or "",
        "official_name": official_name,
        "official_province": row.get("official_province") or "",
        "google_place_id": row.get("google_place_id") or "",
        "google_name": row.get("google_name") or row.get("place_name") or official_name,
        "google_rating": row.get("google_rating") or "",
        "latitude": row.get("latitude") or "",
        "longitude": row.get("longitude") or "",
        "reviewer_hash": row.get("reviewer_hash") or "",
        "review_rating": row.get("review_rating") or "",
        "review_date": row.get("review_date") or "",
        "review_time_text": row.get("review_time_text") or "",
        "review_text": review_text,
        "collected_at_utc": row.get("collected_at_utc") or "",
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--cap-per-branch", type=int, default=500)
    parser.add_argument("--output-csv", type=Path, default=None)
    parser.add_argument("--summary-json", type=Path, default=None)
    args = parser.parse_args()
    output_csv = args.output_csv or DATA_DIR / DEFAULT_OUTPUT_TEMPLATE.format(cap=args.cap_per_branch)
    summary_json = args.summary_json or DATA_DIR / DEFAULT_SUMMARY_TEMPLATE.format(cap=args.cap_per_branch)

    rows = []
    for row in read_csv(DIRECT_CSV):
        normalized = normalize_row(row, "google_maps_direct_browser")
        if normalized:
            rows.append(normalized)
    for row in read_csv(MIRROR_CSV):
        normalized = normalize_row(row, "jasaterdekat_google_maps_mirror")
        if normalized:
            rows.append(normalized)

    deduped = {}
    source_priority = {
        "google_maps_direct_browser": 0,
        "jasaterdekat_google_maps_mirror": 1,
    }
    for row in rows:
        existing = deduped.get(row["review_id"])
        if not existing or source_priority.get(row["source"], 99) < source_priority.get(existing["source"], 99):
            deduped[row["review_id"]] = row

    grouped = defaultdict(list)
    for row in deduped.values():
        grouped[row["official_name"]].append(row)

    output_rows = []
    summary = []
    for branch in sorted(grouped):
        branch_rows = grouped[branch]
        branch_rows.sort(
            key=lambda row: (
                source_priority.get(row["source"], 99),
                row.get("review_date") or row.get("review_time_text") or "",
                row["review_id"],
            )
        )
        selected = branch_rows[: args.cap_per_branch]
        output_rows.extend(selected)
        summary.append(
            {
                "official_name": branch,
                "available_reviews": len(branch_rows),
                "selected_reviews": len(selected),
                "direct_reviews": sum(1 for row in branch_rows if row["source"] == "google_maps_direct_browser"),
                "mirror_reviews": sum(1 for row in branch_rows if row["source"] == "jasaterdekat_google_maps_mirror"),
            }
        )

    with output_csv.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(output_rows)

    summary_json.write_text(
        json.dumps(
            {
                "cap_per_branch": args.cap_per_branch,
                "total_selected_reviews": len(output_rows),
                "branch_count_with_reviews": len(summary),
                "branches": summary,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    print(f"Saved {len(output_rows)} balanced reviews to {output_csv}")


if __name__ == "__main__":
    main()
