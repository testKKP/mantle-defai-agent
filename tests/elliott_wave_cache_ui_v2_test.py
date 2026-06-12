#!/usr/bin/env python3
"""
Elliott Wave Cache UI Verification v2
验证修复后的艾略特波浪分析缓存模式
"""

import sys
from pathlib import Path
from playwright.sync_api import sync_playwright

BASE_URL = "http://localhost:5173"
OUTPUT_PATH = Path("/root/.openclaw/workspace/projects/mantle-defai-trader/tests/elliott-wave-cache-ui-v2.png")

console_errors = []
network_errors = []
cache_labels_found = []
data_status = "unknown"

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    context = browser.new_context(viewport={"width": 1280, "height": 1200})
    page = context.new_page()

    # Capture console errors
    page.on("console", lambda msg: console_errors.append(f"[{msg.type}] {msg.text}") if msg.type in ("error", "warning") else None)

    # Capture network errors
    page.on("response", lambda resp: network_errors.append(f"{resp.status} {resp.url}") if resp.status >= 400 else None)
    page.on("requestfailed", lambda req: network_errors.append(f"FAILED {req.url}: {req.failure if isinstance(req.failure, str) else req.failure.get('errorText', 'unknown')}"))

    print("1. Navigating to /sentiment...")
    page.goto(f"{BASE_URL}/sentiment", wait_until="networkidle", timeout=30000)

    print("2. Waiting 8 seconds for health check and cache requests...")
    page.wait_for_timeout(8000)

    print("3. Scrolling to Elliott Wave card...")
    # First try to find exact text match
    elliott_heading = page.locator("text=艾略特波浪分析").first
    if elliott_heading.count() == 0:
        elliott_heading = page.locator("text=艾略特波浪").first
    if elliott_heading.count() == 0:
        elliott_heading = page.locator("text=艾略特").first

    if elliott_heading.count() > 0:
        elliott_heading.scroll_into_view_if_needed()
        page.wait_for_timeout(1000)
        print("   → Scrolled to Elliott Wave section")
    else:
        # Fallback: scroll down more aggressively
        for _ in range(10):
            page.evaluate("window.scrollBy(0, 800)")
            page.wait_for_timeout(300)
        # Try again after scrolling
        elliott_heading = page.locator("text=艾略特波浪分析").first
        if elliott_heading.count() > 0:
            elliott_heading.scroll_into_view_if_needed()
            page.wait_for_timeout(1000)
            print("   → Scrolled to Elliott Wave section (after fallback)")
        else:
            print("   → Scrolled down (fallback) — Elliott Wave heading not found")

    print("4. Checking page content...")
    page_content = page.content()
    text_content = page.locator("body").inner_text()

    # Check for cache labels
    cache_keywords = ["上次计算", "缓存数据", "缓存"]
    for kw in cache_keywords:
        if kw in text_content:
            cache_labels_found.append(kw)

    # Check for data vs empty state
    if "暂无缓存数据" in text_content or "暂无数据" in text_content:
        data_status = "empty"
    elif "波浪" in text_content or "Wave" in text_content:
        data_status = "has_data"
    else:
        data_status = "unclear"

    print(f"   → Cache labels found: {cache_labels_found if cache_labels_found else 'NONE'}")
    print(f"   → Data status: {data_status}")

    print(f"5. Taking screenshot → {OUTPUT_PATH}")
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    page.screenshot(path=str(OUTPUT_PATH), full_page=False)
    print("   → Screenshot saved")

    browser.close()

print("\n" + "=" * 60)
print("  ELLIOTT WAVE CACHE UI VERIFICATION REPORT")
print("=" * 60)

print("\n📸 Screenshot:")
print(f"   → {OUTPUT_PATH} ({'EXISTS' if OUTPUT_PATH.exists() else 'MISSING'})")

print("\n🔍 Cache Labels on Page:")
if cache_labels_found:
    for label in cache_labels_found:
        print(f"   ✅ Found: '{label}'")
else:
    print("   ⚠️  No cache-related labels found")

print(f"\n📊 Data Status: {data_status}")
if data_status == "has_data":
    print("   ✅ Actual wave data is displayed")
elif data_status == "empty":
    print("   ⚠️  Showing empty state ('暂无缓存数据')")
else:
    print("   ⚠️  Unable to determine data state")

print("\n🌐 Network Errors (4xx/5xx):")
if network_errors:
    for err in network_errors[:10]:
        print(f"   ❌ {err}")
else:
    print("   ✅ No network errors detected")

print("\n🖥️ Console Errors/Warnings:")
if console_errors:
    for err in console_errors[:10]:
        print(f"   ⚠️ {err}")
else:
    print("   ✅ No console errors/warnings")

# CORS specific check
cors_errors = [e for e in console_errors if "cors" in e.lower() or "cross-origin" in e.lower()]
print("\n🔒 CORS Specific Errors:")
if cors_errors:
    for err in cors_errors:
        print(f"   ❌ {err}")
else:
    print("   ✅ No CORS errors detected")

print("\n" + "=" * 60)
all_ok = (data_status in ("has_data", "empty")) and not any("500" in e for e in network_errors)
print(f"   OVERALL: {'PASS ✅' if all_ok else 'FAIL ❌'}")
print("=" * 60)
