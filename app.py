from flask_caching import Cache
from flask_compress import Compress
# app.py

from flask import Flask, render_template, request, send_file, jsonify, redirect, url_for, send_from_directory
import requests
import io
import csv

APP = Flask(__name__) 
API_URL = "http://127.0.0.1:8000"

# Adaugă funcția min în contextul global Jinja2
APP.jinja_env.globals.update(min=min)

Compress(APP)
cache = Cache(APP, config={'CACHE_TYPE': 'SimpleCache', 'CACHE_DEFAULT_TIMEOUT': 20})

# Servește fișiere statice
@APP.route('/static/<path:filename>')
def static_files(filename):
    return send_from_directory('static', filename)

# Home: list products with filters and pagination
@APP.route("/products")
def products_json():
    q = request.args.get("q", "").strip()
    site = request.args.get("site", "").strip()
    page = int(request.args.get("page", 1))
    per_page = min(int(request.args.get("per_page", 25)), 50)
    order_by = request.args.get("order_by", "").strip()
    rev = request.args.get("reversed", "").strip()

    params = {
        "q": q,
        "site": site,
        "page": page,
        "per_page": per_page,
        "order_by": order_by,
        "reversed": rev
    }

    resp = requests.get(f"{API_URL}/products", params=params)
    if resp:
        data = resp.json()
    else:
        return jsonify({"ok": True})

    return jsonify(data)

@APP.route("/")
def index():
    q = request.args.get("q", "").strip()
    site = request.args.get("site", "").strip()
    page = int(request.args.get("page", 1))
    per_page = int(request.args.get("per_page", 25))
    params = {
        "q": q,
        "site": site,
        "page": page,
        "per_page": per_page,
        "order_by": "id",
        "reversed": False
    }
    resp = requests.get(f"{API_URL}/products", params=params)
    if resp:
        data = resp.json()
    else:
        return jsonify({"ok": True})
    
    allowed_per_page = [10, 25, 50]
    if per_page not in allowed_per_page:
        per_page = 25

    # Dacă cererea e AJAX (Accept: application/json), returnează JSON direct
    if request.headers.get('Accept', '').startswith('application/json'):
        return jsonify(data)
    

    items = data["items"]
    total = data["total"]
    total_pages = max(1, (total + per_page - 1) // per_page)
    return render_template("index.html",
                           products=items,
                           total=total,
                           page=page,
                           per_page=per_page,
                           total_pages=total_pages,
                           q=q,
                           site_filter=site)

# Product detail + history rendered in page
@APP.route("/product/<int:product_id>")
def product_detail(product_id):
    resp = requests.get(f"{API_URL}/products/{product_id}")
    if resp.status_code != 200:
        return "Produsul nu a fost găsit", 404
    prod = resp.json()
    hist_resp = requests.get(f"{API_URL}/products/{product_id}/history")
    history = hist_resp.json() if hist_resp.status_code == 200 else []
    return render_template("product.html", product=prod, history=history)

# JSON history (useful for charts)
@APP.route("/product/<int:product_id>/history.json")
def product_history_json(product_id):
    resp = requests.get(f"{API_URL}/products/{product_id}/history")
    if resp.status_code != 200:
        return jsonify([])
    return jsonify(resp.json())

# Export CSV (current page or all if ?all=1)
@APP.route("/export.csv")
def export_csv():
    q = request.args.get("q", "").strip()
    site = request.args.get("site", "").strip()
    params = {
        "q": q,
        "site": site,
        "page": 1,
        "per_page": -1,  # exportă maxim 10.000 produse
        "order_by": "id",
        "reversed": False
    }
    resp = requests.get(f"{API_URL}/products", params=params)
    data = resp.json()
    items = data["items"]
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["id","site_name","external_id","title","link","currency","last_price","rating","ratings_count","first_seen_at","last_seen_at"])
    for r in items:
        writer.writerow([r["id"], r["site_name"], r["external_id"], r["title"], r["link"], r["currency"], r["last_price"], r["rating"], r["ratings_count"], r["first_seen_at"], r["last_seen_at"]])
    mem = io.BytesIO()
    mem.write(output.getvalue().encode("utf-8"))
    mem.seek(0)
    return send_file(mem, mimetype="text/csv", download_name="products.csv", as_attachment=True)

