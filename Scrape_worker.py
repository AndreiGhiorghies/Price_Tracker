import sys
from Scraper import Filters, Scraper
import json

if __name__ == "__main__":
    query = sys.argv[1]
    config_path = sys.argv[2]
    csv_file = sys.argv[3]

    config_path = "config.json"
    try:
        with open(config_path, "r", encoding="utf-8") as f:
            config = json.load(f)
    except Exception:
        config = {}

    min_price = int(config["configuration"]["min_price"])
    max_price = int(config["configuration"]["max_price"])
    min_rating = float(config["configuration"]["min_rating"])
    min_ratings = int(config["configuration"]["min_ratings"])
    min_hours_update = int(config["configuration"]["min_hours_update"])

    filter = Filters(min_price, max_price, min_rating, min_ratings)
    scraper = Scraper(config_path)
    
    import asyncio
    asyncio.run(scraper.RunScrap(query, filter, min_hours_update))
