#!/usr/bin/env python3
"""Take English UI screenshots for the project intro video."""

import os
import time
from playwright.sync_api import sync_playwright

OUTPUT_DIR = "/mnt/datadisk0/.openclaw/workspace/projects/mantle-defai-trader/tests/screenshots/en"
os.makedirs(OUTPUT_DIR, exist_ok=True)

FRONTEND_URL = "http://localhost:5173"
VIEWPORT = {"width": 1920, "height": 1080}


def wait_for_network_idle(page, timeout=15000):
    """Wait for network to be mostly idle."""
    try:
        page.wait_for_load_state("networkidle", timeout=timeout)
    except Exception:
        pass


def take_screenshots():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(viewport=VIEWPORT)
        page = context.new_page()

        # Set English language in localStorage before any page load
        page.goto(f"{FRONTEND_URL}/")
        page.evaluate("""() => {
            localStorage.setItem('i18n_language', 'en-US');
        }""")
        print("Set i18n_language to en-US in localStorage")

        # --- 1. Dashboard ---
        print("\n[1/6] Taking Dashboard screenshot...")
        page.goto(f"{FRONTEND_URL}/")
        page.wait_for_timeout(1000)
        page.reload()
        wait_for_network_idle(page, 20000)
        page.wait_for_timeout(6000)
        page.screenshot(path=os.path.join(OUTPUT_DIR, "en-dashboard.png"))
        print(f"  Saved: en-dashboard.png")

        # --- 2. Sentiment (top) ---
        print("\n[2/6] Taking Sentiment top screenshot...")
        page.goto(f"{FRONTEND_URL}/sentiment")
        wait_for_network_idle(page, 20000)
        page.wait_for_timeout(6000)
        page.screenshot(path=os.path.join(OUTPUT_DIR, "en-sentiment-top.png"))
        print(f"  Saved: en-sentiment-top.png")

        # --- 3. Sentiment (Elliott Wave - scroll down) ---
        print("\n[3/6] Taking Sentiment Elliott Wave screenshot...")
        page.goto(f"{FRONTEND_URL}/sentiment")
        wait_for_network_idle(page, 20000)
        page.wait_for_timeout(3000)
        # Scroll down to Elliott Wave section
        page.evaluate("""() => {
            const headers = Array.from(document.querySelectorAll('h2, h3, h4, .card-title, [class*="elliott"], [class*="wave"]'));
            for (const el of headers) {
                if (el.textContent.toLowerCase().includes('elliott') || el.textContent.toLowerCase().includes('wave')) {
                    el.scrollIntoView({ behavior: 'instant', block: 'start' });
                    return;
                }
            }
            // Fallback: scroll 600px down
            window.scrollTo(0, 600);
        }""")
        page.wait_for_timeout(3000)
        page.screenshot(path=os.path.join(OUTPUT_DIR, "en-sentiment-ew.png"))
        print(f"  Saved: en-sentiment-ew.png")

        # --- 4. Sentiment (Backtest tab) ---
        print("\n[4/6] Taking Sentiment Backtest tab screenshot...")
        page.goto(f"{FRONTEND_URL}/sentiment")
        wait_for_network_idle(page, 20000)
        page.wait_for_timeout(3000)
        # Scroll to top first
        page.evaluate("window.scrollTo(0, 0)")
        page.wait_for_timeout(500)
        # Find and click the Backtest tab
        clicked = page.evaluate("""() => {
            const tabs = Array.from(document.querySelectorAll('button, [role="tab"], .tab, [class*="tab"]'));
            for (const tab of tabs) {
                const text = tab.textContent.toLowerCase();
                if (text.includes('backtest') || text.includes('back test') || text.includes('回测')) {
                    tab.click();
                    return true;
                }
            }
            // Also try nav links
            const links = Array.from(document.querySelectorAll('a, button'));
            for (const link of links) {
                const text = link.textContent.toLowerCase();
                if (text.includes('backtest')) {
                    link.click();
                    return true;
                }
            }
            return false;
        }""")
        print(f"  Clicked backtest tab: {clicked}")
        page.wait_for_timeout(4000)
        page.screenshot(path=os.path.join(OUTPUT_DIR, "en-sentiment-backtest.png"))
        print(f"  Saved: en-sentiment-backtest.png")

        # --- 5. On-Chain Signals ---
        print("\n[5/6] Taking On-Chain Signals screenshot...")
        page.goto(f"{FRONTEND_URL}/onchain-signals")
        wait_for_network_idle(page, 20000)
        page.wait_for_timeout(6000)
        page.screenshot(path=os.path.join(OUTPUT_DIR, "en-onchain-signals.png"))
        print(f"  Saved: en-onchain-signals.png")

        # --- 6. On-Chain Signals (expanded detail) ---
        print("\n[6/6] Taking On-Chain Signals expanded detail screenshot...")
        page.goto(f"{FRONTEND_URL}/onchain-signals")
        wait_for_network_idle(page, 20000)
        page.wait_for_timeout(3000)
        # Try to click the first expand/detail row
        clicked = page.evaluate("""() => {
            // Try various selectors for expand buttons or detail rows
            const selectors = [
                'button[class*="expand"]',
                '[class*="expand"]',
                'button svg',
                'tr',
                'tbody tr',
                '[class*="detail"]',
                '[class*="row"]',
                'td'
            ];
            for (const sel of selectors) {
                const els = document.querySelectorAll(sel);
                for (const el of els) {
                    const text = el.textContent.toLowerCase();
                    if (text.includes('detail') || text.includes('expand') || text.includes('view') || el.querySelector('svg') || el.querySelector('button')) {
                        el.click();
                        return {clicked: true, selector: sel, text: el.textContent.slice(0, 80)};
                    }
                }
            }
            // Fallback: click first tbody row
            const row = document.querySelector('tbody tr');
            if (row) {
                row.click();
                return {clicked: true, selector: 'tbody tr', text: row.textContent.slice(0, 80)};
            }
            return {clicked: false};
        }""")
        print(f"  Clicked expand: {clicked}")
        page.wait_for_timeout(3000)
        page.screenshot(path=os.path.join(OUTPUT_DIR, "en-onchain-detail.png"))
        print(f"  Saved: en-onchain-detail.png")

        browser.close()
        print("\n✅ All screenshots taken successfully!")


if __name__ == "__main__":
    take_screenshots()
