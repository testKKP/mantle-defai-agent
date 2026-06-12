const { chromium } = require('playwright');

(async () => {
  const browser = await chromium.launch();
  const page = await browser.newPage({ viewport: { width: 1280, height: 900 } });
  
  page.on('console', msg => {
    console.log(`[${msg.type()}] ${msg.text()}`);
  });
  page.on('requestfailed', req => {
    console.log(`[FAILED] ${req.method()} ${req.url()} - ${req.failure().errorText}`);
  });
  page.on('response', async res => {
    if (res.url().includes('backtest')) {
      console.log(`[RESPONSE] ${res.status()} ${res.url()}`);
    }
  });
  
  await page.goto('http://YOUR_SERVER_IP:5173/sentiment');
  await page.waitForLoadState('networkidle');
  
  const backtestTab = page.locator('text=/历史回溯/i').first();
  await backtestTab.click();
  
  // Wait longer for response
  await page.waitForTimeout(20000);
  
  // Check DOM for results
  const hasResults = await page.evaluate(() => {
    return document.body.innerText.includes('已测试') || document.body.innerText.includes('推荐');
  });
  console.log('Has results in DOM:', hasResults);
  
  await page.screenshot({ path: '/root/.openclaw/workspace/projects/mantle-defai-trader/tests/screenshots/backtest-debug2.png', fullPage: true });
  
  await browser.close();
})();
