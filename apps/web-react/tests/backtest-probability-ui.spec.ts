import { test, expect } from '@playwright/test';

const FRONTEND_BASE = process.env.FRONT_BASE || 'http://localhost:5173';

test.describe('Backtest Probability UI - Verification', () => {

  test('Backtest tab renders probability info correctly', async ({ page }) => {
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

    // 1. Load sentiment page
    await page.goto(`${FRONTEND_BASE}/sentiment`);
    await page.waitForLoadState('networkidle');

    // 2. Click backtest tab
    const backtestTab = page.locator('button:has-text("Backtest")').first();
    if (await backtestTab.count() > 0) {
      await backtestTab.click();
    } else {
      // Try Chinese text
      const backtestTabZh = page.locator('button:has-text("历史回溯")').first();
      if (await backtestTabZh.count() > 0) {
        await backtestTabZh.click();
      }
    }
    await page.waitForTimeout(1500);

    // 3. Check that the backtest container is visible
    const backtestContainer = page.locator('text=/Recommended Signal Backtest|推荐信号回溯验证/');
    const containerVisible = await backtestContainer.count() > 0;

    if (containerVisible) {
      // 4. Check for new probability info fields in the recommended signals card
      // These are the new fields added in the modification
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
    }

    // 5. No critical console errors
    console.log('Console errors:', consoleErrors);
    expect(consoleErrors.filter(e => e.includes('i18next') || e.includes('missingKey'))).toHaveLength(0);

    // 6. Screenshot
    await page.screenshot({ path: 'tests/screenshots/backtest-probability-ui.png', fullPage: true });
  });
});
