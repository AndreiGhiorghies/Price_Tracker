import sys
import sqlite3
import subprocess
import discord
import asyncio
from typing import List, Tuple, Union
from dotenv import load_dotenv
import os
import json

def get_products_under_maxprice(db_path="D:\\Python\\Web_Scraper\\tracker.db"):
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()

    cur.execute(""" 
        SELECT p.title, p.last_price, s.max_price
        FROM products p
        JOIN scheduler s ON p.id = s.product_id
        WHERE p.last_price < s.max_price
    """)

    results = cur.fetchall()
    conn.close()

    return results

def _build_message(products: List[Tuple[str, float]]) -> str:
    if not products:
        return "Nu există produse sub prag."
    lines = ["**Produse sub prag:**"]
    for t, p, *rest in products:
        lines.append(f"- {t} — {p} = {rest[0]}")
    return "\n".join(lines)

def send_discord_alert_dm(products: List[Tuple[str, float]], token: str, user_id: Union[int, str]):
    try:
        user_id = int(user_id)
    except Exception:
        print("user_id invalid — trebuie un int.")
        return

    async def _main():
        intents = discord.Intents.default()
        intents.guilds = True
        intents.messages = True
        client = discord.Client(intents=intents)

        async def _send_and_close():
            try:
                user = await client.fetch_user(user_id)  # obține obiectul User
                if user is None:
                    print("User-ul nu a fost găsit.")
                    return

                await user.send(_build_message(products))
                print("DM trimis cu succes.")
            except Exception as e:
                print("Eroare la trimiterea DM-ului:", e)

        try:
            await client.login(token)
        except Exception as e:
            print("Login eșuat:", e)
            return

        try:
            ws_task = asyncio.create_task(client.connect())
            await client.wait_until_ready()
            await _send_and_close()
        except Exception as e:
            print("Conectare/trimite eșuat:", e)
        finally:
            try:
                await client.close()
            except Exception as e:
                print("Eroare la inchidere client:", e)

    asyncio.run(_main())

if __name__ == "__main__":
    with open("D:\\Python\\Web_Scraper\\config.json", "r") as f:
        config = json.load(f)
    python_exe = sys.executable
    cmd = [f"{python_exe}", "D:\\Python\\Web_Scraper\\Scrape_worker.py", config["schedule_query"], "D:\\Python\\Web_Scraper\\config.json"]

    proc = subprocess.Popen(cmd)
    proc.wait()

    products = get_products_under_maxprice()
    if len(products) > 0:
        load_dotenv()

        send_discord_alert_dm(products=get_products_under_maxprice(), token=os.getenv("DISCORD_TOKEN") or "", user_id=config["discord_user_id"])

    sys.exit(0)