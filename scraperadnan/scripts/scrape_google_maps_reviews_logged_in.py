import argparse
import csv
import hashlib
import multiprocessing as mp
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote_plus

from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
from playwright.sync_api import sync_playwright


ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"
PROFILE_DIR = ROOT / "chrome-profile-google-maps"
METADATA_CSV = DATA_DIR / "hermina_google_maps_metadata.csv"
OUTPUT_CSV = DATA_DIR / "hermina_google_maps_reviews_logged_in.csv"
MIRROR_CSV = DATA_DIR / "hermina_jasaterdekat_reviews.csv"


OUTPUT_FIELDS = [
    "review_id",
    "official_name",
    "official_province",
    "google_place_id",
    "google_name",
    "google_rating",
    "reviewer_hash",
    "review_rating",
    "review_time_text",
    "review_text",
    "source_url",
    "collected_at_utc",
]


def normalize_text(value):
    return " ".join((value or "").split())


def normalize_text_key(value):
    value = (value or "").lower()
    value = re.sub(r"\s+", " ", value)
    value = re.sub(r"[^\w\s]", "", value)
    return value.strip()


def hash_value(value):
    if not value:
        return ""
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:16]


def build_maps_url(place):
    place_id = place.get("google_place_id") or ""
    name = place.get("google_name") or place.get("official_name") or "RS Hermina"
    url = f"https://www.google.com/maps/search/?api=1&query={quote_plus(name)}"
    if place_id:
        url += f"&query_place_id={quote_plus(place_id)}"
    return url


def load_places():
    with METADATA_CSV.open(newline="", encoding="utf-8-sig") as handle:
        return list(csv.DictReader(handle))


def as_csv_paths(paths=None):
    if paths is None:
        return [OUTPUT_CSV]
    if isinstance(paths, (str, Path)):
        return [Path(paths)]
    return [Path(path) for path in paths]


def load_seen_review_ids(paths=None):
    ids = set()
    for path in as_csv_paths(paths):
        if not path.exists():
            continue
        with path.open(newline="", encoding="utf-8-sig") as handle:
            ids.update(row["review_id"] for row in csv.DictReader(handle) if row.get("review_id"))
    return ids


def load_seen_text_keys(include_mirror=False, paths=None):
    keys = set()

    def add_from(path):
        if not path.exists():
            return
        with path.open(newline="", encoding="utf-8-sig") as handle:
            for row in csv.DictReader(handle):
                branch = row.get("official_name") or row.get("google_name") or ""
                text = normalize_text_key(row.get("review_text") or "")
                if branch and text:
                    keys.add((branch, text))

    for path in as_csv_paths(paths):
        add_from(path)
    if include_mirror:
        add_from(MIRROR_CSV)
    return keys


def load_counts_by_place(paths=None):
    counts = {}
    for path in as_csv_paths(paths):
        if not path.exists():
            continue
        with path.open(newline="", encoding="utf-8-sig") as handle:
            for row in csv.DictReader(handle):
                name = row.get("official_name") or row.get("google_name") or ""
                if not name:
                    continue
                counts[name] = counts.get(name, 0) + 1
    return counts


def load_seed_counts_by_place():
    counts = {}
    if not MIRROR_CSV.exists():
        return counts
    with MIRROR_CSV.open(newline="", encoding="utf-8-sig") as handle:
        for row in csv.DictReader(handle):
            name = row.get("official_name") or ""
            text = (row.get("review_text") or "").strip()
            if not name or len(text) < 8:
                continue
            counts[name] = counts.get(name, 0) + 1
    return counts


def append_rows(rows, output_csv=OUTPUT_CSV):
    if not rows:
        return
    output_csv = Path(output_csv)
    output_csv.parent.mkdir(exist_ok=True)
    exists = output_csv.exists()
    with output_csv.open("a", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=OUTPUT_FIELDS)
        if not exists:
            writer.writeheader()
        writer.writerows(rows)


def log(message):
    print(message, flush=True)


