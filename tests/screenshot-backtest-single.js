const { chromium } = require('playwright');

(async () => {
  const browser = await chromium.launch();
  const page = await browser.newPage({ viewport: { width: 1280, height: 900 } });
  
  page.on('console', msg => console.log(`[${msg.type()}] ${msg.text()}`));
  page.on('requestfailed', req => console.log(`[FAILED] ${req.url()} - ${req.failure().errorText}`));
  page.on('response', async res => {
    if (res.url().includes('backtest')) {
      console.log(`[RESPONSE] ${res.status()} ${res.url()}`);
    }
  });
  
  await page.goto('http://YOUR_SERVER_IP:5173/sentiment');
  await page.waitForLoadState('networkidle');
  
  // Click backtest tab
  await page.locator('text=/历史回溯/i').first().click();
  await page.waitForTimeout(2000);
  
  // Click "查看详情" button for single backtest
  const detailBtn = page.locator('text=/查看详情/i').first();
  if (await detailBtn.count() > 0) {
    await detailBtn.click();
    console.log('Clicked 查看详情');
  }
  
  await page.waitForTimeout(5000);
  
  // Check if single backtest results show
  const hasResults = await page.evaluate(() => {
    return document.body.innerText.includes('回测统计') || document.body.innerText.includes('胜率');
  });
  console.log('Has single backtest results:', hasResults);
  
  await page.screenshot({ path: '/root/.openclaw/workspace/projects/mantle-defai-trader/tests/screenshots/backtest-single.png', fullPage: true });
  
  await browser.close();
})();
