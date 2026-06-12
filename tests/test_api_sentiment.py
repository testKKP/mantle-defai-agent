#!/usr/bin/env python3
"""
Mantle DeFAI Trader Backend API - Comprehensive Test Suite
Focus: Sentiment Analysis Endpoints
"""

import requests
import sys
import json
import re
from datetime import datetime

BASE_URL = "http://127.0.0.1:8000"
TIMEOUT = 30

# Results tracking
results = {
    "total": 0,
    "passed": 0,
    "failed": 0,
    "errors": [],
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


def request_json(method: str, path: str, **kwargs):
    """Make HTTP request and return (response, json_data, error)"""
    url = f"{BASE_URL}{path}"
    kwargs.setdefault("timeout", TIMEOUT)
    try:
        resp = requests.request(method, url, **kwargs)
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
# TEST SUITE
# =============================================================================

def test_health_check():
    print("\n=== 1. Health Check ===")
    name = "GET /health - status and services"
    resp, data, err = request_json("GET", "/health")
    if err:
        log_test(name, False, err)
        return

    checks = []
    checks.append(("status is 'healthy'", data.get("status") == "healthy"))
    checks.append(("has timestamp", "timestamp" in data))
    checks.append(("has services", "services" in data and isinstance(data["services"], dict)))

    services = data.get("services", {})
    expected_services = ["binance", "mantle", "on_chain_collector", "database"]
    for svc in expected_services:
        checks.append((f"service '{svc}' is ok", svc in services and services[svc] in ("ok", "connected", "active")))

    all_pass = all(c[1] for c in checks)
    details = "; ".join(f"{c[0]}: {'OK' if c[1] else 'FAIL'}" for c in checks if not c[1])
    log_test(name, all_pass, details)


def test_sentiment_latest():
    print("\n=== 2. Sentiment Analysis - GET /api/sentiment/latest ===")
    resp, data, err = request_json("GET", "/api/sentiment/latest")
    if err:
        log_test("GET /api/sentiment/latest - basic reachability", False, err)
        return

    # 2.1 Basic success
    log_test("success is true", data.get("success") is True)

    d = data.get("data", {})

    # 2.2 sentiment_index
    si = d.get("sentiment_index")
    log_test("sentiment_index is number 0-100",
             isinstance(si, (int, float)) and 0 <= si <= 100,
             f"got {si}")

    # 2.3 market_bias
    mb = d.get("market_bias")
    log_test("market_bias in [bullish, bearish, neutral]",
             mb in ("bullish", "bearish", "neutral"),
             f"got {mb}")

    # 2.4 bias_strength
    bs = d.get("bias_strength")
    log_test("bias_strength in [strong, moderate, weak]",
             bs in ("strong", "moderate", "weak"),
             f"got {bs}")

    # 2.5 fng
    fng = d.get("fng")
    fng_ok = isinstance(fng, dict)
    fng_details = ""
    if fng_ok:
        fv = fng.get("value")
        fng_ok &= isinstance(fv, (int, float)) and 0 <= fv <= 100
        fng_ok &= isinstance(fng.get("classification"), str) and len(fng.get("classification", "")) > 0
        fng_ok &= isinstance(fng.get("timestamp"), str) and len(fng.get("timestamp", "")) > 0
        if not fng_ok:
            fng_details = f"value={fv}, classification={fng.get('classification')}, timestamp={fng.get('timestamp')}"
    else:
        fng_details = f"type={type(fng)}"
    log_test("fng object with value/classification/timestamp", fng_ok, fng_details)

    # 2.6 market_breadth
    mbr = d.get("market_breadth")
    mbr_ok = isinstance(mbr, str) and bool(re.match(r"^\d+ up / \d+ down / \d+ flat$", mbr))
    log_test("market_breadth matches pattern 'X up / Y down / Z flat'", mbr_ok, f"got {mbr}")

    # 2.7 btc_change_24h
    btc = d.get("btc_change_24h")
    log_test("btc_change_24h is a number", isinstance(btc, (int, float)), f"got {btc}")

    # 2.8 risk_warning
    rw = d.get("risk_warning")
    log_test("risk_warning is non-empty string", isinstance(rw, str) and len(rw) > 0, f"got {rw}")

    # 2.9 signals
    signals = d.get("signals", [])
    sig_ok = isinstance(signals, list)
    sig_details = ""
    if sig_ok:
        required_keys = {"symbol", "timeframe", "direction", "primary_pattern", "confidence", "ma_alignment"}
        for i, sig in enumerate(signals):
            if not isinstance(sig, dict):
                sig_ok = False
                sig_details = f"signal[{i}] is not dict"
                break
            missing = required_keys - set(sig.keys())
            if missing:
                sig_ok = False
                sig_details = f"signal[{i}] missing keys: {missing}"
                break
            if sig.get("direction") not in ("long", "short"):
                sig_ok = False
                sig_details = f"signal[{i}] invalid direction: {sig.get('direction')}"
                break
    else:
        sig_details = f"type={type(signals)}"
    log_test("signals is list with required fields", sig_ok, sig_details)

    # 2.10 position_report
    pr = d.get("position_report")
    pr_ok = isinstance(pr, dict)
    pr_details = ""
    if pr_ok:
        for tf in ("1d", "4h", "1w"):
            if tf not in pr:
                pr_ok = False
                pr_details = f"missing timeframe {tf}"
                break
            report = pr[tf]
            if not isinstance(report, dict):
                pr_ok = False
                pr_details = f"{tf} is not dict"
                break
            for key in ("long", "short", "watch"):
                if key not in report:
                    pr_ok = False
                    pr_details = f"{tf} missing key {key}"
                    break
            if not pr_ok:
                break
            # Validate position items
            pos_keys = {"symbol", "reason", "confidence", "confidence_label"}
            for side in ("long", "short"):
                items = report.get(side, [])
                if not isinstance(items, list):
                    pr_ok = False
                    pr_details = f"{tf}.{side} is not list"
                    break
                for j, item in enumerate(items):
                    if not isinstance(item, dict):
                        pr_ok = False
                        pr_details = f"{tf}.{side}[{j}] not dict"
                        break
                    missing = pos_keys - set(item.keys())
                    if missing:
                        pr_ok = False
                        pr_details = f"{tf}.{side}[{j}] missing {missing}"
                        break
                if not pr_ok:
                    break
            if not pr_ok:
                break
            watch = report.get("watch")
            if not isinstance(watch, str):
                pr_ok = False
                pr_details = f"{tf}.watch is not str"
                break
    else:
        pr_details = f"type={type(pr)}"
    log_test("position_report with 1d/4h/1w structure", pr_ok, pr_details)


def test_sentiment_analyze():
    print("\n=== 3. Sentiment Analysis - POST /api/sentiment/analyze ===")

    def validate_sentiment_response(data, label):
        if not data.get("success"):
            return False, "success is not true"
        d = data.get("data", {})
        required_top = ["sentiment_index", "bullish_count", "bearish_count", "neutral_count",
                        "total_analyzed", "top_bullish", "top_bearish", "market_bias",
                        "bias_strength", "fng", "market_breadth", "btc_change_24h",
                        "risk_warning", "signals", "position_report"]
        missing = [k for k in required_top if k not in d]
        if missing:
            return False, f"missing top-level keys: {missing}"
        return True, ""

    # 3.1 Default params
    resp, data, err = request_json("POST", "/api/sentiment/analyze", json={})
    if err:
        log_test("POST default params", False, err)
    else:
        ok, detail = validate_sentiment_response(data, "default")
        log_test("POST default params", ok, detail)

    # 3.2 timeframe=1d
    resp, data, err = request_json("POST", "/api/sentiment/analyze", json={"timeframe": "1d"})
    if err:
        log_test("POST timeframe=1d", False, err)
    else:
        ok, detail = validate_sentiment_response(data, "1d")
        log_test("POST timeframe=1d", ok, detail)

    # 3.3 timeframe=4h
    resp, data, err = request_json("POST", "/api/sentiment/analyze", json={"timeframe": "4h"})
    if err:
        log_test("POST timeframe=4h", False, err)
    else:
        ok, detail = validate_sentiment_response(data, "4h")
        log_test("POST timeframe=4h", ok, detail)

    # 3.4 limit=30
    resp, data, err = request_json("POST", "/api/sentiment/analyze", json={"limit": 30})
    if err:
        log_test("POST limit=30", False, err)
    else:
        ok, detail = validate_sentiment_response(data, "limit=30")
        total = data.get("data", {}).get("total_analyzed")
        limit_ok = ok and total == 30
        log_test("POST limit=30", limit_ok, f"{detail}; total_analyzed={total}")


def test_other_critical_endpoints():
    print("\n=== 4. Other Critical Endpoints ===")

    # 4.1 GET /
    resp, data, err = request_json("GET", "/")
    if err:
        log_test("GET / (root)", False, err)
    else:
        ok = data.get("status") == "ok" and data.get("service") == "Mantle DeFAI Trader API"
        log_test("GET / (root)", ok, f"status={data.get('status')}, service={data.get('service')}")

    # 4.2 GET /api/mantle/trends
    resp, data, err = request_json("GET", "/api/mantle/trends")
    if err:
        log_test("GET /api/mantle/trends", False, err)
    else:
        d = data.get("data", {})
        ok = data.get("success") is True and isinstance(d.get("block_activity"), list) and isinstance(d.get("gas_trend"), list)
        log_test("GET /api/mantle/trends", ok)

    # 4.3 GET /api/mantle/tvl/history
    resp, data, err = request_json("GET", "/api/mantle/tvl/history")
    if err:
        log_test("GET /api/mantle/tvl/history", False, err)
    else:
        d = data.get("data", {})
        ok = data.get("success") is True and isinstance(d.get("history"), list) and d.get("chain") == "Mantle"
        log_test("GET /api/mantle/tvl/history", ok)

    # 4.4 GET /api/onchain/aggregated
    resp, data, err = request_json("GET", "/api/onchain/aggregated")
    if err:
        log_test("GET /api/onchain/aggregated", False, err)
    else:
        d = data.get("data", {})
        ok = data.get("success") is True and "tvl" in d and isinstance(d.get("top_protocols"), list)
        log_test("GET /api/onchain/aggregated", ok)


def test_error_handling():
    print("\n=== 5. Error Handling ===")

    # 5.1 Invalid timeframe -> 422
    resp, data, err = request_json("POST", "/api/sentiment/analyze", json={"timeframe": "invalid"})
    if err:
        log_test("Invalid timeframe returns 422", False, err)
    else:
        ok = resp.status_code == 422
        detail = f"status_code={resp.status_code}"
        if ok and isinstance(data, dict) and "detail" in data:
            detail += ", has validation detail"
        log_test("Invalid timeframe returns 422", ok, detail)

    # 5.2 CORS preflight with allowed origin
    allowed_origins = ["http://43.134.37.174:3000", "http://43.134.37.174:5173"]
    cors_ok = False
    cors_details = ""
    for origin in allowed_origins:
        try:
            resp = requests.options(
                f"{BASE_URL}/api/sentiment/latest",
                headers={
                    "Origin": origin,
                    "Access-Control-Request-Method": "GET",
                },
                timeout=TIMEOUT,
            )
            acao = resp.headers.get("access-control-allow-origin")
            acam = resp.headers.get("access-control-allow-methods", "")
            if resp.status_code == 200 and acao == origin and "GET" in acam:
                cors_ok = True
                cors_details = f"Origin {origin} allowed, methods: {acam}"
                break
            else:
                cors_details = f"Origin {origin}: status={resp.status_code}, acao={acao}, acam={acam}"
        except Exception as e:
            cors_details = f"Origin {origin}: error {e}"

    log_test("CORS preflight with allowed origin", cors_ok, cors_details)

    # 5.3 CORS disallowed origin
    try:
        resp = requests.options(
            f"{BASE_URL}/api/sentiment/latest",
            headers={
                "Origin": "http://evil.com",
                "Access-Control-Request-Method": "GET",
            },
            timeout=TIMEOUT,
        )
        disallowed_ok = resp.status_code in (400, 403) or "access-control-allow-origin" not in resp.headers
        log_test("CORS disallowed origin rejected", disallowed_ok, f"status={resp.status_code}")
    except Exception as e:
        log_test("CORS disallowed origin rejected", False, str(e))


# =============================================================================
# MAIN
# =============================================================================

def print_report():
    print("\n" + "=" * 60)
    print("TEST REPORT")
    print("=" * 60)
    print(f"Total tests run : {results['total']}")
    print(f"Passed          : {results['passed']}")
    print(f"Failed          : {results['failed']}")
    print(f"Success rate    : {results['passed'] / results['total'] * 100:.1f}%" if results["total"] > 0 else "N/A")

    if results["errors"]:
        print("\n--- FAILED TEST DETAILS ---")
        for e in results["errors"]:
            print(f"\n* {e['test']}")
            print(f"  -> {e['details']}")
    else:
        print("\nAll tests passed! ✓")

    print("\n--- SUMMARY ---")
    if results["failed"] == 0:
        print("All endpoints are working correctly.")
    else:
        print(f"{results['failed']} test(s) failed. Review the details above.")


def main():
    print("Mantle DeFAI Trader API - Comprehensive Sentiment Test Suite")
    print(f"Base URL: {BASE_URL}")
    print(f"Time: {datetime.now().isoformat()}")

    test_health_check()
    test_sentiment_latest()
    test_sentiment_analyze()
    test_other_critical_endpoints()
    test_error_handling()

    print_report()

    return 0 if results["failed"] == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
