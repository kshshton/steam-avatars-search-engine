import asyncio
import csv
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv
from playwright.async_api import async_playwright, Page, TimeoutError as PlaywrightTimeoutError

load_dotenv()

#  Config 
TARGET_URL = os.getenv("SOURCE_URL")
if not TARGET_URL:
    sys.exit("\u274c  SOURCE_URL is not set — add it to your .env file")

SELECTOR    = "._2YbSwspXZ90_vgzS5O3X4F"  #  change me if needed
OUTPUT_FILE = Path("avatars.csv")

CSV_FIELDS = ["url", "date_scraped"]
SCROLL_STEP      = 600    # px per tick (smaller = more scroll events fired)
TICK_DELAY_MS    = 600    # ms between ticks (give network time to respond)
STALL_WAIT_MS    = 4000   # ms to wait each time we're stuck at the bottom
MAX_STALL_TIME_S = 30     # total seconds to keep trying before giving up
BOTTOM_MARGIN    = 100    # px tolerance for "at bottom" detection
HEADLESS_MODE    = True   # cli only mode
# 


def load_csv(path: Path) -> dict[str, dict]:
    """Load existing CSV into a dict keyed by url."""
    rows: dict[str, dict] = {}
    if path.exists():
        with open(path, newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                rows[row["url"]] = row
        print(f"Loaded {len(rows)} existing rows from {path}")
    return rows


def upsert_csv(path: Path, new_srcs: list[str]) -> tuple[int, int]:
    """
    Upsert new_srcs into the CSV at path.

    Returns (added, updated) counts.
    """
    now = datetime.now(timezone.utc).isoformat()
    existing = load_csv(path)

    added = updated = 0
    for src in new_srcs:
        if src in existing:
            existing[src]["date_scraped"] = now
            updated += 1
        else:
            existing[src] = {"url": src, "date_scraped": now}
            added += 1

    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_FIELDS)
        writer.writeheader()
        writer.writerows(existing.values())

    return added, updated


#  Scroll logic 

async def scroll_and_collect(page: Page, selector: str) -> list[str]:
    """
    Steam's Points Shop uses a virtualised list — only items in the viewport
    exist in the DOM at any time.  The page height barely changes as you scroll.

    Strategy:
       Harvest visible srcs on every tick into a running set.
       Track scroll position, not page height, to detect the real end.
       Stall clock only resets when NEW srcs appear (not when height changes).
    """
    import time
    print("Starting scroll collector (virtualised-list mode)…")

    collected: set[str] = set()
    last_scroll_pos: float = -1
    stall_started: float | None = None

    async def harvest() -> int:
        """Grab all currently visible srcs; return count of newly found ones."""
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

        # Harvest on every tick — virtualised items disappear when they scroll out
        new_found = await harvest()
        if new_found:
            print(f"+{new_found} new srcs (total {len(collected)}) @ scroll {scroll_pos:.0f}px")
            stall_started = None  # fresh content resets stall clock

        if at_bottom or abs(scroll_pos - last_scroll_pos) < 5:
            if stall_started is None:
                stall_started = time.monotonic()
                print(f"Reached bottom, waiting for more content… (total so far: {len(collected)})")

            elapsed = time.monotonic() - stall_started
            if elapsed >= MAX_STALL_TIME_S:
                print(f"No new srcs for {MAX_STALL_TIME_S}s — feed exhausted")
                break

            # Nudge up then back down to re-trigger the virtualised renderer
            await page.evaluate("() => window.scrollBy({ top: -400, behavior: 'smooth' })")
            await page.wait_for_timeout(500)
            await page.evaluate("() => window.scrollBy({ top: 450, behavior: 'smooth' })")
            await page.wait_for_timeout(STALL_WAIT_MS)

            remaining = MAX_STALL_TIME_S - (time.monotonic() - stall_started)
            print(f"Still waiting… ({remaining:.0f}s left)")
        else:
            stall_started = None  # still making progress

        last_scroll_pos = scroll_pos

    results = list(collected)
    print(f"\nCollection complete — {len(results)} unique srcs")
    return results


#  Main 

async def main() -> None:
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(
            headless=HEADLESS_MODE,
            args=["--disable-blink-features=AutomationControlled"],
        )
        context = await browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            viewport={"width": 1440, "height": 900},
            locale="en-US",
        )
        await context.add_init_script(
            "Object.defineProperty(navigator, 'webdriver', { get: () => undefined })"
        )

        page = await context.new_page()

        print(f"Navigating to {TARGET_URL} …")
        await page.goto(TARGET_URL, wait_until="domcontentloaded")

        try:
            await page.wait_for_selector(SELECTOR, timeout=15_000)
            print(f"Selector '{SELECTOR}' found on page")
        except PlaywrightTimeoutError:
            print(f"Selector '{SELECTOR}' not found within 15 s — continuing anyway")

        srcs = await scroll_and_collect(page, SELECTOR)
        await browser.close()

    #  Upsert CSV 
    added, updated = upsert_csv(OUTPUT_FILE, srcs)
    print(
    f"CSV saved to {OUTPUT_FILE} — "
        f"{added} new row(s) added, {updated} row(s) updated"
    )


if __name__ == "__main__":
    asyncio.run(main())
