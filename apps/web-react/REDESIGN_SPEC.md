# React 版前端重设计规范

> 目标：将 HTML 版 (apps/web/) 的视觉设计完整移植到 React 版 (apps/web-react/)
> HTML 版是经过精心设计的，配色、布局、交互都很完善。React 版目前太丑，需要全面美化。

## 一、设计系统（从 HTML 版提取）

### 配色方案
```css
:root {
  --mantle-primary: #2D6B5E;
  --mantle-secondary: #4A9B8C;
  --mantle-accent: #7ED7C4;
  --bg-dark: #0a0e17;
  --bg-card: #111827;
  --bg-hover: #1f2937;
}
```

### 关键样式
- **背景**: #0a0e17（深蓝黑）
- **卡片**: #111827 + 1px border rgba(255,255,255,0.05) + border-radius 16px
- **Mantle 渐变**: linear-gradient(135deg, #2D6B5E → #4A9B8C)
- **看涨色**: #10b981（emerald）
- **看跌色**: #ef4444（red）
- **中性色**: #f59e0b（amber）
- **导航栏**: 半透明模糊 rgba(10,14,23,0.9) + backdrop-blur + sticky top
- **API 状态**: 在线=#10b981 + glow / 离线=#ef4444 + glow / 检查中=#f59e0b + pulse
- **骨架加载**: shimmer 动画 linear-gradient(90deg, #111827 25%, #1f2937 50%, #111827 75%)
- **滚动条**: 6px 宽, thumb=#374151

### 字体
- Inter, -apple-system, BlinkMacSystemFont, sans-serif

### 图标
- HTML 版用 Font Awesome (fas fa-chart-line 等)
- React 版用 lucide-react（已安装）

## 二、导航栏设计

```
┌─────────────────────────────────────────────────────────────┐
│ [📈 Mantle DeFAI] [v1.0]     [🟢 API 在线] [🔗 连接钱包]  │
└─────────────────────────────────────────────────────────────┘
```
- 左侧：Mantle 渐变 logo 方块 + "Mantle DeFAI" + emerald 版本标签
- 右侧：API 状态指示器（带 glow dot）+ 连接钱包按钮（mantle-gradient）
- 半透明模糊背景，sticky top

## 三、Dashboard 页面（重点）

Dashboard 是主页，包含 4 个核心区块：

### 区块 1: 情绪研判卡片
- **3 Tab 切换**：总览 | 数据来源 | 分析逻辑
- Tab 1 总览：
  - 左：Gauge 圆形图表（情绪指数 0-100，颜色渐变 red→amber→emerald）
  - 右：情绪指数数值 + 状态文字 + 更新时间
  - 下：3 个计数卡片（看涨/中性/看跌）
- Tab 2 数据来源：
  - 币安市场数据（权重 70%）详情
  - Mantle 链上数据（权重 30%）详情
- Tab 3 分析逻辑：
  - 流程图式展示计算步骤（binance_bullish → binance_score → weighted → final_index）

### 区块 2: 链上数据卡片
- 顶部 4 个指标卡片（区块高度/交易数/Gas价格/活跃度）
- Tab 切换图表：活跃度趋势 | Gas走势 | TVL变化 | 协议排名
- 使用 recharts（React 版已安装）

### 区块 3: 强势/弱势币种
- 两个并列卡片
- 每个卡片列出 top 5 币种 + 价格 + 变化 + alignment 标签

### 区块 4: 全市场分析表格
- 完整表格：币种/价格/24h变化/均线趋势/信号强度/成交量趋势
- 排序功能

## 四、其他页面设计

### Sentiment 页面
- 独立的深度情绪分析页
- 时间周期切换（1h/4h/1d）
- 更大的情绪图表
- 完整币种列表

### Protocols 页面
- 协议 TVL 排名（水平条形图）
- 协议详情卡片网格
- DEX / Lending / Yield 分类 Tab

### OnChain 页面
- 链上数据深度页
- 大趋势图表
- Gas 历史 / TVL 历史 / 网络活跃度

### Swap 页面
- 代币选择器
- 报价展示
- 交易执行
- Mantle 渐变按钮

## 五、组件要求

1. **所有卡片统一风格**：#111827 背景 + 微边框 + 16px 圆角 + hover 微动效
2. **骨架加载**：每个数据区域加载时显示 shimmer 骨架
3. **API 状态指示**：导航栏 + 脱机横幅
4. **响应式**：移动端适配
5. **暗色主题**：全局 #0a0e17 背景，无亮色区域
6. **Mantle 品牌色贯穿**：渐变按钮、高亮色、活跃 Tab

## 六、技术约束

- React 19 + TypeScript
- Tailwind CSS v4（@tailwindcss/vite 插件）
- recharts（替代 Chart.js）
- lucide-react（替代 Font Awesome）
- axios（已安装）
- react-router-dom v7
- Vite 8

## 七、API 端点（已可用）

- `GET /health` — 健康检查
- `POST /api/sentiment/analyze` — 情绪分析（timeframe: 1h/4h/1d, limit: 10-100）
- `GET /api/sentiment/latest` — 最新缓存情绪数据
- `GET /api/onchain/overview` — 链上概览
- `GET /api/onchain/protocols` — 协议列表
- `GET /api/mantle/block` — 最新区块
- `GET /api/mantle/gas` — Gas 价格
- `GET /api/mantle/network` — 网络统计
- `GET /api/mantle/trends` — 24h 趋势数据
- `GET /api/mantle/tvl/history` — TVL 历史
- `POST /api/swap/quote` — Swap 报价
- `POST /api/swap/execute` — Swap 执行
