#!/usr/bin/env python3
"""
Visual Regression Test for Mantle DeFAI Trader - Sentiment Page
===============================================================
Tests the Sentiment page at multiple viewports, captures screenshots,
performs visual assertions, and verifies interactions.
"""

import os
import sys
import time
from pathlib import Path
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional

from playwright.sync_api import sync_playwright, Page, Browser, BrowserContext, expect

# ─── Configuration ───────────────────────────────────────────────
BASE_URL = "http://127.0.0.1:5173"
SENTIMENT_PATH = "/sentiment"
OUTPUT_DIR = Path(__file__).parent / "screenshots"
HEADLESS = True

VIEWPORTS = {
    "desktop": {"width": 1280, "height": 800},
    "mobile": {"width": 375, "height": 812},
}

# ─── Test Report Data Structures ─────────────────────────────────
@dataclass
class AssertionResult:
    name: str
    passed: bool
    message: str
    viewport: str = "desktop"

@dataclass
class ScreenshotResult:
    name: str
    path: Path
    viewport: str
    success: bool
    error: Optional[str] = None

@dataclass
class TestReport:
    screenshots: List[ScreenshotResult] = field(default_factory=list)
    assertions: List[AssertionResult] = field(default_factory=list)
    interactions: List[Dict[str, Any]] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)

    def add_assertion(self, name: str, passed: bool, message: str, viewport: str = "desktop"):
        self.assertions.append(AssertionResult(name, passed, message, viewport))

    def add_screenshot(self, name: str, path: Path, viewport: str, success: bool, error: Optional[str] = None):
        self.screenshots.append(ScreenshotResult(name, path, viewport, success, error))

    def add_error(self, msg: str):
        self.errors.append(msg)

    def print_report(self):
        print("\n" + "=" * 70)
        print("   VISUAL REGRESSION TEST REPORT — Sentiment Page")
        print("=" * 70)

        # Screenshots
        print("\n📸  SCREENSHOTS CAPTURED")
        print("-" * 50)
        for s in self.screenshots:
            status = "✅" if s.success else "❌"
            print(f"  {status} {s.name} ({s.viewport})")
            print(f"     → {s.path}")
            if s.error:
                print(f"     ERROR: {s.error}")

        # Assertions
        print("\n🔍  VISUAL ASSERTIONS")
        print("-" * 50)
        passed = sum(1 for a in self.assertions if a.passed)
        total = len(self.assertions)
        for a in self.assertions:
            status = "✅ PASS" if a.passed else "❌ FAIL"
            print(f"  {status} [{a.viewport}] {a.name}")
            if not a.passed:
                print(f"        → {a.message}")
        print(f"\n  Assertion Summary: {passed}/{total} passed")

        # Interactions
        print("\n🖱️   INTERACTION TESTS")
        print("-" * 50)
        for i in self.interactions:
            status = "✅" if i.get("success") else "❌"
            print(f"  {status} {i.get('action', 'unknown')}")
            if not i.get("success"):
                print(f"     → {i.get('error', 'unknown error')}")

        # Errors
        if self.errors:
            print("\n⚠️   GLOBAL ERRORS")
            print("-" * 50)
            for e in self.errors:
                print(f"  ❌ {e}")

        print("\n" + "=" * 70)
        overall = "PASS ✅" if (passed == total and not self.errors) else "FAIL ❌"
        print(f"   OVERALL RESULT: {overall}")
        print("=" * 70 + "\n")


# ─── Helper Functions ────────────────────────────────────────────
def safe_screenshot(page: Page, path: Path, full_page: bool = False, locator=None) -> tuple[bool, Optional[str]]:
    """Take a screenshot safely, catching any errors."""
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        if locator:
            locator.screenshot(path=str(path), timeout=5000)
        else:
            page.screenshot(path=str(path), full_page=full_page, timeout=15000)
        return True, None
    except Exception as e:
        return False, str(e)


