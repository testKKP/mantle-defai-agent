const { chromium } = require('playwright');

(async () => {
  const browser = await chromium.launch({ headless: true });
  const context = await browser.newContext({ viewport: { width: 1440, height: 900 } });
  const page = await context.newPage();

  const BASE_URL = 'http://43.134.37.174:5173';
  const results = [];

  // Helper to log and collect results
  function log(msg) {
    console.log(msg);
    results.push(msg);
  }

  // ========== DASHBOARD ==========
  log('=== Testing Dashboard ===');
  try {
    await page.goto(`${BASE_URL}/`, { waitUntil: 'networkidle', timeout: 30000 });
    await page.waitForTimeout(3000);

    const dashboardHtml = await page.content();
    const hasGas = dashboardHtml.includes('Gas') || dashboardHtml.includes('gas');
    const hasTVL = dashboardHtml.includes('TVL') || dashboardHtml.includes('tvl');
    const hasTx = dashboardHtml.includes('Tx') || dashboardHtml.includes('Transaction');
    const hasChart = dashboardHtml.includes('canvas') || dashboardHtml.includes('chart') || dashboardHtml.includes('recharts');

    log(`Dashboard - Gas mention: ${hasGas}`);
    log(`Dashboard - TVL mention: ${hasTVL}`);
    log(`Dashboard - Tx mention: ${hasTx}`);
    log(`Dashboard - Chart elements: ${hasChart}`);

    // Look for specific cards
    const cards = await page.locator('[class*="card"], [class*="Card"], [class*="stat"], [class*="Stat"]').count();
    log(`Dashboard - Card-like elements found: ${cards}`);

    // Check for numbers (data displayed)
    const bodyText = await page.locator('body').textContent();
    const hasNumbers = /\$[\d,]+\.?\d*/.test(bodyText) || /\d+\.?\d*\s*[BMK]/.test(bodyText);
    log(`Dashboard - Has numeric values: ${hasNumbers}`);

    await page.screenshot({ path: '/root/.openclaw/workspace/projects/mantle-defai-trader/tests/screenshot-dashboard.png', fullPage: true });
    log('Screenshot saved: screenshot-dashboard.png');
  } catch (e) {
    log(`Dashboard ERROR: ${e.message}`);
    await page.screenshot({ path: '/root/.openclaw/workspace/projects/mantle-defai-trader/tests/screenshot-dashboard.png' });
  }

  // ========== ONCHAIN PAGE ==========
  log('\n=== Testing Onchain Page ===');
  try {
    await page.goto(`${BASE_URL}/onchain`, { waitUntil: 'networkidle', timeout: 30000 });
    await page.waitForTimeout(3000);

    const onchainHtml = await page.content();
    const hasOverview = onchainHtml.includes('Overview') || onchainHtml.includes('overview');
    const hasProtocols = onchainHtml.includes('Protocol') || onchainHtml.includes('protocol');
    const hasMantle = onchainHtml.includes('Mantle') || onchainHtml.includes('mantle');

    log(`Onchain - Overview mention: ${hasOverview}`);
    log(`Onchain - Protocol mention: ${hasProtocols}`);
    log(`Onchain - Mantle mention: ${hasMantle}`);

    const bodyText = await page.locator('body').textContent();
    const hasNumbers = /\$[\d,]+\.?\d*/.test(bodyText) || /\d+\.?\d*\s*[BMK]/.test(bodyText);
    log(`Onchain - Has numeric values: ${hasNumbers}`);

    await page.screenshot({ path: '/root/.openclaw/workspace/projects/mantle-defai-trader/tests/screenshot-onchain.png', fullPage: true });
    log('Screenshot saved: screenshot-onchain.png');
  } catch (e) {
    log(`Onchain ERROR: ${e.message}`);
    await page.screenshot({ path: '/root/.openclaw/workspace/projects/mantle-defai-trader/tests/screenshot-onchain.png' });
  }

  // ========== PROTOCOLS PAGE ==========
  log('\n=== Testing Protocols Page ===');
  try {
    await page.goto(`${BASE_URL}/protocols`, { waitUntil: 'networkidle', timeout: 30000 });
    await page.waitForTimeout(3000);

    const protocolsHtml = await page.content();
    const hasProtocolList = protocolsHtml.includes('Protocol') || protocolsHtml.includes('protocol');
    const hasTVL = protocolsHtml.includes('TVL') || protocolsHtml.includes('tvl');

    log(`Protocols - Protocol mention: ${hasProtocolList}`);
    log(`Protocols - TVL mention: ${hasTVL}`);

    const bodyText = await page.locator('body').textContent();
    const hasNumbers = /\$[\d,]+\.?\d*/.test(bodyText) || /\d+\.?\d*\s*[BMK]/.test(bodyText);
    log(`Protocols - Has numeric values: ${hasNumbers}`);

    await page.screenshot({ path: '/root/.openclaw/workspace/projects/mantle-defai-trader/tests/screenshot-protocols.png', fullPage: true });
    log('Screenshot saved: screenshot-protocols.png');
  } catch (e) {
    log(`Protocols ERROR: ${e.message}`);
    await page.screenshot({ path: '/root/.openclaw/workspace/projects/mantle-defai-trader/tests/screenshot-protocols.png' });
  }

  await browser.close();

  log('\n=== SUMMARY ===');
  console.log('\nFull Results:');
  results.forEach(r => console.log(r));
})();
