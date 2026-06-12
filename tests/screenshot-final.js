const { chromium } = require('playwright');
const fs = require('fs');
const path = require('path');

const API_TARGET = 'http://localhost:8000';
const OUTDIR = path.resolve(__dirname, 'screenshots');

async function createInterceptedPage(browser) {
  const page = await browser.newPage({ viewport: { width: 1440, height: 1200 } });
  await page.route('**/*', async (route) => {
    const req = route.request();
    const reqUrl = req.url();
    if (reqUrl.includes('/api/') || reqUrl.includes('/health')) {
      const targetUrl = reqUrl.replace(/^https?:\/\/[^/]+/, API_TARGET);
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
        await route.fulfill({
          status: response.status,
          headers: Object.fromEntries(response.headers.entries()),
          body: Buffer.from(body),
        });
      } catch (e) {
        await route.continue();
      }
    } else {
      await route.continue();
    }
  });
  return page;
}

async function extractSentimentData(page) {
  return await page.evaluate(() => {
    const result = {};
    const text = document.body.innerText;
    const lines = text.split('\n').map(s => s.trim()).filter(Boolean);
    
    // Sentiment index
    const siIdx = lines.findIndex(l => l.includes('当前情绪指数') || l.includes('市场情绪指数'));
    if (siIdx >= 0) {
      for (let i = siIdx + 1; i < Math.min(siIdx + 6, lines.length); i++) {
        const m = lines[i].match(/^(\d+\.\d+)$/);
        if (m) { result.sentiment_index = m[1]; break; }
      }
    }
    // Also try standalone decimal
    if (!result.sentiment_index) {
      for (const line of lines) {
        const m = line.match(/^(\d{1,2}\.\d)$/);
        if (m) { result.sentiment_index = m[1]; break; }
      }
    }
    
    const extractCount = (keyword) => {
      const idx = lines.findIndex(l => l === keyword || l.includes(keyword));
      if (idx >= 0) {
        for (let i = idx - 2; i <= idx + 4; i++) {
          if (i < 0 || i >= lines.length) continue;
          const m = lines[i].match(/^(\d+)$/);
          if (m) return m[1];
        }
      }
      return null;
    };
    
    result.bullish_count = extractCount('看涨');
    result.bearish_count = extractCount('看跌');
    result.neutral_count = extractCount('中性');
    result.total_analyzed = extractCount('分析总数');
    
    // Top symbols
    result.top_bullish = [];
    result.top_bearish = [];
    let inBullish = false, inBearish = false;
    for (const line of lines) {
      if (line.includes('强势币种') || line.includes('看涨币种')) inBullish = true;
      if (line.includes('弱势币种') || line.includes('看跌币种')) { inBullish = false; inBearish = true; }
      const m = line.match(/^([A-Z]{2,}USDT)$/);
      if (m) {
        if (inBullish) result.top_bullish.push(m[1]);
        if (inBearish) result.top_bearish.push(m[1]);
      }
    }
    
    return result;
  });
}

(async () => {
  const browser = await chromium.launch({ headless: true });
  
  // Screenshot Dashboard
  const dashPage = await createInterceptedPage(browser);
  await dashPage.goto('http://localhost:5173/', { waitUntil: 'networkidle', timeout: 30000 });
  await dashPage.waitForTimeout(4000);
  await dashPage.screenshot({ path: path.join(OUTDIR, '01-dashboard.png'), fullPage: true });
  const dashData = await extractSentimentData(dashPage);
  console.log('DASHBOARD:', JSON.stringify(dashData));
  await dashPage.close();
  
  // Screenshot Sentiment page
  const sentPage = await createInterceptedPage(browser);
  await sentPage.goto('http://localhost:5173/sentiment', { waitUntil: 'networkidle', timeout: 30000 });
  await sentPage.waitForTimeout(4000);
  await sentPage.screenshot({ path: path.join(OUTDIR, '02-sentiment.png'), fullPage: true });
  const sentData = await extractSentimentData(sentPage);
  console.log('SENTIMENT:', JSON.stringify(sentData));
  await sentPage.close();
  
  fs.writeFileSync(
    path.join(OUTDIR, 'extracted-final.json'),
    JSON.stringify({ dashboard: dashData, sentiment: sentData }, null, 2)
  );
  
  await browser.close();
})();
