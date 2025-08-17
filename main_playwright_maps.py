import asyncio
import csv, re, requests
from bs4 import BeautifulSoup
from playwright.async_api import async_playwright

KEYWORD = "Amministratore di condominio Roma"
CITY = "Roma"
OUTPUT = "sample_property_managers_playwright.csv"
EMAIL_REGEX = r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}"

def extract_email(website):
    try:
        r = requests.get(website, timeout=10, headers={"User-Agent": "Mozilla/5.0"})
        soup = BeautifulSoup(r.text, "html.parser")
        match = re.search(EMAIL_REGEX, soup.get_text())
        return match.group(0) if match else ""
    except:
        return ""

async def scrape():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        page = await browser.new_page()
        await page.goto("https://www.google.com/maps", timeout=60000)

        # Cari keyword
        await page.wait_for_selector("#searchboxinput")
        await page.fill("#searchboxinput", KEYWORD)
        await page.press("#searchboxinput", "Enter")

        # Tunggu feed muncul
        await page.wait_for_selector("div[role='feed']", timeout=60000)
        print("✅ Sidebar ditemukan, mulai scroll...")

        feed = page.locator("div[role='feed']")
        for _ in range(15):  # scroll 15 kali
            await feed.evaluate("el => el.scrollTop = el.scrollHeight")
            await page.wait_for_timeout(2000)

        # Ambil semua hasil
        results = page.locator(".hfpxzc")
        total = await results.count()
        print(f"Total results found: {total}")

        data = []
        for i in range(min(50, total)):  # ambil max 50
            try:
                r = results.nth(i)
                name = await r.get_attribute("aria-label")
                url = await r.get_attribute("href")

                await r.click()
                await page.wait_for_timeout(3000)

                try:
                    address = await page.locator('button[data-item-id="address"]').inner_text()
                except:
                    address = ""

                try:
                    phone = await page.locator('button[data-item-id*="phone"]').inner_text()
                except:
                    phone = ""

                try:
                    website = await page.locator('a[data-item-id*="authority"]').get_attribute("href")
                except:
                    website = ""

                email = extract_email(website) if website else ""

                data.append([name, address, CITY, phone, website, email, url])
                print(f"[{i+1}] {name} | {email or 'No email'}")

            except Exception as e:
                print(f"Error on {i+1}: {e}")
                continue

        await browser.close()

        # Save CSV
        with open(OUTPUT, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(["Name","Address","City","Phone","Website","Email","Google Maps URL"])
            writer.writerows(data)

        print(f"✅ Saved to {OUTPUT}")

if __name__ == "__main__":
    asyncio.run(scrape())
