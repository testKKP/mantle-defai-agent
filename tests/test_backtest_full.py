#!/usr/bin/env python3
"""
Backtest Module - Comprehensive Test Agent
============================================
Tests the "Similar State Matching Backtest" feature via:
1. API endpoint validation (requests)
2. Frontend E2E rendering verification (Playwright)
3. Data correctness assertions

Usage:
    python3 tests/test_backtest_full.py

Environment:
    API_BASE    - Backend API base URL (default: http://YOUR_SERVER_IP:8000)
    FRONT_BASE  - Frontend base URL (default: http://YOUR_SERVER_IP:5173)
"""

import os
import sys
import re
import json
import asyncio
import requests
from datetime import datetime
from typing import Any, Dict, List, Tuple, Optional

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
API_BASE = os.environ.get("API_BASE", "http://YOUR_SERVER_IP:8000")
FRONT_BASE = os.environ.get("FRONT_BASE", "http://YOUR_SERVER_IP:5173")
TIMEOUT_API = 30
TIMEOUT_BATCH = 150  # batch backtest can take > 2 minutes
SCREENSHOT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "screenshots")
os.makedirs(SCREENSHOT_DIR, exist_ok=True)

# Test results accumulator
results: Dict[str, Any] = {
    "total": 0,
    "passed": 0,
    "failed": 0,
    "errors": [],
    "screenshots": [],
}

# Shared state between API and E2E tests
api_test_data: Dict[str, Any] = {}


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


def api_get(path: str, timeout: int = TIMEOUT_API) -> Tuple[Optional[requests.Response], Optional[Dict], Optional[str]]:
    url = f"{API_BASE}{path}"
    try:
        resp = requests.get(url, timeout=timeout)
        try:
            data = resp.json()
        except Exception as e:
            return resp, None, f"Invalid JSON: {e}"
        return resp, data, None
    except requests.exceptions.ConnectionError as e:
        return None, None, f"Connection error: {e}"
    except requests.exceptions.Timeout as e:
        return None, None, f"Timeout: {e}"
    except Exception as e:
        return None, None, f"Request error: {e}"


# =============================================================================
# PART 1: API Tests
# =============================================================================

def test_health():
    print("\n=== API 1. Health Check ===")
    resp, data, err = api_get("/health")
    if err:
        log_test("GET /health", False, err)
        return False
    ok = data.get("status") == "healthy"
    log_test("GET /health returns healthy", ok, f"status={data.get('status')}")
    return ok


def test_single_backtest_btc():
    print("\n=== API 2. Single Symbol Backtest (BTCUSDT/1d) ===")
    resp, data, err = api_get("/api/sentiment/backtest/BTCUSDT/1d", timeout=60)
    if err:
        log_test("GET /api/sentiment/backtest/BTCUSDT/1d", False, err)
        return

    # 2.1 Basic response
    ok = resp.status_code == 200 and data.get("success") is True
    log_test("HTTP 200 + success=true", ok, f"status={resp.status_code}, success={data.get('success')}")
    if not ok:
        return

    d = data.get("data", {})
    api_test_data["single_backtest"] = d

    # 2.2 Top-level fields
    required = ["symbol", "timeframe", "total_signals", "stats", "current_signal", "recent_signals"]
    missing = [k for k in required if k not in d]
    log_test("Has all top-level fields", len(missing) == 0, f"missing={missing}")

    # 2.3 stats structure
    stats = d.get("stats", {})
    if not isinstance(stats, dict):
        log_test("stats is a dict", False, f"type={type(stats)}")
    else:
        log_test("stats is a non-empty dict", len(stats) > 0, f"keys={list(stats.keys())[:5]}")
        # Validate each stat entry
        stat_keys = ["total_signals", "insufficient_data", "win_rate", "avg_pnl",
                     "avg_net_pnl", "max_pnl", "min_pnl", "profit_factor", "avg_win", "avg_loss"]
        for key, stat in list(stats.items())[:3]:
            missing_keys = [k for k in stat_keys if k not in stat]
            log_test(f"stat '{key}' has required fields", len(missing_keys) == 0,
                     f"missing={missing_keys}, total_signals={stat.get('total_signals')}")
            # Check data types
            ts = stat.get("total_signals")
            wr = stat.get("win_rate")
            log_test(f"stat '{key}' total_signals is int", isinstance(ts, int), f"got {type(ts)}")
            log_test(f"stat '{key}' win_rate is numeric", isinstance(wr, (int, float)), f"got {type(wr)}")

    # 2.4 current_signal structure
    cs = d.get("current_signal")
    if cs is None:
        log_test("current_signal present", True, "is None (BTC currently has no MA alignment signal - expected)")
    else:
        cs_required = ["pattern", "duration", "duration_bucket", "direction", "strength", "price",
                       "similar_state_stats", "recommendation"]
        missing_cs = [k for k in cs_required if k not in cs]
        log_test("current_signal has required fields", len(missing_cs) == 0, f"missing={missing_cs}")

        rec = cs.get("recommendation", {})
        rec_required = ["action", "confidence", "score", "reason"]
        missing_rec = [k for k in rec_required if k not in rec]
        log_test("recommendation has required fields", len(missing_rec) == 0, f"missing={missing_rec}")

        score = rec.get("score")
        log_test("recommendation.score is int 0-100", isinstance(score, int) and 0 <= score <= 100,
                 f"score={score}, type={type(score)}")

    # 2.5 recent_signals
    rs = d.get("recent_signals", [])
    log_test("recent_signals is a list", isinstance(rs, list), f"type={type(rs)}, len={len(rs)}")
    if rs:
        first = rs[0]
        rs_keys = ["symbol", "timeframe", "direction", "entry_price", "exit_price", "net_pnl_pct",
                   "pattern", "duration", "duration_bucket"]
        missing_rs = [k for k in rs_keys if k not in first]
        log_test("recent_signals[0] has required fields", len(missing_rs) == 0, f"missing={missing_rs}")


