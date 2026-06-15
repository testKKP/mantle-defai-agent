import { chromium } from 'playwright';

(async () => {
  const browser = await chromium.launch();
  const page = await browser.newPage({ viewport: { width: 1920, height: 1080 } });
  
  await page.goto('http://localhost/sentiment', { waitUntil: 'load', timeout: 60000 });
  
  const result = await page.evaluate(async () => {
    const start = performance.now();
    try {
      const res = await fetch('/api/sentiment/latest');
      const data = await res.json();
      return { success: true, status: res.status, duration: performance.now() - start, hasData: !!data.data };
    } catch (e) {
      return { success: false, error: String(e), duration: performance.now() - start };
    }
  });
  
  console.log(JSON.stringify(result, null, 2));
  
  await page.screenshot({ path: 'tests/screenshots/ew-fixed-playwright.png', fullPage: false });
  
  await browser.close();
})();
