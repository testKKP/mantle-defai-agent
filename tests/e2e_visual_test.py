#!/usr/bin/env python3
"""
Comprehensive Visual E2E Test for Smart Routing Wizard
Tests each step UI rendering and captures screenshots.
"""
import asyncio
from playwright.async_api import async_playwright

MOCK_PROVIDER_JS = """
(() => {
  const mockAddress = '0x71C7656EC7ab88b098defB751B7401B5f6d8976F';
  const mockChainId = '0x1388';
  window.ethereum = {
    isMetaMask: true,
    _events: {},
    on(event, handler) { if (!this._events[event]) this._events[event] = []; this._events[event].push(handler); },
    async request({ method }) {
      switch (method) {
        case 'eth_requestAccounts': case 'eth_accounts': return [mockAddress];
        case 'eth_chainId': return mockChainId;
        case 'wallet_switchEthereumChain': return null;
        case 'wallet_addEthereumChain': return null;
        default: return null;
      }
    }
  };
})();
"""

async def capture_step(page, step_name, screenshot_path):
    await asyncio.sleep(2)
    await page.screenshot(path=screenshot_path, full_page=False)
    print(f"[Visual] {step_name} -> {screenshot_path}")

async def test_visual_wizard():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(viewport={"width": 1440, "height": 900})
        page = await context.new_page()
        await page.add_init_script(MOCK_PROVIDER_JS)

        # Step 1: Chain Select
        print("[Visual] Loading routing page...")
        await page.goto("http://127.0.0.1:5173/routing", wait_until="commit", timeout=120000)
        await asyncio.sleep(3)
        await capture_step(page, "Step 1: Chain Select", "/tmp/visual_step1_chain.png")

        # Use API to create a session and advance through steps
        import aiohttp
        async with aiohttp.ClientSession() as session:
            async with session.post("http://127.0.0.1:8000/api/routing/wizard/start") as resp:
                data = await resp.json()
                sid = data["data"]["session_id"]
                print(f"[Visual] Session started: {sid}")

            async def advance(step, payload):
                async with session.post(
                    f"http://127.0.0.1:8000/api/routing/wizard/{sid}/step/{step}",
                    json=payload
                ) as resp:
                    r = await resp.json()
                    print(f"[Visual] Advanced to {step}: {r.get('data',{}).get('current_step')}")
                    return r

            # Step 1: chain_select
            await advance("chain_select", {"source_chain": "mantle", "target_chain": "mantle"})
            await page.evaluate(f"window.location.href = 'http://127.0.0.1:5173/routing?session={sid}'")
            await asyncio.sleep(3)
            await capture_step(page, "Step 1b: Chain Selected", "/tmp/visual_step1b_chain_selected.png")

            # Step 2: token_select
            await advance("token_select", {"token_in": "MNT", "token_out": "USDC", "token_in_symbol": "MNT", "token_out_symbol": "USDC"})
            await page.reload(wait_until="networkidle", timeout=60000)
            await asyncio.sleep(2)
            await capture_step(page, "Step 2: Token Select", "/tmp/visual_step2_token.png")

            # Step 3: amount_input
            await advance("amount_input", {"amount": "1.5"})
            await page.reload(wait_until="networkidle", timeout=60000)
            await asyncio.sleep(2)
            await capture_step(page, "Step 3: Amount Input", "/tmp/visual_step3_amount.png")

            # Step 4: smart_analysis
            await advance("smart_analysis", {})
            await page.reload(wait_until="networkidle", timeout=60000)
            await asyncio.sleep(2)
            await capture_step(page, "Step 4: Smart Analysis", "/tmp/visual_step4_analysis.png")
            # Wait for analysis background task
            await asyncio.sleep(8)
            await page.reload(wait_until="networkidle", timeout=60000)
            await asyncio.sleep(2)
            await capture_step(page, "Step 4b: Analysis Complete", "/tmp/visual_step4b_complete.png")

            # Step 5: route_display
            await page.reload(wait_until="networkidle", timeout=60000)
            await asyncio.sleep(2)
            await capture_step(page, "Step 5: Route Display", "/tmp/visual_step5_routes.png")

            # Step 6: route_select
            async with session.get(f"http://127.0.0.1:8000/api/routing/wizard/{sid}") as resp:
                sdata = await resp.json()
                analysis = sdata.get("data", {}).get("analysis_data") or {}
                routes = analysis.get("routes", [])
                if routes:
                    route_id = routes[0]["route_id"]
                    await session.post(
                        f"http://127.0.0.1:8000/api/routing/wizard/{sid}/select-route",
                        json={"route_id": route_id}
                    )
            await page.reload(wait_until="networkidle", timeout=60000)
            await asyncio.sleep(2)
            await capture_step(page, "Step 6: Route Selected", "/tmp/visual_step6_selected.png")

            # Step 7: wallet_check
            await advance("wallet_check", {})
            await page.reload(wait_until="networkidle", timeout=60000)
            await asyncio.sleep(2)
            await capture_step(page, "Step 7: Wallet Check", "/tmp/visual_step7_wallet.png")

            # Step 8: execute
            await page.reload(wait_until="networkidle", timeout=60000)
            await asyncio.sleep(2)
            await capture_step(page, "Step 8: Execute", "/tmp/visual_step8_execute.png")

        await browser.close()
        print("[Visual] All screenshots captured!")

if __name__ == "__main__":
    asyncio.run(test_visual_wizard())
