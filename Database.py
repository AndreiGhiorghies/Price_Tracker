import aiosqlite
import os

from typing import Optional

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = SCRIPT_DIR + "\\tracker.db"
CONFIG_PATH = SCRIPT_DIR + "\\config.json"
NOW_SQL = "strftime('%Y-%m-%d %H:%M:%f','now','localtime')"
database_initialized = False

async def init_db(path: str = DB_PATH) -> None:
    async with aiosqlite.connect(path) as db:
        await db.executescript("""
        CREATE TABLE IF NOT EXISTS products (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          site_name TEXT NOT NULL,
          external_id TEXT NOT NULL,
          image_link TEXT NOT NULL,
          title TEXT NOT NULL,
          link TEXT NOT NULL,
          currency TEXT,
          rating REAL,
          ratings_count INTEGER,
          -- nou: last_price (poate fi NULL)
          last_price INTEGER,
          first_seen_at DATETIME NOT NULL DEFAULT (strftime('%Y-%m-%d %H:%M:%f','now','localtime')),
          last_seen_at  DATETIME NOT NULL DEFAULT (strftime('%Y-%m-%d %H:%M:%f','now','localtime')),
          watch_price INTEGER NOT NULL,
          watch_max_price INTEGER,
          UNIQUE(site_name, external_id)
        );
        CREATE TABLE IF NOT EXISTS price_history (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          product_id INTEGER NOT NULL,
          price_minor INTEGER,
          captured_at DATETIME NOT NULL DEFAULT (strftime('%Y-%m-%d %H:%M:%f','now','localtime')),
          FOREIGN KEY(product_id) REFERENCES products(id)
        );
        CREATE INDEX IF NOT EXISTS idx_products_site_external ON products(site_name, external_id);
        CREATE INDEX IF NOT EXISTS idx_products_site_link ON products(site_name, link);
        CREATE INDEX IF NOT EXISTS idx_price_history_product ON price_history(product_id, captured_at);
        """)

        await db.commit()

        global database_initialized
        database_initialized = True

async def upsert_product(db: aiosqlite.Connection,
                         site_name: str,
                         title: str,
                         link: Optional[str],
                         external_id: Optional[str],
                         image_link: Optional[str],
                         currency: Optional[str],
                         rating: Optional[float],
                         ratings_count: Optional[int],
                         min_hours_between_changes: float) -> int:

    await db.execute("""
        INSERT OR IGNORE INTO products(site_name, external_id, image_link, title, link, currency, rating, ratings_count, watch_price, watch_max_price)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (site_name, external_id, image_link, title, link, currency, rating, ratings_count, 0, 0))

    async with db.execute("""
        SELECT id, price_minor, captured_at
        FROM price_history
        WHERE product_id = ?
        ORDER BY captured_at DESC
        LIMIT 1
    """, (external_id,)) as cur:
        last_hist = await cur.fetchone()

    if last_hist:
        _, _, last_captured_at = last_hist

        async with db.execute(f"SELECT (julianday({NOW_SQL}) - julianday(?)) * 24.0", (last_captured_at,)) as q:
            diff_row = await q.fetchone()
        diff_hours = diff_row[0] if diff_row else None

        if diff_hours is not None and diff_hours < min_hours_between_changes:
            await db.execute(f"""
                UPDATE products
                SET title = ?, link = ?, currency = COALESCE(?, currency),
                    rating = COALESCE(?, rating), ratings_count = COALESCE(?, ratings_count),
                    last_seen_at = ({NOW_SQL})
                WHERE site_name = ? AND external_id = ?
            """, (title, link, currency, rating, ratings_count, site_name, external_id))

            await db.commit()

    async with db.execute("SELECT id FROM products WHERE site_name = ? AND external_id = ?", (site_name, external_id)) as cur:
        row = await cur.fetchone()
        return row[0] if row else -1

async def upsert_price_history(db: aiosqlite.Connection,
                               product_id: int,
                               price_minor: Optional[int],
                               min_hours_between_changes: float) -> None:
    
    async with db.execute("""
        SELECT id, price_minor, captured_at
        FROM price_history
        WHERE product_id = ?
        ORDER BY captured_at DESC
        LIMIT 1
    """, (product_id,)) as cur:
        last_hist = await cur.fetchone()

    if last_hist:
        _, _, last_captured_at = last_hist

        async with db.execute(f"SELECT (julianday({NOW_SQL}) - julianday(?)) * 24.0", (last_captured_at,)) as q:
            diff_row = await q.fetchone()
        diff_hours = diff_row[0] if diff_row else None

        if diff_hours is not None and diff_hours < min_hours_between_changes:
            return
        
    async with db.execute("SELECT last_price FROM products WHERE id = ?", (product_id,)) as cur:
        row = await cur.fetchone()
    last_price = row[0] if row is not None else None

    if last_price is None:
        await db.execute(f"""
            INSERT INTO price_history(product_id, price_minor, captured_at)
            VALUES (?, ?, {NOW_SQL})
        """, (product_id, price_minor))

        await db.execute(f"""
            UPDATE products
            SET last_price = ?, last_seen_at = ({NOW_SQL}), watch_price = ?, watch_max_price = ?
            WHERE id = ?
        """, (price_minor, 0, price_minor, product_id))

        await db.commit()
        return
    
    if last_price == price_minor:
        async with db.execute(
            "SELECT id FROM price_history WHERE product_id = ? ORDER BY captured_at DESC LIMIT 1",
            (product_id,)) as cur:
            last_row = await cur.fetchone()

        last_hist_id = last_row[0] if last_row is not None else None
        await db.execute(f"UPDATE price_history SET captured_at = ({NOW_SQL}) WHERE id = ?", (last_hist_id,))

        await db.execute(f"UPDATE products SET last_seen_at = ({NOW_SQL}) WHERE id = ?", (product_id,))
        await db.commit()
        return

    await db.execute(f"""
        INSERT INTO price_history(product_id, price_minor, captured_at)
        VALUES (?, ?, {NOW_SQL})
    """, (product_id, price_minor))

    await db.execute(f"""
        UPDATE products
        SET last_price = ?, last_seen_at = ({NOW_SQL})
        WHERE id = ?
    """, (price_minor, product_id))
    
    await db.commit()
