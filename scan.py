import os
import re
import requests
import base64
import mmh3
import json
import asyncio
import aiohttp
from urllib.parse import urlparse
from pyppeteer import launch

# ===== CONFIG =====
TARGET = "nasa.gov"
DISCORD_WEBHOOK = "https://discord.com/api/webhooks/1404518805971140751/QpfHfeqXjfDhUrUA2WgKvFCHo-_ZLT5kDfKoZOdHDWuexa-8BwK4i2xkC7HyXyD4X30i"
SHODAN_API_KEY = "rG44e4mMkKejbSDrMVCJUcERchRX37eN"
SCREENSHOT_DIR = "screenshots"

os.makedirs(SCREENSHOT_DIR, exist_ok=True)

# ===== UTILS =====
async def fetch(session, url):
    try:
        async with session.get(url, timeout=10) as resp:
            return await resp.text()
    except:
        return ""

def extract_domains(text):
    return set(re.findall(r"[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}", text))

async def get_subdomains():
    subdomains = set()

    async with aiohttp.ClientSession() as session:
        # RapidDNS
        rdns = await fetch(session, f"https://rapiddns.io/subdomain/{TARGET}?full=1")
        subdomains |= extract_domains(rdns)

        # Wayback Machine
        wb = await fetch(session, f"http://web.archive.org/cdx/search/cdx?url={TARGET}/*&output=text&fl=original&collapse=urlkey")
        subdomains |= extract_domains(wb)

    return subdomains

def shodan_favicon_search():
    # Get favicon hash
    favicon_url = f"https://{TARGET}/favicon.ico"
    try:
        favicon = requests.get(favicon_url, timeout=10).content
        b64 = base64.b64encode(favicon)
        hash_val = mmh3.hash(b64)
        # Search on Shodan
        url = f"https://api.shodan.io/shodan/host/search?key={SHODAN_API_KEY}&query=http.favicon.hash:{hash_val}"
        data = requests.get(url).json()
        results = set()
        for match in data.get("matches", []):
            for h in match.get("hostnames", []):
                results.add(h)
        return results
    except:
        return set()

async def check_alive(domains):
    alive = []
    async with aiohttp.ClientSession() as session:
        tasks = []
        for d in domains:
            tasks.append(check_one(session, d))
        results = await asyncio.gather(*tasks)
        alive = [r for r in results if r]
    return alive

async def check_one(session, domain):
    for scheme in ["http", "https"]:
        try:
            async with session.get(f"{scheme}://{domain}", timeout=5) as resp:
                if resp.status < 400:
                    return f"{scheme}://{domain}"
        except:
            continue
    return None

async def screenshot_page(url, filename):
    try:
        browser = await launch(headless=True, args=["--no-sandbox"])
        page = await browser.newPage()
        await page.goto(url, {"waitUntil": "networkidle2", "timeout": 10000})
        await page.screenshot({"path": filename, "fullPage": True})
        await browser.close()
    except:
        pass

async def send_to_discord(message, file_path=None):
    data = {"content": message}
    files = {}
    if file_path and os.path.exists(file_path):
        files["file"] = open(file_path, "rb")
    requests.post(DISCORD_WEBHOOK, data=data, files=files)

# ===== MAIN =====
async def main():
    print("[*] Gathering subdomains...")
    subs = await get_subdomains()
    subs |= shodan_favicon_search()

    print(f"[*] Found {len(subs)} potential subdomains")

    print("[*] Checking alive domains...")
    alive = await check_alive(subs)
    print(f"[*] Alive: {len(alive)}")

    for url in alive:
        domain_name = urlparse(url).netloc.replace(":", "_")
        screenshot_path = os.path.join(SCREENSHOT_DIR, f"{domain_name}.png")
        await screenshot_page(url, screenshot_path)
        await send_to_discord(f"Alive: {url}", file_path=screenshot_path)

    with open("alive_subdomains.txt", "w") as f:
        for url in alive:
            f.write(url + "\n")

    print("[+] Done! Results saved to alive_subdomains.txt and sent to Discord.")

if __name__ == "__main__":
    asyncio.run(main())
