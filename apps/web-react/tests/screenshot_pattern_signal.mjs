import { chromium } from 'playwright';

const browser = await chromium.launch({ headless: true });
const context = await browser.newContext({ viewport: { width: 1440, height: 900 } });
const page = await context.newPage();
const logs = [];
page.on('console', msg => logs.push(`${msg.type()}: ${msg.text()}`));
page.on('pageerror', err => logs.push(`PAGEERROR: ${err.message}`));
try {
  await page.goto('http://localhost:5173/sentiment', { waitUntil: 'networkidle', timeout: 30000 });
  await page.waitForTimeout(3000);
  // scroll to Pattern Signal Detection
  const el = await page.locator('text=Pattern Signal Detection').first();
  if (await el.isVisible().catch(() => false)) {
    await el.scrollIntoViewIfNeeded();
    await page.waitForTimeout(1000);
    await el.screenshot({ path: '/tmp/pattern_signal_area.png' });
  } else {
    await page.screenshot({ path: '/tmp/pattern_signal_area.png', fullPage: true });
  }
  // also full page
  await page.screenshot({ path: '/tmp/sentiment_full.png', fullPage: true });
  console.log('SCREENSHOTS_OK');
} catch (e) {
  console.log('ERROR:', e.message);
} finally {
  await browser.close();
}
console.log('---CONSOLE_LOGS---');
console.log(logs.slice(0, 200).join('\n'));
