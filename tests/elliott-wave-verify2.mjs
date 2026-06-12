import { chromium } from 'playwright';

const SCREENSHOT_PATH = '/root/.openclaw/workspace/projects/mantle-defai-trader/tests/elliott-wave-probability-ui.png';

async function runVerify() {
  const browser = await chromium.launch({ headless: true });
  const context = await browser.newContext({ viewport: { width: 1920, height: 1080 } });
  const page = await context.newPage();

  const consoleLogs = [];
  const pageErrors = [];
  const networkRequests = [];
  page.on('console', (msg) => consoleLogs.push({ type: msg.type(), text: msg.text() }));
  page.on('pageerror', (err) => pageErrors.push(err.message));
  page.on('request', (req) => {
    if (req.url().includes('elliott')) networkRequests.push({ url: req.url(), method: req.method() });
  });
  page.on('response', (res) => {
    if (res.url().includes('elliott')) {
      networkRequests.push({ url: res.url(), status: res.status() });
    }
  });

  try {
    console.log('1. 访问页面...');
    await page.goto('http://localhost:5173/sentiment', { waitUntil: 'networkidle', timeout: 30000 });
    console.log('   页面已加载');

    // Wait for Elliott Wave API to complete
    console.log('2. 等待艾略特波浪数据加载...');
    try {
      await page.waitForResponse(
        (res) => res.url().includes('elliott-wave') && res.status() === 200,
        { timeout: 15000 }
      );
      console.log('   Elliott Wave API 请求完成');
    } catch (e) {
      console.log('   未检测到 Elliott Wave API 响应，继续等待...');
    }

    console.log('3. 额外等待 5 秒...');
    await page.waitForTimeout(5000);

    console.log('4. 滚动到艾略特波浪分析卡片...');
    const card = page.locator('text=艾略特波浪分析').first();
    await card.scrollIntoViewIfNeeded();
    await page.waitForTimeout(1000);

    // Check if empty
    const emptyText = await page.locator('text=未在当前数据中发现').first().isVisible().catch(() => false);
    const noCache = await page.locator('text=暂无缓存数据').first().isVisible().catch(() => false);
    console.log(`   空数据提示: ${emptyText}, 无缓存: ${noCache}`);

    if (emptyText || noCache) {
      console.log('   数据为空，尝试点击"重新分析"...');
      const btn = page.locator('button:has-text("重新分析")').first();
      if (await btn.isVisible().catch(() => false)) {
        await btn.click();
        console.log('   已点击，等待 API 响应...');
        try {
          await page.waitForResponse(
            (res) => res.url().includes('elliott-wave') && (res.status() === 200 || res.status() === 202),
            { timeout: 60000 }
          );
          console.log('   API 响应收到');
        } catch (e) {
          console.log('   等待 API 响应超时');
        }
        console.log('   等待 10 秒让数据渲染...');
        await page.waitForTimeout(10000);
      }
    }

    console.log('5. 最终稳定等待...');
    await page.waitForTimeout(3000);
    await card.scrollIntoViewIfNeeded();
    await page.waitForTimeout(1000);

    console.log('6. 截图...');
    await page.screenshot({ path: SCREENSHOT_PATH, fullPage: true });
    console.log(`   截图已保存: ${SCREENSHOT_PATH}`);

    // ========== 检查结果 ==========
    console.log('\n========== 验证报告 ==========\n');

    const html = await page.content();
    const bodyText = await page.innerText('body');

    // 检查网络请求
    console.log('网络请求:');
    networkRequests.forEach(r => console.log(`   ${r.method || r.status} ${r.url}`));

    // 1. 波浪图表
    const imgs = await page.locator('img[alt*="Elliott"], img[alt*="Projection"]').all();
    let waveChartVisible = false;
    let projectionChartVisible = false;
    for (const img of imgs) {
      const src = await img.getAttribute('src');
      const visible = await img.isVisible().catch(() => false);
      const alt = await img.getAttribute('alt') || '';
      console.log(`   img: alt="${alt}", src=${src}, visible=${visible}`);
      if (alt.includes('Projection')) projectionChartVisible = visible;
      else waveChartVisible = visible;
    }
    console.log(`   [${waveChartVisible ? '✅' : '❌'}] 波浪图表（K线 + 波浪标注）`);
    console.log(`   [${projectionChartVisible ? '✅' : '❌'}] 走势预测图（虚线预测）`);

    // 2. 概率进度条
    const probText = bodyText.includes('当前浪概率');
    const probBars = await page.locator('.bg-gray-700.rounded-full').count();
    console.log(`   [${probText ? '✅' : '❌'}] 当前浪概率进度条区域: ${probText ? '文本存在' : '无'} (进度条数: ${probBars})`);

    // 3. 状态标签
    const hasForming = bodyText.includes('正在形成中');
    const hasCompleted = bodyText.includes('completed') || bodyText.includes('Completed');
    console.log(`   [${hasForming || hasCompleted ? '✅' : '❌'}] 状态标签: ${hasForming ? '正在形成中' : hasCompleted ? 'completed' : '未显示'}`);

    // 4. Kimi AI
    const hasKimi = bodyText.toLowerCase().includes('kimi ai');
    console.log(`   [${!hasKimi ? '✅' : '❌'}] 没有 Kimi AI 大段文字`);

    // 5. 控制台错误
    const errors = consoleLogs.filter(l => l.type === 'error');
    console.log(`   [${errors.length === 0 ? '✅' : '⚠️'}] 控制台错误: ${errors.length} 个`);
    errors.forEach(e => console.log(`       ${e.text}`));

    // 6. JS 错误
    console.log(`   [${pageErrors.length === 0 ? '✅' : '⚠️'}] 页面 JS 错误: ${pageErrors.length} 个`);

    await browser.close();
  } catch (e) {
    console.error('失败:', e);
    await browser.close();
    throw e;
  }
}

runVerify().catch(e => { console.error(e); process.exit(1); });