def wait_for_manual_login(page, timeout_seconds):
    page.goto("https://www.google.com/maps", wait_until="domcontentloaded", timeout=60000)
    deadline = time.time() + timeout_seconds
    log("")
    log("Chrome sudah dibuka.")
    log("Silakan login Google di jendela Chrome itu. Jangan masukkan password di chat.")
    log("Scraper akan lanjut otomatis setelah tombol Login tidak terlihat lagi.")
    log("")

    while time.time() < deadline:
        body = ""
        try:
            body = page.locator("body").inner_text(timeout=3000)
        except PlaywrightTimeoutError:
            pass

        login_visible = "Login" in body or "Sign in" in body
        limited_visible = "tampilan terbatas" in body.lower() or "limited version" in body.lower()
        if not login_visible and not limited_visible:
            log("Login terdeteksi. Lanjut scraping.")
            return True
        time.sleep(5)

    log("Waktu tunggu login habis. Scraper tetap mencoba memakai sesi yang ada.")
    return False


def safe_click_first(page, selectors, timeout=1500):
    for selector in selectors:
        try:
            locator = page.locator(selector).first
            if locator.count() and locator.is_visible(timeout=timeout):
                locator.click(timeout=timeout)
                return True
        except Exception:
            continue
    return False


def open_reviews_panel(page):
    selectors = [
        "button[aria-label*='Ulasan']",
        "button[aria-label*='Reviews']",
        "div[role='tab']:has-text('Ulasan')",
        "div[role='tab']:has-text('Reviews')",
        "button:has-text('Ulasan')",
        "button:has-text('Reviews')",
    ]
    if safe_click_first(page, selectors, timeout=3000):
        page.wait_for_timeout(2500)
        return True

    # Some Google Maps pages expose reviews by clicking the rating block.
    rating_patterns = [
        "button:has-text('ulasan')",
        "button:has-text('reviews')",
        "a:has-text('ulasan')",
        "a:has-text('reviews')",
    ]
    if safe_click_first(page, rating_patterns, timeout=2000):
        page.wait_for_timeout(2500)
        return True

    return False


def expand_more_buttons(page):
    labels = [
        "button[aria-label='Lainnya']",
        "button[aria-label='More']",
        "button:has-text('Lainnya')",
        "button:has-text('More')",
    ]
    clicked = 0
    for selector in labels:
        try:
            buttons = page.locator(selector)
            count = min(buttons.count(), 25)
            for idx in range(count):
                try:
                    buttons.nth(idx).click(timeout=500)
                    clicked += 1
                except Exception:
                    continue
        except Exception:
            continue
    if clicked:
        page.wait_for_timeout(500)


def get_review_cards(page):
    selectors = [
        "div[data-review-id]",
        "div.jftiEf",
        "div[role='article']",
    ]
    for selector in selectors:
        locator = page.locator(selector)
        try:
            if locator.count():
                return locator
        except Exception:
            continue
    return page.locator("div[data-review-id]")


def extract_card(card):
    def first_text(selectors):
        for selector in selectors:
            try:
                locator = card.locator(selector).first
                if locator.count():
                    text = normalize_text(locator.inner_text(timeout=500))
                    if text:
                        return text
            except Exception:
                continue
        return ""

    def first_attr(selectors, attr):
        for selector in selectors:
            try:
                locator = card.locator(selector).first
                if locator.count():
                    value = locator.get_attribute(attr, timeout=500)
                    if value:
                        return value
            except Exception:
                continue
        return ""

    card_id = first_attr(["div[data-review-id]", ":scope"], "data-review-id")
    author = first_text(["div.d4r55", ".d4r55", "[class*='d4r55']"])
    text = first_text(["span.wiI7pd", ".wiI7pd", "[class*='wiI7pd']"])
    time_text = first_text(["span.rsqaWe", ".rsqaWe", "[class*='rsqaWe']"])
    rating_label = first_attr(
        ["span.kvMYJc", ".kvMYJc", "[aria-label*='bintang']", "[aria-label*='star']"],
        "aria-label",
    )

    rating = ""
    match = re.search(r"([1-5])", rating_label or "")
    if match:
        rating = match.group(1)

    return {
        "card_id": card_id,
        "author": author,
        "text": text,
        "time_text": time_text,
        "rating": rating,
    }


