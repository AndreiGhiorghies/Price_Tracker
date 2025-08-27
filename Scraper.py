import asyncio
import csv
from playwright.async_api import async_playwright
from playwright.async_api import TimeoutError as PWTimeout
import time
from Matcher import build_generic_matcher
import re
import json
from urllib.parse import quote_plus
from Database import *
import sys
import os

class Filters:
    def __init__(self, min_price = 0, max_price = 0, min_rating:float = 0, min_ratings = 0) -> None:
        self.min_price = min_price
        self.max_price = max_price
        self.min_rating = min_rating
        self.min_ratings = min_ratings

class Scraper:
    def __init__(self, config_path):
        with open(config_path, "r", encoding="utf-8") as f:
            self.config = json.load(f)

    def parse_price(self, price_str : str, separator: str = ","):   
        match = price_str.strip().split(" ")

        numeric_part, currency = match[0], match[-1] if len(match) > 1 else None

        if "," in numeric_part and "." in numeric_part:
            if numeric_part.rfind(",") > numeric_part.rfind("."):
                numeric_part = numeric_part.replace(".", "")
                numeric_part = numeric_part.replace(",", ".")
            else:
                numeric_part = numeric_part.replace(",", "")
        elif "," in numeric_part:
            numeric_part = numeric_part.replace(",", ".")
        elif "." in numeric_part and separator == ",":
            numeric_part = numeric_part.replace(".", "")

        try:
            value = float(numeric_part)
        except ValueError:

            return None, currency
        
        return value, currency

    def parse_rating(self, rating_str : str):
        rating = rating_str.strip().split(" ")

        if "," in rating[0]:
            rating[0] = rating[0].replace(",", ".")
        if len(rating) > 1:
            if  "(" in rating[-1]:
                rating[-1] = rating[-1].replace("(", "")
            if ")" in rating[-1]:
                rating[-1] = rating[-1].replace(")", "")

        value = None
        try:
            value = float(rating[0])
        except:
            pass
        nr = None
        if len(rating) > 1:
            try:
                nr = int(rating[-1])
            except:
                pass

        return value, nr

    async def RunScrap(self, query, filter: Filters, update_time: float = 0.0):
        if not database_initialized:
            await init_db()
        db = await aiosqlite.connect(DB_PATH)

        jumpSite = dict()
        for site in self.config["sites"]:
            jumpSite[site["name"]] = (site["url"] == "")

        produse_nr = 0  
        
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True, channel="chrome",
                args=[
                    "--no-sandbox",
                    "--disable-gpu",
                    "--disable-dev-shm-usage",
                    "--disable-blink-features=AutomationControlled",
            ])

            pgn = 1
            matcher = build_generic_matcher(query)
            outOfSites = False

            while not outOfSites:
                outOfSites = True
                for site in self.config["sites"]:
                    if jumpSite[site["name"]]:
                        continue

                    context = await browser.new_context(
                        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/117.0.0.0 Safari/537.36",
                        locale="ro-RO"
                    )

                    await context.set_extra_http_headers({
                        "Accept-Language": "ro-RO,ro;q=0.9,en-US;q=0.8,en;q=0.7",
                        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                        "Connection": "keep-alive",
                        "Referer": site["url"],
                    })

                    page = await context.new_page()

                    q = quote_plus(query.replace("\"", ""))
                    url = site["url_searchTemplate"].format(query=q, page=pgn)
                    
                    print(f"[INFO] Accesez {url} ...")
                    await page.goto(url, timeout=60000, wait_until="domcontentloaded")

                    try:
                        await page.wait_for_selector(site["selectors"]["product"], timeout=4000)  # 2s max
                    except PWTimeout:
                        jumpSite[site["name"]] = True
                        continue

                    items = await page.query_selector_all(site["selectors"]["product"])

                    if not items:
                        jumpSite[site["name"]] = True
                        continue

                    if site["selectors"]["end_of_pages"] != "":
                        svg_elem = await page.query_selector(site["selectors"]["end_of_pages"])
                        if svg_elem:
                            jumpSite[site["name"]] = True
                            continue

                    empty = True

                    for item in items:
                        if site["selectors"]["remove_items_with"] != "":
                            svg_elem = await item.query_selector(site["selectors"]["remove_items_with"])
                            if svg_elem:
                                continue
                            
                        titlu = await item.query_selector(site["selectors"]["title"])
                        pret = await item.query_selector(site["selectors"]["price"])
                        rating = await item.query_selector(site["selectors"]["rating"])
                        link = await item.query_selector(site["selectors"]["link"])
                        image = await item.query_selector(site["selectors"]["image_link"])

                        titlu_text = (await (titlu.inner_text())).strip() if titlu else "N/A"
                        if link != None:
                            link_text = await link.get_attribute("href")
                            if link_text != None and link_text.startswith("/"):
                                link_text = site["url"] + link_text
                        else:
                            link_text = "N/A"

                        if site["selectors"]["id"] != "":
                            id = await item.get_attribute(site["selectors"]["id"])
                        else:
                            id = link_text
                        
                        pret_text = (await pret.inner_text()).strip() if pret else "N/A"
                        valoare_pret, currency = self.parse_price(pret_text)
                        rating_text = (await rating.inner_text()).strip() if rating else "N/A"
                        if image:
                            image_link = await image.get_attribute("src")
                        else:
                            image_link = "N/A"
                        ratingValue, ratingsNumber = self.parse_rating(rating_text)

                        if titlu_text == "N/A" or not matcher(titlu_text):
                            continue

                        if site["selectors"]["currency"] != "":
                            temp = await item.query_selector(site["selectors"]["currency"])
                            currency = (await temp.inner_text()).strip() if temp else "N/A"

                        empty = False
                        outOfSites = False

                        if filter.min_price != 0 and (valoare_pret is None or valoare_pret < filter.min_price):
                            continue
                        if filter.max_price != 0 and (valoare_pret is None or valoare_pret > filter.max_price):
                            continue
                        if filter.min_rating != 0 and (ratingValue is None or ratingValue < filter.min_rating):
                            continue
                        if filter.min_ratings != 0 and (ratingsNumber is None or ratingsNumber < filter.min_ratings):
                            continue
                        
                        product_id = await upsert_product(db, site["name"], titlu_text, link_text, id, image_link, currency, ratingValue, ratingsNumber, update_time)
                        await upsert_price_history(db, product_id, int(valoare_pret) if valoare_pret else None, update_time)

                        produse_nr += 1
                        """ produse.append({
                            "ID": id,
                            "Titlu": titlu_text,
                            "Pret": valoare_pret,
                            "Currency": currency if currency != None else "N/A",
                            "Rating": ratingValue if ratingValue else "N/A",
                            "Ratings Number": ratingsNumber if ratingsNumber else "N/A",
                            "Link": link_text
                        }) """


                    if empty:
                        jumpSite[site["name"]] = True

                    await page.close()

                await asyncio.sleep(3)
                pgn += 1

            print(f"[OK] Am salvat {produse_nr} produse")
            script_dir = os.path.dirname(os.path.abspath(__file__))
            config_path = script_dir + "\\config.json"
            try:
                with open(config_path, "r", encoding="utf-8") as f:
                    config = json.load(f)
            except Exception:
                config = {}
            config["nr_changed_products"] = str(produse_nr)
            with open(config_path, "w", encoding="utf-8") as f:
                json.dump(config, f, indent=2, ensure_ascii=False)

            await browser.close()
            await db.close()
    
    def Run(self, query, filter:Filters, min_hours_update):
        asyncio.run(self.RunScrap(query, filter, min_hours_update))
