# Mantle DeFAI Agent — 生产级应用

## 项目定位
Mantle 生态的自主 AI Agent for DeFi on Mantle，融合市场情绪分析 + 最佳变现路由 + Mantle 链上数据。

## 核心功能模块

### 1. 市场情绪分析引擎 (生产就绪)
- 数据源：币安 API（交易量前50币种）
- 指标：5线顺上/顺下检测（MA5 > MA10 > MA20 > MA60 > MA120）
- 输出：市场情绪评分 (0-100) + 币种列表
- 缓存：5分钟 TTL，减少 API 调用

### 2. Mantle 链上数据 (生产就绪)
- 实时区块数据查询
- Gas 价格监控
- 网络活跃度分析
- 多 RPC 故障转移

### 3. DEX 报价查询 (基础版)
- 接入 Merchant Moe LBQuoter 合约
- 支持 MNT/USDC/USDT 等主流代币
- 自动降级到模拟数据（RPC 不可用时）

## 技术栈
- 后端：FastAPI + Python 3.11
- 前端：React + Vite + TypeScript + Tailwind CSS
- 链上交互：Web3.py / ethers.js + wagmi
- 数据抓取：币安 API + Mantle RPC

## 快速开始

### 本地开发
```bash
cd apps/api
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
python main.py
```

### Docker 部署
```bash
docker-compose up -d
```

### 前端访问
进入 `apps/web-react/` 运行 `npm install && npm run dev` 进行本地开发；生产构建产物位于 `apps/web-react/dist/`，可直接用 nginx 等静态服务器托管。

## API 端点

| 端点 | 方法 | 说明 |
|------|------|------|
| `/health` | GET | 健康检查 |
| `/api/sentiment/analyze` | POST | 分析市场情绪 |
| `/api/sentiment/latest` | GET | 获取缓存的情绪数据 |
| `/api/swap/quote` | POST | 获取 Swap 报价 |
| `/api/mantle/block` | GET | 最新区块信息 |
| `/api/mantle/gas` | GET | Gas 价格 |
| `/api/mantle/network` | GET | 网络统计 |

## 环境变量

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `PORT` | 8000 | 服务端口 |
| `MANTLE_RPC_URL` | https://rpc.mantle.xyz | Mantle RPC |
| `CACHE_TTL` | 300 | 缓存时间(秒) |
| `RATE_LIMIT_REQUESTS` | 100 | 限流请求数 |
| `RATE_LIMIT_WINDOW` | 60 | 限流窗口(秒) |

## 生产部署检查清单

- [x] 错误处理和日志记录
- [x] 速率限制
- [x] 缓存机制
- [x] CORS 配置
- [x] 健康检查端点
- [x] Docker 支持
- [x] 多 RPC 故障转移
- [x] API 响应标准化
- [x] 输入验证
- [ ] HTTPS 配置
- [ ] 监控告警
- [ ] 数据库持久化
