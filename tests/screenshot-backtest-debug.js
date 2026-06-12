const { chromium } = require('playwright');

(async () => {
  const browser = await chromium.launch();
  const context = await browser.newContext({
    viewport: { width: 1280, height: 900 }
  });
  const page = await context.newPage();
  
  // Capture console logs
  const logs = [];
  page.on('console', msg => {
    const text = msg.text();
    logs.push(`[${msg.type()}] ${text}`);
    console.log(`[${msg.type()}] ${text}`);
  });
  
  // Capture network requests
  page.on('request', req => {
    if (req.url().includes('backtest')) {
      console.log(`[REQUEST] ${req.method()} ${req.url()}`);
    }
  });
  page.on('response', async res => {
    if (res.url().includes('backtest')) {
      const status = res.status();
      console.log(`[RESPONSE] ${status} ${res.url()}`);
      try {
        const body = await res.json();
        console.log(`[RESPONSE BODY] success=${body.success}`);
      } catch(e) {}
    }
  });
  
  console.log('Navigating...');
  await page.goto('http://43.134.37.174:5173/sentiment');
  await page.waitForLoadState('networkidle');
  console.log('Page loaded');
  
  // Click backtest tab
  const backtestTab = page.locator('text=/历史回溯/i').first();
  await backtestTab.click();
  console.log('Clicked backtest tab');
  
  // Wait for network to settle
  await page.waitForTimeout(8000);
  
  // Check batch result state via JS
  const batchState = await page.evaluate(() => {
    // Try to find React state - this won't work directly but we can check DOM
    const btn = document.querySelector('button');
    return {
      btnText: btn ? btn.textContent : 'no button',
      bodyText: document.body.innerText.includes('已测试') ? 'has results' : 'no results'
    };
  });
  console.log('Batch state:', batchState);
  
  await page.screenshot({ path: '/root/.openclaw/workspace/projects/mantle-defai-trader/tests/screenshots/backtest-debug.png', fullPage: true });
  console.log('Screenshot saved');
  
  await browser.close();
  console.log('Done');
})();
