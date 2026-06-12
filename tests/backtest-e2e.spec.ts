import { test, expect } from '@playwright/test';

const API_BASE = process.env.API_BASE || 'http://43.134.37.174:8000';
const FRONTEND_BASE = process.env.FRONT_BASE || 'http://43.134.37.174:5173';

test.describe('Backtest Module - Similar State Matching', () => {

  // ========================
  // API Tests
  // ========================

  test('API health check', async ({ request }) => {
    const response = await request.get(`${API_BASE}/health`);
    expect(response.status()).toBe(200);
    const data = await response.json();
    expect(data.status).toBe('healthy');
  });

  test('Single symbol backtest returns complete data', async ({ request }) => {
    const response = await request.get(`${API_BASE}/api/sentiment/backtest/BTCUSDT/1d`);
    expect(response.status()).toBe(200);
    const data = await response.json();
    expect(data.success).toBe(true);

    const d = data.data;
    expect(d).toHaveProperty('symbol', 'BTCUSDT');
    expect(d).toHaveProperty('timeframe', '1d');
    expect(d).toHaveProperty('total_signals');
    expect(typeof d.total_signals).toBe('number');
    expect(d).toHaveProperty('stats');
    expect(typeof d.stats).toBe('object');
    expect(d).toHaveProperty('current_signal');
    expect(d).toHaveProperty('recent_signals');
    expect(Array.isArray(d.recent_signals)).toBe(true);

    // Validate stats structure
    for (const [key, stat] of Object.entries(d.stats)) {
      const s = stat as any;
      expect(s).toHaveProperty('total_signals');
      expect(s).toHaveProperty('insufficient_data');
      expect(s).toHaveProperty('win_rate');
      expect(s).toHaveProperty('avg_pnl');
      expect(s).toHaveProperty('avg_net_pnl');
      expect(s).toHaveProperty('max_pnl');
      expect(s).toHaveProperty('min_pnl');
      expect(s).toHaveProperty('profit_factor');
      expect(s).toHaveProperty('avg_win');
      expect(s).toHaveProperty('avg_loss');
      expect(typeof s.total_signals).toBe('number');
      expect(typeof s.win_rate).toBe('number');
      expect(s.win_rate).toBeGreaterThanOrEqual(0);
      expect(s.win_rate).toBeLessThanOrEqual(100);
    }

    // Validate current_signal structure
    if (d.current_signal) {
      const cs = d.current_signal;
      expect(cs).toHaveProperty('pattern');
      expect(cs).toHaveProperty('duration');
      expect(cs).toHaveProperty('duration_bucket');
      expect(cs).toHaveProperty('direction');
      expect(cs).toHaveProperty('strength');
      expect(cs).toHaveProperty('price');
      expect(cs).toHaveProperty('similar_state_stats');
      expect(cs).toHaveProperty('recommendation');

      const rec = cs.recommendation;
      expect(rec).toHaveProperty('action');
      expect(rec).toHaveProperty('confidence');
      expect(rec).toHaveProperty('score');
      expect(rec).toHaveProperty('reason');
      expect(typeof rec.score).toBe('number');
      expect(rec.score).toBeGreaterThanOrEqual(0);
      expect(rec.score).toBeLessThanOrEqual(100);
    }
  });

  test('Batch backtest returns recommendations', async ({ request }) => {
    test.setTimeout(150000); // 2.5 minutes
    const response = await request.get(`${API_BASE}/api/sentiment/backtest-batch/1d`);
    expect(response.status()).toBe(200);
    const data = await response.json();
    expect(data.success).toBe(true);

    const d = data.data;
    expect(d).toHaveProperty('total_symbols_tested');
    expect(d).toHaveProperty('symbols_with_signals');
    expect(d).toHaveProperty('recommendations');
    expect(d).toHaveProperty('all_signals');
    expect(d).toHaveProperty('timestamp');

    expect(typeof d.total_symbols_tested).toBe('number');
    expect(d.total_symbols_tested).toBeGreaterThan(0);
    expect(Array.isArray(d.recommendations)).toBe(true);
    expect(Array.isArray(d.all_signals)).toBe(true);

    // Validate recommendations structure
    for (const rec of d.recommendations.slice(0, 2)) {
      expect(rec).toHaveProperty('symbol');
      expect(rec).toHaveProperty('direction');
      expect(rec).toHaveProperty('pattern');
      expect(rec).toHaveProperty('strength');
      expect(rec).toHaveProperty('duration');
      expect(rec).toHaveProperty('duration_bucket');
      expect(rec).toHaveProperty('current_price');
      expect(rec).toHaveProperty('similar_state_stats');
      expect(rec).toHaveProperty('recommendation');
    }

    // Validate all_signals structure
    for (const sig of d.all_signals.slice(0, 2)) {
      expect(sig).toHaveProperty('symbol');
      expect(sig).toHaveProperty('direction');
      expect(sig).toHaveProperty('recommendation');
    }
  });

  test('Invalid timeframe returns error status', async ({ request }) => {
    const response = await request.get(`${API_BASE}/api/sentiment/backtest/BTCUSDT/invalid`);
    expect([400, 422, 500]).toContain(response.status());
  });

  // ========================
  // Frontend E2E Tests
  // ========================

  test('Frontend backtest page loads and renders', async ({ page }) => {
    test.setTimeout(150000);

    // Collect console errors
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

    // 1. Load page
    await page.goto(`${FRONTEND_BASE}/sentiment`);
    await page.waitForLoadState('networkidle');

    // 2. Click backtest tab
    const backtestTab = page.locator('text=/历史回溯/i').first();
    await backtestTab.click();
    await page.waitForTimeout(1000);

    // 3. Check risk warning banner
    const warningText = page.locator('text=/风险提示.*0\.3%/i');
    await expect(warningText).toBeVisible();

    // 4. Batch backtest button - may show "计算中..." if auto-started
    const runBtn = page.locator('button:has-text("运行批量回测")');
    const calcBtn = page.locator('button:has-text("计算中...")');
    if (await runBtn.count() > 0) {
      await runBtn.click();
    } else if (await calcBtn.count() > 0) {
      // Already running, just wait
    }

    // Wait for results to load (up to 2 minutes)
    await page.waitForSelector('text=/已测试|推荐|个币种/', { timeout: 120000 });

    // 5. Check that batch result stats appear
    const testedCount = page.locator('text=/已测试.*个币种/');
    await expect(testedCount).toBeVisible();

    // 6. Check recommendation cards or empty state
    const hasRecs = await page.locator('text=/做多|做空|建议|强烈/').count() > 0;
    const hasEmpty = await page.locator('text=/当前没有符合条件的推荐信号/').count() > 0;
    expect(hasRecs || hasEmpty).toBe(true);

    // 7. Check all signals table
    const tableHeader = page.locator('th:has-text("币种")');
    await expect(tableHeader).toBeVisible();

    // 8. Check single symbol section
    const detailHeader = page.locator('text=/单币种详细回测/');
    await expect(detailHeader).toBeVisible();

    // 9. Check methodology section
    const methodology = page.locator('summary:has-text("相似状态匹配回测")');
    expect(await methodology.count()).toBeGreaterThan(0);

    // 10. No critical console errors
    expect(consoleErrors).toHaveLength(0);

    // Screenshot
    await page.screenshot({ path: 'tests/screenshots/backtest-e2e-full.png', fullPage: true });
  });

  test('Single symbol backtest detail loads', async ({ page }) => {
    test.setTimeout(60000);

    await page.goto(`${FRONTEND_BASE}/sentiment`);
    await page.waitForLoadState('networkidle');

    // Click backtest tab
    const backtestTab = page.locator('text=/历史回溯/i').first();
    await backtestTab.click();
    await page.waitForTimeout(500);

    // Select BTC from dropdown and load detail
    const select = page.locator('select');
    await select.selectOption('BTCUSDT');

    const viewBtn = page.locator('button:has-text("查看详情")');
    await viewBtn.click();

    // Wait for stats table to appear
    await page.waitForSelector('th:has-text("Pattern + 持续时间")', { timeout: 30000 });

    // Check stats table has data
    const statsRows = page.locator('tbody tr');
    expect(await statsRows.count()).toBeGreaterThan(0);

    await page.screenshot({ path: 'tests/screenshots/backtest-e2e-single-btc.png', fullPage: false });
  });
});
