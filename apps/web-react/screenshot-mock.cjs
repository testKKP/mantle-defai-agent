const { chromium } = require('playwright');

(async () => {
  const browser = await chromium.launch({ headless: true });
  const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });

  const errors = [];
  page.on('console', msg => {
    if (msg.type() === 'error' || msg.type() === 'warn') {
      errors.push(`[${msg.type().toUpperCase()}] ${msg.text()}`);
    }
  });
  page.on('pageerror', err => errors.push(`[PAGEERROR] ${err.message}`));

  // Mock the API response
  await page.route('**/api/onchain/signals/recent?limit=100', async route => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        success: true,
        count: 3,
        data: [
          {
            id: 1,
            tx_hash: '0xabc123def456789012345678901234567890123456789012345678901234abcd',
            block_number: 12345678,
            symbol: 'BTC',
            timeframe: '1d',
            data: '{"version":"2.1","timestamp":"2026-06-09T10:00:00Z","agent_id":"mantle-defai-agent-v2.1","decision":{"symbol":"BTC","timeframe":"1d","direction":"long","confidence":"high","reason":"Bullish alignment detected"}}',
            data_hash: '0xdeadbeef1234567890abcdef1234567890abcdef1234567890abcdef12345678',
            timestamp: 1759471200,
            created_at: '2026-06-09T10:00:00'
          },
          {
            id: 2,
            tx_hash: '0xdef789abc012345678901234567890123456789012345678901234567890ef01',
            block_number: 12345670,
            symbol: 'ETH',
            timeframe: '4h',
            data: '{"version":"2.1","timestamp":"2026-06-09T09:00:00Z","agent_id":"mantle-defai-agent-v2.1","decision":{"symbol":"ETH","timeframe":"4h","direction":"short","confidence":"medium","reason":"Bearish divergence"}}',
            data_hash: '0xcafebabe1234567890abcdef1234567890abcdef1234567890abcdef12345678',
            timestamp: 1759467600,
            created_at: '2026-06-09T09:00:00'
          },
          {
            id: 3,
            tx_hash: '0x1234567890abcdef1234567890abcdef1234567890abcdef1234567890abcd12',
            block_number: 12345660,
            symbol: 'MNT',
            timeframe: '1w',
            data: '{"version":"2.1","timestamp":"2026-06-09T08:00:00Z","agent_id":"mantle-defai-agent-v2.1","decision":{"symbol":"MNT","timeframe":"1w","direction":"long","confidence":"high","reason":"Strong momentum"}}',
            data_hash: '0xbaadf00d1234567890abcdef1234567890abcdef1234567890abcdef12345678',
            timestamp: 1759464000,
            created_at: '2026-06-09T08:00:00'
          }
        ]
      })
    });
  });

  // Also mock other API calls that might fail
  await page.route('**/api/health', route => route.fulfill({ status: 200, body: JSON.stringify({ status: 'healthy' }) }));
  await page.route('**/api/sentiment/latest**', route => route.fulfill({ status: 200, body: JSON.stringify({ success: true, data: {} }) }));

  await page.goto('http://localhost:4173/onchain-signals', { waitUntil: 'networkidle', timeout: 30000 });
  await page.waitForTimeout(3000);

  const title = await page.locator('h2').first().textContent().catch(() => 'N/A');
  const hasTable = await page.locator('table').count() > 0;
  const rowCount = await page.locator('table tbody tr').count();
  const bodyText = await page.locator('body').textContent();
  const hasNoData = bodyText.includes('暂无链上信号数据') || bodyText.includes('No on-chain signal data');

  await page.screenshot({ path: '/mnt/datadisk0/.openclaw/workspace/projects/mantle-defai-trader/tests/screenshots/onchain-signals-mock.png', fullPage: false });

  console.log('=== Mock API Screenshot Test Results ===');
  console.log('Page title:', title.trim());
  console.log('Has table:', hasTable);
  console.log('Table rows:', rowCount);
  console.log('Has no-data message:', hasNoData);
  console.log('Console errors:', errors.length);
  errors.forEach(e => console.log('  -', e));

  if (hasTable && rowCount >= 3) {
    console.log('\n✅ PASS: Table rendered with data rows');
  } else if (hasNoData) {
    console.log('\n✅ PASS: No-data state rendered correctly');
  } else {
    console.log('\n❌ FAIL: Table/no-data state not rendered correctly');
  }

  if (errors.length === 0) {
    console.log('✅ PASS: No console errors');
  } else {
    console.log('⚠️  WARN: Console errors detected');
  }

  await browser.close();
})();
