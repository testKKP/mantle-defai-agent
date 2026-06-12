const { chromium } = require('playwright');

(async () => {
  const browser = await chromium.launch({ headless: true });
  const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });

  page.on('request', req => {
    if (req.url().includes('/api/') || req.url().includes('/health')) {
      console.log('REQ:', req.method(), req.url());
    }
  });
  page.on('response', res => {
    if (res.url().includes('/api/') || res.url().includes('/health')) {
      console.log('RES:', res.status(), res.url());
    }
  });
  page.on('console', msg => console.log('CONSOLE:', msg.type(), msg.text()));

  await page.goto('http://localhost:5173/', { waitUntil: 'networkidle', timeout: 30000 });
  await page.waitForTimeout(3000);
  await browser.close();
})();
