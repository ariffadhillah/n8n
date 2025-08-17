# step4_full_with_email.py
import asyncio, csv, re
from urllib.parse import urljoin
import requests
from bs4 import BeautifulSoup
from playwright.async_api import async_playwright

# KEYWORD = "Amministratore di condominio Roma"
# CITY = "Roma"
# OUT = "step4_with_email.csv"

import csv

def load_cities_from_csv(path: str) -> list:
    cities = []
    with open(path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            city = row.get("Multi CITIES")
            if city:
                cities.append(city.strip())
    return cities


KEYWORDS = [
    "Amministratore di condominio",
    "amministrazione condomini",
    "amministrazione condominiale"
]

# CITIES = ["Alessandria"] 

OUT = "hasil lengkap city.csv"

MAX_RESULTS = 500
EMAIL_RE = r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}"

def extract_emails(website: str) -> str:
    headers = {"User-Agent": "Mozilla/5.0"}
    emails = set()

    def grab(url):
        try:
            r = requests.get(url, timeout=12, headers=headers)
            s = BeautifulSoup(r.text, "html.parser")

            # ambil mailto links
            for a in s.find_all("a", href=True):
                href = a["href"].strip()
                if href.lower().startswith("mailto:"):
                    e = href.split(":", 1)[1].split("?", 1)[0].strip()
                    if e:
                        emails.add(e)

            # ambil dengan regex di seluruh text
            found = re.findall(EMAIL_RE, s.get_text(" ", strip=True))
            for e in found:
                emails.add(e.strip())

            return s
        except Exception as e:
            return None

    if not website:
        return ""

    # cek homepage
    s = grab(website)

    # kalau tidak ada email, coba halaman "contact" dll.
    if s and not emails:
        candidates = []
        for a in s.find_all("a", href=True):
            text = (a.get_text() or "").lower()
            href = a["href"]
            if any(k in text for k in ["contatti","contact","contacts","chi siamo","chi-siamo","about"]):
                if not href.startswith("http"):
                    href = urljoin(website, href)
                candidates.append(href)

        for u in candidates[:5]:
            grab(u)  # update emails
            if emails:
                break

    # return semua email (dipisah ;)
    return "; ".join(sorted(emails))




async def safe_text(page, sel):
    try:
        loc = page.locator(sel).first
        if await loc.count() == 0: return ""
        t = await loc.text_content()
        return (t or "").strip()
    except:
        return ""

async def safe_attr(page, sel, attr):
    try:
        loc = page.locator(sel).first
        if await loc.count() == 0: return ""
        v = await loc.get_attribute(attr)
        return v or ""
    except:
        return ""

async def main():
    rows = []
    CITIES = load_cities_from_csv("cities.csv")  # ambil dari file CSV
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()

        for city in CITIES:
            for keyword in KEYWORDS:
                search_query = f"{keyword} {city}"
                print(f"\nSearching: {search_query}")

                await page.goto("https://www.google.com/maps?hl=en", timeout=90000)
                await page.fill("#searchboxinput", search_query)
                await page.press("#searchboxinput", "Enter")
                await page.wait_for_selector("div[role='feed']", timeout=60000)

                try:
                    await page.wait_for_selector(".hfpxzc", timeout=20000)
                except:
                    await page.wait_for_selector("div[role='article']", timeout=20000)

                # Scroll sampai mentok
                feed = page.locator("div[role='feed']")
                last_count = 0
                end_reached = False
                scroll_attempts = 0

                while not end_reached and scroll_attempts < 500:
                    await feed.evaluate("el => el.scrollTo(0, el.scrollHeight)")
                    await page.wait_for_timeout(5000)

                    cnt = await page.locator(".hfpxzc, div[role='article']").count()
                    end_texts = page.locator('text=You\'ve reached the end of the list.')
                    if await end_texts.count() > 0:
                        end_reached = True
                        print("Reached end of list text detected!")
                        break

                    if cnt == last_count or cnt >= 200:
                        end_reached = True
                        print("No new cards loaded, stopping scroll.")
                        break

                    last_count = cnt
                    scroll_attempts += 1

                # Ambil semua card
                cards = page.locator(".hfpxzc, div[role='article']")
                total = await cards.count()
                print("Total cards found:", total)

                for i in range(total):
                    try:
                        await page.wait_for_timeout(2500)
                        # name = await card.get_attribute("aria-label")
                        card = cards.nth(i)

                        await card.click()
                        await page.wait_for_selector("h1", timeout=30000)

                        # await page.wait_for_selector("h1.DUwDvf", timeout=30000)
                        name = (await page.locator("h1.DUwDvf").inner_text()).strip()

                        address = await safe_text(page, 'button[data-item-id="address"]')
                        phone   = await safe_text(page, 'button[data-item-id*="phone"]')
                        website = await safe_attr(page, 'a[data-item-id*="authority"]', "href")
                        await page.wait_for_timeout(3500)
                        email   = extract_emails(website) if website else ""
                        # await page.wait_for_timeout(1000)
                        gmaps_url = page.url

                        rows.append([name, address, city, phone, website, email, gmaps_url])
                        print(f"[{i+1}] {name} | {email or 'No email'}")
                        await page.wait_for_timeout(2000)

                    except Exception as e:
                        print("Error processing card:", i+1, e)


            # Simpan CSV
            with open(OUT, "w", newline="", encoding="utf-8") as f:
                w = csv.writer(f)
                w.writerow(["Name","Address","City","Phone","Website","Email","Google Maps URL"])
                w.writerows(rows)
            print("Saved:", OUT)

        await browser.close()

if __name__ == "__main__":
    asyncio.run(main())