def is_element_visible(page: Page, selector: str, timeout: int = 3000) -> bool:
    """Check if an element is visible on the page."""
    try:
        el = page.locator(selector).first
        el.wait_for(state="visible", timeout=timeout)
        return el.is_visible()
    except Exception:
        return False


def count_elements(page: Page, selector: str) -> int:
    """Count elements matching a selector."""
    try:
        return page.locator(selector).count()
    except Exception:
        return 0


# ─── Page Interaction Helpers ────────────────────────────────────
def navigate_to_sentiment(page: Page) -> bool:
    """Navigate to the Sentiment page via nav link."""
    page.goto(BASE_URL, wait_until="load", timeout=15000)
    # Wait for nav to render
    page.wait_for_selector("nav", timeout=10000)

    # Try clicking the nav link by text (handles both Chinese labels)
    nav_link = page.locator("nav a:has-text('情绪'), nav a:has-text('Sentiment')").first
    if nav_link.count() == 0:
        # Fallback: click by href
        nav_link = page.locator("nav a[href='/sentiment']").first

    if nav_link.count() == 0:
        # Direct navigation fallback
        page.goto(f"{BASE_URL}{SENTIMENT_PATH}", wait_until="load", timeout=15000)
    else:
        nav_link.click()
        page.wait_for_url(f"{BASE_URL}{SENTIMENT_PATH}", timeout=10000)

    # Wait for content to load (either shimmer or actual data)
    page.wait_for_selector(".card, .shimmer", timeout=15000)
    # Extra wait for animations
    page.wait_for_timeout(1500)
    return True


def wait_for_data_loaded(page: Page, timeout: int = 20000) -> bool:
    """Wait until skeletons are replaced with real content or timeout."""
    try:
        # Wait for shimmer to disappear OR for actual content to appear
        page.wait_for_selector("svg", timeout=timeout)
        # Give animations time to finish
        page.wait_for_timeout(2000)
        return True
    except Exception:
        return False


def click_timeframe(page: Page, label: str) -> bool:
    """Click a timeframe button by its label text."""
    try:
        btn = page.locator("button", has_text=label).first
        btn.wait_for(state="visible", timeout=5000)
        btn.click()
        page.wait_for_timeout(2000)  # wait for data refresh
        return True
    except Exception as e:
        print(f"  [WARN] Failed to click timeframe '{label}': {e}")
        return False


# ─── Visual Assertion Functions ──────────────────────────────────
def assert_sentiment_gauge(page: Page, report: TestReport, viewport: str):
    visible = is_element_visible(page, "svg", timeout=3000)
    # There are multiple SVGs; check for gauge-specific text
    has_gauge_text = page.locator("text=市场情绪").first.is_visible() if page.locator("text=市场情绪").count() > 0 else False
    report.add_assertion(
        "Sentiment Gauge SVG present",
        visible and has_gauge_text,
        "Sentiment gauge SVG or '市场情绪' label not found" if not (visible and has_gauge_text) else "OK",
        viewport,
    )


def assert_fng_gauge(page: Page, report: TestReport, viewport: str):
    has_fng = page.locator("text=恐惧").first.is_visible() if page.locator("text=恐惧").count() > 0 else False
    report.add_assertion(
        "FNG Gauge present",
        has_fng,
        "FNG gauge ('恐惧&贪婪') label not found" if not has_fng else "OK",
        viewport,
    )


def assert_market_bias_badge(page: Page, report: TestReport, viewport: str):
    # Market bias badge: contains "市场偏向"
    has_bias = page.locator("text=市场偏向").first.is_visible() if page.locator("text=市场偏向").count() > 0 else False
    report.add_assertion(
        "Market Bias Badge visible",
        has_bias,
        "Market bias badge ('市场偏向') not found" if not has_bias else "OK",
        viewport,
    )


