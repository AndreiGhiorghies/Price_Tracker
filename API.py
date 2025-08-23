# api.py
from fastapi import FastAPI, HTTPException, Query, Depends, Body
from pydantic import BaseModel
from typing import Optional, List
import aiosqlite
import asyncio
import json

from Database import database_initialized, init_db
from fastapi.responses import JSONResponse

DB_PATH = "tracker.db"
APP = FastAPI(title="Price Tracker API")
scrape_process = None

from fastapi.middleware.cors import CORSMiddleware
APP.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------- util / startup ----------
async def get_db():
    if not database_initialized:
        await init_db(DB_PATH)
    
    db = await aiosqlite.connect(DB_PATH)
    # return rows as tuples; we'll map manually
    try:
        yield db
    finally:
        await db.close()

@APP.on_event("startup")
async def on_startup():
    if not database_initialized:
        await init_db(DB_PATH)
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
        last_seen_at=row[10].split(".")[0],
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
    page: int = Query(1),
    per_page: int = Query(25),
    order_by: Optional[str] = Query(None, description="ordoneaza produsele dupa un criteriu"),
    reversed: bool = Query(0, le=1, ge=0),
    db: aiosqlite.Connection = Depends(get_db)
):
    # construire WHERE
    allowed_per_page = [10, 25, 50]
    if per_page not in allowed_per_page:
        per_page = 25

    if page < 0:
        page = 1
    
    where = []
    params = []
    if q:
        where.append("LOWER(title) LIKE ?")
        params.append(f"%{q.lower()}%")
    if site:
        where.append("LOWER(site_name) LIKE ?")
        params.append(f"{site.lower()}%")
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

    rev_text = ""
    if reversed:
        rev_text = "DESC "
    
    page_text = ""
    if per_page != -1:
        offset = (page - 1) * per_page
        page_text = f"LIMIT {per_page} OFFSET {offset} "

    select_sql = f"""
        SELECT id, site_name, external_id, title, link, currency, last_price,
            rating, ratings_count, first_seen_at, last_seen_at
        FROM products
        {where_sql}
        ORDER BY {order_by} {rev_text}
        {page_text}
    """
    async with db.execute(select_sql, params) as cur:
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
    config_path = "config.json"
    csv_file = "produse.csv"

    cmd = ["python", "scrape_worker.py",
            query or "",
            config_path,
            csv_file]
    
    import subprocess

    global scrape_process
    scrape_process = subprocess.Popen(cmd,
                        stderr=subprocess.PIPE,
                        text=True)

    return {"ok": True}

@APP.get("/scrape/status")
def scrape_status():
    global scrape_process
    if scrape_process is None:
        return {"status": "idle"}
    elif scrape_process.poll() is None:
        return {"status": "in_progress"}
    else:
        config_path = "config.json"
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                config = json.load(f)
        except Exception:
            config = {}
        scrape_process = None
        return {"status": "done", "len_products": config["nr_changed_products"]}

@APP.delete("/products/{product_id}")
async def delete_product(product_id: int, db: aiosqlite.Connection = Depends(get_db)):
    # Șterge istoricul de prețuri
    await db.execute("DELETE FROM price_history WHERE product_id = ?", (product_id,))
    # Șterge produsul
    await db.execute("DELETE FROM products WHERE id = ?", (product_id,))
    await db.commit()

    return {"ok": True}


@APP.post("/products/bulk_delete")
async def bulk_delete_products(
    ids: List[int] = Body(..., embed=True),
    db: aiosqlite.Connection = Depends(get_db)
):
    if not ids:
        return JSONResponse({"ok": False, "error": "No ids provided"}, status_code=400)
    
    q_marks = ','.join(['?'] * len(ids))

    await db.execute(f"DELETE FROM price_history WHERE product_id IN ({q_marks})", ids)
    await db.execute(f"DELETE FROM products WHERE id IN ({q_marks})", ids)

    await db.commit()
    
    return JSONResponse({"ok": True, "deleted": len(ids)})

@APP.post("/delete_db")
async def delete_db(db: aiosqlite.Connection = Depends(get_db)):
    await db.execute("DROP TABLE PRODUCTS")
    await db.execute("DROP TABLE PRICE_HISTORY")
    
    await db.commit()

    import Database
    Database.database_initialized = False

    return {"ok": True}

@APP.post("/change_config")
async def change_config(
    min_price: Optional[str] = Query(None, description="Minimum price of the products"),
    max_price: Optional[str] = Query(None, description="Maximum price of the products"),
    min_rating: Optional[str] = Query(None, description="Minimum rating of the products"),
    min_rating_number: Optional[str] = Query(None, description="Minimum number of ratings of the products"),
):
    config_path = "config.json"
    # Citește config-ul existent
    try:
        with open(config_path, "r", encoding="utf-8") as f:
            config = json.load(f)
    except Exception:
        config = {}

    # Actualizează valorile dacă sunt trimise
    if min_price is not None:
        config["configuration"]["min_price"] = min_price
    if max_price is not None:
        config["configuration"]["max_price"] = max_price
    if min_rating is not None:
        config["configuration"]["min_rating"] = min_rating
    if min_rating_number is not None:
        config["configuration"]["min_ratings"] = min_rating_number

    # Scrie config-ul modificat
    with open(config_path, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=2, ensure_ascii=False)

    return {"ok": True}

