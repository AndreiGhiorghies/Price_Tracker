# api.py
from fastapi import FastAPI, HTTPException, Query, Depends
from pydantic import BaseModel
from typing import Optional, List
import aiosqlite
import asyncio
from Scraper import Filters, Scraper

from Database import database_initialized, init_db

DB_PATH = "tracker.db"
APP = FastAPI(title="Price Tracker API")

# ---------- util / startup ----------
async def get_db():
    db = await aiosqlite.connect(DB_PATH)
    # return rows as tuples; we'll map manually
    try:
        yield db
    finally:
        await db.close()

@APP.on_event("startup")
async def on_startup():
    if not database_initialized:
        await init_db()
    # asigură-te că DB-ul există (poți apela init_db din modulul tău)
    # dacă ai funcția init_db importabilă, o poți apela aici.
    # from db import init_db
    # await init_db(DB_PATH)
    pass

# ---------- Pydantic models ----------
class ProductOut(BaseModel):
    id: int
    site_name: str
    external_id: str
    title: str
    link: str
    currency: Optional[str]
    last_price: Optional[int]
    rating: Optional[float]
    ratings_count: Optional[int]
    first_seen_at: str
    last_seen_at: str

class PricePoint(BaseModel):
    id: int
    product_id: int
    price_minor: Optional[int]
    captured_at: str

class ProductsList(BaseModel):
    total: int
    page: int
    per_page: int
    items: List[ProductOut]

# ---------- helpers ----------
def row_to_product(row) -> ProductOut:
    # row order must match the SELECT below
    return ProductOut(
        id=row[0],
        site_name=row[1],
        external_id=row[2],
        title=row[3],
        link=row[4],
        currency=row[5],
        last_price=row[6],
        rating=row[7],
        ratings_count=row[8],
        first_seen_at=row[9],
        last_seen_at=row[10],
    )

def row_to_price(row) -> PricePoint:
    return PricePoint(id=row[0], product_id=row[1], price_minor=row[2], captured_at=row[3])

# ---------- endpoints ----------

@APP.get("/products", response_model=ProductsList)
async def list_products(
    q: Optional[str] = Query(None, description="filtru text pe titlu"),
    site: Optional[str] = Query(None, description="filtru dupa site_name"),
    min_price: Optional[int] = Query(None, description="pret minim in minor units (bani)"),
    max_price: Optional[int] = Query(None, description="pret maxim in minor units (bani)"),
    page: int = Query(1, ge=1),
    per_page: int = Query(25, ge=1, le=200),
    db: aiosqlite.Connection = Depends(get_db)
):
    # construire WHERE
    where = []
    params = []
    if q:
        where.append("LOWER(title) LIKE ?")
        params.append(f"%{q.lower()}%")
    if site:
        where.append("site_name = ?")
        params.append(site)
    if min_price is not None:
        where.append("last_price >= ?")
        params.append(min_price)
    if max_price is not None:
        where.append("last_price <= ?")
        params.append(max_price)

    where_sql = "WHERE " + " AND ".join(where) if where else ""
    count_sql = f"SELECT COUNT(*) FROM products {where_sql}"
    async with db.execute(count_sql, params) as cur:
        row = await cur.fetchone()
        total = row[0] if row is not None else 0

    offset = (page - 1) * per_page
    select_sql = f"""
        SELECT id, site_name, external_id, title, link, currency, last_price,
               rating, ratings_count, first_seen_at, last_seen_at
        FROM products
        {where_sql}
        ORDER BY id
        LIMIT ? OFFSET ?
    """
    async with db.execute(select_sql, params + [per_page, offset]) as cur:
        rows = await cur.fetchall()

    items = [row_to_product(r) for r in rows]
    return ProductsList(total=total, page=page, per_page=per_page, items=items)

@APP.get("/products/{product_id}", response_model=ProductOut)
async def get_product(product_id: int, db: aiosqlite.Connection = Depends(get_db)):
    async with db.execute("""
        SELECT id, site_name, external_id, title, link, currency, last_price,
               rating, ratings_count, first_seen_at, last_seen_at
        FROM products WHERE id = ?
    """, (product_id,)) as cur:
        row = await cur.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Product not found")
    return row_to_product(row)

@APP.get("/products/{product_id}/history", response_model=List[PricePoint])
async def get_price_history(product_id: int,
                            limit: int = Query(200, ge=1, le=2000),
                            db: aiosqlite.Connection = Depends(get_db)):
    async with db.execute("""
        SELECT id, product_id, price_minor, captured_at
        FROM price_history
        WHERE product_id = ?
        ORDER BY captured_at
        LIMIT ?
    """, (product_id, limit)) as cur:
        rows = await cur.fetchall()
    return [row_to_price(r) for r in rows]

# Optional: forțează o rulare de scrape (trebuie să încorporezi logica ta)
@APP.post("/scrape/trigger")
async def trigger_scrape(query: Optional[str] = Query(None, description="Introduci query-ul: "),
                         db: aiosqlite.Connection = Depends(get_db)):
    """
    Endpoint demo: aici ar trebui să chemi funcția ta de scraping (async) care populează DB.
    Ca exemplu, doar returnăm ok. NU pornește automat crawlerul aici.
    """
    config_path = "config.json"
    csv_file = "produse.csv"
    filter = Filters()

    cmd = ["python", "scrape_worker.py",
            query or "",
            config_path,
            str(filter.min_price),
            str(filter.max_price),
            str(filter.min_rating),
            str(filter.min_ratings),
            csv_file]
    
    import subprocess
    subprocess.Popen(cmd)

    # exemplu: asyncio.create_task(scrape_all_sites())   # dacă ai o funcție async
    return {"ok": True, "note": "Integrează apelul către funcția ta de scraping dacă vrei."}


# python -m uvicorn API:APP --reload --host 0.0.0.0 --port 8000
