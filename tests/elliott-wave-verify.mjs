import { chromium } from 'playwright';

const SCREENSHOT_PATH = '/root/.openclaw/workspace/projects/mantle-defai-trader/tests/elliott-wave-probability-ui.png';

async function runVerify() {
  const browser = await chromium.launch({ headless: true });
  const context = await browser.newContext({ viewport: { width: 1920, height: 1080 } });
  const page = await context.newPage();

  const consoleLogs = [];
  const pageErrors = [];
  page.on('console', (msg) => consoleLogs.push({ type: msg.type(), text: msg.text() }));
  page.on('pageerror', (err) => pageErrors.push(err.message));

  try {
    console.log('1. 访问页面 http://localhost:5173/sentiment...');
    await page.goto('http://localhost:5173/sentiment', { waitUntil: 'networkidle', timeout: 30000 });
    console.log('   页面已加载');

    console.log('2. 等待 8 秒让页面完全渲染...');
    await page.waitForTimeout(8000);

    console.log('3. 滚动到艾略特波浪分析卡片...');
    const card = page.locator('text=艾略特波浪分析').first();
    await card.scrollIntoViewIfNeeded();
    await page.waitForTimeout(500);

    // 检查是否有"暂无缓存数据"提示
    const noCache = await page.locator('text=暂无缓存数据').first().isVisible().catch(() => false);
    console.log(`   "暂无缓存数据": ${noCache}`);
    if (noCache) {
      console.log('   尝试点击"重新分析"...');
      const btn = page.locator('button:has-text("重新分析")').first();
      if (await btn.isVisible().catch(() => false)) {
        await btn.click();
        console.log('   已点击，等待 30 秒...');
        await page.waitForTimeout(30000);
      }
    }

    console.log('4. 等待页面稳定...');
    await page.waitForTimeout(3000);
    await card.scrollIntoViewIfNeeded();
    await page.waitForTimeout(2000);

    console.log('5. 保存截图...');
    await page.screenshot({ path: SCREENSHOT_PATH, fullPage: true });
    console.log(`   截图已保存: ${SCREENSHOT_PATH}`);

    // ========== 详细检查 ==========
    console.log('\n========== 艾略特波浪分析 UI 验证报告 ==========\n');

    const html = await page.content();

    // 1. 波浪图表（K线 + 波浪标注）
    // 检查是否有 img 标签且加载了图片
    const imgs = await page.locator('img[alt*="Elliott Wave"], img[alt*="Wave Projection"]').all();
    let waveChartVisible = false;
    let projectionChartVisible = false;
    for (const img of imgs) {
      const src = await img.getAttribute('src');
      const visible = await img.isVisible().catch(() => false);
      const alt = await img.getAttribute('alt');
      if (alt?.includes('Projection')) {
        projectionChartVisible = visible;
        console.log(`   img (projection): src=${src}, visible=${visible}`);
      } else {
        waveChartVisible = visible;
        console.log(`   img (wave): src=${src}, visible=${visible}`);
      }
    }
    console.log(`   [${waveChartVisible ? '✅' : '❌'}] 波浪图表（K线 + 波浪标注）: ${waveChartVisible ? '已显示' : '未显示'}`);

    // 2. 走势预测图（虚线预测）
    console.log(`   [${projectionChartVisible ? '✅' : '❌'}] 走势预测图（虚线预测）: ${projectionChartVisible ? '已显示' : '未显示'}`);

    // 3. 当前浪概率进度条区域
    const probSection = await page.locator('text=当前浪概率').first();
    const probVisible = await probSection.isVisible().catch(() => false);
    console.log(`   [${probVisible ? '✅' : '❌'}] 当前浪概率进度条区域: ${probVisible ? '已显示' : '未显示'}`);

    // 4. 状态标签
    const hasForming = await page.locator('text=正在形成中').first().isVisible().catch(() => false);
    const hasCompleted = await page.locator('text=completed, text=Completed').first().isVisible().catch(() => false);
    const statusVisible = hasForming || hasCompleted;
    console.log(`   [${statusVisible ? '✅' : '❌'}] 状态标签: ${hasForming ? '正在形成中' : hasCompleted ? 'completed' : '未显示'}`);

    // 5. 没有 Kimi AI 大段文字
    const pageText = await page.innerText('body');
    const hasKimiText = pageText.toLowerCase().includes('kimi ai') || (pageText.includes('Kimi') && pageText.includes('分析'));
    console.log(`   [${!hasKimiText ? '✅' : '❌'}] 没有 Kimi AI 大段文字分析: ${!hasKimiText ? '通过' : '发现 Kimi AI 文字'}`);

    // 6. 控制台错误
    const errors = consoleLogs.filter(l => l.type === 'error');
    console.log(`   [${errors.length === 0 ? '✅' : '⚠️'}] 浏览器控制台错误: ${errors.length} 个`);
    errors.forEach(e => console.log(`       ${e.text}`));

    // 7. 页面 JS 错误
    console.log(`   [${pageErrors.length === 0 ? '✅' : '⚠️'}] 页面 JavaScript 错误: ${pageErrors.length} 个`);
    pageErrors.forEach(e => console.log(`       ${e}`));

    // 8. 额外信息
    console.log('\n--- 额外信息 ---');
    const klinesText = await page.locator('text=/基于.*根K线计算/').first().innerText().catch(() => 'N/A');
    console.log(`   K线数量: ${klinesText}`);
    const cacheBadge = await page.locator('text=缓存数据').first().isVisible().catch(() => false);
    console.log(`   缓存标签: ${cacheBadge ? '显示' : '未显示'}`);
    const candidatesCount = await page.locator('text=/Wave [0-9]/').count();
    console.log(`   候选波浪数量: ${candidatesCount}`);

    await browser.close();

    return {
      waveChartVisible,
      projectionChartVisible,
      probVisible,
      statusVisible,
      noKimiText: !hasKimiText,
      consoleErrors: errors.length,
      pageErrors: pageErrors.length,
    };
  } catch (e) {
    console.error('执行失败:', e);
    await browser.close();
    throw e;
  }
}

runVerify().catch((e) => {
  console.error(e);
  process.exit(1);
});
