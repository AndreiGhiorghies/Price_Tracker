import aiosqlite
import json

from fastapi.responses import JSONResponse, StreamingResponse
from fastapi import FastAPI, HTTPException, Query, Depends, Body
from fastapi.middleware.cors import CORSMiddleware
from Database import database_initialized, init_db, DB_PATH, CONFIG_PATH
from pydantic import BaseModel
from typing import Optional, List

APP = FastAPI(title="Price Tracker API")
scrape_process = None

APP.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

async def get_db():
    if not database_initialized:
        await init_db(DB_PATH)
    
    db = await aiosqlite.connect(DB_PATH)

    try:
        yield db
    finally:
        await db.close()

@APP.on_event("startup")
async def on_startup():
    if not database_initialized:
        await init_db(DB_PATH)

class NumbersRequest(BaseModel):
    numbers: List[int]

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
        first_seen_at=row[9].split(".")[0],
        last_seen_at=row[10].split(".")[0],
    )

def row_to_price(row) -> PricePoint:
    return PricePoint(id=row[0], product_id=row[1], price_minor=row[2], captured_at=row[3].split(".")[0])

@APP.get("/products", response_model=ProductsList)
async def list_products(
    q: Optional[str] = Query(None, description="text filter on title"),
    site: Optional[str] = Query(None, description="filter by site_name"),
    min_price: Optional[int] = Query(None, description="minimum price in minor units (cents)"),
    max_price: Optional[int] = Query(None, description="maximum price in minor units (cents)"),
    page: int = Query(1),
    per_page: int = Query(25),
    order_by: Optional[str] = Query(None, description="order products by a criterion"),
    reversed: bool = Query(0, le=1, ge=0),
    db: aiosqlite.Connection = Depends(get_db)
):
    if per_page not in [10, 25, 50]:
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
async def get_price_history(
    product_id: int,
    limit: int = Query(200, ge=1, le=2000),
    db: aiosqlite.Connection = Depends(get_db)
):
    async with db.execute("""
        SELECT id, product_id, price_minor, captured_at
        FROM price_history
        WHERE product_id = ?
        ORDER BY captured_at
        LIMIT ?
    """, (product_id, limit)) as cur:
        rows = await cur.fetchall()
    
    return [row_to_price(r) for r in rows]

@APP.post("/scrape/trigger")
async def trigger_scrape(query: Optional[str] = Query(None, description="Enter the query: ")):
    cmd = ["python", "scrape_worker.py",
            query or "",
            CONFIG_PATH]
    
    import subprocess

    global scrape_process
    scrape_process = subprocess.Popen(cmd, stderr=subprocess.PIPE, text=True)

    return {"ok": True}

@APP.get("/scrape/status")
def scrape_status():
    global scrape_process

    if scrape_process is None:
        return {"status": "idle"}
    elif scrape_process.poll() is None:
        return {"status": "in_progress"}
    else:
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                config = json.load(f)
        except Exception:
            config = {}
        
        scrape_process = None
        return {"status": "done", "len_products": config["nr_changed_products"]}

@APP.post("/products/bulk_delete")
async def bulk_delete_products(
    ids: NumbersRequest,
    db: aiosqlite.Connection = Depends(get_db)
):
    if not ids:
        return JSONResponse({"ok": False, "error": "No ids provided"}, status_code=400)
    
    q_marks = ','.join(['?'] * len(ids.numbers))

    await db.execute(f"DELETE FROM price_history WHERE product_id IN ({q_marks})", ids.numbers)
    await db.execute(f"DELETE FROM products WHERE id IN ({q_marks})", ids.numbers)

    await db.commit()
    
    return JSONResponse({"ok": True, "deleted": len(ids.numbers)})

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
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            config = json.load(f)
    except Exception:
        config = {}

    if min_price is not None:
        config["configuration"]["min_price"] = min_price
    if max_price is not None:
        config["configuration"]["max_price"] = max_price
    if min_rating is not None:
        config["configuration"]["min_rating"] = min_rating
    if min_rating_number is not None:
        config["configuration"]["min_ratings"] = min_rating_number

    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=2, ensure_ascii=False)

    return {"ok": True}

@APP.post("/get_config")
async def get_config():
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            config = json.load(f)
    except Exception:
        config = {}

    return {"max_price": str(config["configuration"]["max_price"]), 
            "min_price": str(config["configuration"]["min_price"]),
            "min_rating": str(config["configuration"]["min_rating"]),
            "min_ratings": str(config["configuration"]["min_ratings"]) }