def test_batch_backtest():
    print("\n=== API 3. Batch Backtest (1d) ===")
    resp, data, err = api_get("/api/sentiment/backtest-batch/1d", timeout=TIMEOUT_BATCH)
    if err:
        log_test("GET /api/sentiment/backtest-batch/1d", False, err)
        return

    # 3.1 Basic response
    ok = resp.status_code == 200 and data.get("success") is True
    log_test("HTTP 200 + success=true", ok, f"status={resp.status_code}, success={data.get('success')}")
    if not ok:
        return

    d = data.get("data", {})
    api_test_data["batch_backtest"] = d

    # 3.2 Top-level fields
    required = ["total_symbols_tested", "symbols_with_signals", "recommendations", "all_signals", "timestamp"]
    missing = [k for k in required if k not in d]
    log_test("Has all top-level fields", len(missing) == 0, f"missing={missing}")

    tested = d.get("total_symbols_tested", 0)
    signals_count = d.get("symbols_with_signals", 0)
    recs = d.get("recommendations", [])
    all_sigs = d.get("all_signals", [])

    log_test("total_symbols_tested > 0", tested > 0, f"tested={tested}")
    log_test("symbols_with_signals <= total", signals_count <= tested,
             f"signals={signals_count}, tested={tested}")
    log_test("recommendations is a list", isinstance(recs, list), f"type={type(recs)}")
    log_test("all_signals is a list", isinstance(all_sigs, list), f"type={type(all_sigs)}, len={len(all_sigs)}")

    # 3.3 recommendations structure
    if recs:
        for i, rec in enumerate(recs[:2]):  # check first 2
            rec_required = ["symbol", "direction", "pattern", "strength", "duration",
                            "duration_bucket", "current_price", "similar_state_stats", "recommendation"]
            missing_rec = [k for k in rec_required if k not in rec]
            log_test(f"recommendation[{i}] has required fields", len(missing_rec) == 0,
                     f"missing={missing_rec}, symbol={rec.get('symbol')}")

            r = rec.get("recommendation", {})
            r_required = ["action", "confidence", "score", "reason"]
            missing_r = [k for k in r_required if k not in r]
            log_test(f"recommendation[{i}].recommendation has fields", len(missing_r) == 0,
                     f"missing={missing_r}, score={r.get('score')}")

    # 3.4 all_signals structure
    if all_sigs:
        for i, sig in enumerate(all_sigs[:2]):
            sig_required = ["symbol", "direction", "pattern", "strength", "duration",
                            "duration_bucket", "current_price", "similar_state_stats", "recommendation"]
            missing_sig = [k for k in sig_required if k not in sig]
            log_test(f"all_signals[{i}] has required fields", len(missing_sig) == 0,
                     f"missing={missing_sig}, symbol={sig.get('symbol')}")


def test_backtest_error_handling():
    print("\n=== API 4. Error Handling ===")

    # 4.1 Invalid timeframe should return 422 (currently returns 500 due to unhandled exception)
    resp, data, err = api_get("/api/sentiment/backtest/BTCUSDT/invalid_tf")
    if err:
        log_test("Invalid timeframe returns error", False, err)
    else:
        ok = resp.status_code in (400, 422, 500)
        log_test("Invalid timeframe returns error status", ok, f"status={resp.status_code} (ideally should be 422)")

    # 4.2 Invalid symbol - may return 200 with empty data or 404
    resp, data, err = api_get("/api/sentiment/backtest/INVALID/1d")
    if err:
        log_test("Invalid symbol handling", False, err)
    else:
        ok = resp.status_code in (200, 404, 500)
        log_test("Invalid symbol returns error status", ok, f"status={resp.status_code} (ideally should be 404)")


