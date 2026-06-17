# Mantle DeFAI Agent — Production-Grade Application

## Project Overview
An autonomous AI Agent for DeFi on the Mantle ecosystem, combining market sentiment analysis, optimal swap routing, and Mantle on-chain data.

## Core Modules

### 1. Market Sentiment Analysis Engine (Production-Ready)
- **Data source:** Binance API (top 50 trading-volume tokens)
- **Indicator:** 5-MA alignment detection (`MA5 > MA10 > MA20 > MA60 > MA120`)
- **Output:** Market sentiment score (0–100) + token list
- **Caching:** 5-minute TTL to reduce API calls

### 2. Mantle On-Chain Data (Production-Ready)
- Real-time block data queries
- Gas price monitoring
- Network activity analysis
- Multi-RPC failover

### 3. DEX Quote Engine (Basic)
- Integrates Merchant Moe `LBQuoter` contract
- Supports mainstream tokens such as MNT/USDC/USDT
- Automatic fallback to simulated data when RPC is unavailable

### 4. On-Chain Signal Registry
The backend automatically generates trading signals every 4 hours.

- Signals are encrypted with AES before submission
- Submitted in batch via `submitSignalsBatch` to the Mantle Sepolia registry contract
- **Registry contract address:** `0xf13CF1217A687e1B4e464BC72AEb40567A7Beb7d`
- Signal structure:
  - `encryptedData` (`bytes`) — AES-encrypted payload
  - `dataHash` (`bytes32`) — integrity hash
  - `timestamp` — signal generation time
  - `submitter` — address that submitted the signal
- Only on-chain subscribers can read and decrypt signals

## Subscription Mechanism

- Users pay **MNT** to the registry contract to activate a subscription
- Subscription **price** and **duration** are configurable by the contract owner
- Only active subscribers can call:
  - `getLatestSignal`
  - `getSignal`
  - `getSignals`
- Non-subscribers receive the `NotSubscribed` revert
- During the current testnet beta, the frontend publicly displays signals through the backend API for demo purposes

## Signal Data Flow

```
Market Data + Kimi AI Analysis
        ↓
Encrypted Signal Payload (AES-GCM)
        ↓
submitSignalsBatch() → Mantle Sepolia Registry
        ↓
Stored in local DB (plaintext for dashboard)
        ↓
Frontend calls /api/onchain/signals/recent
        ↓
Rendered in React Dashboard
```

## Current Testnet Beta Note

- Currently deployed on **Mantle Sepolia testnet**
- Signal data is publicly visible through the backend API during the testing phase
- The production release will switch to pure on-chain, subscription-only read mode

## Tech Stack
- **Backend:** FastAPI + Python 3.11
- **Frontend:** React + Vite + TypeScript + Tailwind CSS
- **On-chain interaction:** Web3.py / ethers.js + wagmi
- **Data sources:** Binance API + Mantle RPC

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

### Frontend Access
Enter `apps/web-react/` and run `npm install && npm run dev` for local development. Production build artifacts are located in `apps/web-react/dist/` and can be served with any static server such as nginx.

## API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/health` | GET | Health check |
| `/api/sentiment/analyze` | POST | Analyze market sentiment |
| `/api/sentiment/latest` | GET | Get cached sentiment data |
| `/api/swap/quote` | POST | Get swap quote |
| `/api/mantle/block` | GET | Latest block information |
| `/api/mantle/gas` | GET | Gas price |
| `/api/mantle/network` | GET | Network statistics |
| `/api/onchain/signals/recent` | GET | Recent on-chain trading signals |

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `PORT` | 8000 | Service port |
| `MANTLE_RPC_URL` | https://rpc.mantle.xyz | Mantle RPC endpoint |
| `CACHE_TTL` | 300 | Cache TTL in seconds |
| `RATE_LIMIT_REQUESTS` | 100 | Rate limit request count |
| `RATE_LIMIT_WINDOW` | 60 | Rate limit window in seconds |
| `REGISTRY_ADDRESS` | - | Mantle Sepolia signal registry contract address |
| `REGISTRY_PRIVATE_KEY` | - | Private key for submitting signals (keep secret) |
| `SIGNAL_ENCRYPTION_KEY` | - | AES key for encrypting signal payloads |
| `SUBSCRIPTION_PRICE` | - | Subscription price in MNT |
| `SUBSCRIPTION_DURATION` | - | Subscription duration in seconds |

Use placeholders for sensitive values; never commit real private keys or API keys.

## Production Deployment Checklist

- [x] Error handling and logging
- [x] Rate limiting
- [x] Caching mechanism
- [x] CORS configuration
- [x] Health check endpoint
- [x] Docker support
- [x] Multi-RPC failover
- [x] Standardized API responses
- [x] Input validation
- [ ] HTTPS configuration
- [ ] Monitoring and alerting
- [ ] Database persistence
- [ ] On-chain subscription-only signal read mode
