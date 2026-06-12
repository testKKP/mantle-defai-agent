#!/usr/bin/env python3
"""
Comprehensive Test Agent for All Recent Changes
=================================================
Tests:
1. TVL: Top 10 Mantle protocols with 1d/7d changes
2. Sentiment: IP whitelist enforcement + auto backtest enrichment
3. Frontend visual verification (Playwright screenshots)

Usage:
    python3 tests/test_all_changes.py
"""

import os
import sys
import re
import json
import asyncio
import requests
from datetime import datetime
from typing import Any, Dict, List, Tuple, Optional

API_BASE = os.environ.get("API_BASE", "http://43.134.37.174:8000")
FRONT_BASE = os.environ.get("FRONT_BASE", "http://43.134.37.174:5173")
TIMEOUT_API = 30
TIMEOUT_BATCH = 150
SCREENSHOT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "screenshots")
os.makedirs(SCREENSHOT_DIR, exist_ok=True)

results: Dict[str, Any] = {
    "total": 0, "passed": 0, "failed": 0, "errors": [], "screenshots": [],
}

def log_test(name: str, passed: bool, details: str = ""):
    results["total"] += 1
    status = "PASS" if passed else "FAIL"
    if passed:
        results["passed"] += 1
    else:
        results["failed"] += 1
        results["errors"].append({"test": name, "details": details})
    detail_str = f" | {details}" if details else ""
    print(f"  [{status}] {name}{detail_str}")

def api_get(path: str, timeout: int = TIMEOUT_API, headers: dict = None) -> Tuple[Optional[requests.Response], Optional[Dict], Optional[str]]:
    url = f"{API_BASE}{path}"
    try:
        resp = requests.get(url, timeout=timeout, headers=headers)
        try:
            data = resp.json()
        except Exception as e:
            return resp, None, f"Invalid JSON: {e}"
        return resp, data, None
    except Exception as e:
        return None, None, f"Request error: {e}"

# =============================================================================
# PART 1: TVL Tests
# =============================================================================

def test_tvl_top10():
    print("\n=== TVL 1. Top 10 Protocols API ===")
    resp, data, err = api_get("/api/onchain/protocols")
    if err:
        log_test("GET /api/onchain/protocols", False, err)
        return
    ok = resp.status_code == 200 and data.get("success") is True
    log_test("HTTP 200 + success", ok, f"status={resp.status_code}")
    if not ok:
        return

    d = data.get("data", {})
    protocols = d.get("protocols", [])
    log_test("Returns protocols list", isinstance(protocols, list), f"type={type(protocols)}")
    log_test("Returns exactly 10 protocols", len(protocols) == 10, f"count={len(protocols)}")

    if protocols:
        first = protocols[0]
        has_24h = "tvl_change_24h" in first
        has_7d = "tvl_change_7d" in first
        log_test("Protocol has tvl_change_24h", has_24h, f"keys={list(first.keys())[:8]}")
        log_test("Protocol has tvl_change_7d", has_7d)
        log_test("Protocols sorted by TVL desc", first.get("tvl", 0) >= protocols[-1].get("tvl", 0),
                 f"first={first.get('tvl')}, last={protocols[-1].get('tvl')}")

        # Check all protocols have required fields
        for i, p in enumerate(protocols):
            for field in ["slug", "name", "category", "tvl"]:
                if field not in p:
                    log_test(f"Protocol[{i}] has {field}", False, f"missing {field}")
                    break
            else:
                continue
            break
        else:
            log_test("All protocols have required fields", True)

def test_tvl_whitelist_rejection():
    print("\n=== TVL 2. Non-whitelist IP rejection (via X-Forwarded-For) ===")
    # Test with a fake IP via X-Forwarded-For header
    headers = {"X-Forwarded-For": "1.2.3.4"}
    resp, data, err = api_get("/api/onchain/protocols", headers=headers)
    # TVL endpoint does NOT have whitelist, so this should still work
    # Only sentiment/backtest have whitelist
    log_test("TVL endpoint accessible without whitelist", resp is not None and resp.status_code == 200,
             f"status={resp.status_code if resp else 'none'}")

# =============================================================================
# PART 2: Sentiment + IP Whitelist + Backtest Enrichment
# =============================================================================

