#!/usr/bin/env node
/**
 * Screenshot script for sentiment consistency testing
 * Screenshots both Dashboard (/) and Sentiment (/sentiment) pages
 * Waits for API data to load before capturing
 */
const { chromium } = require('playwright');
const fs = require('fs');
const path = require('path');

const OUTDIR = path.resolve(__dirname);
const BASE_URL = 'http://localhost:5173';
const API_TIMEOUT = 15000;

async function waitForSentimentData(page, label) {
  // Wait for the sentiment gauge or count cards to appear (non-loading state)
  // The gauge SVG circle with stroke-dashoffset indicates loaded data
  try {
    await page.waitForFunction(() => {
      const gaugeValue = document.querySelector('svg circle[style*="stroke-dashoffset"]');
      const countCards = document.querySelectorAll('.text-4xl, .text-5xl, .text-xl');
      return gaugeValue !== null && countCards.length >= 3;
    }, { timeout: API_TIMEOUT });
    console.log(`[${label}] Data loaded`);
  } catch (e) {
    console.warn(`[${label}] Timeout waiting for data, proceeding anyway`);
  }
  // Extra wait for any animations to settle
  await page.waitForTimeout(2000);
}

async function screenshotPage(browser, url, filename, label) {
  const page = await browser.newPage({
    viewport: { width: 1440, height: 1200 },
  });
  console.log(`[${label}] Navigating to ${url}`);
  await page.goto(url, { waitUntil: 'networkidle', timeout: 30000 });
  await waitForSentimentData(page, label);
  const outPath = path.join(OUTDIR, filename);
  await page.screenshot({ path: outPath, fullPage: true });
  console.log(`[${label}] Screenshot saved: ${outPath}`);
  
  // Extract visible sentiment data from the page
  const extracted = await page.evaluate(() => {
    const result = {};
    // Try to find sentiment index value
    const gaugeText = document.querySelector('svg + div span.text-4xl, svg + div span.text-5xl, .absolute span.text-4xl');
    if (gaugeText) result.gauge_text = gaugeText.textContent.trim();
    
    // Count cards
    const cards = document.querySelectorAll('.card, .rounded-xl');
    cards.forEach(card => {
      const labelEl = card.querySelector('.text-xs.text-gray-500, .text-xs');
      const countEl = card.querySelector('.text-lg, .text-xl, .text-2xl');
      if (labelEl && countEl) {
        const label = labelEl.textContent.trim();
        const count = countEl.textContent.trim();
        if (label.includes('看涨')) result.bullish = count;
        if (label.includes('看跌')) result.bearish = count;
        if (label.includes('中性')) result.neutral = count;
        if (label.includes('分析总数')) result.total = count;
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
    
    // Screenshot Dashboard (homepage) — focus on sentiment area
    const dashboardData = await screenshotPage(browser, `${BASE_URL}/`, 'dashboard-full.png', 'DASHBOARD');
    
    // Screenshot Sentiment page
    const sentimentData = await screenshotPage(browser, `${BASE_URL}/sentiment`, 'sentiment-full.png', 'SENTIMENT');
    
    // Save extracted data
    fs.writeFileSync(
      path.join(OUTDIR, 'extracted-data.json'),
      JSON.stringify({ dashboard: dashboardData, sentiment: sentimentData }, null, 2)
    );
    console.log('Extracted data saved');
    
  } catch (err) {
    console.error('Error:', err.message);
    process.exit(1);
  } finally {
    if (browser) await browser.close();
  }
})();