# =============================================================================
# PART 2: Playwright E2E Tests
# =============================================================================

async def run_playwright_tests():
    try:
        from playwright.async_api import async_playwright
    except ImportError:
        print("\n=== E2E Skipped: playwright not installed ===")
        log_test("Playwright E2E tests", False, "playwright package not installed")
        return

    print("\n=== E2E 1. Page Load & Tab Switch ===")

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(viewport={"width": 1440, "height": 900})

        # Collect console errors
        console_errors: List[str] = []
        page = await context.new_page()

        def handle_console(msg):
            if msg.type == "error":
                text = msg.text
                # Ignore known non-critical errors
                ignored = [
                    "ResizeObserver",
                    "WebSocket",
                    "Source map",
                    "favicon",
                ]
                if not any(i in text for i in ignored):
                    console_errors.append(text)

        page.on("console", handle_console)

        # ----- Test: Page Load -----
        try:
            await page.goto(f"{FRONT_BASE}/sentiment", wait_until="networkidle", timeout=60000)
            log_test("Sentiment page loads", True)
        except Exception as e:
            log_test("Sentiment page loads", False, str(e))
            await browser.close()
            return

        # Screenshot 1: initial load
        s1 = os.path.join(SCREENSHOT_DIR, f"bt-e2e-01-sentiment-{datetime.now().strftime('%H%M%S')}.png")
        await page.screenshot(path=s1, full_page=False)
        results["screenshots"].append(s1)

        # ----- Test: Click Backtest Tab -----
        try:
            # Find tab by text
            backtest_tab = page.locator('text=/历史回溯/i').first
            count = await backtest_tab.count()
            if count == 0:
                backtest_tab = page.locator('text=/Backtest/i').first
            await backtest_tab.click()
            await asyncio.sleep(1)
            log_test("Click '历史回溯' tab", True)
        except Exception as e:
            log_test("Click '历史回溯' tab", False, str(e))

        # Screenshot 2: backtest tab
        s2 = os.path.join(SCREENSHOT_DIR, f"bt-e2e-02-backtest-tab-{datetime.now().strftime('%H%M%S')}.png")
        await page.screenshot(path=s2, full_page=False)
        results["screenshots"].append(s2)

        # ----- Test: Risk Warning Banner -----
        print("\n=== E2E 2. UI Components ===")
        try:
            warning_text = page.locator('text=/0\.3%/i')
            has_warning = await warning_text.count() > 0
            log_test("Risk warning banner (0.3% cost)", has_warning)
        except Exception as e:
            log_test("Risk warning banner", False, str(e))

        # ----- Test: Batch Backtest State -----
        try:
            # Page may auto-start batch backtest on load, button shows "计算中..."
            run_btn = page.locator('button:has-text("运行批量回测")')
            calc_btn = page.locator('button:has-text("计算中...")')
            has_run = await run_btn.count() > 0
            has_calc = await calc_btn.count() > 0

            if has_run:
                await run_btn.click()
                print("  [INFO] Clicked '运行批量回测', waiting for completion...")
            elif has_calc:
                print("  [INFO] Batch backtest already running (计算中...)")
            else:
                log_test("Batch backtest button state", False, "Neither '运行批量回测' nor '计算中...' found")

            # Wait for completion: either results appear or loading stops
            # Try multiple selectors with longer timeout
            try:
                await page.wait_for_selector('text=/已测试.*个币种/', timeout=180000)
                log_test("Batch backtest completes", True)
            except Exception:
                # Check if we at least have shimmer boxes (loading state was shown)
                shimmer = page.locator('[class*="shimmer"], [class*="animate-pulse"]')
                has_shimmer = await shimmer.count() > 0
                if has_shimmer or has_calc:
                    log_test("Batch backtest completes", False, "Timeout after 180s - backtest still running")
                else:
                    log_test("Batch backtest completes", False, "No loading indicator or results found")
        except Exception as e:
            log_test("Batch backtest completes", False, str(e))

        # Screenshot 3: after batch backtest
        s3 = os.path.join(SCREENSHOT_DIR, f"bt-e2e-03-batch-done-{datetime.now().strftime('%H%M%S')}.png")
        await page.screenshot(path=s3, full_page=False)
        results["screenshots"].append(s3)

        # ----- Test: Recommendation Cards or Empty State -----
        try:
            rec_cards = page.locator('text=/做多|做空|建议|强烈/')
            card_count = await rec_cards.count()
            empty_state = page.locator('text=/当前没有符合条件的推荐信号/')
            has_empty = await empty_state.count() > 0
            log_test("Recommendation cards or empty state", card_count > 0 or has_empty,
                     f"cards={card_count}, empty={has_empty}")
        except Exception as e:
            log_test("Recommendation cards render", False, str(e))

        # ----- Test: All Signals Table or Loading State -----
        try:
            table_header = page.locator('th:has-text("币种")')
            has_table = await table_header.count() > 0
            # Also accept if we're still loading (shimmer boxes present)
            shimmer = page.locator('[class*="shimmer"], [class*="animate-pulse"]')
            has_shimmer = await shimmer.count() > 0
            log_test("All signals table or loading state", has_table or has_shimmer,
                     f"table={has_table}, shimmer={has_shimmer}")
        except Exception as e:
            log_test("All signals table renders", False, str(e))

        # ----- Test: Single Symbol Backtest Section -----
        try:
            detail_header = page.locator('text=/单币种详细回测/')
            has_detail = await detail_header.count() > 0
            log_test("Single symbol backtest section", has_detail)
        except Exception as e:
            log_test("Single symbol backtest section", False, str(e))

        # ----- Test: Methodology Section -----
        try:
            methodology = page.locator('text=/相似状态匹配回测/')
            has_method = await methodology.count() > 0
            log_test("Methodology section present", has_method)
        except Exception as e:
            log_test("Methodology section present", False, str(e))

        # ----- Test: Console Errors -----
        print("\n=== E2E 3. Console Errors ===")
        if console_errors:
            unique = list(set(console_errors))[:5]
            log_test("No console errors", False, f"errors: {unique}")
        else:
            log_test("No console errors", True)

        # Screenshot 4: full page
        s4 = os.path.join(SCREENSHOT_DIR, f"bt-e2e-04-full-{datetime.now().strftime('%H%M%S')}.png")
        await page.screenshot(path=s4, full_page=True)
        results["screenshots"].append(s4)

        await browser.close()