def scroll_reviews(
    page,
    place,
    target_for_place,
    global_seen,
    seen_text_keys,
    global_target,
    max_scroll_rounds,
    stagnant_limit,
    scroll_delay_ms,
    output_csv=OUTPUT_CSV,
):
    rows = []
    place_seen = set()
    collected_at = datetime.now(tz=timezone.utc).isoformat()
    source_url = build_maps_url(place)
    stagnant_rounds = 0
    previous_progress = None

    feed = page.locator("div[role='feed']").first
    has_feed = False
    try:
        has_feed = feed.count() > 0
    except Exception:
        has_feed = False

    for _ in range(max_scroll_rounds):
        expand_more_buttons(page)
        cards = get_review_cards(page)
        try:
            count = cards.count()
        except Exception:
            count = 0

        visible_keys = []
        for idx in range(count):
            try:
                data = extract_card(cards.nth(idx))
            except Exception:
                continue

            review_text = normalize_text(data.get("text"))
            visible_key = data.get("card_id") or (
                f"{data.get('author')}|{data.get('time_text')}|"
                f"{data.get('rating')}|{review_text[:80]}"
            )
            if visible_key:
                visible_keys.append(visible_key)
            if not review_text:
                continue

            branch_key = place.get("official_name") or place.get("google_name") or ""
            text_key = (branch_key, normalize_text_key(review_text))
            if text_key in seen_text_keys:
                continue

            base_id = data.get("card_id") or (
                f"{place.get('google_place_id')}|{data.get('author')}|"
                f"{data.get('time_text')}|{data.get('rating')}|{review_text[:80]}"
            )
            review_id = hashlib.sha256(base_id.encode("utf-8")).hexdigest()[:20]
            if review_id in global_seen:
                continue

            global_seen.add(review_id)
            seen_text_keys.add(text_key)
            place_seen.add(review_id)
            rows.append(
                {
                    "review_id": review_id,
                    "official_name": place.get("official_name"),
                    "official_province": place.get("official_province"),
                    "google_place_id": place.get("google_place_id"),
                    "google_name": place.get("google_name"),
                    "google_rating": place.get("google_rating"),
                    "reviewer_hash": hash_value(data.get("author")),
                    "review_rating": data.get("rating"),
                    "review_time_text": data.get("time_text"),
                    "review_text": review_text,
                    "source_url": source_url,
                    "collected_at_utc": collected_at,
                }
            )

            if len(rows) % 25 == 0:
                append_rows(rows, output_csv)
                rows.clear()

            if len(global_seen) >= global_target:
                append_rows(rows, output_csv)
                return
            if target_for_place and len(place_seen) >= target_for_place:
                append_rows(rows, output_csv)
                return

        current_progress = (len(place_seen), tuple(visible_keys[:3]), tuple(visible_keys[-3:]))
        if current_progress == previous_progress:
            stagnant_rounds += 1
        else:
            stagnant_rounds = 0
        previous_progress = current_progress

        if stagnant_rounds >= stagnant_limit:
            break

        if has_feed:
            try:
                feed.evaluate("(el) => el.scrollTop = el.scrollHeight")
            except Exception:
                page.mouse.wheel(0, 2500)
        else:
            page.mouse.wheel(0, 2500)
        page.wait_for_timeout(scroll_delay_ms)

    append_rows(rows, output_csv)


