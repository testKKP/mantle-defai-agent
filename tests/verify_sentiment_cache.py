#!/usr/bin/env python3
"""Playwright verification for Sentiment page: no refresh button, no console errors."""
import asyncio
from playwright.async_api import async_playwright

URL = "http://43.134.37.174/sentiment"
SCREENSHOT_PATH = "/root/.openclaw/workspace/projects/mantle-defai-trader/tests/screenshots/sentiment_verification.png"


async def main():
    console_errors = []
    console_messages = []

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(viewport={"width": 1920, "height": 1080})
        page = await context.new_page()

        page.on("console", lambda msg: console_messages.append(f"[{msg.type}] {msg.text}"))
        page.on("pageerror", lambda err: console_errors.append(str(err)))

        await page.goto(URL, wait_until="networkidle", timeout=60000)
        await asyncio.sleep(3)

        await page.screenshot(path=SCREENSHOT_PATH, full_page=True)

        refresh_candidates = []

        # Text-based refresh labels
        text_candidates = ["刷新", "Refresh", "refreshNow", "立即刷新", "refresh"]
        for text in text_candidates:
            locators = [
                page.locator(f"button:has-text('{text}')"),
                page.locator(f"a:has-text('{text}')"),
                page.locator(f"[role='button']:has-text('{text}')"),
            ]
            for loc in locators:
                try:
                    count = await loc.count()
                    if count > 0:
                        refresh_candidates.append(f"text='{text}' count={count}")
                except Exception:
                    pass

        # Inspect interactive elements for refresh-cw icon and report details
        try:
            btns = await page.locator("button, a, [role='button']").all()
            for idx, btn in enumerate(btns):
                html = await btn.inner_html()
                if "refresh-cw" in html.lower() or "refreshcw" in html.lower():
                    txt = await btn.text_content()
                    outer = await btn.evaluate("el => el.outerHTML")
                    refresh_candidates.append(
                        f"interactive element with refresh-cw icon: text='{txt.strip() if txt else ''}' outer={outer[:500]}"
                    )
        except Exception as e:
            print(f"Error inspecting interactive elements: {e}")

        # Header area check
        try:
            header = page.locator("h1:has-text('Market Sentiment'), h2:has-text('Market Sentiment')")
            if await header.count() > 0:
                header_html = await header.first.inner_html()
                if "refresh" in header_html.lower():
                    refresh_candidates.append("refresh icon found inside sentiment header")
        except Exception:
            pass

        await browser.close()

    print(f"Screenshot saved: {SCREENSHOT_PATH}")
    print(f"Console errors ({len(console_errors)}):")
    for err in console_errors:
        print("  -", err)
    print(f"Console messages ({len(console_messages)}):")
    for msg in console_messages[:20]:
        print("  -", msg)
    print(f"Refresh candidates ({len(refresh_candidates)}):")
    for c in refresh_candidates:
        print("  -", c)

    if console_errors or refresh_candidates:
        print("\nVERIFICATION_FAILED")
    else:
        print("\nVERIFICATION_OK")


if __name__ == "__main__":
    asyncio.run(main())
