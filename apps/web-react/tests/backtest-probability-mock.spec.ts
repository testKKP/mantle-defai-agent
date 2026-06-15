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
          "bullish_all_2-3": { "total_signals": 12, "win_rate": 58.3, "avg_net_pnl": 0.89, "max_pnl": 2.80, "min_pnl": -0.95, "profit_factor": 1.42, "insufficient_data": false }
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
      },
      "ETH_1d": {
        "total_signals": 35,
        "stats": {
          "bearish_all_1": { "total_signals": 5, "win_rate": 40.0, "avg_net_pnl": -0.50, "max_pnl": 1.20, "min_pnl": -2.10, "profit_factor": 0.68, "insufficient_data": false }
        },
        "current_signal": {
          "direction": "short",
          "pattern": "bearish_all",
          "duration": 1,
          "duration_bucket": "1",
          "strength": "medium",
          "price": 3450.20,
          "similar_state_stats": {
            "total_signals": 5,
            "win_rate": 40.0,
            "avg_net_pnl": -0.50,
            "insufficient_data": false
          },
          "recommendation": {
            "action": "short",
            "confidence": "medium",
            "score": 55,
            "reason": "历史胜率40.0%，建议谨慎做空"
          }
        }
      },
      "SOL_1d": {
        "total_signals": 3,
        "stats": {},
        "current_signal": {
          "direction": "long",
          "pattern": "bullish_all",
          "duration": 1,
          "duration_bucket": "1",
          "strength": "weak",
          "price": 145.80,
          "similar_state_stats": {
            "insufficient_data": true
          },
          "recommendation": {
            "action": "watch",
            "confidence": "low",
            "score": 30,
            "reason": "历史样本不足，无法评估"
          }
        }
      }
    }
  }
};

test.describe('Backtest Probability UI with Mock Data', () => {

  test('Backtest tab renders probability info with mock data', async ({ page }) => {
    test.setTimeout(60000);

    const consoleErrors: string[] = [];
    page.on('console', msg => {
      if (msg.type() === 'error') {
        const text = msg.text();
        const ignored = ['ResizeObserver', 'WebSocket', 'Source map', 'favicon'];
        if (!ignored.some(i => text.includes(i))) {
          consoleErrors.push(text);
        }
      }
    });

    // Intercept API calls and return mock data
    await page.route('**/api/sentiment/**', async (route) => {
      const url = route.request().url();
      if (url.includes('/api/sentiment/analyze') || url.includes('/api/sentiment/latest')) {
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify(mockSentimentResponse)
        });
      } else {
        await route.continue();
      }
    });

    // 1. Load sentiment page
    await page.goto(`${FRONTEND_BASE}/sentiment`);
    await page.waitForLoadState('networkidle');
    await page.waitForTimeout(2000);

    // 2. Click backtest tab
    const backtestTab = page.locator('button:has-text("Backtest")').first();
    if (await backtestTab.count() > 0) {
      await backtestTab.click();
    } else {
      const backtestTabZh = page.locator('button:has-text("历史回溯")').first();
      if (await backtestTabZh.count() > 0) {
        await backtestTabZh.click();
      }
    }
    await page.waitForTimeout(2000);

    // 3. Check that the backtest container with data is visible
    const container = page.locator('text=/Recommended Signal Backtest|推荐信号回溯验证/');
    expect(await container.count()).toBeGreaterThan(0);

    // 4. Check for new probability info fields
    const checks = [
      { name: 'Recommended Action', patterns: [/Recommended Action|建议动作/] },
      { name: 'Confidence', patterns: [/Confidence|置信度/] },
      { name: 'Score', patterns: [/Score|综合评分/] },
      { name: 'Current Win Rate', patterns: [/Current Match Win Rate|当前匹配胜率/] },
      { name: 'Reason', patterns: [/Reason|建议原因/] },
      { name: 'Signal Strength', patterns: [/Signal Strength|信号强度/] },
    ];

    for (const check of checks) {
      let found = false;
      for (const pattern of check.patterns) {
        const locators = page.locator(`text=/${pattern.source}/i`);
        if (await locators.count() > 0) {
          found = true;
          break;
        }
      }
      expect(found, `Expected to find "${check.name}" label in backtest UI`).toBe(true);
    }

    // 5. Check specific mock values
    // BTC strong_long action should show "Long"
    const longText = page.locator('text=/Long|做多/').first();
    expect(await longText.count()).toBeGreaterThan(0);

    // Score 85 should be visible
    const score85 = page.locator('text=/\\b85\\b/').first();
    expect(await score85.count()).toBeGreaterThan(0);

    // Win rate 58.3% should be visible
    const winRate = page.locator('text=/58\\.3/').first();
    expect(await winRate.count()).toBeGreaterThan(0);

    // 6. No i18n missingKey errors
    const i18nErrors = consoleErrors.filter(e => 
      e.includes('i18next') || e.includes('missingKey') || e.includes('backtest.')
    );
    expect(i18nErrors, `i18n errors: ${i18nErrors.join(', ')}`).toHaveLength(0);

    // 7. Screenshot
    await page.screenshot({ path: 'tests/screenshots/backtest-probability-mock.png', fullPage: true });
  });
});