def scrape(args, places_override=None, output_csv=OUTPUT_CSV, profile_dir=PROFILE_DIR, worker_label=""):
    places = list(places_override) if places_override is not None else load_places()
    output_csv = Path(output_csv)
    profile_dir = Path(profile_dir)
    read_paths = [OUTPUT_CSV]
    if output_csv != OUTPUT_CSV:
        read_paths.append(output_csv)

    global_seen = load_seen_review_ids(read_paths)
    seen_text_keys = load_seen_text_keys(include_mirror=args.include_mirror_counts, paths=read_paths)
    counts_by_place = load_counts_by_place(read_paths)
    if args.include_mirror_counts:
        seed_counts = load_seed_counts_by_place()
        for name, count in seed_counts.items():
            counts_by_place[name] = counts_by_place.get(name, 0) + count
        log(f"{worker_label}Menghitung mirror publik sebagai stok awal: {sum(seed_counts.values())} review.")
    log(f"{worker_label}Review yang sudah ada: {len(global_seen)}")
    if args.coverage_min:
        log(f"{worker_label}Mode coverage-first aktif: target minimal {args.coverage_min} review per cabang.")
    if args.round_step:
        log(f"{worker_label}Mode round-robin aktif: naik per {args.round_step} review per cabang.")

    exhausted_places = set()

    with sync_playwright() as playwright:
        context = playwright.chromium.launch_persistent_context(
            str(profile_dir),
            channel="chrome",
            headless=args.headless,
            viewport={"width": 1366, "height": 900},
            locale="id-ID",
            timezone_id="Asia/Jakarta",
            args=["--start-maximized"],
        )
        page = context.new_page()

        if args.login:
            wait_for_manual_login(page, args.login_timeout)

        if args.login_only:
            log(f"{worker_label}Profil login tersimpan di: {profile_dir}")
            context.close()
            return

        def scrape_one_place(index, total, place, limit_for_place, round_label=""):
            if len(global_seen) >= args.target:
                return False

            place_key = place.get("official_name") or place.get("google_name") or ""
            prefix = f"[{index}/{total}]"
            if round_label:
                prefix = f"{round_label} {prefix}"
            if place_key in exhausted_places:
                log(f"{worker_label}{prefix} {place_key}: skip, sesi ini sudah mentok tanpa tambahan.")
                return True

            existing_for_place = counts_by_place.get(place_key, 0)
            url = build_maps_url(place)
            log(f"{worker_label}{prefix} {place_key} ({existing_for_place} existing, ambil maks {limit_for_place or 'unlimited'}) -> {url}")
            try:
                page.goto(url, wait_until="domcontentloaded", timeout=60000)
                page.wait_for_timeout(5000)
            except Exception as exc:
                log(f"{worker_label}  gagal buka halaman: {exc}")
                return True

            opened = open_reviews_panel(page)
            if not opened:
                body = ""
                try:
                    body = page.locator("body").inner_text(timeout=3000)
                except Exception:
                    pass
                if "tampilan terbatas" in body.lower() or "limited version" in body.lower():
                    log(f"{worker_label}  Google Maps masih mode terbatas; login belum aktif untuk halaman ini.")
                else:
                    log(f"{worker_label}  panel review tidak ditemukan.")
                return True

            before = len(global_seen)
            scroll_reviews(
                page,
                place,
                limit_for_place,
                global_seen,
                seen_text_keys,
                args.target,
                args.max_scroll_rounds,
                args.stagnant_rounds,
                args.scroll_delay_ms,
                output_csv,
            )
            after = len(global_seen)
            counts_by_place[place_key] = existing_for_place + (after - before)
            if after == before:
                exhausted_places.add(place_key)
            log(f"{worker_label}  tambah {after - before} review teks; total sementara {after}")
            page.wait_for_timeout(args.delay_ms)
            return True

        if args.coverage_min and args.round_step:
            thresholds = list(range(args.round_step, args.coverage_min + args.round_step, args.round_step))
            thresholds = [min(value, args.coverage_min) for value in thresholds]
            thresholds = list(dict.fromkeys(thresholds))
            for threshold in thresholds:
                if len(global_seen) >= args.target:
                    break
                log(f"{worker_label}=== Coverage round: kejar minimal {threshold} review per cabang ===")
                places.sort(key=lambda row: (counts_by_place.get(row.get("official_name"), 0), row.get("official_name") or ""))
                for index, place in enumerate(places, start=1):
                    if len(global_seen) >= args.target:
                        break
                    place_key = place.get("official_name") or place.get("google_name") or ""
                    existing_for_place = counts_by_place.get(place_key, 0)
                    if existing_for_place >= threshold:
                        continue
                    scrape_one_place(
                        index,
                        len(places),
                        place,
                        threshold - existing_for_place,
                        round_label=f"[round {threshold}]",
                    )
        else:
            if args.coverage_min:
                places.sort(key=lambda row: (counts_by_place.get(row.get("official_name"), 0), row.get("official_name") or ""))
            for index, place in enumerate(places, start=1):
                if len(global_seen) >= args.target:
                    break

                place_key = place.get("official_name") or place.get("google_name") or ""
                existing_for_place = counts_by_place.get(place_key, 0)
                limit_for_place = args.per_place_limit
                if args.coverage_min:
                    if existing_for_place >= args.coverage_min:
                        log(f"{worker_label}[{index}/{len(places)}] {place_key}: skip, sudah {existing_for_place} review.")
                        continue
                    limit_for_place = args.coverage_min - existing_for_place
                scrape_one_place(index, len(places), place, limit_for_place)

        context.close()
    log(f"{worker_label}Selesai. Output worker: {output_csv}")


