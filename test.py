import asyncio
from playwright.async_api import async_playwright

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        await page.goto('https://twitchtracker.com/vulpeshd/games')
        await page.wait_for_selector('#games')
        print("Page loaded successfully.")
        await browser.close()

asyncio.run(main())
