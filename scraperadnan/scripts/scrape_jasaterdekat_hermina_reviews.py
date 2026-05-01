import csv
import hashlib
import html
import json
import re
import time
from pathlib import Path
from urllib.parse import parse_qs, urljoin, urlparse

import requests
from bs4 import BeautifulSoup


ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"
METADATA_CSV = DATA_DIR / "hermina_google_maps_metadata.csv"
OUTPUT_CSV = DATA_DIR / "hermina_jasaterdekat_reviews.csv"
SUMMARY_JSON = DATA_DIR / "hermina_jasaterdekat_summary.json"
SITEMAP_INDEX_URL = "https://jasaterdekat.hpandroid.co.id/sitemap.xml"
WP_SEARCH_URL = "https://jasaterdekat.hpandroid.co.id/wp-json/wp/v2/search"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    ),
    "Accept-Language": "id-ID,id;q=0.9,en-US;q=0.8,en;q=0.7",
}


FIELDS = [
    "review_id",
    "source",
    "source_url",
    "place_page_url",
    "place_name",
    "official_name",
    "official_province",
    "google_place_id",
    "google_rating",
    "latitude",
    "longitude",
    "reviewer_hash",
    "review_rating",
    "review_date",
    "review_text",
    "collected_at_utc",
]


def fetch(url):
    response = requests.get(url, headers=HEADERS, timeout=45)
    response.raise_for_status()
    return response.text


def clean_text(value):
    if not value:
        return ""
    soup = BeautifulSoup(html.unescape(value), "html.parser")
    text = soup.get_text(" ")
    text = re.sub(r"\bSelengkapnya\b", " ", text, flags=re.I)
    return " ".join(text.split())


def normalize_key(value):
    value = (value or "").lower()
    value = re.sub(r"https?://\S+", " ", value)
    value = re.sub(r"\b(rsu|rsia|rs|rumah|sakit|umum|hospital|hospitals|hermina|managed|by)\b", " ", value)
    value = re.sub(r"[^a-z0-9]+", " ", value)
    return " ".join(value.split())


def hash_value(value):
    return hashlib.sha256((value or "").encode("utf-8")).hexdigest()[:16] if value else ""


def load_metadata():
    if not METADATA_CSV.exists():
        return []
    with METADATA_CSV.open(newline="", encoding="utf-8-sig") as handle:
        return list(csv.DictReader(handle))


def match_metadata(place_name, url, metadata_rows):
    haystack = normalize_key(f"{place_name} {url}")
    best = None
    best_score = 0

    for row in metadata_rows:
        candidates = [
            row.get("official_name"),
            row.get("google_name"),
            row.get("official_branch"),
        ]
        keys = [normalize_key(c) for c in candidates if c]
        keys = [k for k in keys if k and not k.startswith("http")]

        score = 0
        for key in keys:
            tokens = key.split()
            if key in haystack:
                score = max(score, 10 + len(tokens))
            elif tokens and all(token in haystack for token in tokens):
                score = max(score, len(tokens))

        if score > best_score:
            best = row
            best_score = score

    return best if best_score else {}


def sitemap_urls():
    index = fetch(SITEMAP_INDEX_URL)
    post_sitemaps = re.findall(r"<loc>(https://jasaterdekat\.hpandroid\.co\.id/post-sitemap\d+\.xml)</loc>", index)
    urls = []
    for sitemap in post_sitemaps:
        try:
            text = fetch(sitemap)
        except Exception as exc:
            print(f"skip sitemap {sitemap}: {exc}")
            continue

        for loc in re.findall(r"<loc>(.*?)</loc>", text):
            if "hermina" in loc.lower():
                urls.append(loc)
        time.sleep(0.15)

    try:
        response = requests.get(
            WP_SEARCH_URL,
            params={"search": "Hermina", "per_page": 100},
            headers=HEADERS,
            timeout=45,
        )
        response.raise_for_status()
        for item in response.json():
            url = item.get("url")
            if url and "hermina" in url.lower():
                urls.append(url)
    except Exception as exc:
        print(f"skip wp search: {exc}")

    seen = set()
    unique = []
    for url in urls:
        if url not in seen:
            unique.append(url)
            seen.add(url)
    return unique


def title_from_soup(soup, fallback_url):
    h1 = soup.find("h1")
    if h1:
        text = clean_text(h1.get_text(" "))
        if text:
            return text
    og = soup.find("meta", property="og:title")
    if og and og.get("content"):
        return clean_text(og["content"].split(":")[0])
    slug = Path(urlparse(fallback_url).path.strip("/")).name
    return slug.replace("-", " ").title()


