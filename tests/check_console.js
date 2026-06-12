const { chromium } = require('playwright');
(async () => {
  const browser = await chromium.launch({ headless: true });
  const page = await browser.newPage();
  const logs = [];
  page.on('console', msg => logs.push(`${msg.type()}: ${msg.text()}`));
  page.on('pageerror', err => logs.push(`PAGEERROR: ${err.message}`));
  await page.goto('http://43.134.37.174:5173/onchain', { waitUntil: 'networkidle', timeout: 30000 });
  await page.waitForTimeout(3000);
  // Click Gas tab
  const gasTab = await page.locator('text=/Gas/i').first();
  if (await gasTab.count() > 0) await gasTab.click();
  await page.waitForTimeout(2000);
  // Click TVL tab
  const tvlTab = await page.locator('text=/TVL/i').first();
  if (await tvlTab.count() > 0) await tvlTab.click();
  await page.waitForTimeout(2000);
  logs.forEach(l => console.log(l));
  await browser.close();
})();
