#!/usr/bin/env node
/**
 * Screenshot script v3 - intercepts API requests and proxies to localhost:8000
 * to bypass CORS issues when frontend uses external IP
 */
const { chromium } = require('playwright');
const fs = require('fs');
const path = require('path');

const OUTDIR = path.resolve(__dirname, 'screenshots');
const BASE_URL = 'http://localhost:5173';
const API_TARGET = 'http://localhost:8000';

async function screenshotPage(browser, url, filename, label) {
  const page = await browser.newPage({
    viewport: { width: 1440, height: 1200 },
  });

  // Intercept API requests and forward to localhost:8000
  await page.route('**/*', async (route) => {
    const req = route.request();
    const reqUrl = req.url();
    if (reqUrl.includes('/api/') || reqUrl.includes('/health')) {
      const targetUrl = reqUrl.replace(/^https?:\/\/[^/]+/, API_TARGET);
      try {
        const fetchOptions = {
          method: req.method(),
          headers: req.headers(),
        };
        if (req.method() !== 'GET' && req.method() !== 'HEAD') {
          fetchOptions.body = req.postData();
        }
        const response = await fetch(targetUrl, fetchOptions);
        const body = await response.arrayBuffer();
        await route.fulfill({
          status: response.status,
          headers: Object.fromEntries(response.headers.entries()),
          body: Buffer.from(body),
        });
      } catch (e) {
        console.warn(`[${label}] Proxy error for ${reqUrl}:`, e.message);
        await route.continue();
      }
    } else {
      await route.continue();
    }
  });

  console.log(`[${label}] Navigating to ${url}`);
  await page.goto(url, { waitUntil: 'networkidle', timeout: 30000 });

  // Wait for sentiment data to load (shimmer gone, actual numbers present)
  try {
    await page.waitForFunction(() => {
      const hasShimmer = !!document.querySelector('.shimmer');
      const bodyText = document.body.innerText;
      // Sentiment page shows gauge, dashboard shows gauge + counts
      const hasSentimentLabel = bodyText.includes('市场情绪') || bodyText.includes('情绪指数');
      // Look for actual numbers (not just '--')
      const hasNumbers = /\d+\.\d+/.test(bodyText);
      return !hasShimmer && hasSentimentLabel && hasNumbers;
    }, { timeout: 15000 });
    console.log(`[${label}] Data loaded`);
  } catch (e) {
    console.warn(`[${label}] Timeout waiting for data, proceeding anyway`);
  }

  // Wait for gauge animation to settle
  await page.waitForTimeout(3000);

  const outPath = path.join(OUTDIR, filename);
  await page.screenshot({ path: outPath, fullPage: true });
  console.log(`[${label}] Screenshot saved: ${outPath}`);

  // Extract visible sentiment data
  const extracted = await page.evaluate(() => {
    const result = {};
    const bodyText = document.body.innerText;
    const lines = bodyText.split('\n').map(s => s.trim()).filter(Boolean);

    // Find sentiment index - usually a standalone decimal number near gauge
    for (let i = 0; i < lines.length; i++) {
      if (lines[i].includes('市场情绪') || lines[i].includes('情绪指数')) {
        for (let j = i + 1; j < Math.min(i + 8, lines.length); j++) {
          const m = lines[j].match(/^(\d+\.\d+)$/);
          if (m) { result.sentiment_index = m[1]; break; }
        }
        if (result.sentiment_index) break;
      }
    }

    // Also try finding any decimal that could be sentiment index
    if (!result.sentiment_index) {
      for (const line of lines) {
        const m = line.match(/^(\d{1,2}\.\d{1,2})$/);
        if (m) { result.sentiment_index = m[1]; break; }
      }
    }

    // Extract counts
    const extractCountNear = (keyword) => {
      const idx = lines.findIndex(l => l.includes(keyword));
      if (idx >= 0) {
        for (let i = idx; i < Math.min(idx + 6, lines.length); i++) {
          const m = lines[i].match(/^(\d+)$/);
          if (m) return m[1];
        }
      }
      return null;
    };

    result.bullish_count = extractCountNear('看涨');
    result.bearish_count = extractCountNear('看跌');
    result.neutral_count = extractCountNear('中性');
    result.total_analyzed = extractCountNear('分析总数');

    // Extract timestamp
    const timeMatch = bodyText.match(/更新于\s*(.+)/);
    if (timeMatch) result.timestamp_text = timeMatch[1];

    // Extract top bullish/bearish symbols
    result.top_bullish_symbols = [];
    result.top_bearish_symbols = [];
    let inBullish = false, inBearish = false;
    for (const line of lines) {
      if (line.includes('强势币种') || line.includes('看涨币种')) inBullish = true;
      if (line.includes('弱势币种') || line.includes('看跌币种')) { inBullish = false; inBearish = true; }
      const symMatch = line.match(/^([A-Z]{2,}USDT)$/);
      if (symMatch) {
        if (inBullish) result.top_bullish_symbols.push(symMatch[1]);
        if (inBearish) result.top_bearish_symbols.push(symMatch[1]);
      }
    }

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

    const dashboardData = await screenshotPage(
      browser, `${BASE_URL}/`, 'dashboard-loaded.png', 'DASHBOARD'
    );
    const sentimentData = await screenshotPage(
      browser, `${BASE_URL}/sentiment`, 'sentiment-loaded.png', 'SENTIMENT'
    );

    fs.writeFileSync(
      path.join(OUTDIR, 'extracted-loaded.json'),
      JSON.stringify({ dashboard: dashboardData, sentiment: sentimentData }, null, 2)
    );
    console.log('All done. Extracted:', JSON.stringify({ dashboard: dashboardData, sentiment: sentimentData }, null, 2));
  } catch (err) {
    console.error('Error:', err.message);
    process.exit(1);
  } finally {
    if (browser) await browser.close();
  }
})();
