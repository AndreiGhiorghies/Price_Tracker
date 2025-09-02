import sqlite3
from datetime import datetime, timedelta
import random

DB_PATH = "Data\\tracker.db"
EXTERNAL_ID = 1

def insert_price_history(n=10):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    # Generează n înregistrări cu prețuri random și date consecutive
    now = datetime.now()
    base_price = 3549

    for i in range(n):
        captured_at = (now - timedelta(days=n-i)).strftime("%Y-%m-%d %H:%M:%S")
        price_minor = base_price + random.randint(-500, 500)
        cur.execute(
            "INSERT INTO price_history (product_id, price_minor, captured_at) VALUES (?, ?, ?)",
            (EXTERNAL_ID, price_minor, captured_at)
        )
    conn.commit()

    cur.execute("SELECT COUNT(*) FROM price_history WHERE product_id = ?", (EXTERNAL_ID,))
    count = cur.fetchone()[0]
    conn.close()
    print(f"Inserted {n} rows for external_id={EXTERNAL_ID}")
    print(f"Total rows with external_id={EXTERNAL_ID}: {count}")

if __name__ == "__main__":
    insert_price_history(10)