def test_sentiment_whitelist():
    print("\n=== SENTIMENT 3. IP Whitelist Enforcement ===")

    # 3.1 Sentiment endpoint is PUBLIC (no whitelist gate) but filters data for non-auth users
    headers = {"X-Forwarded-For": "1.2.3.4"}
    resp, data, err = api_get("/api/sentiment/latest", headers=headers)
    if err:
        log_test("Sentiment latest accessible to all", False, err)
    else:
        ok = resp.status_code == 200
        has_login_req = data.get("data", {}).get("login_required") is True if isinstance(data, dict) else False
        log_test("Sentiment latest accessible to all (filtered)", ok,
                 f"status={resp.status_code}, login_required={has_login_req}")

    # 3.2 Without whitelist IP on backtest -> should get 403
    resp, data, err = api_get("/api/sentiment/backtest/BTCUSDT/1d", headers=headers)
    if err:
        log_test("Non-whitelist IP rejected (backtest)", False, err)
    else:
        ok = resp.status_code == 403
        log_test("Non-whitelist IP rejected (backtest)", ok, f"status={resp.status_code}")

    # 3.3 Without whitelist IP on batch backtest -> should get 403
    resp, data, err = api_get("/api/sentiment/backtest-batch/1d", headers=headers)
    if err:
        log_test("Non-whitelist IP rejected (batch)", False, err)
    else:
        ok = resp.status_code == 403
        log_test("Non-whitelist IP rejected (batch)", ok, f"status={resp.status_code}")

    # 3.4 Local IP can access sentiment (public endpoint)
    resp, data, err = api_get("/api/sentiment/latest")
    if err:
        log_test("Local IP sentiment access", False, err)
    else:
        ok = resp.status_code == 200
        log_test("Local IP can access sentiment (public)", ok, f"status={resp.status_code}")

def test_sentiment_backtest_enrichment():
    print("\n=== SENTIMENT 4. Auto Backtest Enrichment ===")
    # Since whitelist blocks us from direct API, test via debug endpoint or check structure
    # Actually, let's check if the server is accessible with the correct origin
    # The server's own IP is in whitelist, so if we set X-Forwarded-For to the server IP:
    headers = {"X-Forwarded-For": "43.134.37.174"}
    resp, data, err = api_get("/api/sentiment/latest", headers=headers)
    if err:
        log_test("Whitelisted IP can access sentiment", False, err)
        return
    ok = resp.status_code == 200 and data.get("success") is True
    log_test("Whitelisted IP can access sentiment", ok, f"status={resp.status_code}")
    if not ok:
        return

    d = data.get("data", {})
    # Check if backtest_results exists
    bt_results = d.get("backtest_results")
    has_position_report = "position_report" in d
    log_test("Response has position_report", has_position_report)

    if bt_results:
        log_test("Response has backtest_results", True,
                 f"keys={list(bt_results.keys())[:5]}, count={len(bt_results)}")
        # Validate structure
        for key, bt in list(bt_results.items())[:2]:
            has_stats = "stats" in bt
            has_current = "current_signal" in bt
            log_test(f"backtest '{key}' has stats", has_stats)
            log_test(f"backtest '{key}' has current_signal", has_current)
    else:
        # position_report might be empty (no signals currently), so no backtest_results is expected
        pr = d.get("position_report", {})
        has_signals = any(len(pr.get(tf, {}).get("long", [])) > 0 or len(pr.get(tf, {}).get("short", [])) > 0 for tf in ["1d", "4h", "1w"])
        if has_signals:
            log_test("Response has backtest_results", False, "position_report has signals but no backtest_results")
        else:
            log_test("No backtest_results (no signals)", True, "No long/short signals currently")

# =============================================================================
# PART 3: Playwright E2E Visual Tests
# =============================================================================

