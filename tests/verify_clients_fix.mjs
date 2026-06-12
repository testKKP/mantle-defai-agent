import { chromium } from 'playwright';
import fs from 'fs';

const BASE_URL = 'http://localhost:5173';
const OUT_DIR = '/mnt/datadisk0/.openclaw/workspace/projects/mantle-defai-trader/tests/verify_clients_fix';

if (!fs.existsSync(OUT_DIR)) {
  fs.mkdirSync(OUT_DIR, { recursive: true });
}

const browser = await chromium.launch({ headless: true });
const context = await browser.newContext({ viewport: { width: 1440, height: 900 } });
const page = await context.newPage();

const consoleErrors = [];
const consoleMessages = [];

page.on('console', (msg) => {
  const text = msg.text();
  consoleMessages.push({ type: msg.type(), text });
  if (msg.type() === 'error') {
    consoleErrors.push(text);
  }
});

page.on('pageerror', (err) => {
  consoleErrors.push(err.message);
});

async function screenshot(path, filename) {
  console.log(`Navigating to ${BASE_URL}${path}`);
  await page.goto(`${BASE_URL}${path}`, { waitUntil: 'networkidle', timeout: 60000 });
  await page.waitForTimeout(3000);
  const fullPath = `${OUT_DIR}/${filename}`;
  await page.screenshot({ path: fullPath, fullPage: true });
  console.log(`Screenshot saved: ${fullPath}`);
}

await screenshot('/', 'dashboard-home.png');
await screenshot('/sentiment', 'sentiment.png');

await browser.close();

fs.writeFileSync(`${OUT_DIR}/console.json`, JSON.stringify({ errors: consoleErrors, messages: consoleMessages }, null, 2));

console.log('\nConsole errors:', consoleErrors.length);
consoleErrors.forEach((e) => console.log('  -', e));
