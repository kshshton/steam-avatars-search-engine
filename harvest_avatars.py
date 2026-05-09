import asyncio
import csv
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv
from playwright.async_api import async_playwright, Page, TimeoutError as PlaywrightTimeoutError

load_dotenv()

# --- Config ---
TARGET_URL = os.getenv("SOURCE_URL")
if not TARGET_URL:
    sys.exit("SOURCE_URL is not set - add it to your .env file")

SELECTOR    = "._2YbSwspXZ90_vgzS5O3X4F"  
OUTPUT_FILE = Path(__file__).parent / "avatars.csv"

CSV_FIELDS = ["url", "date_scraped"]
SCROLL_STEP      = 600    
TICK_DELAY_MS    = 600    
STALL_WAIT_MS    = 4000   
MAX_STALL_TIME_S = 30     
BOTTOM_MARGIN    = 100    
HEADLESS_MODE    = True   

# --- File Logic ---

def load_csv_urls(path: Path) -> set[str]:
    """Load existing CSV and return a set of URLs for fast lookup."""
    urls: set[str] = set()
    if path.exists():
        try:
            with open(path, newline="", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    if row.get("url"):
                        urls.add(row["url"])
            print(f"Loaded {len(urls)} existing URLs from {path.name}")
        except Exception as e:
            print(f"Warning: Could not read existing CSV: {e}")
    return urls


def insert_csv(path: Path, new_urls: list[str]) -> int:
    """
    Appends only new URLs to the CSV. 
    Does not modify or re-write existing data.
    """
    now = datetime.now(timezone.utc).isoformat()
    existing_urls = load_csv_urls(path)
    
    # Filter for URLs we don't already have in the file
    to_append = [
        {"url": url, "date_scraped": now} 
        for url in new_urls 
        if url not in existing_urls
    ]

    if not to_append:
        print("No new unique URLs found to insert.")
        return 0

    file_exists = path.exists() and path.stat().st_size > 0

    try:
        # Open in append mode ('a') to avoid re-writing the whole file
        with open(path, "a", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=CSV_FIELDS)
            
            # Write header only if the file is being created for the first time
            if not file_exists:
                writer.writeheader()
            
            writer.writerows(to_append)
            f.flush()
            os.fsync(f.fileno()) 
            
        print(f"Successfully appended {len(to_append)} new rows to {path.name}.")
    except Exception as e:
        print(f"Critical Error writing to CSV: {e}")

    return len(to_append)


# --- Scroll logic ---

async def scroll_and_collect(page: Page, selector: str) -> list[str]:
    print("Starting scroll collector (Firefox / Virtualised-list mode)...")

    collected: set[str] = set()
    last_scroll_pos: float = -1
    stall_started: float | None = None

    async def harvest() -> int:
        visible: list[str] = await page.evaluate(
            """([sel]) =>
                [...document.querySelectorAll(sel)]
                    .map(e => e.src)
                    .filter(Boolean)
            """,
            [selector],
        )
        before = len(collected)
        collected.update(visible)
        return len(collected) - before

    while True:
        await page.evaluate(
            "([step]) => window.scrollBy({ top: step, behavior: 'smooth' })",
            [SCROLL_STEP],
        )
        await page.wait_for_timeout(TICK_DELAY_MS)

        scroll_pos, viewport_h, total_h = await page.evaluate(
            "() => [window.scrollY, window.innerHeight, document.body.scrollHeight]"
        )
        at_bottom = (scroll_pos + viewport_h) >= (total_h - BOTTOM_MARGIN)

        new_found = await harvest()
        if new_found:
            print(f"+{new_found} new URLs (total {len(collected)}) @ {scroll_pos:.0f}px")
            stall_started = None  

        if at_bottom or (last_scroll_pos > 0 and abs(scroll_pos - last_scroll_pos) < 5):
            if stall_started is None:
                stall_started = time.monotonic()
                print("Waiting for content to load...")

            elapsed = time.monotonic() - stall_started
            if elapsed >= MAX_STALL_TIME_S:
                print("End of page reached.")
                break

            # Small "jiggle" to trigger lazy loading
            await page.evaluate("() => window.scrollBy({ top: -300, behavior: 'smooth' })")
            await page.wait_for_timeout(500)
            await page.evaluate("() => window.scrollBy({ top: 350, behavior: 'smooth' })")
            await page.wait_for_timeout(STALL_WAIT_MS)
        else:
            stall_started = None  

        last_scroll_pos = scroll_pos

    return list(collected)


# --- Main ---

async def main() -> None:
    async with async_playwright() as pw:
        browser = await pw.firefox.launch(headless=HEADLESS_MODE)
        
        context = await browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:125.0) "
                "Gecko/20100101 Firefox/125.0"
            ),
            viewport={"width": 1440, "height": 900},
        )

        page = await context.new_page()

        print(f"Navigating to {TARGET_URL} ...")
        await page.goto(TARGET_URL, wait_until="domcontentloaded")

        try:
            await page.wait_for_selector(SELECTOR, timeout=15_000)
            print("Selector found.")
        except PlaywrightTimeoutError:
            print(f"Warning: Selector '{SELECTOR}' not found initially.")

        urls = await scroll_and_collect(page, SELECTOR)
        await browser.close()

    if urls:
        inserted_count = insert_csv(OUTPUT_FILE, urls)
        print(f"\nSUCCESS: {inserted_count} new rows added.")
        print(f"File location: {OUTPUT_FILE.absolute()}")
    else:
        print("Error: No URLs were collected. CSV not updated.")


if __name__ == "__main__":
    asyncio.run(main())
