#!/usr/bin/env node
/**
 * Screenshot script v2 - sets API base URL via localStorage before loading page
 */
const { chromium } = require('playwright');
const fs = require('fs');
const path = require('path');

const OUTDIR = path.resolve(__dirname, 'screenshots');
const BASE_URL = 'http://localhost:5173';
const API_BASE = 'http://localhost:8000';

async function screenshotPage(browser, url, filename, label) {
  const page = await browser.newPage({
    viewport: { width: 1440, height: 1200 },
  });

  // Pre-configure API base URL via localStorage
  await page.goto(`${BASE_URL}/`, { waitUntil: 'domcontentloaded', timeout: 30000 });
  await page.evaluate((apiBase) => {
    localStorage.setItem('mantle_settings', JSON.stringify({ apiBase, refreshInterval: 900000 }));
  }, API_BASE);

  console.log(`[${label}] Navigating to ${url}`);
  await page.goto(url, { waitUntil: 'networkidle', timeout: 30000 });

  // Wait for actual sentiment data to appear (not skeleton)
  try {
    await page.waitForFunction(() => {
      const text = document.body.innerText;
      // Wait until we see a sentiment index value (not just loading shimmer)
      return /市场情绪/.test(text) && !document.querySelector('.shimmer');
    }, { timeout: 15000 });
    console.log(`[${label}] Data loaded`);
  } catch (e) {
    console.warn(`[${label}] Timeout waiting for data, proceeding anyway`);
  }

  // Extra wait for gauge animations
  await page.waitForTimeout(2500);

  const outPath = path.join(OUTDIR, filename);
  await page.screenshot({ path: outPath, fullPage: true });
  console.log(`[${label}] Screenshot saved: ${outPath}`);

  // Extract visible data
  const extracted = await page.evaluate(() => {
    const result = { visible_texts: [] };
    const bodyText = document.body.innerText;

    // Try to extract gauge value - look for number near "市场情绪" or gauge area
    const allText = document.body.innerText.split('\n').map(s => s.trim()).filter(Boolean);
    result.all_lines = allText.slice(0, 80);

    // Find sentiment index value
    const gaugeSection = allText.findIndex(t => t.includes('市场情绪') || t.includes('情绪指数'));
    if (gaugeSection >= 0) {
      for (let i = gaugeSection; i < Math.min(gaugeSection + 10, allText.length); i++) {
        const match = allText[i].match(/^(\d+\.\d+)$/);
        if (match) result.sentiment_index = match[1];
      }
    }

    // Find counts
    allText.forEach((line, idx) => {
      if (line.includes('看涨')) {
        // Look at next few lines for number
        for (let i = idx; i < Math.min(idx + 5, allText.length); i++) {
          const m = allText[i].match(/^(\d+)$/);
          if (m && !result.bullish_count) result.bullish_count = m[1];
        }
      }
      if (line.includes('看跌')) {
        for (let i = idx; i < Math.min(idx + 5, allText.length); i++) {
          const m = allText[i].match(/^(\d+)$/);
          if (m && !result.bearish_count) result.bearish_count = m[1];
        }
      }
      if (line.includes('中性')) {
        for (let i = idx; i < Math.min(idx + 5, allText.length); i++) {
          const m = allText[i].match(/^(\d+)$/);
          if (m && !result.neutral_count) result.neutral_count = m[1];
        }
      }
    });

    return result;
  });

  await page.close();
  return extracted;
}

(async () => {
  let browser;
  try {
    browser = await chromium.launch({ headless: true });
    console.log('Browser launched');

    const dashboardData = await screenshotPage(browser, `${BASE_URL}/`, 'dashboard-v2.png', 'DASHBOARD');
    const sentimentData = await screenshotPage(browser, `${BASE_URL}/sentiment`, 'sentiment-v2.png', 'SENTIMENT');

    fs.writeFileSync(
      path.join(OUTDIR, 'extracted-v2.json'),
      JSON.stringify({ dashboard: dashboardData, sentiment: sentimentData }, null, 2)
    );
    console.log('Done');
  } catch (err) {
    console.error('Error:', err.message);
    process.exit(1);
  } finally {
    if (browser) await browser.close();
  }
})();
