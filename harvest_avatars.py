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

def load_csv(path: Path) -> dict[str, dict]:
    """Load existing CSV into a dict keyed by url."""
    rows: dict[str, dict] = {}
    if path.exists():
        try:
            with open(path, newline="", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    if row.get("url"):
                        rows[row["url"]] = row
            print(f"Loaded {len(rows)} existing rows from {path}")
        except Exception as e:
            print(f"Warning: Could not read existing CSV: {e}")
    return rows


def upsert_csv(path: Path, new_srcs: list[str]) -> tuple[int, int]:
    """
    Upsert new_srcs into the CSV.
    """
    now = datetime.now(timezone.utc).isoformat()
    existing = load_csv(path)

    added = 0
    updated = 0
    
    for src in new_srcs:
        if src in existing:
            existing[src]["date_scraped"] = now
            updated += 1
        else:
            existing[src] = {"url": src, "date_scraped": now}
            added += 1

    print(f"Writing {len(existing)} total rows to {path.name}...")

    try:
        data_to_write = list(existing.values())
        
        with open(path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=CSV_FIELDS)
            writer.writeheader()
            writer.writerows(data_to_write)
            f.flush()
            os.fsync(f.fileno()) 
    except Exception as e:
        print(f"Critical Error writing CSV: {e}")

    return added, updated


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
            print(f"+{new_found} new srcs (total {len(collected)}) @ {scroll_pos:.0f}px")
            stall_started = None  

        if at_bottom or (last_scroll_pos > 0 and abs(scroll_pos - last_scroll_pos) < 5):
            if stall_started is None:
                stall_started = time.monotonic()
                print("Waiting for content to load...")

            elapsed = time.monotonic() - stall_started
            if elapsed >= MAX_STALL_TIME_S:
                print("End of page reached.")
                break

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

        srcs = await scroll_and_collect(page, SELECTOR)
        await browser.close()

    if srcs:
        added, updated = upsert_csv(OUTPUT_FILE, srcs)
        print(f"\nSUCCESS: {added} new, {updated} updated. Total: {len(srcs)}")
        print(f"File location: {OUTPUT_FILE.absolute()}")
    else:
        print("Error: No sources were collected. CSV not updated.")


if __name__ == "__main__":
    asyncio.run(main())
