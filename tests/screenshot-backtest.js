const { chromium } = require('playwright');

(async () => {
  const browser = await chromium.launch();
  const page = await browser.newPage();
  
  console.log('Navigating to sentiment page...');
  await page.goto('http://43.134.37.174:5173/sentiment');
  await page.waitForLoadState('networkidle');
  console.log('Page loaded');
  
  // Take initial screenshot
  await page.screenshot({ path: '/root/.openclaw/workspace/projects/mantle-defai-trader/tests/screenshots/sentiment-initial.png', fullPage: false });
  console.log('Initial screenshot saved');
  
  // Try to find and click backtest tab
  try {
    const backtestTab = page.locator('text=/历史回溯|Backtest|回溯/i').first();
    const count = await backtestTab.count();
    if (count > 0) {
      await backtestTab.click();
      console.log('Clicked backtest tab');
      await page.waitForTimeout(2000);
      
      // Try to find batch backtest button
      const batchBtn = page.locator('text=/批量|Batch|全部/i').first();
      const btnCount = await batchBtn.count();
      if (btnCount > 0) {
        await batchBtn.click();
        console.log('Clicked batch backtest button');
        await page.waitForTimeout(3000);
      }
      
      await page.screenshot({ path: '/root/.openclaw/workspace/projects/mantle-defai-trader/tests/screenshots/backtest-page.png', fullPage: true });
      console.log('Backtest screenshot saved');
    } else {
      console.log('Backtest tab not found, taking full page screenshot');
      await page.screenshot({ path: '/root/.openclaw/workspace/projects/mantle-defai-trader/tests/screenshots/backtest-page.png', fullPage: true });
    }
  } catch (e) {
    console.log('Error during interaction:', e.message);
    await page.screenshot({ path: '/root/.openclaw/workspace/projects/mantle-defai-trader/tests/screenshots/backtest-error.png', fullPage: true });
  }
  
  await browser.close();
  console.log('Done');
})();
