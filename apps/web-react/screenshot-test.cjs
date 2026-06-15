const { chromium } = require('playwright');

(async () => {
  const browser = await chromium.launch({ headless: true });
  const context = await browser.newContext({
    viewport: { width: 1440, height: 900 }
  });
  const page = await context.newPage();

  const errors = [];
  page.on('console', msg => {
    const type = msg.type();
    if (type === 'error' || type === 'warn') {
      errors.push(`[${type.toUpperCase()}] ${msg.text()}`);
    }
  });
  page.on('pageerror', err => {
    errors.push(`[PAGEERROR] ${err.message}`);
  });

  try {
    await page.goto('http://localhost:4173/onchain-signals', {
      waitUntil: 'networkidle',
      timeout: 30000
    });

    // Wait for the page to render
    await page.waitForTimeout(3000);

    // Check for key elements
    const title = await page.locator('h2').first().textContent().catch(() => 'N/A');
    const hasTable = await page.locator('table').count() > 0;
    const hasNoData = await page.locator('text=/暂无链上信号数据|No on-chain signal data/i').count() > 0;

    // Screenshot
    await page.screenshot({
      path: '/mnt/datadisk0/.openclaw/workspace/projects/mantle-defai-trader/tests/screenshots/onchain-signals-test.png',
      fullPage: false
    });

    console.log('=== Screenshot Test Results ===');
    console.log('Page title text:', title.trim());
    console.log('Has table:', hasTable);
    console.log('Has no-data message:', hasNoData);
    console.log('Console errors/warnings:', errors.length);
    errors.forEach(e => console.log('  -', e));

    if (errors.length === 0) {
      console.log('\n✅ PASS: No console errors');
    } else {
      console.log('\n⚠️  WARN: Console errors/warnings detected');
    }

    if (hasTable || hasNoData) {
      console.log('✅ PASS: Table or no-data state rendered correctly');
    } else {
      console.log('❌ FAIL: Neither table nor no-data message found');
      process.exitCode = 1;
    }
  } catch (e) {
    console.error('Screenshot test failed:', e.message);
    process.exitCode = 1;
  } finally {
    await browser.close();
  }
})();