@APP.get("/get_site_settings")
async def get_site_settings(index: Optional[str] = Query(None, description="Site index")):
    idx = int(index if index is not None else "0")
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
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
    index: Optional[str] = Query(None, description="Site index"),
    name: Optional[str] = Query(None, description="Site name"),
    url: Optional[str] = Query(None, description="Site URL"),
    url_searchTemplate: Optional[str] = Query(None, description="Site search template URL"),
    product: Optional[str] = Query(None, description="Product selector"),
    title: Optional[str] = Query(None, description="Product title selector"),
    link: Optional[str] = Query(None, description="Product link selector"),
    price: Optional[str] = Query(None, description="Product price selector"),
    currency: Optional[str] = Query(None, description="Product currency selector"),
    rating: Optional[str] = Query(None, description="Product rating selector"),
    id: Optional[str] = Query(None, description="Product ID selector"),
    image_link: Optional[str] = Query(None, description="Product image link selector"),
    remove_items_with: Optional[str] = Query(None, description="Ignore product selector"),
    end_of_pages: Optional[str] = Query(None, description="End of product pages selector"),
):
    
    idx = int(index if index is not None else "0")
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
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

    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=2, ensure_ascii=False)

@APP.get("/get_site_number")
async def get_site_number():    
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            config = json.load(f)
    except Exception:
        config = {}

    return {"nr_sites": len(config["sites"])}

@APP.post("/delete_site")
async def delete_site(index: Optional[str] = Query(None, description="Index of the site to delete")):
    try:
        if index:
            idx = int(index)
        else:
            return
    except Exception:
        return
    
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            config = json.load(f)
    except Exception:
        return

    if idx < 0 or idx >= len(config["sites"]):
        return

    del config["sites"][idx]

    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=2, ensure_ascii=False)

@APP.get("/product_image")
async def get_product_image(
    product_id: Optional[str] = Query(0, description="Product id"), 
    db: aiosqlite.Connection = Depends(get_db)
):
    async with db.execute("""SELECT image_link FROM products WHERE id = ?""", (str(product_id),)) as cur:
        row = await cur.fetchone()
    
    return row[0] if row else ""

@APP.get("/export_csv")
async def export_csv(
    q: Optional[str] = Query(None, description="Search query"),
    site: Optional[str] = Query(None, description="Site filter"),
    db: aiosqlite.Connection = Depends(get_db)
):
    import io
    import csv

    resp = await list_products(q=q, site=site, per_page=-1, page=1, order_by='id', reversed=False, db=db, min_price=None, max_price=None)
    items = resp.items if resp else None

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["id","site_name","external_id","title","link","currency","last_price","rating","ratings_count","first_seen_at","last_seen_at"])
    
    if items:
        for r in items:
            writer.writerow([r.id, r.site_name, r.external_id, r.title, r.link, r.currency, r.last_price, r.rating, r.ratings_count, r.first_seen_at, r.last_seen_at])
    output.seek(0)

    return StreamingResponse(output, media_type="text/csv", headers={"Content-Disposition": "attachment; filename=products.csv"})

@APP.get("/export_pdf")
async def export_pdf(
    q: Optional[str] = Query(None, description="Search query"),
    site: Optional[str] = Query(None, description="Site filter"),
    db: aiosqlite.Connection = Depends(get_db)
):
    import tempfile
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfgen import canvas
    from reportlab.lib.utils import simpleSplit
    from fastapi.responses import FileResponse

    resp = await list_products(q=q, site=site, per_page=-1, page=1, order_by='id', reversed=False, db=db, min_price=None, max_price=None)
    items = resp.items if resp else None

    with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
        pdf_path = tmp.name
    c = canvas.Canvas(pdf_path, pagesize=A4)
    width, height = A4
    x, y = 40, height - 40
    line_height = 18
    max_width = width - 80

    if items:
        keys = list(items[0].dict().keys())

        c.setFont("Helvetica-Bold", 12)
        header_text = " | ".join(keys)
        header_lines = simpleSplit(header_text, "Helvetica-Bold", 12, max_width)

        for line in header_lines:
            c.drawString(x, y, line)
            y -= line_height
        
        c.setFont("Helvetica", 10)
        for item in items:
            item_dict = item.dict()
            line = " | ".join(str(item_dict.get(k, "")) for k in keys)
            lines = simpleSplit(line, "Helvetica", 10, max_width)

            for l in lines:
                c.drawString(x, y, l)
                y -= line_height
                if y < 40:
                    c.showPage()
                    y = height - 40

            y -= line_height
            if y < 40:
                c.showPage()
                y = height - 40

    c.save()
    return FileResponse(pdf_path, media_type="application/pdf", filename="products.pdf")

