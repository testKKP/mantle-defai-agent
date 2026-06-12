const { chromium } = require('playwright');
const fs = require('fs');
const path = require('path');

const API_TARGET = 'http://localhost:8000';

(async () => {
  const browser = await chromium.launch({ headless: true });
  const page = await browser.newPage({ viewport: { width: 1440, height: 1200 } });

  page.on('console', msg => console.log('CONSOLE:', msg.type(), msg.text()));

  await page.route('**/*', async (route) => {
    const req = route.request();
    const reqUrl = req.url();
    if (reqUrl.includes('/api/') || reqUrl.includes('/health')) {
      const targetUrl = reqUrl.replace(/^https?:\/\/[^/]+/, API_TARGET);
      console.log('PROXY:', req.method(), reqUrl, '->', targetUrl);
      try {
        const fetchOptions = {
          method: req.method(),
          headers: { ...req.headers(), origin: 'http://localhost:5173' },
        };
        if (req.method() !== 'GET' && req.method() !== 'HEAD') {
          fetchOptions.body = req.postDataBuffer() || req.postData();
        }
        const response = await fetch(targetUrl, fetchOptions);
        const body = await response.arrayBuffer();
        console.log('PROXY RES:', response.status, targetUrl, 'len=', body.byteLength);
        await route.fulfill({
          status: response.status,
          headers: Object.fromEntries(response.headers.entries()),
          body: Buffer.from(body),
        });
      } catch (e) {
        console.warn('PROXY ERR:', reqUrl, e.message);
        await route.continue();
      }
    } else {
      await route.continue();
    }
  });

  await page.goto('http://localhost:5173/', { waitUntil: 'networkidle', timeout: 30000 });
  await page.waitForTimeout(5000);

  const extracted = await page.evaluate(() => {
    return {
      bodyText: document.body.innerText.slice(0, 2000),
      hasShimmer: !!document.querySelector('.shimmer'),
    };
  });
  console.log('EXTRACTED:', JSON.stringify(extracted, null, 2));

  await page.screenshot({ path: path.resolve(__dirname, 'screenshots', 'dashboard-debug.png'), fullPage: true });
  console.log('Screenshot saved');
  await browser.close();
})();
