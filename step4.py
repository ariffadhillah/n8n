# step4_full_with_email.py
import asyncio, csv, re
from urllib.parse import urljoin
import requests
from bs4 import BeautifulSoup
from playwright.async_api import async_playwright

KEYWORD = "Amministratore di condominio Roma"
CITY = "Roma"
OUT = "step4_with_email.csv"
MAX_RESULTS = 200
EMAIL_RE = r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}"

def extract_email(website: str) -> str:
    headers = {"User-Agent": "Mozilla/5.0"}
    emails = set()

    def grab(url):
        try:
            r = requests.get(url, timeout=12, headers=headers)
            s = BeautifulSoup(r.text, "html.parser")
            # mailto
            for a in s.find_all("a", href=True):
                href = a["href"].strip()
                if href.lower().startswith("mailto:"):
                    emails.add(href.split(":", 1)[1].split("?", 1)[0].strip())
            # regex
            emails.update(re.findall(EMAIL_RE, s.get_text(" ", strip=True)))
            return s
        except:
            return None

    if not website:
        return ""
    s = grab(website)
    if emails:
        return next(iter(emails))
    if s:
        candidates = []
        for a in s.find_all("a", href=True):
            text = (a.get_text() or "").lower()
            href = a["href"]
            if any(k in text for k in ["contatti","contact","contacts","chi siamo","chi-siamo","about"]):
                if not href.startswith("http"):
                    href = urljoin(website, href)
                candidates.append(href)
        for u in candidates[:5]:
            s2 = grab(u)
            if emails:
                break
    return next(iter(emails)) if emails else ""

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
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        page = await browser.new_page()
        await page.goto("https://www.google.com/maps?hl=en", timeout=90000)

        # Search
        await page.fill("#searchboxinput", KEYWORD)
        await page.press("#searchboxinput", "Enter")
        await page.wait_for_selector("div[role='feed']", timeout=60000)
        try:
            await page.wait_for_selector(".hfpxzc", timeout=20000)
        except:
            await page.wait_for_selector("div[role='article']", timeout=20000)

        feed = page.locator("div[role='feed']")
        last_count = 0
        end_reached = False
        scroll_attempts = 0

        while not end_reached and scroll_attempts < 500:  # safety max scrolls
            await feed.evaluate("el => el.scrollTo(0, el.scrollHeight)")
            await page.wait_for_timeout(5000)  # tunggu load item baru

            cnt = await page.locator(".hfpxzc, div[role='article']").count()

            # Cek text global di page
            end_texts = page.locator('text=You\'ve reached the end of the list.')
            if await end_texts.count() > 0:
                end_reached = True
                print("Reached end of list text detected!")
                break

            if cnt == last_count or cnt >= MAX_RESULTS:
                end_reached = True
                print("No new cards loaded, stopping scroll.")
                break

            last_count = cnt
            scroll_attempts += 1


        # Ambil semua card
        cards = page.locator(".hfpxzc, div[role='article']")
        total = await cards.count()
        print("Total cards found:", total)

        # Proses setiap card
        for i in range(total):
            try:
                await page.wait_for_timeout(2000)
                card = cards.nth(i)
                await card.click()
                await page.wait_for_selector("h1", timeout=30000)

                name = (await page.locator("h1").first.text_content() or "").strip()
                address = await safe_text(page, 'button[data-item-id="address"]')
                phone   = await safe_text(page, 'button[data-item-id*="phone"]')
                website = await safe_attr(page, 'a[data-item-id*="authority"]', "href")
                email   = extract_email(website) if website else ""
                gmaps_url = page.url

                rows.append([name, address, CITY, phone, website, email, gmaps_url])
                print(f"[{i+1}] {name} | {email or 'No email'}")
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