def assert_position_report_cards(page: Page, report: TestReport, viewport: str):
    # Cards should contain "日线", "4小时", "周线"
    has_1d = page.locator("text=日线").first.is_visible() if page.locator("text=日线").count() > 0 else False
    has_4h = page.locator("text=4小时").first.is_visible() if page.locator("text=4小时").count() > 0 else False
    has_1w = page.locator("text=周线").first.is_visible() if page.locator("text=周线").count() > 0 else False

    report.add_assertion(
        "Position Report Card: 日线",
        has_1d,
        "'日线' card not found" if not has_1d else "OK",
        viewport,
    )
    report.add_assertion(
        "Position Report Card: 4小时",
        has_4h,
        "'4小时' card not found" if not has_4h else "OK",
        viewport,
    )
    report.add_assertion(
        "Position Report Card: 周线",
        has_1w,
        "'周线' card not found" if not has_1w else "OK",
        viewport,
    )


def assert_signal_table(page: Page, report: TestReport, viewport: str):
    # Signal table heading
    has_heading = page.locator("text=形态信号检测").first.is_visible() if page.locator("text=形态信号检测").count() > 0 else False
    # Check if table has rows (either real data or "暂无" message)
    has_content = page.locator("table tbody tr").count() > 0 or page.locator("text=暂无信号数据").count() > 0
    report.add_assertion(
        "Signal Detection Table present",
        has_heading,
        "Signal table heading not found" if not has_heading else "OK",
        viewport,
    )
    report.add_assertion(
        "Signal Detection Table has rows or empty state",
        has_content,
        "Signal table has no rows and no empty state" if not has_content else "OK",
        viewport,
    )


def assert_risk_warning_banner(page: Page, report: TestReport, viewport: str):
    # Banner is conditional; just note whether it's present
    has_banner = page.locator("text=风险提示").first.is_visible() if page.locator("text=风险提示").count() > 0 else False
    report.add_assertion(
        "Risk Warning Banner visible (conditional)",
        True,  # Always pass — presence depends on data
        f"Banner {'present' if has_banner else 'not present'} (data-dependent)" if True else "",
        viewport,
    )


def assert_timeframe_buttons_clickable(page: Page, report: TestReport, viewport: str):
    for label in ["1小时", "4小时", "1天"]:
        try:
            btn = page.locator("button", has_text=label).first
            btn.wait_for(state="visible", timeout=3000)
            clickable = btn.is_enabled() and btn.is_visible()
            report.add_assertion(
                f"Timeframe button '{label}' clickable",
                clickable,
                f"Button '{label}' not clickable" if not clickable else "OK",
                viewport,
            )
        except Exception as e:
            report.add_assertion(
                f"Timeframe button '{label}' clickable",
                False,
                str(e),
                viewport,
            )


# ─── Screenshot Capture Functions ────────────────────────────────
def capture_full_page(page: Page, report: TestReport, viewport: str):
    path = OUTPUT_DIR / f"sentiment_full_{viewport}.png"
    ok, err = safe_screenshot(page, path, full_page=True)
    report.add_screenshot("Full Page", path, viewport, ok, err)


def capture_hero_dashboard(page: Page, report: TestReport, viewport: str):
    # Hero dashboard is the first .card that contains gauges
    path = OUTPUT_DIR / f"hero_dashboard_{viewport}.png"
    try:
        # Try to capture the first card which contains the gauges
        locator = page.locator(".card").first
        if locator.count() > 0:
            ok, err = safe_screenshot(page, path, locator=locator)
        else:
            ok, err = False, "No .card element found for hero dashboard"
        report.add_screenshot("Hero Dashboard", path, viewport, ok, err)
    except Exception as e:
        report.add_screenshot("Hero Dashboard", path, viewport, False, str(e))


