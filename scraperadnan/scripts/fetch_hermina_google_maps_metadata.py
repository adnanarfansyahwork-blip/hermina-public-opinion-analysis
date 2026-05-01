import csv
import json
import math
import time
from pathlib import Path
from urllib.parse import quote_plus

import requests


ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"
OFFICIAL_URL = "https://api.herminahospitals.com/api/v1/public/hospitals"
GOOGLE_MAPS_SEARCH_URL = "https://www.google.com/search"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    ),
    "Accept": "application/json,text/plain,*/*",
    "Accept-Language": "id-ID,id;q=0.9,en-US;q=0.8,en;q=0.7",
}


def signed_to_unsigned_64(value: int) -> int:
    return value + (1 << 64) if value < 0 else value


def hex_to_unsigned_decimal(hex_value: str) -> int:
    return int(hex_value, 16)


def haversine_km(lat1, lon1, lat2, lon2):
    if None in (lat1, lon1, lat2, lon2):
        return None
    radius = 6371.0088
    phi1 = math.radians(float(lat1))
    phi2 = math.radians(float(lat2))
    d_phi = math.radians(float(lat2) - float(lat1))
    d_lam = math.radians(float(lon2) - float(lon1))
    a = (
        math.sin(d_phi / 2) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(d_lam / 2) ** 2
    )
    return 2 * radius * math.asin(math.sqrt(a))


def strip_google_prefix(text: str) -> str:
    if text.startswith(")]}'"):
        return text.split("\n", 1)[1]
    return text


def find_first_chij(value):
    if isinstance(value, str):
        return value if value.startswith("ChIJ") else None
    if isinstance(value, list):
        for item in value:
            found = find_first_chij(item)
            if found:
                return found
    if isinstance(value, dict):
        for item in value.values():
            found = find_first_chij(item)
            if found:
                return found
    return None


def parse_direct_place(payload):
    try:
        place = payload[0][1][0][14]
    except (TypeError, IndexError):
        return None

    if not isinstance(place, list) or len(place) < 12:
        return None

    feature_id = place[10] if len(place) > 10 else None
    google_name = place[11] if len(place) > 11 else None
    coords = place[9] if len(place) > 9 else None
    rating_blob = place[4] if len(place) > 4 else None
    categories = place[13] if len(place) > 13 and isinstance(place[13], list) else []
    address_parts = place[2] if len(place) > 2 and isinstance(place[2], list) else []
    full_address = place[18] if len(place) > 18 and isinstance(place[18], str) else None

    if not feature_id or not google_name:
        return None

    lat = lon = rating = None
    if isinstance(coords, list) and len(coords) >= 4:
        lat, lon = coords[2], coords[3]
    if isinstance(rating_blob, list) and len(rating_blob) >= 8:
        rating = rating_blob[7]

    cid_decimal = None
    if isinstance(feature_id, str) and ":" in feature_id:
        try:
            cid_decimal = str(hex_to_unsigned_decimal(feature_id.split(":")[1]))
        except ValueError:
            cid_decimal = None

    return {
        "google_name": google_name,
        "google_feature_id": feature_id,
        "google_place_id": find_first_chij(place),
        "google_cid_decimal": cid_decimal,
        "google_latitude": lat,
        "google_longitude": lon,
        "google_rating": rating,
        "google_categories": "|".join(str(c) for c in categories),
        "google_address": full_address or ", ".join(str(p) for p in address_parts if p),
        "google_maps_url": (
            f"https://www.google.com/maps/search/?api=1&query={quote_plus(google_name)}"
            + (f"&query_place_id={find_first_chij(place)}" if find_first_chij(place) else "")
        ),
    }


def google_maps_search(query):
    response = requests.get(
        GOOGLE_MAPS_SEARCH_URL,
        params={"tbm": "map", "authuser": "0", "hl": "id", "gl": "id", "q": query},
        headers=HEADERS,
        timeout=30,
    )
    response.raise_for_status()
    return json.loads(strip_google_prefix(response.text))


