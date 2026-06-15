const { chromium } = require('playwright');

(async () => {
  const browser = await chromium.launch({ headless: true });
  const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });

  await page.route('**/api/onchain/signals/recent?limit=100', async route => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        success: true,
        count: 1,
        data: [{
          id: 1,
          tx_hash: '0xabc123def456789012345678901234567890123456789012345678901234abcd',
          block_number: 12345678,
          symbol: 'BTC',
          timeframe: '1d',
          data: '{"version":"2.1","timestamp":"2026-06-09T10:00:00Z","agent_id":"mantle-defai-agent-v2.1","decision":{"symbol":"BTC","timeframe":"1d","direction":"long","confidence":"high","reason":"Bullish alignment detected"}}',
          data_hash: '0xdeadbeef1234567890abcdef1234567890abcdef1234567890abcdef12345678',
          timestamp: 1759471200,
          created_at: '2026-06-09T10:00:00'
        }]
      })
    });
  });
  await page.route('**/api/health', route => route.fulfill({ status: 200, body: JSON.stringify({ status: 'healthy' }) }));

  await page.goto('http://localhost:4173/onchain-signals', { waitUntil: 'networkidle', timeout: 30000 });
  await page.waitForTimeout(2000);

  // Click expand button on first row
  await page.locator('table tbody tr').first().click();
  await page.waitForTimeout(1000);

  const hasJson = await page.locator('pre').count() > 0;
  const preText = hasJson ? await page.locator('pre').first().textContent() : '';

  await page.screenshot({ path: '/mnt/datadisk0/.openclaw/workspace/projects/mantle-defai-trader/tests/screenshots/onchain-signals-expanded.png', fullPage: true });

  console.log('=== Expand Test Results ===');
  console.log('Has JSON pre block:', hasJson);
  console.log('JSON content preview:', preText.substring(0, 200));
  console.log(hasJson ? '\n✅ PASS: Expanded JSON rendered correctly' : '\n❌ FAIL: No JSON block found');

  await browser.close();
})();
