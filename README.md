# Mantle DeFAI Agent

> Autonomous AI trading signal agent for the Mantle ecosystem, transforming multi-source market sentiment and AI technical analysis into verifiable, subscribable on-chain signals.

---

## Positioning

**Mantle DeFAI Agent** is a DeFAI (DeFi + AI) agent built for the Mantle ecosystem:

- Aggregates Binance market data and on-chain data to compute real-time market sentiment scores
- Uses Kimi AI to perform Elliott Wave analysis on raw candlestick charts, identifying support/resistance and directional bias
- Validates historical signal performance through a backtest engine
- Batches AES-encrypted signals and submits them to the Mantle Sepolia on-chain registry contract, readable only by subscribers
- Includes a React frontend dashboard with wallet connection for viewing encrypted signals

---

## Core Modules

### 1. Market Sentiment Engine
- Data source: Binance API (top 50 symbols by trading volume)
- Indicator: 5-line alignment detection (MA5 > MA10 > MA20 > MA60 > MA120)
- Output: Market sentiment score 0-100 + symbol list
- Refresh interval: Every 4 hours
- Cache TTL: 15,000 seconds

### 2. AI Elliott Wave Analysis
- Kimi dual-mode analysis:
  - **Vision mode**: Visual analysis using raw candlestick charts for BTC/ETH
  - **Text-only mode**: Fast text-based analysis for other symbols
- Automatically identifies key support levels, resistance levels, and directional bias
- Generates analysis charts every 4 hours for the top 10 daily long-biased symbols
- Coverage increased from ~13% to ~83%

### 3. Backtest Engine
- Validates strategy performance through historical signal backtesting
- `/api/sentiment/latest` returns trimmed backtest results to avoid oversized responses

### 4. Encrypted On-chain Signal Registry (P0-3)
- Signals are AES-encrypted and batch-submitted to the Mantle Sepolia registry contract
- Contract address: `0xf13CF1217A687e1B4e464BC72AEb40567A7Beb7d`
- Only subscribers can read and decrypt the signals
- Real submission transactions have been verified on-chain

### 5. Frontend Dashboard
- React 18 + Vite + TypeScript + Tailwind CSS + wagmi
- Unified view of sentiment analysis, on-chain signals, and Elliott Wave charts
- Supports wallet connection for viewing encrypted signals

---

## Tech Stack

| Layer | Technology |
|------|------|
| Backend | FastAPI + Python 3.11 + Web3.py |
| Frontend | React 18 + Vite + TypeScript + Tailwind CSS + wagmi |
| AI | Kimi CLI (vision / text analysis) |
| Data | Binance API, Mantle RPC, Moralis (quota currently exhausted) |
| On-chain | Mantle Sepolia / Mantle Mainnet |

---

## Quick Start

### Local Development

```bash
cd apps/api
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
python main.py
```

### Docker Deployment

```bash
docker-compose up -d
```

### Frontend

Navigate to `apps/web-react/` and run:

```bash
npm install && npm run dev
```

Production build artifacts are located in `apps/web-react/dist/` and can be served directly by nginx or any static server.

---

## API Endpoints

| Endpoint | Method | Description |
|------|------|------|
| `/health` | GET | Health check |
| `/api/sentiment/analyze` | POST | Analyze market sentiment |
| `/api/sentiment/latest` | GET | Latest sentiment data + backtest summary |
| `/api/sentiment/refresh` | POST | Refresh sentiment data manually |
| `/api/sentiment/elliott-wave/list` | GET | Elliott wave analysis list |
| `/api/sentiment/elliott-wave/refresh` | POST | Refresh Elliott wave analysis manually |
| `/api/sentiment/backtest` | GET | Backtest results |
| `/api/onchain/signals` | GET | On-chain signals |
| `/api/onchain/subscriptions` | GET | Subscription info |
| `/api/swap/quote` | POST | Swap quote |
| `/api/mantle/block` | GET | Latest block info |
| `/api/mantle/gas` | GET | Gas price |
| `/api/mantle/network` | GET | Network stats |

---

## Environment Variables

| Variable | Default | Description |
|------|--------|------|
| `PORT` | 8000 | Server port |
| `MANTLE_RPC_URL` | https://rpc.mantle.xyz | Mantle RPC |
| `CACHE_TTL` | 300 | Cache TTL in seconds |
| `RATE_LIMIT_REQUESTS` | 100 | Rate limit request count |
| `RATE_LIMIT_WINDOW` | 60 | Rate limit window in seconds |
| `REGISTRY_ADDRESS` | `0xf13CF1217A687e1B4e464BC72AEb40567A7Beb7d` | On-chain signal registry contract address |
| `REGISTRY_PRIVATE_KEY` | `<YOUR_PRIVATE_KEY>` | Submitter private key (placeholder) |
| `SIGNAL_ENCRYPTION_KEY` | `<YOUR_AES_KEY>` | Signal AES encryption key (placeholder) |
| `MORALIS_API_KEY` | `<YOUR_MORALIS_API_KEY>` | Moralis API key (placeholder) |
| `ALLOWED_ORIGINS` | `*` | Allowed CORS origins |
| `IP_WHITELIST` | `<COMMA_SEPARATED_IPS>` | IP whitelist (placeholder) |

> ⚠️ Do not commit real private keys, API keys, or IP whitelists to the repository.

---

## Production Checklist

- [x] Error handling & logging
- [x] Rate limiting
- [x] Caching
- [x] CORS configuration
- [x] Health check endpoint
- [x] Docker support
- [x] Multi-RPC failover
- [x] Standardized API responses
- [x] Input validation
- [x] Encrypted on-chain signal submission
- [ ] HTTPS configuration
- [ ] Monitoring & alerting
- [ ] Database persistence
