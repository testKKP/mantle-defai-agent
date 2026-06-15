# Mantle DeFAI Agent

> Mantle 生态的自主 AI 交易信号 Agent —— 将多源市场情绪（Market Sentiment）与 AI 技术分析转化为可验证、可订阅的加密链上信号（On-chain Signals）。
> 
> Autonomous AI trading signal agent for the Mantle ecosystem, transforming multi-source market sentiment and AI technical analysis into verifiable, subscribable on-chain signals.

---

## 项目定位 | Positioning

**Mantle DeFAI Agent** 是一款面向 Mantle 生态的 DeFAI（DeFi + AI）智能体：

- 聚合币安市场数据与链上数据，计算实时市场情绪评分
- 使用 Kimi AI 对原始 K 线图进行艾略特波浪（Elliott Wave）分析，识别支撑/阻力与方向性偏向
- 通过回测引擎（Backtest Engine）验证历史信号表现
- 将信号 AES 加密后批量提交至 Mantle Sepolia 链上注册表合约，仅订阅者可解密读取
- 配套 React 前端仪表盘，支持钱包连接查看加密信号

---

## 核心功能模块 | Core Modules

### 1. 市场情绪分析引擎 | Market Sentiment Engine
- 数据源：币安 API（交易量前 50 币种 / Top 50 Binance symbols by volume）
- 指标：5 线顺上/顺下检测（MA5 > MA10 > MA20 > MA60 > MA120）
- 输出：市场情绪评分 0-100 + 币种列表
- 刷新频率：每 4 小时
- 缓存 TTL：15000 秒

### 2. AI 艾略特波浪分析 | AI Elliott Wave Analysis
- Kimi 双模式：
  - **Vision 模式**：BTC/ETH 使用原始 K 线图进行视觉分析
  - **Text-only 模式**：其他币种使用文本数据快速分析
- 自动识别关键支撑位、阻力位与方向性偏向
- 每 4 小时为日线做多前 10 币种生成分析图表
- 覆盖率从约 13% 提升至约 83%

### 3. 回测引擎 | Backtest Engine
- 基于历史信号回测验证策略表现
- `/api/sentiment/latest` 返回裁剪后的回测结果，避免响应过大

### 4. 加密链上信号注册表 | Encrypted On-chain Signal Registry (P0-3)
- 信号经 AES 加密后批量提交至 Mantle Sepolia 注册表合约
- 合约地址：`0xf13CF1217A687e1B4e464BC72AEb40567A7Beb7d`
- 仅订阅者可读取并解密信号
- 真实提交交易已上链验证

### 5. 前端仪表盘 | Frontend Dashboard
- React 18 + Vite + TypeScript + Tailwind CSS + wagmi
- 情绪分析、链上信号、艾略特波浪图表一体化展示
- 支持钱包连接查看加密信号

---

## 技术栈 | Tech Stack

| 层级 | 技术 |
|------|------|
| 后端 | FastAPI + Python 3.11 + Web3.py |
| 前端 | React 18 + Vite + TypeScript + Tailwind CSS + wagmi |
| AI | Kimi CLI（视觉 / 文本分析） |
| 数据 | Binance API、Mantle RPC、Moralis（当前额度耗尽） |
| 链上 | Mantle Sepolia / Mantle Mainnet |

---

## 快速开始 | Quick Start

### 本地开发 | Local Development

```bash
cd apps/api
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
python main.py
```

### Docker 部署 | Docker Deployment

```bash
docker-compose up -d
```

### 前端访问 | Frontend

进入 `apps/web-react/`，运行：

```bash
npm install && npm run dev
```

生产构建产物位于 `apps/web-react/dist/`，可直接用 nginx 等静态服务器托管。

---

## API 端点 | API Endpoints

| 端点 | 方法 | 说明 |
|------|------|------|
| `/health` | GET | 健康检查 / Health check |
| `/api/sentiment/analyze` | POST | 分析市场情绪 / Analyze market sentiment |
| `/api/sentiment/latest` | GET | 获取最新情绪数据与回测摘要 / Latest sentiment + backtest summary |
| `/api/sentiment/refresh` | POST | 手动刷新情绪数据 / Refresh sentiment data |
| `/api/sentiment/elliott-wave/list` | GET | 获取艾略特波浪分析列表 / Elliott wave analysis list |
| `/api/sentiment/elliott-wave/refresh` | POST | 手动刷新艾略特波浪分析 / Refresh Elliott wave analysis |
| `/api/sentiment/backtest` | GET | 获取回测结果 / Backtest results |
| `/api/onchain/signals` | GET | 获取链上信号 / On-chain signals |
| `/api/onchain/subscriptions` | GET | 获取订阅信息 / Subscription info |
| `/api/swap/quote` | POST | 获取 Swap 报价 / Swap quote |
| `/api/mantle/block` | GET | 最新区块信息 / Latest block info |
| `/api/mantle/gas` | GET | Gas 价格 / Gas price |
| `/api/mantle/network` | GET | 网络统计 / Network stats |

---

## 环境变量 | Environment Variables

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `PORT` | 8000 | 服务端口 / Server port |
| `MANTLE_RPC_URL` | https://rpc.mantle.xyz | Mantle RPC |
| `CACHE_TTL` | 300 | 缓存时间（秒）/ Cache TTL (seconds) |
| `RATE_LIMIT_REQUESTS` | 100 | 限流请求数 / Rate limit requests |
| `RATE_LIMIT_WINDOW` | 60 | 限流窗口（秒）/ Rate limit window (seconds) |
| `REGISTRY_ADDRESS` | `0xf13CF1217A687e1B4e464BC72AEb40567A7Beb7d` | 链上信号注册表合约地址 / On-chain signal registry address |
| `REGISTRY_PRIVATE_KEY` | `<YOUR_PRIVATE_KEY>` | 提交者私钥（占位符）/ Submitter private key (placeholder) |
| `SIGNAL_ENCRYPTION_KEY` | `<YOUR_AES_KEY>` | 信号 AES 加密密钥（占位符）/ Signal AES encryption key (placeholder) |
| `MORALIS_API_KEY` | `<YOUR_MORALIS_API_KEY>` | Moralis API Key（当前额度耗尽）/ Moralis API key (placeholder) |
| `ALLOWED_ORIGINS` | `*` | CORS 允许来源 / Allowed CORS origins |
| `IP_WHITELIST` | `<COMMA_SEPARATED_IPS>` | IP 白名单（占位符）/ IP whitelist (placeholder) |

> ⚠️ 请勿将真实私钥、API Key 或 IP 白名单提交到仓库。/ Do not commit real private keys, API keys, or IP whitelists to the repository.

---

## 生产部署检查清单 | Production Checklist

- [x] 错误处理和日志记录 / Error handling & logging
- [x] 速率限制 / Rate limiting
- [x] 缓存机制 / Caching
- [x] CORS 配置 / CORS configuration
- [x] 健康检查端点 / Health check endpoint
- [x] Docker 支持 / Docker support
- [x] 多 RPC 故障转移 / Multi-RPC failover
- [x] API 响应标准化 / Standardized API responses
- [x] 输入验证 / Input validation
- [x] 链上信号加密提交 / Encrypted on-chain signal submission
- [ ] HTTPS 配置 / HTTPS configuration
- [ ] 监控告警 / Monitoring & alerting
- [ ] 数据库持久化 / Database persistence