def capture_risk_warning(page: Page, report: TestReport, viewport: str):
    path = OUTPUT_DIR / f"risk_warning_{viewport}.png"
    try:
        # Check if the banner text exists first
        risk_count = page.locator("text=风险提示").count()
        if risk_count > 0:
            locator = page.locator("text=风险提示").first.locator("xpath=ancestor::*[contains(@class, 'rounded-xl') or contains(@class, 'border-red')]").first
            if locator.count() > 0:
                ok, err = safe_screenshot(page, path, locator=locator)
            else:
                # Fallback to nearest div parent
                locator = page.locator("text=风险提示").first.locator("xpath=..")
                ok, err = safe_screenshot(page, path, locator=locator)
        else:
            ok, err = False, "Risk warning banner not present (data-dependent)"
        report.add_screenshot("Risk Warning Banner", path, viewport, ok, err)
    except Exception as e:
        report.add_screenshot("Risk Warning Banner", path, viewport, False, str(e))


def capture_position_report_cards(page: Page, report: TestReport, viewport: str):
    path = OUTPUT_DIR / f"position_reports_{viewport}.png"
    try:
        # The section containing "持仓建议报告" and the 3 cards
        heading = page.locator("text=持仓建议报告").first
        if heading.count() > 0:
            section = heading.locator("xpath=ancestor::div[contains(@class, 'space-y-4') or contains(@class, 'grid')]")
            if section.count() == 0:
                section = heading.locator("xpath=../..")
        else:
            section = page.locator(".grid.grid-cols-1.md\\:grid-cols-3").first

        if section.count() > 0:
            ok, err = safe_screenshot(page, path, locator=section.first)
        else:
            ok, err = False, "Position report cards section not found"
        report.add_screenshot("Position Report Cards", path, viewport, ok, err)
    except Exception as e:
        report.add_screenshot("Position Report Cards", path, viewport, False, str(e))


def capture_signal_table(page: Page, report: TestReport, viewport: str):
    path = OUTPUT_DIR / f"signal_table_{viewport}.png"
    try:
        # The card containing "形态信号检测"
        heading = page.locator("text=形态信号检测").first
        if heading.count() > 0:
            card = heading.locator("xpath=ancestor::div[contains(@class, 'card')]")
            if card.count() == 0:
                card = heading.locator("xpath=../..")
        else:
            card = page.locator(".card:has-text('形态信号检测')").first

        if card.count() > 0:
            ok, err = safe_screenshot(page, path, locator=card.first)
        else:
            ok, err = False, "Signal table card not found"
        report.add_screenshot("Signal Detection Table", path, viewport, ok, err)
    except Exception as e:
        report.add_screenshot("Signal Detection Table", path, viewport, False, str(e))


def capture_token_analysis(page: Page, report: TestReport, viewport: str):
    path = OUTPUT_DIR / f"token_analysis_{viewport}.png"
    try:
        # The card containing "完整币种分析"
        heading = page.locator("text=完整币种分析").first
        if heading.count() > 0:
            card = heading.locator("xpath=ancestor::div[contains(@class, 'card')]")
            if card.count() == 0:
                card = heading.locator("xpath=../..")
        else:
            card = page.locator(".card:has-text('完整币种分析')").first

        if card.count() > 0:
            ok, err = safe_screenshot(page, path, locator=card.first)
        else:
            ok, err = False, "Token analysis card not found"
        report.add_screenshot("Token Analysis Section", path, viewport, ok, err)
    except Exception as e:
        report.add_screenshot("Token Analysis Section", path, viewport, False, str(e))


# ─── Interaction Tests ───────────────────────────────────────────
def test_timeframe_interactions(page: Page, report: TestReport, viewport: str):
    """Click each timeframe button and verify page doesn't crash."""
    for label in ["1小时", "4小时", "1天"]:
        try:
            success = click_timeframe(page, label)
            # After click, verify that page still has content (not blank/errored)
            body_text = page.locator("body").inner_text(timeout=5000)
            crashed = len(body_text.strip()) < 50 or "error" in body_text.lower()
            report.interactions.append({
                "action": f"Click timeframe '{label}'",
                "success": success and not crashed,
                "error": "Page appears crashed or empty after click" if crashed else None,
                "viewport": viewport,
            })
            # Give animations time
            page.wait_for_timeout(1500)
        except Exception as e:
            report.interactions.append({
                "action": f"Click timeframe '{label}'",
                "success": False,
                "error": str(e),
                "viewport": viewport,
            })