def build_queries(attrs):
    name = attrs.get("name") or ""
    branch = attrs.get("branch") or ""
    address = attrs.get("address") or ""
    province = attrs.get("provincy_name") or ""

    queries = [
        f"{name} {address}",
        name,
        f"RS {name}",
        f"{name} {province}",
    ]

    if branch and not branch.startswith("http"):
        queries.insert(1, f"RS Hermina {branch}")

    seen = set()
    cleaned = []
    for query in queries:
        query = " ".join(str(query).split())
        if query and query.lower() not in seen:
            cleaned.append(query)
            seen.add(query.lower())
    return cleaned


def load_official_hospitals():
    headers = {
        **HEADERS,
        "Origin": "https://herminahospitals.com",
        "Referer": "https://herminahospitals.com/",
    }
    response = requests.get(OFFICIAL_URL, headers=headers, timeout=30)
    response.raise_for_status()
    return response.json()["data"]


def official_row(item):
    attrs = item["attributes"]
    return {
        "official_id": item.get("id"),
        "official_name": attrs.get("name"),
        "official_branch": attrs.get("branch"),
        "official_province": attrs.get("provincy_name"),
        "official_address": attrs.get("address"),
        "official_latitude": attrs.get("latitude"),
        "official_longitude": attrs.get("longitude"),
        "official_url": attrs.get("permalink") or attrs.get("website") or "",
        "official_about": attrs.get("about") or "",
    }


def choose_google_place(attrs):
    official_lat = attrs.get("latitude")
    official_lon = attrs.get("longitude")
    candidates = []

    for query in build_queries(attrs):
        try:
            payload = google_maps_search(query)
            place = parse_direct_place(payload)
        except Exception as exc:
            candidates.append({"query": query, "error": str(exc)})
            continue

        if place:
            distance = haversine_km(
                official_lat, official_lon, place["google_latitude"], place["google_longitude"]
            )
            place["google_query"] = query
            place["distance_km_from_official"] = round(distance, 4) if distance is not None else None
            candidates.append(place)

        time.sleep(0.25)

    valid = [c for c in candidates if c.get("google_feature_id")]
    if not valid:
        return {}, candidates

    valid.sort(key=lambda row: row.get("distance_km_from_official") if row.get("distance_km_from_official") is not None else 999999)
    return valid[0], candidates


def write_csv(path, rows, fieldnames):
    with path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def main():
    DATA_DIR.mkdir(exist_ok=True)
    hospitals = load_official_hospitals()

    official_rows = [official_row(item) for item in hospitals]
    metadata_rows = []
    diagnostics = []

    for item in hospitals:
        attrs = item["attributes"]
        base = official_row(item)
        google_place, attempts = choose_google_place(attrs)
        metadata_rows.append({**base, **google_place})
        diagnostics.append(
            {
                "official_name": attrs.get("name"),
                "selected_google_name": google_place.get("google_name"),
                "selected_query": google_place.get("google_query"),
                "attempts": attempts,
            }
        )
        print(f"{attrs.get('name')}: {google_place.get('google_name', 'NOT FOUND')}")

    official_fields = [
        "official_id",
        "official_name",
        "official_branch",
        "official_province",
        "official_address",
        "official_latitude",
        "official_longitude",
        "official_url",
        "official_about",
    ]

    metadata_fields = official_fields + [
        "google_name",
        "google_feature_id",
        "google_place_id",
        "google_cid_decimal",
        "google_latitude",
        "google_longitude",
        "google_rating",
        "google_categories",
        "google_address",
        "google_maps_url",
        "google_query",
        "distance_km_from_official",
    ]

    write_csv(DATA_DIR / "hermina_official_branches.csv", official_rows, official_fields)
    write_csv(DATA_DIR / "hermina_google_maps_metadata.csv", metadata_rows, metadata_fields)

    summary = {
        "official_branch_count": len(official_rows),
        "google_maps_matched_count": sum(1 for row in metadata_rows if row.get("google_feature_id")),
        "google_maps_unmatched": [
            row["official_name"] for row in metadata_rows if not row.get("google_feature_id")
        ],
        "note": (
            "Google Maps logged-out view exposes branch metadata/rating, but review text is "
            "not currently returned for these hospital pages without authenticated/API access."
        ),
    }

    (DATA_DIR / "fetch_summary.json").write_text(
        json.dumps({"summary": summary, "diagnostics": diagnostics}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
