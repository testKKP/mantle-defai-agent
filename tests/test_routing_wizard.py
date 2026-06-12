"""
Test suite for Smart Routing Wizard API
"""
import asyncio
import aiohttp

BASE_URL = "http://127.0.0.1:8000"

async def test_start_wizard():
    async with aiohttp.ClientSession() as s:
        r = await s.post(f"{BASE_URL}/api/routing/wizard/start")
        assert r.status == 200, f"Expected 200, got {r.status}"
        d = await r.json()
        assert d["success"] is True
        assert "session_id" in d["data"]
        assert d["data"]["current_step"] == "chain_select"
        print("✓ test_start_wizard passed")
        return d["data"]["session_id"]

async def test_get_chains():
    async with aiohttp.ClientSession() as s:
        r = await s.get(f"{BASE_URL}/api/routing/chains")
        assert r.status == 200
        d = await r.json()
        assert d["success"] is True
        assert len(d["data"]) >= 4
        chain_ids = [c["id"] for c in d["data"]]
        assert "mantle" in chain_ids
        assert "ethereum" in chain_ids
        print("✓ test_get_chains passed")

async def test_get_tokens():
    async with aiohttp.ClientSession() as s:
        r = await s.get(f"{BASE_URL}/api/routing/tokens/mantle")
        assert r.status == 200
        d = await r.json()
        assert d["success"] is True
        symbols = [t["symbol"] for t in d["data"]]
        assert "MNT" in symbols
        assert "USDC" in symbols
        print("✓ test_get_tokens passed")

async def test_full_wizard_flow():
    async with aiohttp.ClientSession() as s:
        # 1. Start
        r = await s.post(f"{BASE_URL}/api/routing/wizard/start")
        d = await r.json()
        sid = d["data"]["session_id"]
        
        # 2. Chain select
        r = await s.post(f"{BASE_URL}/api/routing/wizard/{sid}/step/chain_select",
            json={"source_chain": "mantle", "target_chain": "ethereum"})
        d = await r.json()
        assert d["data"]["current_step"] == "token_select"
        assert d["data"]["is_cross_chain"] is True
        
        # 3. Token select
        r = await s.post(f"{BASE_URL}/api/routing/wizard/{sid}/step/token_select",
            json={"token_in": "MNT", "token_out": "ETH", "token_in_symbol": "MNT", "token_out_symbol": "ETH"})
        d = await r.json()
        assert d["data"]["current_step"] == "amount_input"
        
        # 4. Amount input
        r = await s.post(f"{BASE_URL}/api/routing/wizard/{sid}/step/amount_input",
            json={"amount": "100", "amount_usd": 65.0})
        d = await r.json()
        assert d["data"]["current_step"] == "smart_analysis"
        
        # 5. Analyze
        r = await s.post(f"{BASE_URL}/api/routing/wizard/{sid}/analyze")
        d = await r.json()
        assert d["data"]["status"] == "analyzing"
        
        # 6. Poll until complete
        for _ in range(20):
            await asyncio.sleep(1)
            r = await s.get(f"{BASE_URL}/api/routing/wizard/{sid}/status")
            d = await r.json()
            if d["data"]["analysis_status"] in ("completed", "failed"):
                break
        
        assert d["data"]["analysis_status"] == "completed", f"Analysis failed: {d}"
        assert d["data"]["routes_count"] > 0
        
        # 7. Get session with routes
        r = await s.get(f"{BASE_URL}/api/routing/wizard/{sid}")
        d = await r.json()
        routes = d["data"]["analysis_data"]["routes"]
        assert len(routes) > 0
        
        # 8. Select route
        best = routes[0]
        r = await s.post(f"{BASE_URL}/api/routing/wizard/{sid}/select-route",
            json={"route_id": best["route_id"]})
        d = await r.json()
        assert d["data"]["current_step"] == "wallet_check"
        
        # 9. Wallet check
        r = await s.post(f"{BASE_URL}/api/routing/wizard/{sid}/wallet-check",
            json={"wallet_address": "0x1234567890123456789012345678901234567890"})
        d = await r.json()
        assert d["success"] is True
        assert "can_proceed" in d["data"]
        
        # 10. Execute
        r = await s.post(f"{BASE_URL}/api/routing/wizard/{sid}/execute",
            json={"simulate": True})
        d = await r.json()
        assert d["success"] is True
        assert d["data"]["status"] == "confirmed"
        assert d["data"]["tx_hash"] is not None
        
        print("✓ test_full_wizard_flow passed")

async def test_invalid_session():
    async with aiohttp.ClientSession() as s:
        r = await s.get(f"{BASE_URL}/api/routing/wizard/nonexistent")
        assert r.status == 404
        print("✓ test_invalid_session passed")

async def test_skip_step_error():
    async with aiohttp.ClientSession() as s:
        r = await s.post(f"{BASE_URL}/api/routing/wizard/start")
        d = await r.json()
        sid = d["data"]["session_id"]
        
        r = await s.post(f"{BASE_URL}/api/routing/wizard/{sid}/step/amount_input",
            json={"amount": "100"})
        assert r.status == 400
        print("✓ test_skip_step_error passed")

async def run_all():
    await test_start_wizard()
    await test_get_chains()
    await test_get_tokens()
    await test_invalid_session()
    await test_skip_step_error()
    await test_full_wizard_flow()
    print("\nAll tests passed!")

if __name__ == "__main__":
    asyncio.run(run_all())