@APP.post("/get_config")
async def get_config():
    config_path = "config.json"
    # Citește config-ul existent
    try:
        with open(config_path, "r", encoding="utf-8") as f:
            config = json.load(f)
    except Exception:
        config = {}

    return {"max_price": str(config["configuration"]["max_price"]), 
            "min_price": str(config["configuration"]["min_price"]),
            "min_rating": str(config["configuration"]["min_rating"]),
            "min_ratings": str(config["configuration"]["min_ratings"]) }

@APP.get("/get_site_settings")
async def get_site_settings(index: Optional[str] = Query(None, description="Indexul site-ului")):
    
    config_path = "config.json"
    idx = int(index if index is not None else "0")
    try:
        with open(config_path, "r", encoding="utf-8") as f:
            config = json.load(f)
    except Exception:
        config = {}

    return {
        "name": config["sites"][idx]["name"],
        "url": config["sites"][idx]["url"],
        "url_searchTemplate": config["sites"][idx]["url_searchTemplate"],
        "product": config["sites"][idx]["selectors"]["product"],
        "title": config["sites"][idx]["selectors"]["title"],
        "link": config["sites"][idx]["selectors"]["link"],
        "price": config["sites"][idx]["selectors"]["price"],
        "currency": config["sites"][idx]["selectors"]["currency"],
        "rating": config["sites"][idx]["selectors"]["rating"],
        "id": config["sites"][idx]["selectors"]["id"],
        "image_link": config["sites"][idx]["selectors"]["image_link"],
        "remove_items_with": config["sites"][idx]["selectors"]["remove_items_with"],
        "end_of_pages": config["sites"][idx]["selectors"]["end_of_pages"]
    }

@APP.post("/set_site_settings")
async def set_site_settings(
    index: Optional[str] = Query(None, description="Indexul site-ului"),
    name: Optional[str] = Query(None, description="Numele site-ului"),
    url: Optional[str] = Query(None, description="URL-ul site-ului"),
    url_searchTemplate: Optional[str] = Query(None, description="URL_searchTemplate-ul site-ului"),
    product: Optional[str] = Query(None, description="Casuta produs"),
    title: Optional[str] = Query(None, description="Titlul produsului"),
    link: Optional[str] = Query(None, description="Linkul produsului"),
    price: Optional[str] = Query(None, description="Pretul produsului"),
    currency: Optional[str] = Query(None, description="Currency-ul produsului"),
    rating: Optional[str] = Query(None, description="Ratingul produsului"),
    id: Optional[str] = Query(None, description="ID-ul produsului"),
    image_link: Optional[str] = Query(None, description="Image_link-ul produsului"),
    remove_items_with: Optional[str] = Query(None, description="Ignora produsul"),
    end_of_pages: Optional[str] = Query(None, description="Sfarsitul paginilor cu produse"),
):
    
    config_path = "config.json"
    idx = int(index if index is not None else "0")
    try:
        with open(config_path, "r", encoding="utf-8") as f:
            config = json.load(f)
    except Exception:
        config = {}

    if config and idx >= len(config["sites"]):
        config["sites"].append({
            "name": "",
            "url": "",
            "url_searchTemplate": "",
            "selectors": {
                "product": "",
                "title": "",
                "link": "",
                "price": "",
                "currency": "",
                "rating": "",
                "id": "",
                "image_link": "",
                "remove_items_with": "",
                "end_of_pages": ""
            }
        })

    config["sites"][idx]["name"] = name
    config["sites"][idx]["url"] = url if url else ""
    config["sites"][idx]["url_searchTemplate"] = url_searchTemplate if url_searchTemplate else ""
    config["sites"][idx]["selectors"]["product"] = product if product else ""
    config["sites"][idx]["selectors"]["title"] = title if title else ""
    config["sites"][idx]["selectors"]["link"] = link if link else ""
    config["sites"][idx]["selectors"]["price"] = price if price else ""
    config["sites"][idx]["selectors"]["currency"] = currency if currency else ""
    config["sites"][idx]["selectors"]["rating"] = rating if rating else ""
    config["sites"][idx]["selectors"]["id"] = id if id else ""
    config["sites"][idx]["selectors"]["image_link"] = image_link if image_link else ""
    config["sites"][idx]["selectors"]["remove_items_with"] = remove_items_with if remove_items_with else ""
    config["sites"][idx]["selectors"]["end_of_pages"] = end_of_pages if end_of_pages else ""

    with open(config_path, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=2, ensure_ascii=False)

@APP.get("/get_site_number")
async def get_site_number():
    
    config_path = "config.json"
    try:
        with open(config_path, "r", encoding="utf-8") as f:
            config = json.load(f)
    except Exception:
        config = {}

    return {"nr_sites": len(config["sites"])}

@APP.post("/delete_site")
async def delete_site(index: Optional[str] = Query(None, description="Indexul site-ului care trebuie sters")):
    try:
        if index:
            idx = int(index)
        else:
            return
    except Exception:
        return
    
    
    config_path = "config.json"
    try:
        with open(config_path, "r", encoding="utf-8") as f:
            config = json.load(f)
    except Exception:
        return

    if idx < 0 or idx >= len(config["sites"]):
        return

    del config["sites"][idx]

    with open(config_path, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=2, ensure_ascii=False)

# python -m uvicorn API:APP --reload --host 0.0.0.0 --port 8000
