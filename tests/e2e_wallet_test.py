#!/usr/bin/env python3
"""
E2E Wallet Connection Test with Mock MetaMask Provider
Uses Playwright to inject a mock window.ethereum and test wallet connection flow.
"""
import asyncio
from playwright.async_api import async_playwright

# Mock Ethereum provider that simulates MetaMask
MOCK_PROVIDER_JS = """
(() => {
  const mockAddress = '0x71C7656EC7ab88b098defB751B7401B5f6d8976F';
  const mockChainId = '0x1388'; // Mantle Mainnet

  const mockProvider = {
    isMetaMask: true,
    _events: {},
    on(event, handler) {
      if (!this._events[event]) this._events[event] = [];
      this._events[event].push(handler);
    },
    removeListener(event, handler) {
      if (this._events[event]) {
        this._events[event] = this._events[event].filter(h => h !== handler);
      }
    },
    async request({ method, params }) {
      console.log('[MockProvider]', method, params);
      switch (method) {
        case 'eth_requestAccounts':
        case 'eth_accounts':
          return [mockAddress];
        case 'eth_chainId':
          return mockChainId;
        case 'wallet_switchEthereumChain':
          return null;
        case 'wallet_addEthereumChain':
          return null;
        case 'eth_getBalance':
          return '0x' + (10n**18n * 100n).toString(16); // 100 MNT
        default:
          return null;
      }
    },
    // Simulate account change
    _emit(event, data) {
      if (this._events[event]) {
        this._events[event].forEach(h => h(data));
      }
    }
  };

  window.ethereum = mockProvider;
  console.log('[MockProvider] Injected mock MetaMask provider');
})();
"""

async def test_wallet_connection():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(viewport={"width": 1440, "height": 900})
        page = await context.new_page()

        # Inject mock provider before navigation
        await page.add_init_script(MOCK_PROVIDER_JS)

        print("[Test] Navigating to app...")
        await page.goto("http://YOUR_SERVER_IP:5173/")
        await page.wait_for_load_state("networkidle")
        await asyncio.sleep(2)

        # Screenshot 1: Initial state (disconnected)
        await page.screenshot(path="/tmp/wallet_test_1_initial.png", full_page=False)
        print("[Test] Screenshot saved: /tmp/wallet_test_1_initial.png")

        # Find and click connect wallet button in header
        # The button text might be "连接钱包" or wallet icon
        connect_btn = page.locator("button").filter(has_text="连接")
        if await connect_btn.count() == 0:
            # Try other selectors
            connect_btn = page.locator("button").filter(has_text="钱包")
        if await connect_btn.count() == 0:
            # Try wallet icon in header
            connect_btn = page.locator("header button, nav button").first

        if await connect_btn.count() > 0:
            print(f"[Test] Found connect button, clicking...")
            await connect_btn.first.click()
            await asyncio.sleep(3)

            # Screenshot 2: After connection attempt
            await page.screenshot(path="/tmp/wallet_test_2_connected.png", full_page=False)
            print("[Test] Screenshot saved: /tmp/wallet_test_2_connected.png")

            # Check if wallet address is displayed
            address_text = await page.locator("text=/0x71C7.../").count()
            short_addr = await page.locator("text=/71C7.../").count()
            print(f"[Test] Address indicators found: {address_text + short_addr}")
        else:
            print("[Test] WARN: Could not find connect wallet button")

        # Navigate to routing page
        print("[Test] Navigating to Smart Routing...")
        await page.goto("http://YOUR_SERVER_IP:5173/routing")
        await page.wait_for_load_state("networkidle")
        await asyncio.sleep(2)

        # Screenshot 3: Routing page initial
        await page.screenshot(path="/tmp/wallet_test_3_routing.png", full_page=False)
        print("[Test] Screenshot saved: /tmp/wallet_test_3_routing.png")

        # Test routing wizard flow
        print("[Test] Testing routing wizard flow...")

        # Step 1: Select source chain (Mantle)
        mantle_card = page.locator("text=Mantle").first
        if await mantle_card.count() > 0:
            await mantle_card.click()
            await asyncio.sleep(1)
            # Find target chain card and click
            target_cards = page.locator("[class*='card'], [class*='step']").filter(has_text="Mantle")
            if await target_cards.count() > 1:
                await target_cards.nth(1).click()
            await asyncio.sleep(1)

        # Proceed through wizard
        next_btn = page.locator("button").filter(has_text="下一步")
        for step in range(3):
            if await next_btn.count() > 0 and await next_btn.first.is_enabled():
                await next_btn.first.click()
                await asyncio.sleep(2)
            else:
                break

        # Screenshot 4: Routing wizard progress
        await page.screenshot(path="/tmp/wallet_test_4_wizard.png", full_page=False)
        print("[Test] Screenshot saved: /tmp/wallet_test_4_wizard.png")

        await browser.close()
        print("[Test] Wallet connection test completed!")

if __name__ == "__main__":
    asyncio.run(test_wallet_connection())
