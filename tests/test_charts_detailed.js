const { chromium } = require('playwright');

(async () => {
  const browser = await chromium.launch({ headless: true });
  const context = await browser.newContext({ viewport: { width: 1440, height: 900 } });
  const page = await context.newPage();
  const BASE_URL = 'http://YOUR_SERVER_IP:5173';

  // Test Dashboard Charts
  console.log('=== Dashboard Detailed Check ===');
  await page.goto(`${BASE_URL}/`, { waitUntil: 'networkidle', timeout: 30000 });
  await page.waitForTimeout(3000);

  // Check for chart canvases or SVGs
  const canvases = await page.locator('canvas').count();
  const svgs = await page.locator('svg').count();
  console.log(`Dashboard - Canvas elements: ${canvases}`);
  console.log(`Dashboard - SVG elements: ${svgs}`);

  // Check onchain overview section specifically
  const onchainSection = await page.locator('text=/链上数据概览|Onchain|TVL/').first();
  const onchainVisible = await onchainSection.isVisible().catch(() => false);
  console.log(`Dashboard - Onchain section visible: ${onchainVisible}`);

  // Check specific data values
  const bodyText = await page.locator('body').textContent();
  const hasTvlValue = /\$564/.test(bodyText) || /\$563/.test(bodyText);
  const hasGasValue = /50\.0001/.test(bodyText) || /50\./.test(bodyText);
  console.log(`Dashboard - Has TVL value ~$564M: ${hasTvlValue}`);
  console.log(`Dashboard - Has Gas value: ${hasGasValue}`);

  // Test Onchain Page - Charts
  console.log('\n=== Onchain Page Detailed Check ===');
  await page.goto(`${BASE_URL}/onchain`, { waitUntil: 'networkidle', timeout: 30000 });
  await page.waitForTimeout(3000);

  // Check trend chart section
  const trendSection = await page.locator('text=/趋势图表|Trend|Gas|TVL/').first();
  const trendVisible = await trendSection.isVisible().catch(() => false);
  console.log(`Onchain - Trend section visible: ${trendVisible}`);

  // Check chart tabs
  const gasTab = await page.locator('text=/Gas/i').first();
  const tvlTab = await page.locator('text=/TVL/i').first();
  console.log(`Onchain - Gas tab exists: ${await gasTab.count() > 0}`);
  console.log(`Onchain - TVL tab exists: ${await tvlTab.count() > 0}`);

  // Try clicking Gas tab and check chart
  if (await gasTab.count() > 0) {
    await gasTab.click();
    await page.waitForTimeout(1500);
    const gasCanvases = await page.locator('canvas').count();
    const gasSvgs = await page.locator('svg').count();
    console.log(`Onchain (Gas tab) - Canvas: ${gasCanvases}, SVG: ${gasSvgs}`);
  }

  // Try clicking TVL tab and check chart
  if (await tvlTab.count() > 0) {
    await tvlTab.click();
    await page.waitForTimeout(1500);
    const tvlCanvases = await page.locator('canvas').count();
    const tvlSvgs = await page.locator('svg').count();
    console.log(`Onchain (TVL tab) - Canvas: ${tvlCanvases}, SVG: ${tvlSvgs}`);
  }

  // Check for "No Data" or empty states
  const bodyText2 = await page.locator('body').textContent();
  const hasNoData = /no data|暂无数据|empty|no chart/i.test(bodyText2);
  console.log(`Onchain - Has 'no data' indicator: ${hasNoData}`);

  // Check if chart area has any content
  const chartArea = await page.locator('[class*="chart"], [class*="Chart"], [class*="recharts"]').first();
  const chartHasContent = await chartArea.evaluate(el => el.children.length > 0).catch(() => false);
  console.log(`Onchain - Chart area has children: ${chartHasContent}`);

  // Check block details section
  const blockDetails = await page.locator('text=/区块详情|Block Detail/i').first();
  console.log(`Onchain - Block details section exists: ${await blockDetails.count() > 0}`);

  // Check gas details section
  const gasDetails = await page.locator('text=/Gas 详情|Gas Detail/i').first();
  console.log(`Onchain - Gas details section exists: ${await gasDetails.count() > 0}`);

  // Check for actual numeric values in onchain page
  const onchainBodyText = await page.locator('body').textContent();
  const hasBlockHeight = /95,747,\d+/.test(onchainBodyText);
  const hasOnchainTvl = /\$564/.test(onchainBodyText);
  const hasGasPrice = /50\.0001/.test(onchainBodyText);
  console.log(`Onchain - Has block height: ${hasBlockHeight}`);
  console.log(`Onchain - Has TVL value: ${hasOnchainTvl}`);
  console.log(`Onchain - Has gas price: ${hasGasPrice}`);

  await page.screenshot({ path: '/root/.openclaw/workspace/projects/mantle-defai-trader/tests/screenshot-onchain-gas-tab.png', fullPage: true });

  await browser.close();
})();
