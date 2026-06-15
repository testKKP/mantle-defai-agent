import { test, expect } from '@playwright/test';

const FRONTEND_BASE = process.env.FRONT_BASE || 'http://localhost:5173';

const mockSentimentResponse = {
  success: true,
  data: {
    sentiment_index: 65,
    bullish_count: 12,
    neutral_count: 5,
    bearish_count: 8,
    timestamp: new Date().toISOString(),
    data_freshness: new Date().toISOString(),
    total_analyzed: 25,
    top_bullish: [],
    top_bearish: [],
    backtest_results: {
      "BTC_1d": {
        "total_signals": 42,
        "stats": {
          "bullish_all_1": { "total_signals": 8, "win_rate": 62.5, "avg_net_pnl": 1.23, "max_pnl": 3.45, "min_pnl": -1.20, "profit_factor": 1.61, "insufficient_data": false },
        },
        "current_signal": {
          "direction": "long",
          "pattern": "bullish_all",
          "duration": 2,
          "duration_bucket": "2-3",
          "strength": "strong",
          "price": 67500.50,
          "similar_state_stats": {
            "total_signals": 12,
            "win_rate": 58.3,
            "avg_net_pnl": 0.89,
            "insufficient_data": false
          },
          "recommendation": {
            "action": "strong_long",
            "confidence": "high",
            "score": 85,
            "reason": "历史胜率58.3%；平均收益0.89%；盈亏比1.42"
          }
        }
      }
    }
  }
};

test('Debug backtest data rendering', async ({ page }) => {
  test.setTimeout(60000);

  await page.route('**/*', async (route) => {
    const url = route.request().url();
    if (url.includes('/api/sentiment/')) {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(mockSentimentResponse)
      });
      return;
    }
    await route.continue();
  });

  await page.goto(`${FRONTEND_BASE}/sentiment`);
  await page.waitForLoadState('networkidle');
  await page.waitForTimeout(3000);

  // Click backtest tab
  const backtestTab = page.locator('button:has-text("Backtest")').first();
  if (await backtestTab.count() > 0) {
    await backtestTab.click();
  }
  await page.waitForTimeout(3000);

  // Get ALL divs and find ones containing BTC
  const allDivs = await page.evaluate(() => {
    const divs = document.querySelectorAll('div');
    const results: any[] = [];
    for (const div of divs) {
      const text = div.textContent || '';
      if (text.includes('BTC') && text.includes('1d')) {
        results.push({
          className: div.className,
          textPreview: text.substring(0, 200),
          childCount: div.children.length,
          innerHTML: div.innerHTML,
        });
      }
    }
    return results;
  });
  
  console.log('BTC divs found:', allDivs.length);
  for (const div of allDivs.slice(0, 3)) {
    console.log('--- BTC div ---');
    console.log('className:', div.className);
    console.log('textPreview:', div.textPreview);
    console.log('childCount:', div.childCount);
    console.log('innerHTML:', div.innerHTML.substring(0, 800));
  }

  // Find the parent card container
  const cardContainers = await page.evaluate(() => {
    const allElements = document.querySelectorAll('*');
    const results: any[] = [];
    for (const el of allElements) {
      const text = el.textContent || '';
      if (text.includes('Historical Signals') && text.includes('42')) {
        // This is likely the card containing BTC mock data
        const parent = el.closest('.card, [class*="card"], div[class*="p-5"]');
        if (parent) {
          results.push({
            tagName: parent.tagName,
            className: parent.className,
            fullText: parent.textContent?.substring(0, 500),
          });
        }
      }
    }
    return results;
  });
  
  console.log('Card containers:', JSON.stringify(cardContainers, null, 2));

  await page.screenshot({ path: 'tests/screenshots/backtest-debug.png', fullPage: true });
});
