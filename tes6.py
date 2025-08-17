import asyncio, csv, re, requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin
from playwright.async_api import async_playwright

OUT = "results.csv"
KEYWORDS = ["Amministratore di condominio"]
EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")

# ------------ Helpers ------------
def load_cities_from_csv(path):
    cities = []
    with open(path, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            if row.get("multi CITIES"):
                cities.append(row["multi CITIES"].strip())
    return cities

async def safe_text(page, selector):
    try:
        el = page.locator(selector).first
        if await el.count() > 0:
            txt = await el.text_content()
            return (txt or "").strip()
    except:
        return ""
    return ""

async def safe_attr(page, selector, attr):
    try:
        el = page.locator(selector).first
        if await el.count() > 0:
            val = await el.get_attribute(attr)
            return (val or "").strip()
    except:
        return ""
    return ""

def extract_emails(website: str) -> str:
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
        return "; ".join(emails)
    if s:
        candidates = []
        for a in s.find_all("a", href=True):
            text = (a.get_text() or "").lower()
            href = a["href"]
            if any(k in text for k in ["contact","contacts","contatti","chi siamo","about"]):
                if not href.startswith("http"):
                    href = urljoin(website, href)
                candidates.append(href)
        for u in candidates[:5]:
            s2 = grab(u)
            if emails:
                break
    return "; ".join(emails) if emails else ""

# ------------ Main ------------
async def main():
    rows = []
    CITIES = load_cities_from_csv("cities.csv")

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        page = await browser.new_page()

        for city in CITIES:
            for keyword in KEYWORDS:
                search_query = f"{keyword} {city}"
                print(f"\nSearching: {search_query}")

                await page.goto("https://www.google.com/maps?hl=en", timeout=90000)
                await page.fill("#searchboxinput", search_query)
                await page.press("#searchboxinput", "Enter")
                await page.wait_for_selector("div[role='feed']", timeout=60000)

                # Scroll sampai mentok
                feed = page.locator("div[role='feed']")
                last_count = 0
                while True:
                    await feed.evaluate("el => el.scrollTo(0, el.scrollHeight)")
                    await page.wait_for_timeout(2000)

                    cnt = await page.locator(".hfpxzc, div[role='article']").count()
                    if await page.locator("text=You've reached the end of the list.").count() > 0:
                        print("Reached end of list text detected!")
                        break
                    if cnt == last_count or cnt >= 200:
                        print("No new cards loaded, stopping scroll.")
                        break
                    last_count = cnt

                # Ambil semua card
                cards = page.locator(".hfpxzc, div[role='article']")
                total = await cards.count()
                print("Total cards found:", total)

                for i in range(total):
                    try:
                        await page.wait_for_timeout(1500)
                        card = cards.nth(i)
                        fallback_name = await card.get_attribute("aria-label")

                        await card.click()
                        await page.wait_for_selector("h1", timeout=30000)

                        # ambil name dari panel detail
                        name = (await page.locator("h1").first.text_content() or "").strip()
                        if not name:
                            name = fallback_name or "N/A"

                        address = await safe_text(page, 'button[data-item-id="address"]')
                        phone   = await safe_text(page, 'button[data-item-id*="phone"]')
                        website = await safe_attr(page, 'a[data-item-id*="authority"]', "href")
                        await page.wait_for_timeout(1200)
                        email   = extract_emails(website) if website else ""
                        gmaps_url = page.url

                        rows.append([name, address, city, phone, website, email, gmaps_url])
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
