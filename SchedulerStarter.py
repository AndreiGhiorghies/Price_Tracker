import sys
import sqlite3
import subprocess
import discord
import asyncio
import os
import json

from typing import List, Tuple, Union
from dotenv import load_dotenv
from Database import DB_PATH, CONFIG_PATH, SCRIPT_DIR

def get_products_under_maxprice():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    cur.execute(""" 
        SELECT title, last_price, watch_max_price
        FROM products
        WHERE watch_price = 1 AND last_price < watch_max_price
    """)

    results = cur.fetchall()
    conn.close()

    return results

def build_discord_message(products: List[Tuple[str, float]]) -> str:
    if not products:
        return "Nu există produse sub prag."
    
    lines = ["**Produse sub prag:**"]
    for t, p, *rest in products:
        lines.append(f"- {t} — {p} = {rest[0]}")
    
    return "\n".join(lines)

def send_discord_alert_dm(products: List[Tuple[str, float]], token: str, user_id: Union[int, str]):
    if user_id is None or user_id == '':
        return
    
    try:
        user_id = int(user_id)
    except Exception:
        print("user_id invalid — trebuie un int.")
        return

    async def main():
        intents = discord.Intents.default()
        intents.guilds = True
        intents.messages = True
        client = discord.Client(intents=intents)

        async def send_and_close():
            try:
                user = await client.fetch_user(user_id)
                if user is None:
                    print("User-ul nu a fost găsit.")
                    return

                await user.send(build_discord_message(products))
            except Exception as e:
                print("Eroare la trimiterea DM-ului:", e)

        try:
            await client.login(token)
        except Exception as e:
            print("Login eșuat:", e)
            return

        try:
            asyncio.create_task(client.connect())
            await client.wait_until_ready()
            await send_and_close()
        except Exception as e:
            print("Conectare/trimite eșuat:", e)
        finally:
            try:
                await client.close()
            except Exception as e:
                print("Eroare la inchidere client:", e)

    asyncio.run(main())

if __name__ == "__main__":
    with open(CONFIG_PATH, "r") as f:
        config = json.load(f)
    
    python_exe = sys.executable
    cmd = [f"{python_exe}", SCRIPT_DIR + "\\Scrape_worker.py", config["schedule_query"], CONFIG_PATH]

    proc = subprocess.Popen(cmd)
    proc.wait()

    products = get_products_under_maxprice()
    if len(products) > 0:
        load_dotenv()

        send_discord_alert_dm(products=get_products_under_maxprice(), token=os.getenv("DISCORD_TOKEN") or "", user_id=config["discord_user_id"])

    sys.exit(0)