async def run_playwright_tests():
    try:
        from playwright.async_api import async_playwright
    except ImportError:
        print("\n=== E2E Skipped: playwright not installed ===")
        log_test("Playwright E2E tests", False, "playwright not installed")
        return

    print("\n=== E2E 5. Protocols Page (TVL Top 10) ===")

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(viewport={"width": 1440, "height": 900})
        page = await context.new_page()

        console_errors: List[str] = []
        def handle_console(msg):
            if msg.type == "error":
                text = msg.text
                ignored = ["ResizeObserver", "WebSocket", "Source map", "favicon"]
                if not any(i in text for i in ignored):
                    console_errors.append(text)
        page.on("console", handle_console)

        # ----- Protocols Page -----
        try:
            await page.goto(f"{FRONT_BASE}/protocols", wait_until="networkidle", timeout=60000)
            log_test("Protocols page loads", True)
        except Exception as e:
            log_test("Protocols page loads", False, str(e))
            await browser.close()
            return

        await asyncio.sleep(2)

        # Check "Top 10" title
        top10_text = page.locator('text=/Top 10/i')
        has_top10 = await top10_text.count() > 0
        log_test("Protocols page shows 'Top 10'", has_top10)

        # Check 7d change column in table
        col_7d = page.locator('th:has-text("7d 变化")')
        has_7d = await col_7d.count() > 0
        log_test("Protocols table has '7d 变化' column", has_7d)

        # Screenshot protocols
        s1 = os.path.join(SCREENSHOT_DIR, f"all-protocols-{datetime.now().strftime('%H%M%S')}.png")
        await page.screenshot(path=s1, full_page=True)
        results["screenshots"].append(s1)

        print("\n=== E2E 6. Sentiment Page (Whitelist + Backtest) ===")

        # ----- Sentiment Page -----
        try:
            await page.goto(f"{FRONT_BASE}/sentiment", wait_until="networkidle", timeout=60000)
            log_test("Sentiment page loads", True)
        except Exception as e:
            log_test("Sentiment page loads", False, str(e))
            await browser.close()
            return

        await asyncio.sleep(2)

        # Check for whitelist error banner (frontend should show access denied)
        error_text = page.locator('text=/403|Access denied|访问受限|白名单/i')
        has_error = await error_text.count() > 0
        log_test("Sentiment page shows content (no 403 blocker)", not has_error,
                 f"error elements={await error_text.count()}")

        # If no error, check for backtest enrichment section
        if not has_error:
            bt_section = page.locator('text=/推荐信号回溯验证|backtest_results/i')
            has_bt = await bt_section.count() > 0
            log_test("Sentiment page has backtest enrichment section", has_bt)

        # Screenshot sentiment
        s2 = os.path.join(SCREENSHOT_DIR, f"all-sentiment-{datetime.now().strftime('%H%M%S')}.png")
        await page.screenshot(path=s2, full_page=True)
        results["screenshots"].append(s2)

        # Check console errors
        print("\n=== E2E 7. Console Errors ===")
        if console_errors:
            unique = list(set(console_errors))[:5]
            log_test("No console errors", False, f"errors: {unique}")
        else:
            log_test("No console errors", True)

        await browser.close()

# =============================================================================
# Report
# =============================================================================

def print_report():
    print("\n" + "=" * 70)
    print("COMPREHENSIVE CHANGE TEST REPORT")
    print("=" * 70)
    print(f"Total tests run : {results['total']}")
    print(f"Passed          : {results['passed']}")
    print(f"Failed          : {results['failed']}")
    rate = results['passed'] / results['total'] * 100 if results['total'] > 0 else 0
    print(f"Success rate    : {rate:.1f}%")

    if results["errors"]:
        print("\n--- FAILED TEST DETAILS ---")
        for e in results["errors"]:
            print(f"\n* {e['test']}")
            print(f"  -> {e['details']}")
    else:
        print("\nAll tests passed! ✓")

    if results["screenshots"]:
        print("\n--- SCREENSHOTS ---")
        for s in results["screenshots"]:
            print(f"  {s}")

    print("\n" + "=" * 70)
    return 0 if results["failed"] == 0 else 1

def main():
    print("Comprehensive Test Agent - All Recent Changes")
    print(f"API Base   : {API_BASE}")
    print(f"Frontend   : {FRONT_BASE}")
    print(f"Time       : {datetime.now().isoformat()}")

    test_tvl_top10()
    test_tvl_whitelist_rejection()
    test_sentiment_whitelist()
    test_sentiment_backtest_enrichment()
    asyncio.run(run_playwright_tests())

    return print_report()

if __name__ == "__main__":
    sys.exit(main())
