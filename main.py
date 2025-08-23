from Scraper import Scraper, Filters

query = 'Laptop Lenovo LOQ "Ryzen 5" "3050"'
config_path = "config.json"
csv_file = "produse.csv"

scrap = Scraper(config_path)

filter = Filters()

scrap.Run('Telefon samsung a55', filter, 0)
