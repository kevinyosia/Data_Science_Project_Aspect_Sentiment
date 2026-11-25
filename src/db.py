import os
from dotenv import load_dotenv
from sqlalchemy import create_engine, text
from sqlalchemy.engine import URL

load_dotenv()


def get_engine():
    url = URL.create(
        "postgresql+psycopg2",
        username=os.getenv("DB_USER"),
        password=os.getenv("DB_PASSWORD"),
        host=os.getenv("DB_HOST"),
        port=int(os.getenv("DB_PORT", 5432)),
        database=os.getenv("DB_NAME"),
    )
    return create_engine(url)


def init_db(engine):
    with engine.begin() as conn:
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS reviews (
                review_id    TEXT PRIMARY KEY,
                app_id       TEXT NOT NULL,
                content      TEXT,
                score        SMALLINT,
                thumbs_up    INTEGER,
                app_version  TEXT,
                reviewed_at  TIMESTAMP,
                scraped_at   TIMESTAMP DEFAULT NOW()
            )
        """))
        conn.execute(text("""
            CREATE INDEX IF NOT EXISTS idx_reviews_app_time
            ON reviews (app_id, reviewed_at)
        """))


def get_latest_review_time(engine, app_id):
    with engine.connect() as conn:
        return conn.execute(
            text("SELECT MAX(reviewed_at) FROM reviews WHERE app_id = :a"),
            {"a": app_id},
        ).scalar()


def insert_reviews(engine, records):
    if not records:
        return
    sql = text("""
        INSERT INTO reviews
            (review_id, app_id, content, score, thumbs_up, app_version, reviewed_at)
        VALUES
            (:review_id, :app_id, :content, :score, :thumbs_up, :app_version, :reviewed_at)
        ON CONFLICT (review_id) DO NOTHING
    """)
    with engine.begin() as conn:
        conn.execute(sql, records)


def count_reviews(engine, app_id):
    with engine.connect() as conn:
        return conn.execute(
            text("SELECT COUNT(*) FROM reviews WHERE app_id = :a"),
            {"a": app_id},
        ).scalar()