@APP.get("/export_xlsx")
async def export_xlsx(q: Optional[str] = Query(None, description="Search query"),
    site: Optional[str] = Query(None, description="Site filter"),
    db: aiosqlite.Connection = Depends(get_db)
):
    import tempfile
    import xlsxwriter
    from flask import jsonify
    from fastapi.responses import FileResponse

    resp = await list_products(q=q, site=site, per_page=-1, page=1, order_by='id', reversed=False, db=db, min_price=None, max_price=None)
    items = resp.items if resp else None

    with tempfile.NamedTemporaryFile(delete=False, suffix=".xlsx") as tmp:
        xlsx_path = tmp.name

    workbook = xlsxwriter.Workbook(xlsx_path)
    worksheet = workbook.add_worksheet()

    if items:
        keys = list(items[0].dict().keys())
        for col, key in enumerate(keys):
            worksheet.write(0, col, key)
        
        for row, item in enumerate(items, start=1):
            for col, key in enumerate(keys):
                item_dict = item.dict()
                worksheet.write(row, col, item_dict.get(key, ""))
    workbook.close()

    return FileResponse(xlsx_path, media_type="application/pdf", filename="products.xlsx")

@APP.post("/delete_schedule")
async def delete_schedule():
    with open(CONFIG_PATH, "r") as f:
        config = json.load(f)

    config["schedule_query"] = ""

    with open(CONFIG_PATH, "w") as f:
        json.dump(config, f, indent=2, ensure_ascii=False)

    from Scheduler import delete_task

    delete_task()

@APP.post("/add_schedule")
async def add_schedule(query: str = Query(None), time: str = Query(None), discord_id: str = Query(None)):
    with open(CONFIG_PATH, "r") as f:
        config = json.load(f)

    config["discord_user_id"] = discord_id

    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=2, ensure_ascii=False)
    
    from Scheduler import create_task

    create_task(run_time=time, scrape_query=query)

@APP.get("/get_schedule_data")
async def get_schedule_data():
    with open(CONFIG_PATH, "r") as f:
        config = json.load(f)

    return {
        "query": config["schedule_query"],
        "time": config["schedule_time"],
        "discord_id": config["discord_user_id"]
    }

@APP.post("/add_watch_products")
async def add_watch_products(
    ids: NumbersRequest,
    max_price: Optional[str] = Query(None),
    db: aiosqlite.Connection = Depends(get_db)
):
    q_marks = ','.join(['?'] * len(ids.numbers))
    if max_price is not None:
        await db.execute(f"UPDATE products SET watch_price = 1, watch_max_price = {max_price} WHERE id IN ({q_marks})", ids.numbers)
    else:
        await db.execute(f"UPDATE products SET watch_price = 1 WHERE id IN ({q_marks})", ids.numbers)

    await db.commit()

@APP.post("/delete_watch_products")
async def delete_watch_products(
    ids: NumbersRequest,
    db: aiosqlite.Connection = Depends(get_db)
):
    q_marks = ','.join(['?'] * len(ids.numbers))
    await db.execute(f"UPDATE products SET watch_price = 0 WHERE id IN ({q_marks})", ids.numbers) 

    await db.commit()

@APP.get("/is_product_tracked")
async def is_product_tracked(
    id: str = Query(None),
    db: aiosqlite.Connection = Depends(get_db)
):
    async with db.execute("""
        SELECT watch_price, watch_max_price
        FROM products
        WHERE id = ?
    """, (int(id),)) as cur:
        row = await cur.fetchone()

    return { "tracked": row[0] == 1 if row else False, "max_price": row[1] if row else 0 }

@APP.post("/set_notify_price")
async def set_notify_price(
    id: str = Query(None),
    new_max_price: str = Query(None),
    db: aiosqlite.Connection = Depends(get_db)
):
    await db.execute("UPDATE products SET watch_max_price = ? WHERE id = ?", (new_max_price, id))
    await db.commit()

    return {"ok": True}

@APP.get("/total_products")
async def get_total_products(db: aiosqlite.Connection = Depends(get_db)):
    async with db.execute("SELECT COUNT(*) FROM products") as cur:
        row = await cur.fetchone()

    return {"total": row[0] if row else 0}

# python -m uvicorn API:APP --reload --host 0.0.0.0 --port 8000