def merge_worker_outputs(worker_outputs, include_mirror_counts=False):
    seen_ids = load_seen_review_ids([OUTPUT_CSV])
    seen_text_keys = load_seen_text_keys(include_mirror=include_mirror_counts, paths=[OUTPUT_CSV])
    pending = []
    added = 0
    skipped = 0
    scanned = 0

    for output in worker_outputs:
        output = Path(output)
        if not output.exists():
            continue
        with output.open(newline="", encoding="utf-8-sig") as handle:
            for row in csv.DictReader(handle):
                scanned += 1
                review_id = row.get("review_id") or ""
                branch = row.get("official_name") or row.get("google_name") or ""
                text = normalize_text_key(row.get("review_text") or "")
                text_key = (branch, text)

                if not review_id or not branch or not text:
                    skipped += 1
                    continue
                if review_id in seen_ids or text_key in seen_text_keys:
                    skipped += 1
                    continue

                seen_ids.add(review_id)
                seen_text_keys.add(text_key)
                pending.append({field: row.get(field, "") for field in OUTPUT_FIELDS})

                if len(pending) >= 500:
                    append_rows(pending, OUTPUT_CSV)
                    added += len(pending)
                    pending.clear()

    if pending:
        append_rows(pending, OUTPUT_CSV)
        added += len(pending)

    return scanned, added, skipped


def scrape_worker(args_dict, worker_places, worker_index, output_csv, profile_dir):
    args = argparse.Namespace(**args_dict)
    args.login = False
    args.login_only = False
    args.workers = 1
    label = f"[worker {worker_index}] "
    scrape(
        args,
        places_override=worker_places,
        output_csv=Path(output_csv),
        profile_dir=Path(profile_dir),
        worker_label=label,
    )


