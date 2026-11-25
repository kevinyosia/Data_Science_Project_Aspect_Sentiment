import json
import logging
import time
from datetime import datetime
from pathlib import Path

import yaml
from google_play_scraper import Sort, reviews

from db import count_reviews, get_engine, get_latest_review_time, init_db, insert_reviews

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parent.parent


def load_config():
    with open(ROOT / "config" / "config.yaml", encoding="utf-8") as f:
        return yaml.safe_load(f)


def fetch_batch(cfg, token):
    """Ambil satu batch review, dengan retry dan exponential backoff."""
    max_retries = cfg["scraper"]["max_retries"]
    for attempt in range(1, max_retries + 1):
        try:
            return reviews(
                cfg["app"]["id"],
                lang=cfg["app"]["lang"],
                country=cfg["app"]["country"],
                sort=Sort.NEWEST,
                count=cfg["scraper"]["batch_size"],
                continuation_token=token,
            )
        except Exception as e:
            wait = 2 ** attempt
            log.warning("Percobaan %d/%d gagal (%s). Tunggu %d detik.", attempt, max_retries, e, wait)
            time.sleep(wait)
    raise RuntimeError("Gagal mengambil review setelah beberapa percobaan")


def to_record(r, app_id):
    """Anonimisasi: userName dan userImage sengaja tidak disimpan."""
    return {
        "review_id": r["reviewId"],
        "app_id": app_id,
        "content": r["content"],
        "score": r["score"],
        "thumbs_up": r["thumbsUpCount"],
        "app_version": r.get("reviewCreatedVersion") or r.get("appVersion"),
        "reviewed_at": r["at"],
    }


def run():
    cfg = load_config()
    app_id = cfg["app"]["id"]
    max_reviews = cfg["scraper"]["max_reviews"]

    engine = get_engine()
    init_db(engine)
    last_time = get_latest_review_time(engine, app_id)
    log.info("Review terbaru di database: %s", last_time)

    raw_dir = ROOT / cfg["paths"]["raw_dir"]
    raw_dir.mkdir(parents=True, exist_ok=True)
    raw_file = raw_dir / f"{app_id}_{datetime.now():%Y%m%d_%H%M%S}.jsonl"

    token = None
    total_new = 0
    reached_old = False

    with open(raw_file, "w", encoding="utf-8") as f:
        while total_new < max_reviews and not reached_old:
            batch, token = fetch_batch(cfg, token)
            if not batch:
                break

            records = [to_record(r, app_id) for r in batch]

            # Mode incremental: berhenti saat bertemu review yang sudah ada
            if last_time:
                new_records = [r for r in records if r["reviewed_at"] > last_time]
                reached_old = len(new_records) < len(records)
            else:
                new_records = records

            for r in new_records:
                line = {**r, "reviewed_at": r["reviewed_at"].isoformat()}
                f.write(json.dumps(line, ensure_ascii=False) + "\n")

            insert_reviews(engine, new_records)
            total_new += len(new_records)
            log.info("Batch diproses: %d review baru (total sesi ini: %d)", len(new_records), total_new)

            if token is None:
                break
            time.sleep(cfg["scraper"]["sleep_seconds"])

    log.info("Selesai. Total review di database: %d", count_reviews(engine, app_id))


if __name__ == "__main__":
    run()