#Something
@APP.route("/export.xlsx")
def export_xlsx():
    import tempfile
    import xlsxwriter

    q = request.args.get("q", "").strip()
    site = request.args.get("site", "").strip()
    params = {
        "q": q,
        "site": site,
        "page": 1,
        "per_page": -1,
        "order_by": "id",
        "reversed": False
    }
    resp = requests.get(f"{API_URL}/products", params=params)
    data = resp.json()
    items = data["items"]

    # Creează fișier Excel temporar
    with tempfile.NamedTemporaryFile(delete=False, suffix=".xlsx") as tmp:
        xlsx_path = tmp.name

    workbook = xlsxwriter.Workbook(xlsx_path)
    worksheet = workbook.add_worksheet()

    if items:
        keys = list(items[0].keys())
        for col, key in enumerate(keys):
            worksheet.write(0, col, key)
        for row, item in enumerate(items, start=1):
            for col, key in enumerate(keys):
                worksheet.write(row, col, item.get(key, ""))
    workbook.close()

    return send_file(xlsx_path, download_name="products.xlsx", as_attachment=True)

@APP.route("/export.pdf")
def export_pdf():
    import tempfile
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfgen import canvas
    from reportlab.lib.utils import simpleSplit

    q = request.args.get("q", "").strip()
    site = request.args.get("site", "").strip()
    params = {
        "q": q,
        "site": site,
        "page": 1,
        "per_page": -1,
        "order_by": "id",
        "reversed": False
    }
    resp = requests.get(f"{API_URL}/products", params=params)
    data = resp.json()
    items = data["items"]

    with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
        pdf_path = tmp.name
    c = canvas.Canvas(pdf_path, pagesize=A4)
    width, height = A4
    x, y = 40, height - 40
    line_height = 18
    max_width = width - 80  # margini

    if items:
        keys = list(items[0].keys())
        c.setFont("Helvetica-Bold", 12)
        header_text = " | ".join(keys)
        header_lines = simpleSplit(header_text, "Helvetica-Bold", 12, max_width)
        for line in header_lines:
            c.drawString(x, y, line)
            y -= line_height
        c.setFont("Helvetica", 10)
        for item in items:
            line = " | ".join(str(item.get(k, "")) for k in keys)
            lines = simpleSplit(line, "Helvetica", 10, max_width)
            for l in lines:
                c.drawString(x, y, l)
                y -= line_height
                if y < 40:
                    c.showPage()
                    y = height - 40
            # empty line between items
            y -= line_height
            if y < 40:
                c.showPage()
                y = height - 40

    c.save()
    return send_file(pdf_path, mimetype="application/pdf", download_name="products.pdf", as_attachment=True)


# Trigger external scraper (calls FastAPI endpoint)
""" @APP.route("/trigger_1scrape", methods=["POST"])
def trigger_scrape():
    print("DA")
    query = request.form.get("query", "")
    # Apelează endpointul FastAPI pentru scraping
    resp = requests.post(f"{API_URL}/scrape/trigger?query={query}")
    if resp.status_code == 200:
        return resp.json()
    return {"ok": False, "error": "Eroare la pornirea scraperului"}, 500 """

@APP.route("/product/<int:product_id>/delete", methods=["POST"])
def delete_product(product_id):
    resp = requests.delete(f"{API_URL}/products/{product_id}")
    if resp.status_code == 200:
        return redirect(url_for('index'))
    return f"Eroare la ștergere: {resp.text}", 500

@APP.route("/bulk_delete", methods=["POST"])
def bulk_delete_products():
    ids = request.form.getlist("product_ids")
    if not ids:
        return jsonify({"ok": True})
    # Trimite la API ca POST și asigură-te că sunt int
    ids_int = [int(i) for i in ids]
    resp = requests.post(f"{API_URL}/products/bulk_delete", json={"ids": ids_int})
    if resp.status_code == 200:
        return jsonify({"ok": True})
    return jsonify({"Eroare la stergere: ": resp.text})


if __name__ == "__main__":
    APP.run(debug=True, port=5000)
