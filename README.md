# Mantle DeFAI Agent

> **Verifiable AI Trading Intelligence on Mantle Network**  
> **Mantle 网络上的可验证 AI 交易智能体**

---

## Overview / 项目概述

Mantle DeFAI Agent is an autonomous, AI-powered trading intelligence platform built for the Mantle ecosystem. It fuses on-chain and off-chain data — market sentiment, Elliott Wave pattern recognition, and verifiable signal attestation — to generate actionable position recommendations with transparent, tamper-proof history.

Mantle DeFAI Agent 是一个为 Mantle 生态构建的自主 AI 交易智能平台。它融合链上与链下数据 —— 市场情绪、艾略特波浪形态识别以及可验证信号存证 —— 生成可执行的持仓建议，并提供透明、不可篡改的历史记录。

---

## Key Features / 核心功能

| Feature / 功能 | Description / 描述 |
|---|---|
| **AI Market Sentiment Engine / AI 市场情绪引擎** | Analyzes top-N Binance trading pairs, detects MA alignment and candlestick patterns, and outputs a 0-100 sentiment index plus token scores. / 分析币安交易量前 N 币种，检测均线排列与 K 线形态，输出 0-100 情绪指数及币种评分。 |
| **Elliott Wave Analysis / 艾略特波浪分析** | Multi-timeframe wave detection (1h / 4h / 1d / 1w) combining AI vision models with a custom algorithm to predict support and resistance levels. / 多时间框架波浪识别（1h / 4h / 1d / 1w），结合 AI 视觉模型与自定义算法预测支撑/阻力位。 |
| **On-Chain Signal Attestation / 链上信号存证** | Hashes every AI-generated signal and anchors it on Mantle Sepolia for verifiable, tamper-proof history. / 每笔 AI 生成信号哈希上链，部署于 Mantle Sepolia，提供可验证且不可篡改的历史。 |
| **Position Recommendation Report / 持仓建议报告** | Generates directional long/short recommendations with win-rate, confidence level, and target timeframe. / 生成做多/做空方向建议，附带胜率、置信度与目标时间框架。 |

---

## Tech Stack / 技术栈

| Layer / 层级 | Technologies / 技术 |
|---|---|
| **Backend / 后端** | Python 3.11, FastAPI, SQLite |
| **Frontend / 前端** | React 18, Vite, Tailwind CSS, Recharts |
| **AI / ML / 人工智能** | Kimi / Moonshot vision models, custom Elliott Wave algorithm |
| **Blockchain / 区块链** | Solidity, Mantle Sepolia, Web3.py |
| **Data / 数据** | Binance API, on-chain RPC |

---

## Architecture / 架构

The system is split into three layers:

1. **Data Layer / 数据层** — Binance market data and Mantle RPC feeds are collected, normalized, and cached.
2. **AI Layer / AI 层** — Sentiment scoring, Elliott Wave detection, and vision-based chart analysis run inside containerized services.
3. **Attestation & Presentation Layer / 存证与展示层** — Signals are hashed and recorded on Mantle Sepolia; the React + Vite frontend visualizes reports, charts, and on-chain proofs.

系统分为三层：

1. **数据层**：采集、归一化并缓存币安行情数据与 Mantle RPC 数据。
2. **AI 层**：在容器化服务中运行情绪评分、艾略特波浪识别与基于视觉的图表分析。
3. **存证与展示层**：信号哈希记录于 Mantle Sepolia；React + Vite 前端可视化报告、图表与链上证明。

---

## Quick Start / 快速开始

### Local Development / 本地开发

```bash
cd apps/api
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
python main.py
```

### Frontend / 前端

```bash
cd apps/web-react
npm install
npm run dev
```

### Docker Deployment / Docker 部署

```bash
docker-compose up -d
```

---

## Environment Variables / 环境变量

| Variable / 变量 | Default / 默认值 | Description / 说明 |
|---|---|---|
| `PORT` | `8000` | Backend service port / 后端服务端口 |
| `MANTLE_RPC_URL` | `YOUR_MANTLE_RPC_URL` | Mantle network RPC endpoint / Mantle 网络 RPC 端点 |
| `MANTLE_SEPOLIA_RPC_URL` | `YOUR_MANTLE_SEPOLIA_RPC_URL` | Mantle Sepolia RPC endpoint / Mantle Sepolia RPC 端点 |
| `CONTRACT_ADDRESS` | `YOUR_CONTRACT_ADDRESS` | Signal attestation contract address / 信号存证合约地址 |
| `BINANCE_API_KEY` | `YOUR_BINANCE_API_KEY` | Binance API key / 币安 API 密钥 |
| `MOONSHOT_API_KEY` | `YOUR_MOONSHOT_API_KEY` | Moonshot / Kimi API key / Moonshot / Kimi API 密钥 |
| `CACHE_TTL` | `300` | Cache TTL in seconds / 缓存时间（秒） |
| `RATE_LIMIT_REQUESTS` | `100` | Rate limit request count / 限流请求数 |
| `RATE_LIMIT_WINDOW` | `60` | Rate limit window in seconds / 限流窗口（秒） |

---

## Demo / 演示

- **Live Dashboard / 在线面板**: `https://YOUR_SERVER_IP` (replace with actual deployment URL / 替换为实际部署地址)
- **API Docs / API 文档**: `https://YOUR_SERVER_IP/docs` (FastAPI auto-generated docs / FastAPI 自动生成的文档)
- **On-Chain Explorer / 链上浏览器**: [Mantle Sepolia Explorer](https://sepolia.mantlescan.xyz)

---

## Hackathon Track / 黑客松赛道

**Mantle Turing Test Hackathon 2026 — AI Trading & Strategy**

---

## License / 许可

This project is licensed under the MIT License.

本项目采用 MIT 许可证。
