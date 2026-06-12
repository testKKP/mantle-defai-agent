const { chromium } = require('playwright');

(async () => {
  const browser = await chromium.launch();
  const page = await browser.newPage({ viewport: { width: 1280, height: 900 } });
  
  console.log('Navigating to sentiment page...');
  await page.goto('http://YOUR_SERVER_IP:5173/sentiment');
  await page.waitForLoadState('networkidle');
  console.log('Page loaded');
  
  // Click backtest tab
  const backtestTab = page.locator('text=/历史回溯|Backtest/i').first();
  await backtestTab.click();
  console.log('Clicked backtest tab');
  
  // Wait for content to load
  await page.waitForTimeout(3000);
  
  // Try clicking timeframe buttons to trigger data load
  const dayBtn = page.locator('button:has-text("1天")').first();
  if (await dayBtn.count() > 0) {
    await dayBtn.click();
    console.log('Clicked 1天 button');
  }
  
  // Wait for API response
  await page.waitForTimeout(5000);
  
  // Check if there are recommendation cards
  const cards = page.locator('[class*="recommendation"], [class*="signal"], [class*="card"]').first();
  const hasCards = await cards.count() > 0;
  console.log('Has cards:', hasCards);
  
  await page.screenshot({ path: '/root/.openclaw/workspace/projects/mantle-defai-trader/tests/screenshots/backtest-v2.png', fullPage: true });
  console.log('Screenshot saved');
  
  await browser.close();
  console.log('Done');
})();
