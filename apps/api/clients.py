"""
External API clients and data providers (Binance, Mantle, DEX, Sentiment).
Global service instances are created at the bottom.
"""

import asyncio
import aiohttp
import numpy as np
import re
import time
from typing import List, Dict, Optional, Any
from datetime import datetime
from loguru import logger
from fastapi import HTTPException
from web3 import Web3

from db import db_save_signal, db_set

from core import (
    BINANCE_API_URL, DATA_API_URL, MANTLE_RPC_URL, MANTLE_CHAIN_ID,
    WMNT, USDC, USDT, LB_QUOTER, LB_ROUTER, LB_FACTORY,
    TOKEN_DECIMALS, CACHE_TTL, MAX_CACHE_SIZE,
    ERC20_ABI, LB_ROUTER_ABI,
    sanitize_for_json, cache, WHITELIST,
)

# External modules (global instance dependencies)
from onchain_collector import OnChainDataCollector, DataRefreshScheduler
from defillama_client import DeFiLlamaClient
from data_aggregator import DataAggregator, AggregatorScheduler as DataAggregatorScheduler
from whale_monitor import WhaleMonitor

# ============ Binance API Client ============

class BinanceClient:
    """Production-ready Binance API client with robust error handling"""
    
    _klines_semaphore = asyncio.Semaphore(10)
    
    def __init__(self):
        self.session: Optional[aiohttp.ClientSession] = None
        self.base_url = DATA_API_URL
        self._request_count = 0
        self._last_reset = time.time()
        
    async def __aenter__(self):
        timeout = aiohttp.ClientTimeout(total=30, connect=10)
        self.session = aiohttp.ClientSession(timeout=timeout)
        return self
        
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.session:
            await self.session.close()
    
    def _check_rate_limit(self):
        now = time.time()
        if now - self._last_reset >= 60:
            self._request_count = 0
            self._last_reset = now
        self._request_count += 1
        
        if self._request_count > 1000:
            logger.warning("Approaching Binance rate limit")
    
    async def _make_request(self, endpoint: str, params: Dict = None, max_retries: int = 3) -> Any:
        self._check_rate_limit()
        url = f"{self.base_url}{endpoint}"

        for attempt in range(max_retries):
            try:
                async with self.session.get(url, params=params, timeout=10) as resp:
                    if resp.status == 429:
                        retry_after = int(resp.headers.get("Retry-After", 2 ** attempt))
                        logger.warning(f"Binance rate limited (429), waiting {retry_after}s (attempt {attempt + 1})")
                        await asyncio.sleep(retry_after)
                        continue

                    if resp.status == 418:
                        logger.error("Binance IP banned (418)")
                        raise HTTPException(status_code=503, detail="Service temporarily unavailable due to rate limiting")

                    if resp.status >= 500:
                        logger.warning(f"Binance server error {resp.status}, attempt {attempt + 1}")
                        if attempt < max_retries - 1:
                            wait = 2 ** attempt
                            await asyncio.sleep(wait)
                            continue

                    resp.raise_for_status()
                    return await resp.json()

            except aiohttp.ClientResponseError as e:
                logger.error(f"Binance HTTP error (attempt {attempt + 1}): {e.status} {e.message}")
                if attempt < max_retries - 1 and e.status >= 500:
                    wait = 2 ** attempt
                    logger.info(f"Retrying in {wait}s...")
                    await asyncio.sleep(wait)
                else:
                    raise HTTPException(status_code=503, detail=f"Binance API error: {e.status} {e.message}")
            except aiohttp.ClientError as e:
                logger.error(f"Request failed (attempt {attempt + 1}): {e}")
                if attempt < max_retries - 1:
                    wait = 2 ** attempt
                    logger.info(f"Retrying in {wait}s...")
                    await asyncio.sleep(wait)
                else:
                    raise HTTPException(status_code=503, detail=f"Failed to fetch data: {str(e)}")
            except asyncio.TimeoutError:
                logger.error(f"Request timeout (attempt {attempt + 1})")
                if attempt < max_retries - 1:
                    wait = 2 ** attempt
                    logger.info(f"Retrying in {wait}s...")
                    await asyncio.sleep(wait)
                else:
                    raise HTTPException(status_code=504, detail="Binance API timeout")

        raise HTTPException(status_code=503, detail="Max retries exceeded")
    
    async def get_top_50_symbols(self, quote_asset: str = "USDT") -> List[dict]:
        cache_key = ("top50", quote_asset)
        cached = await cache.get("binance", *cache_key)
        if cached:
            return cached
        
        data = await self._make_request("/api/v3/ticker/24hr")
        
        filtered = [
            t for t in data 
            if t["symbol"].endswith(quote_asset) 
            and not any(t["symbol"].startswith(prefix) for prefix in ["UP", "DOWN", "BEAR", "BULL"])
            and float(t.get("quoteVolume", 0)) > 0
        ]
        
        sorted_tickers = sorted(filtered, key=lambda x: float(x["quoteVolume"]), reverse=True)
        
        result = [
            {
                "symbol": t["symbol"],
                "lastPrice": float(t["lastPrice"]),
                "volume": float(t["volume"]),
                "quoteVolume": float(t["quoteVolume"]),
                "priceChangePercent": float(t["priceChangePercent"]),
                "highPrice": float(t.get("highPrice", 0)),
                "lowPrice": float(t.get("lowPrice", 0)),
            }
            for t in sorted_tickers[:50]
        ]
        
        await cache.set("binance", *cache_key, data=result)
        return result
    
    async def get_klines(self, symbol: str, interval: str = "1h", limit: int = 500) -> List[dict]:
        cache_key = (symbol, interval, limit)
        cached = await cache.get("klines", *cache_key)
        if cached:
            return cached
        
        params = {
            "symbol": symbol.upper(),
            "interval": interval,
            "limit": min(limit, 1000)
        }
        
        async with self._klines_semaphore:
            data = await self._make_request("/api/v3/klines", params)
        
        result = [
            {
                "open_time": item[0],
                "open": float(item[1]),
                "high": float(item[2]),
                "low": float(item[3]),
                "close": float(item[4]),
                "volume": float(item[5]),
                "close_time": item[6],
                "quote_volume": float(item[7]),
                "trades": item[8],
                "taker_buy_volume": float(item[9]),
                "taker_buy_quote_volume": float(item[10]),
            }
            for item in data
        ]
        
        await cache.set("klines", *cache_key, data=result)
        return result

# ============ Moving Average Calculator ============

