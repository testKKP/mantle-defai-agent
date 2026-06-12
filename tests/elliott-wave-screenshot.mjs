import { chromium } from 'playwright';
import * as fs from 'fs';

const FRONTEND_BASE = 'http://localhost:5173';
const SCREENSHOT_PATH = '/root/.openclaw/workspace/projects/mantle-defai-trader/tests/elliott-wave-probability-ui.png';
const SCREENSHOT_PRE = '/root/.openclaw/workspace/projects/mantle-defai-trader/tests/elliott-wave-probability-pre.png';

const consoleLogs = [];

async function hasText(page, text) {
  const el = page.locator(`text=${text}`).first();
  return await el.isVisible().catch(() => false);
}

async function scrollToElliottWaveCard(page) {
  const card = await page.locator('text=艾略特波浪分析').first();
  if (await card.isVisible().catch(() => false)) {
    await card.scrollIntoViewIfNeeded();
    await page.waitForTimeout(500);
  }
}

async function runScreenshot() {
  const browser = await chromium.launch({ headless: true });
  const context = await browser.newContext({ viewport: { width: 1920, height: 1080 } });
  const page = await context.newPage();

  page.on('console', (msg) => {
    consoleLogs.push({ type: msg.type(), text: msg.text() });
  });

  const pageErrors = [];
  page.on('pageerror', (err) => {
    pageErrors.push(err.message);
  });

  try {
    console.log('1. 访问页面 http://localhost:5173/sentiment...');
    await page.goto(`${FRONTEND_BASE}/sentiment`, { waitUntil: 'networkidle', timeout: 30000 });
    console.log('   页面已加载');

    console.log('2. 等待 8 秒让页面完全渲染...');
    await page.waitForTimeout(8000);

    console.log('3. 滚动到艾略特波浪分析卡片...');
    await scrollToElliottWaveCard(page);

    // Pre-check screenshot
    await page.screenshot({ path: SCREENSHOT_PRE, fullPage: true });
    console.log(`   预检查截图已保存: ${SCREENSHOT_PRE}`);

    // Check if re-analyze needed
    const noCacheText = await hasText(page, '暂无缓存数据');
    const reanalyzeBtnVisible = await page.locator('button:has-text("重新分析"), button:has-text("Re-analyze")').first().isVisible().catch(() => false);

    console.log(`   "暂无缓存数据": ${noCacheText}, "重新分析"按钮可见: ${reanalyzeBtnVisible}`);

    if (noCacheText || reanalyzeBtnVisible) {
      console.log('4. 发现需要重新分析，点击按钮触发实时计算...');
      const btn = page.locator('button:has-text("重新分析"), button:has-text("Re-analyze")').first();
      if (await btn.isVisible().catch(() => false)) {
        await btn.click();
        console.log('   已点击重新分析按钮，等待计算完成（最多 60 秒）...');
        for (let i = 0; i < 60; i++) {
          await page.waitForTimeout(1000);
          // Check if chart appeared
          const chartVisible = await page.locator('svg.recharts-surface, .recharts-wrapper, canvas').first().isVisible().catch(() => false);
          if (chartVisible) {
            console.log(`   图表已出现（等待 ${i + 1} 秒）`);
            break;
          }
          if (i % 5 === 0 && i > 0) {
            console.log(`   仍在等待... ${i}s`);
          }
        }
      }
    } else {
      console.log('4. 已有缓存数据，无需点击重新分析');
    }

    // Final stabilization wait
    console.log('5. 等待页面稳定...');
    await page.waitForTimeout(5000);
    await scrollToElliottWaveCard(page);
    await page.waitForTimeout(2000);

    console.log('6. 保存最终截图...');
    await page.screenshot({ path: SCREENSHOT_PATH, fullPage: true });
    console.log(`   截图已保存: ${SCREENSHOT_PATH}`);

    // ========== 检查结果 ==========
    console.log('\n7. ========== 检查结果 ==========');
    const html = await page.content();

    // 1. Wave chart
    const waveChart = await page.locator('svg.recharts-surface, .recharts-wrapper, canvas').first().isVisible().catch(() => false);
    console.log(`   [${waveChart ? '✅' : '❌'}] 波浪图表（K线 + 波浪标注）: ${waveChart ? '已显示' : '未显示'}`);

    // 2. Dashed prediction
    const hasDashedLine = html.includes('stroke-dasharray') || html.includes('dashed') || await hasText(page, '预测');
    console.log(`   [${hasDashedLine ? '✅' : '❌'}] 走势预测图（虚线预测）: ${hasDashedLine ? '已显示' : '未显示'}`);

    // 3. Probability progress bar
    const hasProgressBar = await page.locator('[role="progressbar"], .progress-bar, .MuiLinearProgress-root').first().isVisible().catch(() => false);
    const hasProbabilityText = await hasText(page, '当前浪概率');
    console.log(`   [${hasProgressBar || hasProbabilityText ? '✅' : '❌'}] 当前浪概率进度条区域: ${hasProgressBar || hasProbabilityText ? '已显示' : '未显示'}`);

    // 4. Status label
    const hasForming = await hasText(page, '正在形成中');
    const hasCompleted = await hasText(page, 'completed') || await hasText(page, 'Completed');
    console.log(`   [${hasForming || hasCompleted ? '✅' : '❌'}] 状态标签: ${hasForming ? '正在形成中' : hasCompleted ? 'completed' : '未显示'}`);

    // 5. No Kimi AI text
    const hasKimiText = html.toLowerCase().includes('kimi ai') || html.toLowerCase().includes('kimi') && html.includes('分析');
    console.log(`   [${!hasKimiText ? '✅' : '❌'}] 没有 Kimi AI 大段文字分析: ${!hasKimiText ? '通过' : '发现 Kimi AI 相关文字'}`);

    // 6. Console errors
    const errors = consoleLogs.filter(l => l.type === 'error');
    console.log(`   [${errors.length === 0 ? '✅' : '⚠️'}] 浏览器控制台错误: ${errors.length} 个`);
    errors.forEach(e => console.log(`       ERROR: ${e.text}`));

    // 7. Page errors
    console.log(`   [${pageErrors.length === 0 ? '✅' : '⚠️'}] 页面 JavaScript 错误: ${pageErrors.length} 个`);
    pageErrors.forEach(e => console.log(`       PAGEERROR: ${e}`));

    await browser.close();

    const results = {
      waveChart,
      hasDashedLine,
      hasProbabilityBar: hasProgressBar || hasProbabilityText,
      hasStatus: hasForming || hasCompleted,
      noKimiText: !hasKimiText,
      consoleErrors: errors.length,
      pageErrors: pageErrors.length,
      success: waveChart && (hasProgressBar || hasProbabilityText) && (hasForming || hasCompleted)
    };
    console.log('\n========== 验证结果汇总 ==========');
    console.log(JSON.stringify(results, null, 2));
    return results;
  } catch (e) {
    console.error('执行失败:', e);
    await browser.close();
    throw e;
  }
}

runScreenshot().catch((e) => {
  console.error(e);
  process.exit(1);
});
