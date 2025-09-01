from Scraper import Scraper, Filters
from Database import CONFIG_PATH

query = 'Laptop Lenovo LOQ "Ryzen 5" "3050"'
config_path = "config.json"
csv_file = "produse.csv"

scrap = Scraper(CONFIG_PATH)

filter = Filters()

scrap.Run('Telefon samsung a55', filter, 0)
