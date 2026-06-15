const { chromium } = require('playwright');

(async () => {
  const browser = await chromium.launch({ headless: true });
  const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });

  page.on('console', msg => console.log(`[${msg.type()}] ${msg.text()}`));
  page.on('pageerror', err => console.log(`[PAGEERROR] ${err.message}`));
  page.on('response', resp => {
    if (resp.status() >= 400) {
      console.log(`[HTTP ${resp.status()}] ${resp.url()}`);
    }
  });

  await page.goto('http://localhost:4173/onchain-signals', { waitUntil: 'networkidle', timeout: 30000 });
  await page.waitForTimeout(5000);

  const html = await page.content();
  console.log('\n=== Page body text (first 2000 chars) ===');
  const bodyText = await page.locator('body').textContent();
  console.log(bodyText.substring(0, 2000));

  // Check what elements exist
  const headings = await page.locator('h2').allTextContents();
  console.log('\n=== All h2 headings ===');
  headings.forEach(h => console.log('  -', h));

  const divs = await page.locator('div').count();
  console.log('\n=== Element counts ===');
  console.log('divs:', divs);
  console.log('tables:', await page.locator('table').count());
  console.log('cards:', await page.locator('.card').count());

  await page.screenshot({ path: '/mnt/datadisk0/.openclaw/workspace/projects/mantle-defai-trader/tests/screenshots/onchain-signals-debug.png', fullPage: true });
  console.log('\nScreenshot saved');

  await browser.close();
})();