class MACalculator:
    @staticmethod
    def calculate(prices: List[float]) -> Dict[str, float]:
        mas = {}
        if len(prices) >= 5:
            mas["MA5"] = round(np.mean(prices[-5:]), 6)
        if len(prices) >= 10:
            mas["MA10"] = round(np.mean(prices[-10:]), 6)
        if len(prices) >= 20:
            mas["MA20"] = round(np.mean(prices[-20:]), 6)
        if len(prices) >= 60:
            mas["MA60"] = round(np.mean(prices[-60:]), 6)
        if len(prices) >= 120:
            mas["MA120"] = round(np.mean(prices[-120:]), 6)
        return mas
    
    @staticmethod
    def analyze_alignment(mas: Dict[str, float], current_price: float) -> dict:
        if not mas:
            return {
                "alignment": "neutral",
                "strength": "NONE",
                "score": 50,
                "price_above_all": False,
                "price_below_all": False,
                "spreads": {"5_10": 0, "10_20": 0, "20_60": 0, "60_120": 0},
                "mas": {},
            }
        
        ma5 = mas.get("MA5")
        ma10 = mas.get("MA10")
        ma20 = mas.get("MA20")
        ma60 = mas.get("MA60")
        ma120 = mas.get("MA120")
        
        num_ma = len(mas)
        
        # 计算spreads，缺少的MA字段用0填充
        spreads = {
            "5_10": (ma5 - ma10) / ma10 * 100 if ma10 and ma10 > 0 else 0,
            "10_20": (ma10 - ma20) / ma20 * 100 if ma20 and ma20 > 0 else 0,
            "20_60": (ma20 - ma60) / ma60 * 100 if ma60 and ma60 > 0 else 0,
            "60_120": (ma60 - ma120) / ma120 * 100 if ma120 and ma120 > 0 else 0,
        }
        
        # 构建可用的均线对
        pairs = []
        if ma5 is not None and ma10 is not None:
            pairs.append((ma5, ma10))
        if ma10 is not None and ma20 is not None:
            pairs.append((ma10, ma20))
        if ma20 is not None and ma60 is not None:
            pairs.append((ma20, ma60))
        if ma60 is not None and ma120 is not None:
            pairs.append((ma60, ma120))
        
        # 计算趋势分数
        trend_score = 0
        for short, long in pairs:
            if long > 0:
                diff_pct = (short - long) / long * 100
                trend_score += diff_pct
        
        bullish_count = sum(1 for s, l in pairs if s > l)
        bearish_count = sum(1 for s, l in pairs if s < l)
        
        # 完美5线顺上/顺下（需要全部5个MA）
        is_bullish = num_ma >= 5 and ma5 > ma10 > ma20 > ma60 > ma120
        is_bearish = num_ma >= 5 and ma5 < ma10 < ma20 < ma60 < ma120
        
        # 1-2个MA时：基于短均线给出弱判断
        if num_ma <= 2 and ma5 is not None:
            if current_price > ma5:
                alignment, strength, score = "bullish", "WEAK", 55
            elif current_price < ma5:
                alignment, strength, score = "bearish", "WEAK", 45
            else:
                alignment, strength, score = "neutral", "NONE", 50
        elif is_bullish:
            alignment = "bullish"
            avg_spread = (spreads["5_10"] + spreads["10_20"]) / 2
            if avg_spread > 1.0:
                strength, score = "STRONG", min(95 + avg_spread, 100)
            elif avg_spread > 0.5:
                strength, score = "MEDIUM", 70 + (avg_spread - 0.5) * 40
            else:
                strength, score = "WEAK", 50 + avg_spread * 40
        elif is_bearish:
            alignment = "bearish"
            avg_spread = abs((spreads["5_10"] + spreads["10_20"]) / 2)
            if avg_spread > 1.0:
                strength, score = "STRONG", max(5 - avg_spread, 0)
            elif avg_spread > 0.5:
                strength, score = "MEDIUM", 30 - (avg_spread - 0.5) * 40
            else:
                strength, score = "WEAK", 50 - avg_spread * 40
        elif bullish_count >= max(1, len(pairs) * 3 // 4) and trend_score > 0.3:
            # 3-4个MA时：用可用的均线对计算趋势；5个MA时同原来逻辑
            alignment = "bullish"
            strength = "WEAK"
            score = min(50 + trend_score * 3, 69.9)
        elif bearish_count >= max(1, len(pairs) * 3 // 4) and trend_score < -0.3:
            alignment = "bearish"
            strength = "WEAK"
            score = max(50 + trend_score * 3, 30.1)
        else:
            alignment, strength, score = "neutral", "NONE", 50
        
        available_mas = [v for v in [ma5, ma10, ma20, ma60, ma120] if v is not None]
        price_above_all = all(current_price > ma for ma in available_mas) if available_mas else False
        price_below_all = all(current_price < ma for ma in available_mas) if available_mas else False
        
        return {
            "alignment": alignment,
            "strength": strength,
            "price_above_all": price_above_all,
            "price_below_all": price_below_all,
            "score": round(score, 2),
            "spreads": {k: round(v, 4) for k, v in spreads.items()},
            "mas": mas,
        }

# ============ Mantle On-Chain Provider ============

class MantleProvider:
    """Production-ready Mantle data provider with fallback RPCs"""
    
    def __init__(self):
        self.rpc_urls = [
            MANTLE_RPC_URL,
            "https://mantle-rpc.publicnode.com",
            "https://mantle.drpc.org",
        ]
        self.w3 = None
        self._connected = False
        self._current_rpc_index = 0
        self._connect()
    
    def _connect(self):
        for i, url in enumerate(self.rpc_urls[self._current_rpc_index:], self._current_rpc_index):
            try:
                w3 = Web3(Web3.HTTPProvider(url, request_kwargs={"timeout": 5}))
                if w3.is_connected():
                    self.w3 = w3
                    self._connected = True
                    self._current_rpc_index = i
                    logger.info(f"Connected to Mantle RPC: {url}")
                    return
            except Exception as e:
                logger.warning(f"Failed to connect to {url}: {e}")
        
        self._connected = False
        logger.error("All Mantle RPCs failed")
    
    def _ensure_connection(self):
        if not self.w3 or not self.w3.is_connected():
            self._connect()
        return self._connected
    
    def get_gas_price(self) -> Optional[Dict]:
        if not self._ensure_connection():
            return None
        try:
            gas_price = self.w3.eth.gas_price
            return {
                "wei": gas_price,
                "gwei": round(gas_price / 1e9, 4),
                "mnt": round(gas_price / 1e18, 10),
            }
        except Exception as e:
            logger.error(f"Failed to get gas price: {e}")
            return None
    
    def get_block_info(self) -> Optional[dict]:
        if not self._ensure_connection():
            return None
        try:
            block = self.w3.eth.get_block('latest')
            return {
                "number": block.number,
                "hash": block.hash.hex(),
                "timestamp": block.timestamp,
                "timestamp_iso": datetime.fromtimestamp(block.timestamp).isoformat(),
                "gas_used": block.gasUsed,
                "gas_limit": block.gasLimit,
                "gas_utilization": round(block.gasUsed / block.gasLimit * 100, 2),
                "tx_count": len(block.transactions),
                "size": block.size,
            }
        except Exception as e:
            logger.error(f"Failed to get block info: {e}")
            return None
    
    def get_network_stats(self) -> Optional[dict]:
        if not self._ensure_connection():
            return None
        try:
            block = self.w3.eth.get_block('latest')
            gas_price = self.w3.eth.gas_price
            
            recent_blocks = []
            for i in range(min(10, block.number)):
                try:
                    b = self.w3.eth.get_block(block.number - i)
                    recent_blocks.append(b)
                except:
                    break
            
            block_times = []
            for i in range(1, len(recent_blocks)):
                dt = recent_blocks[i-1].timestamp - recent_blocks[i].timestamp
                block_times.append(dt)
            
            avg_block_time = np.mean(block_times) if block_times else 2.0
            
            return {
                "latest_block": block.number,
                "avg_block_time_sec": round(avg_block_time, 2),
                "gas_price_gwei": round(gas_price / 1e9, 4),
                "network_utilization": round(block.gasUsed / block.gasLimit * 100, 2),
                "pending_tx_count": len(block.transactions),
                "chain_id": self.w3.eth.chain_id,
            }
        except Exception as e:
            logger.error(f"Failed to get network stats: {e}")
            return None
    
    def get_token_balance(self, token_address: str, wallet_address: str) -> Optional[int]:
        """Get ERC20 token balance in wei/smallest unit."""
        if not self._ensure_connection():
            return None
        try:
            if token_address.lower() == WMNT.lower():
                # Native MNT balance
                balance = self.w3.eth.get_balance(Web3.to_checksum_address(wallet_address))
                return balance
            contract = self.w3.eth.contract(
                address=Web3.to_checksum_address(token_address),
                abi=ERC20_ABI
            )
            balance = contract.functions.balanceOf(Web3.to_checksum_address(wallet_address)).call()
            return balance
        except Exception as e:
            logger.error(f"Failed to get balance for {token_address}: {e}")
            return None
    
    def get_token_decimals(self, token_address: str) -> int:
        """Get token decimals."""
        if token_address.lower() in TOKEN_DECIMALS:
            return TOKEN_DECIMALS[token_address.lower()]
        if not self._ensure_connection():
            return 18
        try:
            contract = self.w3.eth.contract(
                address=Web3.to_checksum_address(token_address),
                abi=ERC20_ABI
            )
            return contract.functions.decimals().call()
        except Exception as e:
            logger.warning(f"Failed to get decimals for {token_address}: {e}, defaulting to 18")
            return 18
    
    def get_token_allowance(self, token_address: str, owner: str, spender: str) -> int:
        """Get token allowance."""
        if not self._ensure_connection():
            return 0
        try:
            contract = self.w3.eth.contract(
                address=Web3.to_checksum_address(token_address),
                abi=ERC20_ABI
            )
            return contract.functions.allowance(
                Web3.to_checksum_address(owner),
                Web3.to_checksum_address(spender)
            ).call()
        except Exception as e:
            logger.error(f"Failed to get allowance: {e}")
            return 0

# ============ DEX Quote Provider ============

class DEXQuoteProvider:
    """Real DEX quote provider using Mantle on-chain data"""
    
    def __init__(self):
        self.mantle = MantleProvider()
        self._quoter_abi = [
            {
                "inputs": [
                    {"internalType": "address[]", "name": "route", "type": "address[]"},
                    {"internalType": "uint128", "name": "amountIn", "type": "uint128"}
                ],
                "name": "findBestPathFromAmountIn",
                "outputs": [{
                    "components": [
                        {"internalType": "address[]", "name": "route", "type": "address[]"},
                        {"internalType": "address[]", "name": "pairs", "type": "address[]"},
                        {"internalType": "uint256[]", "name": "binSteps", "type": "uint256[]"},
                        {"internalType": "uint8[]", "name": "versions", "type": "uint8[]"},
                        {"internalType": "uint128[]", "name": "amounts", "type": "uint128[]"},
                        {"internalType": "uint128[]", "name": "virtualAmountsWithoutSlippage", "type": "uint128[]"},
                        {"internalType": "uint128[]", "name": "fees", "type": "uint128[]"}
                    ],
                    "internalType": "struct LBQuoter.Quote",
                    "name": "quote",
                    "type": "tuple"
                }],
                "stateMutability": "view",
                "type": "function"
            }
        ]
    
    def _resolve_token(self, token: str) -> str:
        token_map = {
            "MNT": WMNT, "WMNT": WMNT,
            "USDC": USDC, "USDT": USDT,
        }
        
        upper = token.upper()
        if upper in token_map:
            return token_map[upper]
        
        if token.startswith("0x") and len(token) == 42:
            return Web3.to_checksum_address(token)
        
        raise HTTPException(status_code=400, detail=f"Unknown token: {token}")
    
    def get_quote(self, token_in: str, token_out: str, amount_in: str) -> dict:
        if not self.mantle._connected:
            raise HTTPException(status_code=503, detail="Mantle RPC not connected, cannot get real quote")
        
        token_in_addr = self._resolve_token(token_in)
        token_out_addr = self._resolve_token(token_out)
        amount = int(amount_in)
        
        quoter = self.mantle.w3.eth.contract(
            address=Web3.to_checksum_address(LB_QUOTER),
            abi=self._quoter_abi
        )
        
        route = [token_in_addr, token_out_addr]
        quote = quoter.functions.findBestPathFromAmountIn(route, amount).call()
        
        amounts = quote[4]
        fees = quote[6]
        total_fee = sum(fees) if fees else 0
        
        expected_output = amounts[-1] if amounts else 0
        price_impact = self._estimate_price_impact(amount, expected_output, total_fee)
        
        slippage = 0.005
        min_output = int(expected_output * (1 - slippage))
        
        return {
            "token_in": token_in,
            "token_out": token_out,
            "token_in_address": token_in_addr,
            "token_out_address": token_out_addr,
            "amount_in": amount_in,
            "expected_output": str(expected_output),
            "minimum_output": str(min_output),
            "price_impact": round(price_impact, 4),
            "fee_amount": str(total_fee),
            "route": [token_in, token_out],
            "route_addresses": route,
            "pairs": quote[1] if len(quote) > 1 else [],
            "gas_estimate": "150000",
            "is_mock": False,
        }
    

    def _estimate_price_impact(self, amount_in: int, amount_out: int, fee: int) -> float:
        if amount_in == 0:
            return 0.0
        ideal_output = amount_in
        if ideal_output > 0:
            impact = (ideal_output - amount_out - fee) / ideal_output * 100
            return max(0, impact)
        return 0.0

# ============ Sentiment Analysis ============

class SentimentAnalyzer:
    """Production-ready market sentiment analyzer"""
    
    _analysis_semaphore = asyncio.Semaphore(8)
    
    def __init__(self):
        self.mantle = MantleProvider()
        self.ma_calc = MACalculator()
    
    async def _save_signals_async(self, signals: List[dict], symbol_meta: Dict[str, dict]):
        """异步保存信号到数据库。symbol_meta: {symbol: {price, strength, timestamp}}"""
        try:
            for s in signals:
                direction = s.get("direction")
                if not direction:
                    continue
                meta = symbol_meta.get(s.get("symbol", ""), {})
                await db_save_signal(
                    symbol=s.get("symbol", ""),
                    timeframe=s.get("timeframe", ""),
                    direction=direction,
                    confidence=s.get("confidence", "low"),
                    strength=meta.get("strength", "NONE"),
                    entry_price=meta.get("price", 0.0),
                    timestamp=meta.get("timestamp", datetime.now().isoformat()),
                    primary_pattern=s.get("primary_pattern"),
                    secondary_patterns=s.get("secondary_patterns", []),
                )
        except Exception as e:
            logger.warning(f"Failed to save signals: {e}")

    def _is_valid_wallet_address(self, wallet_address: Optional[str]) -> bool:
        """Validate Ethereum address format: 0x + 40 hex chars"""
        if not wallet_address:
            return False
        return bool(re.match(r'^0x[a-fA-F0-9]{40}$', wallet_address))

    def _filter_public_data(self, result: dict) -> dict:
        """Return only public/basic sentiment fields for unauthenticated users."""
        return {
            "sentiment_index": result.get("sentiment_index"),
            "bullish_count": result.get("bullish_count"),
            "bearish_count": result.get("bearish_count"),
            "neutral_count": result.get("neutral_count"),
            "total_analyzed": result.get("total_analyzed"),
            "market_bias": result.get("market_bias"),
            "timestamp": result.get("timestamp"),
            "timeframe": result.get("timeframe"),
            "data_freshness": result.get("data_freshness"),
            "login_required": True,
            "message": "连接钱包以查看详细分析",
        }

    async def analyze(self, timeframe: str = "1h", limit: int = 50, force_refresh: bool = False, wallet_address: Optional[str] = None, client_ip: Optional[str] = None) -> dict:
        """Analyze sentiment. ALWAYS returns FULL data. Callers are responsible for filtering."""

        if not force_refresh:
            cached = await cache.get("sentiment", timeframe, limit)
            if cached:
                logger.info("Returning cached sentiment analysis")
                return sanitize_for_json(cached)
        
        try:
            result = await asyncio.wait_for(
                self._do_analyze(timeframe, limit),
                timeout=60
            )
            return result
        except asyncio.TimeoutError:
            logger.error("Sentiment analysis timed out after 60s")
            cached = await cache.get("sentiment", timeframe, limit)
            if cached:
                return sanitize_for_json(cached)
            raise HTTPException(status_code=504, detail="Analysis timeout")
    
    async def _do_analyze(self, timeframe: str, limit: int) -> dict:
        async with BinanceClient() as client:
            symbols = await client.get_top_50_symbols()

            if not symbols:
                raise HTTPException(status_code=503, detail="Failed to fetch market data from Binance")

            results = []
            bullish_count = bearish_count = neutral_count = 0

            batch_size = 5
            quick_limit = min(20, limit)
            for i in range(0, min(len(symbols), quick_limit), batch_size):
                batch = symbols[i:i+batch_size]

                tasks = [self._analyze_symbol(client, s, timeframe) for s in batch]
                batch_results = await asyncio.gather(*tasks, return_exceptions=True)

                for result in batch_results:
                    if isinstance(result, Exception):
                        logger.error(f"Analysis error: {result}")
                        continue

                    results.append(result)

                    if result["alignment"] == "bullish":
                        bullish_count += 1
                    elif result["alignment"] == "bearish":
                        bearish_count += 1
                    else:
                        neutral_count += 1

                if i + batch_size < len(symbols):
                    await asyncio.sleep(0.3)
            
            # 快速保存前20个结果到缓存
            if results:
                await self._save_quick_result(results, symbols, timeframe, limit, bullish_count, bearish_count, neutral_count)
            
            # 后台继续分析剩余币种
            remaining = min(len(symbols), limit) - quick_limit
            if remaining > 0:
                asyncio.create_task(
                    self._analyze_remaining(client, symbols, timeframe, quick_limit, limit, results.copy(), bullish_count, bearish_count, neutral_count)
                )

            mantle_data = self._get_mantle_sentiment()

            total = len(results) if results else 1
            base_sentiment = (bullish_count / total) * 100

            # Calculate detailed scoring
            binance_score = base_sentiment
            binance_weight = 0.7
            binance_contribution = binance_score * binance_weight

            mantle_score = mantle_data.get("on_chain_score", 0) if mantle_data else 0
            mantle_weight = 0.3
            mantle_contribution = mantle_score * mantle_weight

            if mantle_data and mantle_data.get("on_chain_score") is not None:
                sentiment_index = binance_contribution + mantle_contribution
            else:
                sentiment_index = base_sentiment

            # Build analysis_params
            analysis_params = {
                "symbols_count": min(limit, len(symbols)),
                "symbols_source": "币安USDT交易对（交易量前50）",
                "timeframe": timeframe,
                "indicators": ["MA5", "MA10", "MA20", "MA60", "MA120"],
                "binance_weight": binance_weight,
                "mantle_weight": mantle_weight,
            }

            # Build calculation_steps as array for frontend compatibility
            tx_count = mantle_data.get("tx_count", 0) if mantle_data else 0
            gas_ratio = mantle_data.get("gas_ratio", 0) if mantle_data else 0
            tx_score = min(tx_count / 2, 100)
            gas_score = gas_ratio * 100

            calculation_steps = [
                {"step": "币安信号聚合", "value": round(binance_score, 2), "description": f"{bullish_count} 看涨 / {bearish_count} 看跌 / {neutral_count} 中性"},
                {"step": "币安权重贡献", "value": round(binance_contribution, 2), "description": f"权重 {binance_weight}"},
                {"step": "链上得分", "value": round(mantle_score, 2), "description": f"交易 {tx_count}, Gas比率 {round(gas_ratio, 4)}"},
                {"step": "链上权重贡献", "value": round(mantle_contribution, 2), "description": f"权重 {mantle_weight}"},
                {"step": "最终情绪指数", "value": round(min(100, max(0, sentiment_index)), 2), "description": "标准化至 0-100 区间"},
            ]

            # Enhance mantle_data with weight and network_activity
            if mantle_data:
                mantle_data["weight"] = mantle_weight
                if "network_activity" not in mantle_data:
                    mantle_data["network_activity"] = "high" if tx_score > 50 else "medium" if tx_score > 20 else "low"

            # --- NEW: Advanced sentiment analysis ---
            all_raw_signals = []
            for r in results:
                all_raw_signals.extend(r.get("raw_signals", []))

            fng_data = await self._fetch_fng()

            btc_change = None
            for s in symbols:
                if s["symbol"] == "BTCUSDT":
                    btc_change = float(s.get("priceChangePercent", 0))
                    break

            market_bias = self._calculate_market_bias(
                bullish_count, bearish_count, neutral_count,
                fng_data.get("value") if fng_data else None,
                btc_change,
            )

            signals = []
            for raw in all_raw_signals:
                if self._is_excluded_asset(raw["symbol"]):
                    continue
                confidence = self._calculate_confidence(
                    raw["direction"],
                    raw["primary_pattern"],
                    raw["secondary_patterns"],
                    raw["ma_alignment"],
                    market_bias["bias"],
                    fng_data.get("value") if fng_data else None,
                )
                signals.append({
                    "symbol": raw["symbol"],
                    "timeframe": raw["timeframe"],
                    "direction": raw["direction"],
                    "primary_pattern": raw["primary_pattern"],
                    "secondary_patterns": raw["secondary_patterns"],
                    "confidence": confidence,
                    "ma_alignment": raw["ma_alignment"],
                })

            # Build symbol metadata for signal persistence
            symbol_meta = {
                r["symbol"]: {
                    "price": r.get("price", 0.0),
                    "strength": r.get("strength", "NONE"),
                    "timestamp": datetime.now().isoformat(),
                }
                for r in results
            }
            if signals:
                asyncio.create_task(self._save_signals_async(signals, symbol_meta))

            position_report = self._generate_position_report(
                market_bias["bias"],
                fng_data.get("value") if fng_data else None,
                signals,
            )
            risk_warning = self._generate_risk_warning(
                market_bias["bias"],
                fng_data.get("value") if fng_data else None,
                len(signals),
            )

            market_breadth_str = f"{bullish_count} up / {bearish_count} down / {neutral_count} flat"
            # --- END NEW ---

            result = {
                "sentiment_index": round(min(100, max(0, sentiment_index)), 2),
                "bullish_count": bullish_count,
                "bearish_count": bearish_count,
                "neutral_count": neutral_count,
                "total_analyzed": len(results),
                "top_bullish": sorted(
                    [r for r in results if r["alignment"] == "bullish" and not self._is_excluded_asset(r.get("symbol", ""))],
                    key=lambda x: x.get("score") or 0,
                    reverse=True
                )[:5],
                "top_bearish": sorted(
                    [r for r in results if r["alignment"] == "bearish" and not self._is_excluded_asset(r.get("symbol", ""))],
                    key=lambda x: x.get("score") or 50,
                )[:5],
                "symbol_scores": sorted(
                    [
                        {
                            "symbol": r["symbol"],
                            "alignment": r["alignment"],
                            "strength": r["strength"],
                            "score": r["score"],
                            "price": r["price"],
                            "price_change_24h": r["price_change_24h"],
                            "volume": r.get("volume_24h", next((float(s["volume"]) for s in symbols if s["symbol"] == r["symbol"]), 0)),
                        }
                        for r in results
                        if r["alignment"] not in ("unknown", "error") and not self._is_excluded_asset(r.get("symbol", ""))
                    ],
                    key=lambda x: x.get("score") or 0 or 0,
                    reverse=True,
                ),
                "mantle_data": mantle_data,
                "analysis_params": analysis_params,
                "calculation_steps": calculation_steps,
                "timestamp": datetime.now().isoformat(),
                "timeframe": timeframe,
                "data_freshness": "real-time",
                # NEW fields
                "market_bias": market_bias["bias"],
                "bias_strength": market_bias["strength"],
                "fng": fng_data,
                "market_breadth": market_breadth_str,
                "btc_change_24h": round(btc_change, 2) if btc_change is not None else 0.0,
                "position_report": position_report,
                "risk_warning": risk_warning,
                "signals": signals,
            }

            # 构建 decision（最高优先级信号）
            for tf in ("1d", "4h", "1w"):
                report = position_report.get(tf, {})
                for side in ("long", "short"):
                    items = report.get(side, [])
                    if items:
                        result["decision"] = {
                            "symbol": items[0]["symbol"],
                            "timeframe": tf,
                            "direction": side,
                            "confidence": items[0].get("confidence", "medium"),
                            "reason": items[0].get("reason", ""),
                        }
                        break
                if "decision" in result:
                    break

            await cache.set("sentiment", timeframe, limit, data=result)
            return sanitize_for_json(result)
    
    async def _analyze_symbol(self, client: BinanceClient, symbol_info: dict, timeframe: str) -> dict:
        async with self._analysis_semaphore:
            return await self._analyze_symbol_inner(client, symbol_info, timeframe)
    
    async def _analyze_symbol_inner(self, client: BinanceClient, symbol_info: dict, timeframe: str) -> dict:
        symbol = symbol_info["symbol"]

        try:
            klines = await client.get_klines(symbol, timeframe, limit=200)
            # 排除最新一根未收盘的K线，用已收盘的数据进行分析
            if klines and len(klines) >= 2:
                klines = klines[:-1]

            if not klines or len(klines) < 5:
                return {
                    "symbol": symbol,
                    "alignment": "unknown",
                    "strength": "NONE",
                    "score": 50,
                    "price": symbol_info["lastPrice"],
                    "price_change_24h": symbol_info["priceChangePercent"],
                    "error": "Insufficient data",
                    "raw_signals": [],
                }

            prices = [k["close"] for k in klines]
            volumes = [k["volume"] for k in klines]

            mas = self.ma_calc.calculate(prices)
            alignment = self.ma_calc.analyze_alignment(mas, prices[-1])

            vol_ma5 = float(np.mean(volumes[-5:]))
            vol_ma20 = float(np.mean(volumes[-20:]))
            volume_trend = "increasing" if vol_ma5 > vol_ma20 * 1.05 else "decreasing" if vol_ma5 < vol_ma20 * 0.95 else "stable"

            price_range = {
                "high_24h": float(symbol_info.get("highPrice", 0)),
                "low_24h": float(symbol_info.get("lowPrice", 0)),
                "range": round((symbol_info.get("highPrice", 0) - symbol_info.get("lowPrice", 0)) / symbol_info.get("lowPrice", 1) * 100, 2) if symbol_info.get("lowPrice", 0) > 0 else 0,
            }

            # Multi-timeframe raw signal detection
            raw_signals = []
            # 实时分析时：外部已经排除了未收盘K线，内部不要再切
            main_signal = self._build_raw_signal(symbol, klines, timeframe, skip_last_candle=False)
            if main_signal:
                raw_signals.append(main_signal)
            # 其他时间框架信号
            extra_timeframes = [tf for tf in ["1d", "4h", "1w"] if tf != timeframe]
            for tf in extra_timeframes:
                try:
                    tf_klines = await asyncio.wait_for(
                        client.get_klines(symbol, tf, limit=200),
                        timeout=5
                    )
                    # 其他时间框架的K线从外面获取，需要排除最后一根未收盘K线
                    signal = self._build_raw_signal(symbol, tf_klines, tf, skip_last_candle=True)
                    if signal:
                        raw_signals.append(signal)
                except Exception as e:
                    logger.error(f"Failed to analyze {symbol} {tf}: {e}")

            return sanitize_for_json({
                "symbol": symbol,
                "price": round(float(prices[-1]), 4),
                "price_change_24h": float(symbol_info["priceChangePercent"]),
                "alignment": alignment["alignment"],
                "strength": alignment["strength"],
                "score": float(alignment["score"]),
                "price_above_all": bool(alignment.get("price_above_all", False)),
                "price_below_all": bool(alignment.get("price_below_all", False)),
                "mas": alignment.get("mas", {}),
                "spreads": alignment.get("spreads", {}),
                "volume_trend": volume_trend,
                "volume_24h": float(symbol_info["volume"]),
                "price_range": price_range,
                "raw_signals": raw_signals,
            })
        except Exception as e:
            logger.error(f"Failed to analyze {symbol}: {e}")
            return {
                "symbol": symbol,
                "alignment": "error",
                "strength": "NONE",
                "score": 50,
                "price": float(symbol_info.get("lastPrice", 0)),
                "price_change_24h": float(symbol_info.get("priceChangePercent", 0)),
                "error": str(e),
                "raw_signals": [],
            }
    
    def _build_raw_signal(self, symbol: str, klines: list, tf: str, skip_last_candle: bool = True) -> Optional[dict]:
        if not klines or len(klines) < 5:
            return None

        # 参数控制是否排除最后一根K线
        if skip_last_candle:
            klines = klines[:-1]
            if len(klines) < 5:
                return None

        prices = [k["close"] for k in klines]
        mas = self.ma_calc.calculate(prices)
        alignment = self.ma_calc.analyze_alignment(mas, prices[-1])
        ma_alignment = alignment["alignment"]

        patterns = []
        if self._detect_bullish_engulfing(klines):
            patterns.append("阳包阴")
        if self._detect_bearish_engulfing(klines):
            patterns.append("阴包阳")
        if self._detect_morning_star(klines):
            patterns.append("早晨之星")
        if self._detect_bullish_tri_star(klines):
            patterns.append("早晨十字星")
        if self._detect_bullish_harami(klines):
            patterns.append("内包孕线多")
        if self._detect_bearish_harami(klines):
            patterns.append("内包孕线空")

        # 排除稳定币/法币/黄金锚定币，从源头不生成任何信号
        if self._is_excluded_asset(symbol):
            return None

        direction = None
        primary_pattern = None

        has_all_5 = len(mas) >= 5 and all(mas.get(k) is not None for k in ["MA5", "MA10", "MA20", "MA60", "MA120"])
        if has_all_5 and ma_alignment == "bullish" and alignment.get("price_above_all", False):
            direction = "long"
            primary_pattern = "5线顺上"
        elif has_all_5 and ma_alignment == "bearish" and alignment.get("price_below_all", False):
            direction = "short"
            primary_pattern = "5线顺下"
        elif patterns:
            bullish_patterns = {"阳包阴", "早晨之星", "早晨十字星", "内包孕线多"}
            bearish_patterns = {"阴包阳", "内包孕线空"}
            bullish_found = [p for p in patterns if p in bullish_patterns]
            bearish_found = [p for p in patterns if p in bearish_patterns]
            if bullish_found and not bearish_found:
                direction = "long"
                primary_pattern = bullish_found[0]
            elif bearish_found and not bullish_found:
                direction = "short"
                primary_pattern = bearish_found[0]

        if direction is None:
            return None

        # 计算与形态/方向一致的均线排列描述，避免"混合"与做多/做空矛盾
        current_price = prices[-1]
        ma5 = mas.get("MA5")
        if primary_pattern in ("5线顺上",):
            ma_alignment = "bullish_all"
        elif primary_pattern in ("5线顺下",):
            ma_alignment = "bearish_all"
        elif direction == "long":
            # 做多形态：价格是否在均线上方支撑
            if alignment.get("price_above_all"):
                ma_alignment = "bullish_all"
            elif ma5 is not None and current_price > ma5:
                ma_alignment = "bullish_all"
            else:
                ma_alignment = "mixed"
        elif direction == "short":
            # 做空形态：价格是否在均线下方压制
            if alignment.get("price_below_all"):
                ma_alignment = "bearish_all"
            elif ma5 is not None and current_price < ma5:
                ma_alignment = "bearish_all"
            else:
                ma_alignment = "mixed"
        else:
            ma_alignment = "mixed"

        return {
            "symbol": symbol,
            "timeframe": tf,
            "direction": direction,
            "primary_pattern": primary_pattern,
            "secondary_patterns": [p for p in patterns if p != primary_pattern],
            "ma_alignment": ma_alignment,
        }
    
    def _get_mantle_sentiment(self) -> Optional[dict]:
        try:
            block_info = self.mantle.get_block_info()
            gas_price = self.mantle.get_gas_price()

            if not block_info:
                return None

            tx_count = int(block_info.get("tx_count", 0))
            gas_used = int(block_info.get("gas_used", 0))
            gas_limit = int(block_info.get("gas_limit", 1))
            gas_ratio = gas_used / gas_limit if gas_limit > 0 else 0

            tx_score = min(tx_count / 2, 100)
            gas_score = gas_ratio * 100
            on_chain_score = (tx_score + gas_score) / 2

            return sanitize_for_json({
                "block_number": int(block_info["number"]),
                "tx_count": tx_count,
                "gas_ratio": round(gas_ratio, 4),
                "gas_price_gwei": float(gas_price.get("gwei")) if gas_price else None,
                "on_chain_score": round(on_chain_score, 2),
                "network_activity": "high" if tx_score > 50 else "medium" if tx_score > 20 else "low",
            })
        except Exception as e:
            logger.error(f"Failed to get Mantle sentiment: {e}")
            return None

    # ------------------------------------------------------------------
    # 新增：情绪分析增强方法 (inspired by crypto-analyst)
    # ------------------------------------------------------------------

    async def _fetch_fng(self) -> Optional[dict]:
        """Fetch Fear & Greed Index from alternative.me"""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    "https://api.alternative.me/fng/?limit=1",
                    timeout=aiohttp.ClientTimeout(total=3)
                ) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        item = data.get("data", [{}])[0]
                        value = int(item.get("value", 50))
                        classification = item.get("value_classification", "Neutral")
                        return {
                            "value": value,
                            "classification": classification,
                            "timestamp": datetime.now().isoformat(),
                        }
        except asyncio.TimeoutError:
            logger.warning("FNG API timeout, skipping")
        except Exception as e:
            logger.warning(f"Failed to fetch FNG: {e}")
        return None

    def _detect_bullish_engulfing(self, klines: list) -> bool:
        """检测看涨吞没：当前阳线完全包住前一根阴线"""
        if len(klines) < 2:
            return False
        prev, curr = klines[-2], klines[-1]
        prev_bearish = prev["close"] < prev["open"]
        curr_bullish = curr["close"] > curr["open"]
        if not (prev_bearish and curr_bullish):
            return False
        return curr["open"] <= prev["close"] and curr["close"] >= prev["open"]

    def _detect_bearish_engulfing(self, klines: list) -> bool:
        """检测看跌吞没：当前阴线完全包住前一根阳线"""
        if len(klines) < 2:
            return False
        prev, curr = klines[-2], klines[-1]
        prev_bullish = prev["close"] > prev["open"]
        curr_bearish = curr["close"] < curr["open"]
        if not (prev_bullish and curr_bearish):
            return False
        return curr["open"] >= prev["close"] and curr["close"] <= prev["open"]

    def _detect_morning_star(self, klines: list) -> bool:
        """检测启明星：3根K线， bearish → small body → bullish，且第三根close超过第一根open的50%"""
        if len(klines) < 3:
            return False
        k1, k2, k3 = klines[-3], klines[-2], klines[-1]
        k1_bearish = k1["close"] < k1["open"]
        k3_bullish = k3["close"] > k3["open"]
        if not (k1_bearish and k3_bullish):
            return False
        # k2 是小实体（doji-like）
        k2_body = abs(k2["close"] - k2["open"])
        k2_range = k2["high"] - k2["low"]
        if k2_range > 0 and k2_body / k2_range > 0.5:
            return False
        # k3 收盘超过 k1 实体中点
        k1_mid = (k1["open"] + k1["close"]) / 2
        return k3["close"] > k1_mid

    def _detect_bullish_tri_star(self, klines: list) -> bool:
        """检测多方炮：3根K线， bullish → bearish → bullish，且第三根close高于第一根high"""
        if len(klines) < 3:
            return False
        k1, k2, k3 = klines[-3], klines[-2], klines[-1]
        k1_bullish = k1["close"] > k1["open"]
        k2_bearish = k2["close"] < k2["open"]
        k3_bullish = k3["close"] > k3["open"]
        if not (k1_bullish and k2_bearish and k3_bullish):
            return False
        return k3["close"] > k1["high"]

    def _detect_bullish_harami(self, klines: list) -> bool:
        """检测看涨内包孕线：前一根大阴线，当前小阳线实体完全在前一根实体内"""
        if len(klines) < 2:
            return False
        prev, curr = klines[-2], klines[-1]
        prev_bearish = prev["close"] < prev["open"]
        curr_bullish = curr["close"] > curr["open"]
        if not (prev_bearish and curr_bullish):
            return False
        prev_top = max(prev["open"], prev["close"])
        prev_bottom = min(prev["open"], prev["close"])
        curr_top = max(curr["open"], curr["close"])
        curr_bottom = min(curr["open"], curr["close"])
        # 当前实体在前一根实体内，且当前实体较小（< 前一根50%）
        inside = curr_bottom >= prev_bottom and curr_top <= prev_top
        if not inside:
            return False
        prev_body = prev_top - prev_bottom
        curr_body = curr_top - curr_bottom
        return curr_body < prev_body * 0.5

    def _detect_bearish_harami(self, klines: list) -> bool:
        """检测看跌内包孕线：前一根大阳线，当前小阴线实体完全在前一根实体内"""
        if len(klines) < 2:
            return False
        prev, curr = klines[-2], klines[-1]
        prev_bullish = prev["close"] > prev["open"]
        curr_bearish = curr["close"] < curr["open"]
        if not (prev_bullish and curr_bearish):
            return False
        prev_top = max(prev["open"], prev["close"])
        prev_bottom = min(prev["open"], prev["close"])
        curr_top = max(curr["open"], curr["close"])
        curr_bottom = min(curr["open"], curr["close"])
        inside = curr_bottom >= prev_bottom and curr_top <= prev_top
        if not inside:
            return False
        prev_body = prev_top - prev_bottom
        curr_body = curr_top - curr_bottom
        return curr_body < prev_body * 0.5

    def _detect_patterns(self, klines: list) -> dict:
        """检测所有K线形态，返回形态列表和主形态"""
        patterns = []
        primary = ""
        if self._detect_bullish_engulfing(klines):
            patterns.append("阳包阴")
            primary = primary or "阳包阴"
        if self._detect_bearish_engulfing(klines):
            patterns.append("阴包阳")
            primary = primary or "阴包阳"
        if self._detect_morning_star(klines):
            patterns.append("启明星")
            primary = primary or "启明星"
        if self._detect_bullish_tri_star(klines):
            patterns.append("多方炮")
            primary = primary or "多方炮"
        if self._detect_bullish_harami(klines):
            patterns.append("内包孕线多")
            primary = primary or "内包孕线多"
        if self._detect_bearish_harami(klines):
            patterns.append("内包孕线空")
            primary = primary or "内包孕线空"
        return {"primary": primary, "all": patterns}

    def _calculate_market_bias(
        self,
        bullish_count: int,
        bearish_count: int,
        neutral_count: int,
        fng_value: int,
        btc_change: float,
    ) -> dict:
        """计算市场氛围：bullish / bearish / neutral + strength"""
        total = bullish_count + bearish_count + neutral_count
        if total == 0:
            return {"bias": "neutral", "strength": "weak", "breadth": "0 up / 0 down / 0 flat"}

        breadth_score = (bullish_count - bearish_count) / total * 100
        fng_score = ((fng_value or 50) - 50) * 2  # normalize to -100~100, default 50 (neutral)
        btc_score = btc_change * 10  # normalize roughly

        total_score = breadth_score * 0.4 + fng_score * 0.3 + btc_score * 0.3

        if total_score > 30:
            bias = "bullish"
            strength = "strong" if total_score > 60 else "moderate"
        elif total_score < -30:
            bias = "bearish"
            strength = "strong" if total_score < -60 else "moderate"
        else:
            bias = "neutral"
            strength = "weak"

        return {
            "bias": bias,
            "strength": strength,
            "breadth": f"{bullish_count} up / {bearish_count} down / {neutral_count} flat",
        }

    def _downgrade_confidence(self, conf: str) -> str:
        order = {"high": "medium", "medium": "low", "low": "low"}
        return order.get(conf, "low")

    def _upgrade_confidence(self, conf: str) -> str:
        order = {"low": "medium", "medium": "high", "high": "high"}
        return order.get(conf, "high")

    def _calculate_confidence(
        self,
        direction: str,
        primary_pattern: str,
        secondary_patterns: list,
        ma_alignment: str,
        market_bias: str,
        fng_value: int,
    ) -> str:
        """计算信号信心度：high / medium / low"""
        # 基础信心度
        if primary_pattern in ("5线顺上", "5线顺下"):
            conf = "high"
        elif primary_pattern in ("阳包阴", "阴包阳", "启明星", "多方炮"):
            conf = "medium"
        else:
            conf = "low"

        # 与市场氛围矛盾时降级
        if market_bias == "bullish" and direction == "short":
            conf = self._downgrade_confidence(conf)
        elif market_bias == "bearish" and direction == "long":
            conf = self._downgrade_confidence(conf)

        # FNG 极端调整
        if fng_value < 20:
            if direction == "long":
                conf = self._upgrade_confidence(conf)
            elif direction == "short":
                conf = self._downgrade_confidence(conf)
        elif fng_value > 80:
            if direction == "short":
                conf = self._upgrade_confidence(conf)
            elif direction == "long":
                conf = self._downgrade_confidence(conf)

        return conf

    @staticmethod
    def _is_excluded_asset(symbol: str) -> bool:
        """排除稳定币、法币锚定币、黄金锚定币等非加密资产"""
        # 常见 quote suffix
        for suffix in ("USDT", "USDC", "BUSD", "BTC", "ETH", "BNB"):
            if symbol.endswith(suffix):
                base = symbol[:-len(suffix)]
                break
        else:
            base = symbol

        excluded = {
            # 美元稳定币
            "USDC", "BUSD", "DAI", "TUSD", "FDUSD", "USDD", "PYUSD", "GUSD",
            "USD1", "XUSD", "USDS", "USDE", "AEUR", "EURC", "SUSD", "LUSD",
            "FRAX", "USDP", "USTC", "USDX", "EURI",
            # 法币锚定
            "EUR", "GBP", "TRY", "AUD", "CHF", "CAD", "JPY", "CZK", "BRL",
            "MXN", "ZAR", "SGD", "PLN", "SEK", "NOK", "HUF", "RON", "DKK",
            "NZD", "HKD", "PHP", "IDR", "VND", "RUB", "UAH", "ARS", "COP",
            "PEN", "CLP", "MYR", "KWD", "BHD", "OMR", "SAR", "AED", "QAR",
            "JOD", "TWD", "THB", "INR", "KRW",
            # 黄金/贵金属锚定
            "XAUT", "PAXG",
        }
        return base in excluded

    def _generate_position_report(
        self,
        market_bias: str,
        fng_value: int,
        signals: list,
    ) -> dict:
        """生成持仓建议报告，按时间级别分组。保留 high 和 medium 确定性信号，排除稳定币。"""
        report = {}
        for tf in ("1d", "4h", "1w"):
            tf_signals = [s for s in signals if s.get("timeframe") == tf]
            # 应用信心度微调
            adjusted = []
            for s in tf_signals:
                conf = self._calculate_confidence(
                    s["direction"],
                    s["primary_pattern"],
                    s.get("secondary_patterns", []),
                    s["ma_alignment"],
                    market_bias,
                    fng_value,
                )
                adjusted.append({**s, "confidence": conf})

            # 排序：高信心 > 形态优先级 > 币种名
            conf_order = {"high": 0, "medium": 1, "low": 2}
            prio = {"5线顺上": 1, "5线顺下": 1, "阳包阴": 2, "阴包阳": 2, "启明星": 2, "多方炮": 2, "内包孕线多": 2, "内包孕线空": 2}
            adjusted.sort(key=lambda s: (
                conf_order.get(s["confidence"], 99),
                prio.get(s["primary_pattern"], 99),
                s["symbol"],
            ))

            # 保留 high 和 medium 可信度信号，不过滤数量
            longs = [s for s in adjusted if s["direction"] == "long" and s["confidence"] in ("high", "medium")]
            shorts = [s for s in adjusted if s["direction"] == "short" and s["confidence"] in ("high", "medium")]

            report[tf] = {
                "long": [
                    {
                        "symbol": s["symbol"].replace("USDT", ""),
                        "reason": s["primary_pattern"] + ("+" + "+".join(s.get("secondary_patterns", [])) if s.get("secondary_patterns") else ""),
                        "confidence": s["confidence"],
                        "confidence_label": "高" if s["confidence"] == "high" else "中" if s["confidence"] == "medium" else "低",
                    }
                    for s in longs
                ],
                "short": [
                    {
                        "symbol": s["symbol"].replace("USDT", ""),
                        "reason": s["primary_pattern"] + ("+" + "+".join(s.get("secondary_patterns", [])) if s.get("secondary_patterns") else ""),
                        "confidence": s["confidence"],
                        "confidence_label": "高" if s["confidence"] == "high" else "中" if s["confidence"] == "medium" else "低",
                    }
                    for s in shorts
                ],
                "watch": "其余币种无明确信号",
            }
        return report

    def _generate_risk_warning(
        self,
        market_bias: str,
        fng_value: int,
        total_signals: int,
    ) -> str:
        """生成风险提示"""
        warnings = []
        if total_signals < 3:
            warnings.append("明确信号较少，建议控制仓位或观望。")
        if fng_value > 75:
            warnings.append("恐惧贪婪指数处于贪婪区间，注意追高风险。")
        elif fng_value < 25:
            warnings.append("恐惧贪婪指数处于恐惧区间，可能存在超跌反弹机会。")
        if market_bias == "neutral":
            warnings.append("市场整体方向不明，建议减少操作频率。")
        if not warnings:
            warnings.append("市场研判仅供参考，不构成投资建议。")
        return " ".join(warnings)

    async def _save_quick_result(self, results, symbols, timeframe, limit, bullish_count, bearish_count, neutral_count):
        """快速保存前20个币种的分析结果到缓存"""
        try:
            total = len(results) if results else 1
            base_sentiment = (bullish_count / total) * 100
            
            mantle_data = self._get_mantle_sentiment()
            
            binance_weight = 0.7
            mantle_weight = 0.3
            binance_contribution = base_sentiment * binance_weight
            mantle_score = mantle_data.get("on_chain_score", 0) if mantle_data else 0
            mantle_contribution = mantle_score * mantle_weight
            
            if mantle_data and mantle_data.get("on_chain_score") is not None:
                sentiment_index = binance_contribution + mantle_contribution
            else:
                sentiment_index = base_sentiment
            
            # Generate preliminary signals and position report from the first 20 symbols
            all_raw_signals = []
            for r in results:
                all_raw_signals.extend(r.get("raw_signals", []))
            
            market_bias = self._calculate_market_bias(
                bullish_count, bearish_count, neutral_count,
                None,
                None,
            )
            
            signals = []
            for raw in all_raw_signals:
                if self._is_excluded_asset(raw["symbol"]):
                    continue
                confidence = self._calculate_confidence(
                    raw["direction"],
                    raw["primary_pattern"],
                    raw["secondary_patterns"],
                    raw["ma_alignment"],
                    market_bias["bias"],
                    None,
                )
                signals.append({
                    "symbol": raw["symbol"],
                    "timeframe": raw["timeframe"],
                    "direction": raw["direction"],
                    "primary_pattern": raw["primary_pattern"],
                    "secondary_patterns": raw["secondary_patterns"],
                    "confidence": confidence,
                    "ma_alignment": raw["ma_alignment"],
                })
            
            position_report = self._generate_position_report(
                market_bias["bias"],
                None,
                signals,
            )
            
            quick_result = {
                "sentiment_index": round(min(100, max(0, sentiment_index)), 2),
                "bullish_count": bullish_count,
                "bearish_count": bearish_count,
                "neutral_count": neutral_count,
                "total_analyzed": len(results),
                "top_bullish": sorted(
                    [r for r in results if r["alignment"] == "bullish" and not self._is_excluded_asset(r.get("symbol", ""))],
                    key=lambda x: x.get("score") or 0,
                    reverse=True
                )[:5],
                "top_bearish": sorted(
                    [r for r in results if r["alignment"] == "bearish" and not self._is_excluded_asset(r.get("symbol", ""))],
                    key=lambda x: x.get("score") or 50,
                )[:5],
                "symbol_scores": sorted(
                    [
                        {
                            "symbol": r["symbol"],
                            "alignment": r["alignment"],
                            "strength": r["strength"],
                            "score": r["score"],
                            "price": r["price"],
                            "price_change_24h": r["price_change_24h"],
                            "volume": r.get("volume_24h", next((float(s["volume"]) for s in symbols if s["symbol"] == r["symbol"]), 0)),
                        }
                        for r in results
                        if r["alignment"] not in ("unknown", "error") and not self._is_excluded_asset(r.get("symbol", ""))
                    ],
                    key=lambda x: x.get("score") or 0 or 0,
                    reverse=True,
                ),
                "mantle_data": mantle_data,
                "analysis_params": {
                    "symbols_count": min(limit, len(symbols)),
                    "symbols_source": "币安USDT交易对（交易量前50）",
                    "timeframe": timeframe,
                    "indicators": ["MA5", "MA10", "MA20", "MA60", "MA120"],
                    "binance_weight": binance_weight,
                    "mantle_weight": mantle_weight,
                },
                "timestamp": datetime.now().isoformat(),
                "timeframe": timeframe,
                "data_freshness": "partial (quick result)",
                "market_bias": market_bias["bias"],
                "bias_strength": market_bias["strength"],
                "fng": None,
                "market_breadth": f"{bullish_count} up / {bearish_count} down / {neutral_count} flat",
                "btc_change_24h": 0.0,
                "position_report": position_report,
                "risk_warning": "快速结果，完整分析进行中...",
                "signals": signals,
            }
            await cache.set("sentiment", timeframe, limit, data=quick_result)
            logger.info(f"Saved quick sentiment result with {len(results)} symbols")
        except Exception as e:
            logger.error(f"Failed to save quick result: {e}")

    async def _analyze_remaining(self, _client, symbols, timeframe, start_idx, limit, initial_results, initial_bullish, initial_bearish, initial_neutral):
        """后台分析剩余币种并更新缓存"""
        try:
            results = list(initial_results)
            bullish_count = initial_bullish
            bearish_count = initial_bearish
            neutral_count = initial_neutral
            
            async with BinanceClient() as client:
                batch_size = 5
                for i in range(start_idx, min(len(symbols), limit), batch_size):
                    batch = symbols[i:i+batch_size]
                    tasks = [self._analyze_symbol(client, s, timeframe) for s in batch]
                    batch_results = await asyncio.gather(*tasks, return_exceptions=True)
                    
                    for result in batch_results:
                        if isinstance(result, Exception):
                            logger.error(f"Background analysis error: {result}")
                            continue
                        results.append(result)
                        if result["alignment"] == "bullish":
                            bullish_count += 1
                        elif result["alignment"] == "bearish":
                            bearish_count += 1
                        else:
                            neutral_count += 1
                    
                    if i + batch_size < len(symbols):
                        await asyncio.sleep(0.3)
            
            # 更新完整缓存
            total = len(results) if results else 1
            base_sentiment = (bullish_count / total) * 100
            
            mantle_data = self._get_mantle_sentiment()
            
            binance_weight = 0.7
            mantle_weight = 0.3
            binance_contribution = base_sentiment * binance_weight
            mantle_score = mantle_data.get("on_chain_score", 0) if mantle_data else 0
            mantle_contribution = mantle_score * mantle_weight
            
            if mantle_data and mantle_data.get("on_chain_score") is not None:
                sentiment_index = binance_contribution + mantle_contribution
            else:
                sentiment_index = base_sentiment
            
            all_raw_signals = []
            for r in results:
                all_raw_signals.extend(r.get("raw_signals", []))
            
            fng_data = await self._fetch_fng()
            
            btc_change = None
            for s in symbols:
                if s["symbol"] == "BTCUSDT":
                    btc_change = float(s.get("priceChangePercent", 0))
                    break
            
            market_bias = self._calculate_market_bias(
                bullish_count, bearish_count, neutral_count,
                fng_data.get("value") if fng_data else None,
                btc_change,
            )
            
            signals = []
            for raw in all_raw_signals:
                if self._is_excluded_asset(raw["symbol"]):
                    continue
                confidence = self._calculate_confidence(
                    raw["direction"],
                    raw["primary_pattern"],
                    raw["secondary_patterns"],
                    raw["ma_alignment"],
                    market_bias["bias"],
                    fng_data.get("value") if fng_data else None,
                )
                signals.append({
                    "symbol": raw["symbol"],
                    "timeframe": raw["timeframe"],
                    "direction": raw["direction"],
                    "primary_pattern": raw["primary_pattern"],
                    "secondary_patterns": raw["secondary_patterns"],
                    "confidence": confidence,
                    "ma_alignment": raw["ma_alignment"],
                })

            # Build symbol metadata for signal persistence
            symbol_meta = {
                r["symbol"]: {
                    "price": r.get("price", 0.0),
                    "strength": r.get("strength", "NONE"),
                    "timestamp": datetime.now().isoformat(),
                }
                for r in results
            }
            if signals:
                asyncio.create_task(self._save_signals_async(signals, symbol_meta))
            
            position_report = self._generate_position_report(
                market_bias["bias"],
                fng_data.get("value") if fng_data else None,
                signals,
            )
            risk_warning = self._generate_risk_warning(
                market_bias["bias"],
                fng_data.get("value") if fng_data else None,
                len(signals),
            )
            
            market_breadth_str = f"{bullish_count} up / {bearish_count} down / {neutral_count} flat"
            
            full_result = {
                "sentiment_index": round(min(100, max(0, sentiment_index)), 2),
                "bullish_count": bullish_count,
                "bearish_count": bearish_count,
                "neutral_count": neutral_count,
                "total_analyzed": len(results),
                "top_bullish": sorted(
                    [r for r in results if r["alignment"] == "bullish" and not self._is_excluded_asset(r.get("symbol", ""))],
                    key=lambda x: x.get("score") or 0,
                    reverse=True
                )[:5],
                "top_bearish": sorted(
                    [r for r in results if r["alignment"] == "bearish" and not self._is_excluded_asset(r.get("symbol", ""))],
                    key=lambda x: x.get("score") or 50,
                )[:5],
                "mantle_data": mantle_data,
                "analysis_params": {
                    "symbols_count": min(limit, len(symbols)),
                    "symbols_source": "币安USDT交易对（交易量前50）",
                    "timeframe": timeframe,
                    "indicators": ["MA5", "MA10", "MA20", "MA60", "MA120"],
                    "binance_weight": binance_weight,
                    "mantle_weight": mantle_weight,
                },
                "timestamp": datetime.now().isoformat(),
                "timeframe": timeframe,
                "data_freshness": "real-time",
                "market_bias": market_bias["bias"],
                "bias_strength": market_bias["strength"],
                "fng": fng_data,
                "market_breadth": market_breadth_str,
                "btc_change_24h": round(btc_change, 2) if btc_change is not None else 0.0,
                "symbol_scores": sorted(
                    [
                        {
                            "symbol": r["symbol"],
                            "alignment": r["alignment"],
                            "strength": r["strength"],
                            "score": r["score"],
                            "price": r["price"],
                            "price_change_24h": r["price_change_24h"],
                            "volume": r.get("volume_24h", 0),
                        }
                        for r in results
                        if r["alignment"] not in ("unknown", "error") and not self._is_excluded_asset(r.get("symbol", ""))
                    ],
                    key=lambda x: x.get("score") or 0 or 0,
                    reverse=True,
                ),
                "position_report": position_report,
                "risk_warning": risk_warning,
                "signals": signals,
            }
            await cache.set("sentiment", timeframe, limit, data=full_result)
            try:
                await db_set("sentiment", full_result, ttl_seconds=900)
                logger.info("[Background] Full sentiment persisted to DB")
            except Exception as db_err:
                logger.warning(f"Failed to persist sentiment to DB: {db_err}")
            logger.info(f"Background analysis complete: {len(results)} symbols analyzed")
        except Exception as e:
            logger.error(f"Background analysis failed: {e}")

# ============ Global Instances ============

analyzer = SentimentAnalyzer()
router = DEXQuoteProvider()
onchain_collector = OnChainDataCollector()
onchain_scheduler = DataRefreshScheduler(onchain_collector, interval=900)
llama_client = DeFiLlamaClient()

# Data aggregator (initialized in lifespan)
data_aggregator: DataAggregator = None  # type: ignore
aggregator_scheduler: DataAggregatorScheduler = None  # type: ignore

# Unified DB refresh scheduler
_unified_refresh_task: asyncio.Task = None  # type: ignore
_unified_refresh_running = False

# Whale monitor — try/except graceful init
try:
    whale_monitor = WhaleMonitor()
except Exception as e:
    logger.warning(f"WhaleMonitor init failed: {e}")
    whale_monitor = None