def run_parallel(args):
    worker_count = max(1, args.workers)
    places = load_places()
    counts_by_place = load_counts_by_place([OUTPUT_CSV])
    if args.include_mirror_counts:
        seed_counts = load_seed_counts_by_place()
        for name, count in seed_counts.items():
            counts_by_place[name] = counts_by_place.get(name, 0) + count

    if args.coverage_min:
        places = [
            place
            for place in places
            if counts_by_place.get(place.get("official_name") or place.get("google_name") or "", 0) < args.coverage_min
        ]

    places.sort(key=lambda row: (counts_by_place.get(row.get("official_name"), 0), row.get("official_name") or ""))
    assignments = [[] for _ in range(worker_count)]
    for index, place in enumerate(places):
        assignments[index % worker_count].append(place)
    assignments = [assignment for assignment in assignments if assignment]

    if not assignments:
        log("Tidak ada cabang yang perlu discrape berdasarkan target coverage saat ini.")
        return

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    temp_dir = DATA_DIR / "parallel_worker_outputs"
    temp_dir.mkdir(parents=True, exist_ok=True)
    profile_root = ROOT / "chrome-profiles-parallel"
    profile_root.mkdir(parents=True, exist_ok=True)
    args_dict = vars(args).copy()
    args_dict["workers"] = 1

    log(f"Mode paralel aktif: {len(assignments)} worker, {len(places)} cabang masuk antrean.")
    processes = []
    worker_outputs = []
    for index, worker_places in enumerate(assignments, start=1):
        output_csv = temp_dir / f"google_maps_worker_{stamp}_{index}.csv"
        profile_dir = profile_root / f"profile_{stamp}_{index}"
        worker_outputs.append(output_csv)
        process = mp.Process(
            target=scrape_worker,
            args=(args_dict, worker_places, index, str(output_csv), str(profile_dir)),
            name=f"google-maps-worker-{index}",
        )
        process.start()
        processes.append(process)
        log(f"[worker {index}] mulai, {len(worker_places)} cabang, output sementara: {output_csv}")

    next_merge_at = time.time() + args.merge_interval
    while any(process.is_alive() for process in processes):
        time.sleep(10)
        if args.merge_interval and time.time() >= next_merge_at:
            scanned, added, skipped = merge_worker_outputs(worker_outputs, include_mirror_counts=args.include_mirror_counts)
            log(
                "Merge sementara: "
                f"scan {scanned} row worker, tambah {added} row ke CSV utama, skip {skipped}; "
                f"total utama {len(load_seen_review_ids([OUTPUT_CSV]))}."
            )
            next_merge_at = time.time() + args.merge_interval

    failures = []
    for process in processes:
        process.join()
        if process.exitcode:
            failures.append((process.name, process.exitcode))

    scanned, added, skipped = merge_worker_outputs(worker_outputs, include_mirror_counts=args.include_mirror_counts)
    log(
        "Merge worker selesai: "
        f"scan {scanned} row sementara, tambah {added} row ke CSV utama, skip duplikat/kosong {skipped}."
    )
    log(f"Total review unik di file utama: {len(load_seen_review_ids([OUTPUT_CSV]))}")

    if failures:
        detail = ", ".join(f"{name} exit {code}" for name, code in failures)
        raise SystemExit(f"Ada worker gagal: {detail}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--target", type=int, default=3000)
    parser.add_argument("--per-place-limit", type=int, default=0)
    parser.add_argument("--coverage-min", type=int, default=0)
    parser.add_argument("--round-step", type=int, default=0)
    parser.add_argument("--include-mirror-counts", action="store_true")
    parser.add_argument("--delay-ms", type=int, default=1500)
    parser.add_argument("--scroll-delay-ms", type=int, default=1200, help="Jeda antar scroll review Google Maps.")
    parser.add_argument("--max-scroll-rounds", type=int, default=600)
    parser.add_argument("--stagnant-rounds", type=int, default=18)
    parser.add_argument("--workers", type=int, default=1, help="Jumlah proses scraper paralel. Gunakan 2-4 dulu agar Google Maps tidak terlalu agresif.")
    parser.add_argument("--merge-interval", type=int, default=60, help="Detik antar merge sementara output worker ke CSV utama saat mode paralel.")
    parser.add_argument("--headless", action="store_true", help="Jalankan Chrome tanpa jendela terlihat.")
    parser.add_argument("--login", action="store_true", help="Buka Chrome dan tunggu login manual.")
    parser.add_argument("--login-only", action="store_true", help="Hanya simpan sesi login, tidak scraping.")
    parser.add_argument("--login-timeout", type=int, default=900)
    args = parser.parse_args()
    if args.workers > 1 and not args.login and not args.login_only:
        run_parallel(args)
    else:
        scrape(args)


if __name__ == "__main__":
    main()