def parse_review_li(li, page_url, place_name, matched, collected_at):
    author_anchor = li.select_one("a[itemprop='author']")
    author_name = clean_text(author_anchor.get_text(" ")) if author_anchor else ""
    author_href = author_anchor.get("href") if author_anchor else ""
    params = parse_qs(urlparse(author_href).query)

    rating_el = li.select_one(".review_score[itemprop='reviewRating']")
    date_el = li.select_one(".date_review[itemprop='datePublished']")
    desc_el = li.select_one(".description_review")

    review_text = ""
    if params.get("review"):
        review_text = clean_text(params["review"][0])
    if not review_text and desc_el:
        review_text = clean_text(desc_el.decode_contents())

    rating = ""
    if params.get("rating"):
        rating = params["rating"][0]
    elif rating_el and rating_el.get("data-rating"):
        rating = rating_el.get("data-rating")
    rating = rating.replace(",", ".")

    review_date = ""
    if params.get("date"):
        review_date = params["date"][0]
    elif date_el and date_el.get("data-date"):
        review_date = date_el.get("data-date")
    elif date_el:
        review_date = clean_text(date_el.get_text(" "))

    reviewer_id = params.get("id", [""])[0]
    review_identity = f"{page_url}|{reviewer_id}|{review_date}|{rating}|{review_text[:120]}"
    review_id = hashlib.sha256(review_identity.encode("utf-8")).hexdigest()[:20]

    return {
        "review_id": review_id,
        "source": "jasaterdekat_google_maps_mirror",
        "source_url": author_href or page_url,
        "place_page_url": page_url,
        "place_name": place_name,
        "official_name": matched.get("official_name", ""),
        "official_province": matched.get("official_province", ""),
        "google_place_id": matched.get("google_place_id", ""),
        "google_rating": matched.get("google_rating", ""),
        "latitude": matched.get("google_latitude", "") or matched.get("official_latitude", ""),
        "longitude": matched.get("google_longitude", "") or matched.get("official_longitude", ""),
        "reviewer_hash": hash_value(reviewer_id or author_name),
        "review_rating": rating,
        "review_date": review_date,
        "review_text": review_text,
        "collected_at_utc": collected_at,
    }


def scrape_page(url, metadata_rows, collected_at):
    review_url = url.rstrip("/") + "/review/"
    html_text = fetch(review_url)
    soup = BeautifulSoup(html_text, "html.parser")
    place_name = title_from_soup(soup, url)
    matched = match_metadata(place_name, url, metadata_rows)

    rows = []
    for li in soup.select("li[data-review-item][itemscope]"):
        row = parse_review_li(li, review_url, place_name, matched, collected_at)
        if len(row["review_text"]) >= 8:
            rows.append(row)

    return place_name, review_url, rows


def write_csv(rows):
    DATA_DIR.mkdir(exist_ok=True)
    with OUTPUT_CSV.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(rows)


def main():
    metadata_rows = load_metadata()
    urls = sitemap_urls()
    collected_at = datetime_now_utc()
    all_rows = []
    page_summaries = []
    seen_review_ids = set()

    for index, url in enumerate(urls, start=1):
        try:
            place_name, review_url, rows = scrape_page(url, metadata_rows, collected_at)
        except Exception as exc:
            print(f"[{index}/{len(urls)}] ERROR {url}: {exc}")
            page_summaries.append({"url": url, "error": str(exc), "review_count": 0})
            continue

        unique_rows = []
        for row in rows:
            if row["review_id"] in seen_review_ids:
                continue
            seen_review_ids.add(row["review_id"])
            unique_rows.append(row)

        all_rows.extend(unique_rows)
        page_summaries.append(
            {
                "url": review_url,
                "place_name": place_name,
                "official_name": unique_rows[0].get("official_name") if unique_rows else "",
                "review_count": len(unique_rows),
            }
        )
        print(f"[{index}/{len(urls)}] {place_name}: {len(unique_rows)} reviews")
        time.sleep(0.25)

    write_csv(all_rows)
    SUMMARY_JSON.write_text(
        json.dumps(
            {
                "source": "jasaterdekat_google_maps_mirror",
                "sitemap_url_count": len(urls),
                "review_count": len(all_rows),
                "pages": page_summaries,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    print(f"Saved {len(all_rows)} reviews to {OUTPUT_CSV}")


def datetime_now_utc():
    from datetime import datetime, timezone

    return datetime.now(tz=timezone.utc).isoformat()


if __name__ == "__main__":
    main()