# ─── Main Test Runner ────────────────────────────────────────────
def run_tests_for_viewport(browser: Browser, viewport_name: str, size: dict) -> TestReport:
    report = TestReport()
    context: BrowserContext = browser.new_context(
        viewport={"width": size["width"], "height": size["height"]},
        device_scale_factor=1,
    )
    page: Page = context.new_page()

    try:
        print(f"\n🔧 Testing viewport: {viewport_name} ({size['width']}x{size['height']})")
        print("-" * 50)

        # 1. Navigate
        print("  → Navigating to Sentiment page...")
        navigate_to_sentiment(page)
        print("  ✓ Page loaded")

        # 2. Wait for data
        print("  → Waiting for data to load...")
        data_loaded = wait_for_data_loaded(page)
        print(f"  {'✓' if data_loaded else '⚠'} Data load state: {'loaded' if data_loaded else 'timeout/skeleton'}")

        # 3. Screenshots
        print("  → Capturing screenshots...")
        capture_full_page(page, report, viewport_name)
        capture_hero_dashboard(page, report, viewport_name)
        capture_risk_warning(page, report, viewport_name)
        capture_position_report_cards(page, report, viewport_name)
        capture_signal_table(page, report, viewport_name)
        capture_token_analysis(page, report, viewport_name)
        print(f"  ✓ Captured {len([s for s in report.screenshots if s.viewport == viewport_name and s.success])} screenshots")

        # 4. Visual assertions
        print("  → Running visual assertions...")
        assert_sentiment_gauge(page, report, viewport_name)
        assert_fng_gauge(page, report, viewport_name)
        assert_market_bias_badge(page, report, viewport_name)
        assert_position_report_cards(page, report, viewport_name)
        assert_signal_table(page, report, viewport_name)
        assert_risk_warning_banner(page, report, viewport_name)
        assert_timeframe_buttons_clickable(page, report, viewport_name)
        print(f"  ✓ Assertions complete")

        # 5. Interaction tests (only on desktop to save time, or both)
        print("  → Testing interactions...")
        test_timeframe_interactions(page, report, viewport_name)
        print(f"  ✓ Interactions complete")

    except Exception as e:
        report.add_error(f"Viewport {viewport_name}: {str(e)}")
        # Try to capture a failure screenshot
        try:
            fail_path = OUTPUT_DIR / f"error_{viewport_name}.png"
            page.screenshot(path=str(fail_path), full_page=True)
            report.add_screenshot("Error Screenshot", fail_path, viewport_name, True)
        except Exception:
            pass
    finally:
        context.close()

    return report


def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    overall_report = TestReport()

    with sync_playwright() as p:
        print("=" * 70)
        print("  Mantle DeFAI Trader — Sentiment Page Visual Regression Test")
        print("=" * 70)

        browser: Browser = p.chromium.launch(headless=HEADLESS)

        for viewport_name, size in VIEWPORTS.items():
            report = run_tests_for_viewport(browser, viewport_name, size)
            overall_report.screenshots.extend(report.screenshots)
            overall_report.assertions.extend(report.assertions)
            overall_report.interactions.extend(report.interactions)
            overall_report.errors.extend(report.errors)

        browser.close()

    # Print consolidated report
    overall_report.print_report()

    # Exit code
    failed_assertions = [a for a in overall_report.assertions if not a.passed]
    failed_interactions = [i for i in overall_report.interactions if not i.get("success")]
    if failed_assertions or failed_interactions or overall_report.errors:
        print("Exiting with code 1 (failures detected)\n")
        sys.exit(1)
    else:
        print("Exiting with code 0 (all tests passed)\n")
        sys.exit(0)


if __name__ == "__main__":
    main()