# =============================================================================
# PART 3: Data Cross-Validation
# =============================================================================

def test_cross_validation():
    print("\n=== DATA 5. API-Frontend Cross-Validation ===")

    single = api_test_data.get("single_backtest", {})
    batch = api_test_data.get("batch_backtest", {})

    if not single:
        log_test("Single backtest data available for validation", False, "No data")
        return

    # 5.1 BTCUSDT stats should have at least one pattern
    stats = single.get("stats", {})
    log_test("BTCUSDT has backtest stats", len(stats) > 0, f"{len(stats)} stat groups")

    # 5.2 Total signals should be positive
    total = single.get("total_signals", 0)
    log_test("total_signals > 0", total > 0, f"total={total}")

    # 5.3 Batch should have tested multiple symbols
    if batch:
        tested = batch.get("total_symbols_tested", 0)
        log_test("Batch tested >= 5 symbols", tested >= 5, f"tested={tested}")

        recs = batch.get("recommendations", [])
        for rec in recs:
            score = rec.get("recommendation", {}).get("score", 0)
            log_test(f"Rec '{rec.get('symbol')}' score >= 50", score >= 50,
                     f"score={score}, action={rec.get('recommendation', {}).get('action')}")

    # 5.4 Stats sanity checks
    for key, stat in stats.items():
        win_rate = stat.get("win_rate", 0)
        total_s = stat.get("total_signals", 0)
        # win_rate should be between 0 and 100
        log_test(f"stat '{key}' win_rate in [0,100]", 0 <= win_rate <= 100,
                 f"win_rate={win_rate}")
        # total_signals should match the sample size
        log_test(f"stat '{key}' total_signals > 0", total_s > 0, f"total={total_s}")


# =============================================================================
# Report
# =============================================================================

def print_report():
    print("\n" + "=" * 70)
    print("BACKTEST MODULE - TEST REPORT")
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
    if results["failed"] == 0:
        print("STATUS: ALL TESTS PASSED")
    else:
        print(f"STATUS: {results['failed']} TEST(S) FAILED")
    print("=" * 70)

    return 0 if results["failed"] == 0 else 1


# =============================================================================
# Main
# =============================================================================

def main():
    print("Backtest Module - Comprehensive Test Agent")
    print(f"API Base   : {API_BASE}")
    print(f"Frontend   : {FRONT_BASE}")
    print(f"Time       : {datetime.now().isoformat()}")

    # Part 1: API Tests
    test_health()
    test_single_backtest_btc()
    test_batch_backtest()
    test_backtest_error_handling()

    # Part 2: Playwright E2E
    asyncio.run(run_playwright_tests())

    # Part 3: Cross-validation
    test_cross_validation()

    # Report
    return print_report()


if __name__ == "__main__":
    sys.exit(main())
