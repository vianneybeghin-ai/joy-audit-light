"""Dumpe le HTML rendu de 3 fiches golden vers /tmp pour inspection.
Usage : python scripts/dump_html.py"""
import asyncio
from playwright.async_api import async_playwright

URLS = [
    "https://www.privateaser.com/lieu/52456-chez-eloise",
    "https://www.privateaser.es/local/52379-Gabys-club",
    "https://www.privateaser.es/local/55798-lina-restaurante",
]

UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")


async def dump():
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        ctx = await browser.new_context(user_agent=UA)
        for url in URLS:
            page = await ctx.new_page()
            await page.goto(url, wait_until="networkidle", timeout=15000)
            html = await page.content()
            slug = url.rsplit("/", 1)[-1]
            path = f"/tmp/fiche-{slug}.html"
            with open(path, "w", encoding="utf-8") as f:
                f.write(html)
            print(f"  → {path} ({len(html):,} chars)")
            await page.close()
        await browser.close()


if __name__ == "__main__":
    asyncio.run(dump())
