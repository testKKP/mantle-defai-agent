import { test, expect, chromium } from '@playwright/test';
import * as fs from 'fs';

const FRONTEND_BASE = 'http://localhost:5173';
const SCREENSHOT_PATH = '/root/.openclaw/workspace/projects/mantle-defai-trader/tests/elliott-wave-probability-ui.png';

// Helper: scroll into view
async function scrollToElliottWaveCard(page: any) {
  const card = await page.locator('text=艾略特波浪分析').first();
  if (await card.isVisible().catch(() => false)) {
    await card.scrollIntoViewIfNeeded();
    await page.waitForTimeout(500);
  }
}

// Helper: check if element exists
async function hasText(page: any, text: string): Promise<boolean> {
  const el = page.locator(`text=${text}`).first();
  return await el.isVisible().catch(() => false);
}

// Helper: capture console logs
const consoleLogs: { type: string; text: string }[] = [];

// We'll use a manual script approach since Playwright test runner
// might not have all the flexibility we need for the long waits.
async function runScreenshot() {
  const browser = await chromium.launch({ headless: true });
  const context = await browser.newContext({ viewport: { width: 1920, height: 1080 } });
  const page = await context.newPage();

  // Capture console logs
  page.on('console', (msg) => {
    consoleLogs.push({ type: msg.type(), text: msg.text() });
  });

  // Capture page errors
  const pageErrors: string[] = [];
  page.on('pageerror', (err) => {
    pageErrors.push(err.message);
  });

  try {
    console.log('1. 访问页面...');
    await page.goto(`${FRONTEND_BASE}/sentiment`, { waitUntil: 'networkidle', timeout: 30000 });
    console.log('   页面已加载');

    // Wait for initial render
    await page.waitForTimeout(8000);
    console.log('2. 等待 8 秒完成');

    // Scroll to Elliott Wave card
    console.log('3. 滚动到艾略特波浪分析卡片...');
    await scrollToElliottWaveCard(page);

    // Take a pre-check screenshot
    await page.screenshot({ path: SCREENSHOT_PATH.replace('.png', '-pre.png'), fullPage: true });

    // Check if "暂无缓存数据" or "re-analyze" button exists
    const noCacheText = await hasText(page, '暂无缓存数据');
    const reanalyzeBtn = await page.locator('button:has-text("重新分析"), button:has-text("Re-analyze")').first().isVisible().catch(() => false);

    if (noCacheText || reanalyzeBtn) {
      console.log('4. 发现"暂无缓存数据"或"重新分析"按钮，点击触发实时计算...');
      const btn = page.locator('button:has-text("重新分析"), button:has-text("Re-analyze")').first();
      if (await btn.isVisible().catch(() => false)) {
        await btn.click();
        console.log('   已点击重新分析按钮，等待计算完成...');
        // Wait up to 60 seconds for the chart to appear
        for (let i = 0; i < 60; i++) {
          await page.waitForTimeout(1000);
          const hasChart = await page.locator('svg.recharts-surface, .recharts-wrapper, canvas').first().isVisible().catch(() => false);
          if (hasChart) {
            console.log(`   图表已出现（等待 ${i + 1} 秒）`);
            break;
          }
          if (i % 5 === 0) {
            console.log(`   等待中... ${i + 1}s`);
          }
        }
      }
    } else {
      console.log('4. 已有缓存数据，无需点击重新分析');
    }

    // Final wait and scroll
    await page.waitForTimeout(3000);
    await scrollToElliottWaveCard(page);
    await page.waitForTimeout(2000);

    // Take final screenshot
    console.log('6. 截图保存...');
    await page.screenshot({ path: SCREENSHOT_PATH, fullPage: true });
    console.log(`   截图已保存: ${SCREENSHOT_PATH}`);

    // Evaluate checks
    console.log('\n7. 检查结果:');

    // Check for wave chart
    const waveChart = await page.locator('svg.recharts-surface, .recharts-wrapper, canvas').first().isVisible().catch(() => false);
    console.log(`   [${waveChart ? '✅' : '❌'}] 波浪图表（K线 + 波浪标注）: ${waveChart ? '显示' : '未显示'}`);

    // Check for dashed prediction line
    const html = await page.content();
    const hasDashedLine = html.includes('stroke-dasharray') || html.includes('dashed') || html.includes('预测');
    console.log(`   [${hasDashedLine ? '✅' : '❌'}] 走势预测图（虚线预测）: ${hasDashedLine ? '显示' : '未显示'}`);

    // Check for probability progress bar
    const hasProgressBar = await page.locator('[role="progressbar"], .progress-bar, .MuiLinearProgress-root').first().isVisible().catch(() => false);
    const hasProbabilityText = await hasText(page, '当前浪概率');
    console.log(`   [${hasProgressBar || hasProbabilityText ? '✅' : '❌'}] 当前浪概率进度条: ${hasProgressBar || hasProbabilityText ? '显示' : '未显示'}`);

    // Check status label
    const hasForming = await hasText(page, '正在形成中');
    const hasCompleted = await hasText(page, 'completed') || await hasText(page, 'Completed');
    console.log(`   [${hasForming || hasCompleted ? '✅' : '❌'}] 状态标签（正在形成中/completed）: ${hasForming ? '正在形成中' : hasCompleted ? 'completed' : '未显示'}`);

    // Check no Kimi AI text
    const hasKimiText = await hasText(page, 'Kimi AI') || html.includes('Kimi AI') || html.includes('kimi');
    console.log(`   [${!hasKimiText ? '✅' : '❌'}] 没有 Kimi AI 大段文字分析: ${!hasKimiText ? '通过' : '发现 Kimi AI 文字'}`);

    // Console errors
    const errors = consoleLogs.filter(l => l.type === 'error');
    console.log(`   [${errors.length === 0 ? '✅' : '⚠️'}] 浏览器控制台错误: ${errors.length} 个`);
    errors.forEach(e => console.log(`       - ${e.text}`));

    // Page errors
    console.log(`   [${pageErrors.length === 0 ? '✅' : '⚠️'}] 页面错误: ${pageErrors.length} 个`);
    pageErrors.forEach(e => console.log(`       - ${e}`));

    await browser.close();
    return { waveChart, hasDashedLine, hasProgressBar: hasProgressBar || hasProbabilityText, hasStatus: hasForming || hasCompleted, noKimiText: !hasKimiText, consoleErrors: errors.length, pageErrors: pageErrors.length };
  } catch (e) {
    console.error('执行失败:', e);
    await browser.close();
    throw e;
  }
}

runScreenshot();
