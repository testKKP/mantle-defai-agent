"""
Core utilities, configuration, Pydantic models, cache, and rate limiting.
This module has NO side-effects (no global service initialization).
"""

from fastapi import HTTPException, Request
from pydantic import BaseModel, Field, field_validator
from typing import List, Dict, Optional, Any
from datetime import datetime, timedelta
from enum import Enum
import asyncio
import numpy as np
from dataclasses import dataclass
from loguru import logger
import json
import os
import hashlib
import time
from functools import wraps


# ============ Numpy JSON Serialization Helper ============

def sanitize_for_json(obj: Any) -> Any:
    """Recursively convert numpy types and other non-JSON-serializable objects to native Python types."""
    if isinstance(obj, dict):
        return {k: sanitize_for_json(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [sanitize_for_json(v) for v in obj]
    elif isinstance(obj, (np.bool_,)):
        return bool(obj)
    elif isinstance(obj, (np.integer,)):
        return int(obj)
    elif isinstance(obj, (np.floating,)):
        return float(obj)
    elif isinstance(obj, np.ndarray):
        return obj.tolist()
    elif isinstance(obj, bytes):
        return obj.hex() if hasattr(obj, 'hex') else obj.decode('utf-8', errors='replace')
    return obj

# ============ Configuration ============
BINANCE_API_URL = os.getenv("BINANCE_API_URL", "https://api.binance.com")
DATA_API_URL = os.getenv("DATA_API_URL", "https://data-api.binance.vision")
MANTLE_RPC_URL = os.getenv("MANTLE_RPC_URL", "https://rpc.mantle.xyz")
MANTLE_CHAIN_ID = int(os.getenv("MANTLE_CHAIN_ID", "5000"))

# Mantle Contract Addresses (Mainnet)
WMNT = "0x78c1b0C915c4FAA5FffA6CAbf0219DA63d7f4cb8"
USDC = "0x09Bc4E0D864854c6aFB6eB9A9cdF58aC190D0dF9"
USDT = "0x201EBa5CC46D216Ce6DC03F6a759e8E766e956aE"
LB_QUOTER = "0x501b8AFd35df20f531fF45F6f695793AC3316c85"
LB_ROUTER = "0x013e138EF6008ae5FDFDE29700e3f2Bc61d21E3a"
LB_FACTORY = "0xAFb979913B438952745F9e6E7d8b3E4aC04F7382"

# Token decimals
TOKEN_DECIMALS = {
    WMNT.lower(): 18,
    USDC.lower(): 6,
    USDT.lower(): 6,
}

# Cache settings
CACHE_TTL = int(os.getenv("CACHE_TTL", "900"))
MAX_CACHE_SIZE = 1000

# Rate limiting
RATE_LIMIT_REQUESTS = int(os.getenv("RATE_LIMIT_REQUESTS", "100"))
RATE_LIMIT_WINDOW = int(os.getenv("RATE_LIMIT_WINDOW", "60"))

# IP Whitelist — comma-separated list from env, fallback to old default
# DEBUG=true 时自动加入 localhost，方便本地开发测试
_WHITELIST_ENV = os.getenv("IP_WHITELIST", "114.246.236.230,127.0.0.1,::1")
WHITELIST = [ip.strip() for ip in _WHITELIST_ENV.split(",") if ip.strip()]
# 始终允许本地访问
for _local_ip in ("127.0.0.1", "localhost", "::1"):
    if _local_ip not in WHITELIST:
        WHITELIST.append(_local_ip)
# DEBUG 模式下跳过白名单检查（在 routes.py 的 require_whitelist 中生效）
DEBUG_MODE = os.getenv("DEBUG", "false").lower() == "true"

def get_client_ip(request: Request) -> str:
    """Extract real client IP from request, considering X-Forwarded-For header."""
    x_forwarded_for = request.headers.get("X-Forwarded-For")
    if x_forwarded_for:
        return x_forwarded_for.split(",")[0].strip()
    return request.client.host if request.client else "unknown"

# ============ Models ============

class Timeframe(str, Enum):
    HOUR_1 = "1h"
    HOUR_4 = "4h"
    DAY_1 = "1d"

class SentimentRequest(BaseModel):
    timeframe: Timeframe = Field(default=Timeframe.HOUR_1, description="K线周期")
    limit: int = Field(default=50, ge=10, le=100, description="分析币种数量")
    force_refresh: bool = Field(default=False, description="强制刷新缓存")
    wallet_address: Optional[str] = Field(default=None, description="Wallet address for authenticated access")

class SwapQuoteRequest(BaseModel):
    token_in: str = Field(..., description="输入代币地址或符号")
    token_out: str = Field(..., description="输出代币地址或符号")
    amount_in: str = Field(..., description="输入数量 (wei/最小单位)")
    slippage: float = Field(default=0.005, ge=0.0001, le=0.1, description="最大滑点")

    @field_validator('amount_in')
    @classmethod
    def validate_amount(cls, v: str) -> str:
        try:
            val = int(v)
            if val <= 0:
                raise ValueError('amount_in must be greater than 0')
        except (ValueError, TypeError):
            raise ValueError('amount_in must be a valid positive integer string (wei)')
        return v

class SwapBuildTxRequest(BaseModel):
    token_in: str = Field(..., description="输入代币地址或符号")
    token_out: str = Field(..., description="输出代币地址或符号")
    amount_in: str = Field(..., description="输入数量 (wei/最小单位)")
    min_amount_out: str = Field(..., description="最小输出数量 (wei/最小单位)")
    recipient: str = Field(..., description="接收地址")
    deadline: int = Field(..., description="交易截止时间 (Unix timestamp)")
    sender_address: str = Field(..., description="发送方地址 (0x...)")

    @field_validator('min_amount_out')
    @classmethod
    def validate_min_amount_out(cls, v: str) -> str:
        try:
            val = int(v)
            if val <= 0:
                raise ValueError('min_amount_out must be greater than 0')
        except (ValueError, TypeError):
            raise ValueError('min_amount_out must be a valid positive integer string (wei)')
        return v

    @field_validator('sender_address')
    @classmethod
    def validate_sender_address(cls, v: str) -> str:
        if not v.startswith('0x') or len(v) != 42:
            raise ValueError('sender_address must be a valid Ethereum address (0x + 40 hex chars)')
        return v

class WalletValidateRequest(BaseModel):
    address: str = Field(..., description="钱包地址")


# ============ On-Chain Trend Analysis Models ============

class ChainTransaction(BaseModel):
    chain: str
    tx_hash: str
    block_number: Optional[int] = None
    block_time: datetime
    from_address: Optional[str] = None
    to_address: Optional[str] = None
    token_address: Optional[str] = None
    token_symbol: Optional[str] = None
    token_amount: Optional[float] = None
    token_amount_usd: Optional[float] = None
    tx_type: Optional[str] = None
    category: Optional[str] = None
    protocol: Optional[str] = None


class TokenMetadata(BaseModel):
    chain: str
    token_address: str
    token_symbol: str
    token_name: Optional[str] = None
    category: Optional[str] = None
    protocol: Optional[str] = None
    decimals: Optional[int] = None


class HourlyAnalysis(BaseModel):
    hour_timestamp: datetime
    chain: Optional[str] = None
    top_tokens: Optional[List[Dict[str, Any]]] = None
    top_categories: Optional[List[Dict[str, Any]]] = None
    hot_narrative: Optional[str] = None
    trend_direction: Optional[str] = None
    total_volume_usd: Optional[float] = None
    tx_count: Optional[int] = None
    kimi_analysis: Optional[str] = None


class HalfDaySummary(BaseModel):
    period_start: datetime
    period_end: datetime
    chains: Optional[List[str]] = None
    total_volume_usd: Optional[float] = None
    category_breakdown: Optional[Dict[str, Any]] = None
    top_movers: Optional[List[Dict[str, Any]]] = None
    kimi_summary: Optional[str] = None


class BigSummary(BaseModel):
    period_start: datetime
    period_end: datetime
    chains: Optional[List[str]] = None
    narrative_trends: Optional[str] = None
    category_rotation: Optional[str] = None
    top_performers: Optional[List[Dict[str, Any]]] = None
    kimi_deep_analysis: Optional[str] = None


# ============ ERC20 & Router ABIs ============

ERC20_ABI = [
    {"constant": True, "inputs": [{"name": "_owner", "type": "address"}], "name": "balanceOf", "outputs": [{"name": "balance", "type": "uint256"}], "type": "function"},
    {"constant": True, "inputs": [], "name": "decimals", "outputs": [{"name": "", "type": "uint8"}], "type": "function"},
    {"constant": True, "inputs": [], "name": "symbol", "outputs": [{"name": "", "type": "string"}], "type": "function"},
    {"constant": False, "inputs": [{"name": "_spender", "type": "address"}, {"name": "_value", "type": "uint256"}], "name": "approve", "outputs": [{"name": "", "type": "bool"}], "type": "function"},
    {"constant": True, "inputs": [{"name": "_owner", "type": "address"}, {"name": "_spender", "type": "address"}], "name": "allowance", "outputs": [{"name": "", "type": "uint256"}], "type": "function"},
]

LB_ROUTER_ABI = [
    {
        "inputs": [
            {"internalType": "uint256", "name": "amountIn", "type": "uint256"},
            {"internalType": "uint256", "name": "amountOutMin", "type": "uint256"},
            {"components": [
                {"internalType": "address", "name": "token", "type": "address"},
                {"internalType": "uint256", "name": "binStep", "type": "uint256"},
                {"internalType": "uint8", "name": "version", "type": "uint8"}
            ], "internalType": "struct ILBRouter.Path[]", "name": "path", "type": "tuple[]"},
            {"internalType": "address", "name": "to", "type": "address"},
            {"internalType": "uint256", "name": "deadline", "type": "uint256"}
        ],
        "name": "swapExactTokensForTokens",
        "outputs": [{"internalType": "uint256", "name": "amountOut", "type": "uint256"}],
        "stateMutability": "nonpayable",
        "type": "function"
    },
    {
        "inputs": [
            {"internalType": "uint256", "name": "amountOutMin", "type": "uint256"},
            {"components": [
                {"internalType": "address", "name": "token", "type": "address"},
                {"internalType": "uint256", "name": "binStep", "type": "uint256"},
                {"internalType": "uint8", "name": "version", "type": "uint8"}
            ], "internalType": "struct ILBRouter.Path[]", "name": "path", "type": "tuple[]"},
            {"internalType": "address", "name": "to", "type": "address"},
            {"internalType": "uint256", "name": "deadline", "type": "uint256"}
        ],
        "name": "swapExactNATIVEForTokens",
        "outputs": [{"internalType": "uint256", "name": "amountOut", "type": "uint256"}],
        "stateMutability": "payable",
        "type": "function"
    },
    {
        "inputs": [
            {"internalType": "uint256", "name": "amountIn", "type": "uint256"},
            {"internalType": "uint256", "name": "amountOutMinNATIVE", "type": "uint256"},
            {"components": [
                {"internalType": "address", "name": "token", "type": "address"},
                {"internalType": "uint256", "name": "binStep", "type": "uint256"},
                {"internalType": "uint8", "name": "version", "type": "uint8"}
            ], "internalType": "struct ILBRouter.Path[]", "name": "path", "type": "tuple[]"},
            {"internalType": "address payable", "name": "to", "type": "address"},
            {"internalType": "uint256", "name": "deadline", "type": "uint256"}
        ],
        "name": "swapExactTokensForNATIVE",
        "outputs": [{"internalType": "uint256", "name": "amountOut", "type": "uint256"}],
        "stateMutability": "nonpayable",
        "type": "function"
    },
]

# ============ Cache Manager ============

class CacheManager:
    def __init__(self, ttl: int = CACHE_TTL):
        self._cache: Dict[str, Dict[str, Any]] = {}
        self._ttl = ttl
        self._lock = asyncio.Lock()
    
    def _make_key(self, prefix: str, *args) -> str:
        key_data = json.dumps(args, sort_keys=True, default=str)
        return f"{prefix}:{hashlib.md5(key_data.encode()).hexdigest()}"
    
    async def get(self, prefix: str, *args) -> Optional[Any]:
        key = self._make_key(prefix, *args)
        async with self._lock:
            if key in self._cache:
                entry = self._cache[key]
                ttl = entry.get("ttl", self._ttl)
                if datetime.now() - entry["time"] < timedelta(seconds=ttl):
                    return entry["data"]
                else:
                    del self._cache[key]
            return None
    
    async def set(self, prefix: str, *args, data: Any = None, ttl: Optional[int] = None):
        # Support both positional and keyword data argument for backward compatibility:
        #   cache.set("prefix", "arg1", data=value)
        #   cache.set("prefix", "arg1", value, ttl=900)
        if data is None and args:
            *key_args, data = args
        else:
            key_args = args
        
        key = self._make_key(prefix, *key_args)
        async with self._lock:
            if len(self._cache) >= MAX_CACHE_SIZE:
                oldest = min(self._cache.keys(), key=lambda k: self._cache[k]["time"])
                del self._cache[oldest]
            
            effective_ttl = ttl if ttl is not None else self._ttl
            self._cache[key] = {
                "data": data,
                "time": datetime.now(),
                "ttl": effective_ttl,
            }
    
    async def invalidate(self, prefix: str = None):
        async with self._lock:
            if prefix:
                keys_to_delete = [k for k in self._cache if k.startswith(f"{prefix}:")]
                for k in keys_to_delete:
                    del self._cache[k]
            else:
                self._cache.clear()

cache = CacheManager()

# ============ Request/Response Logging Middleware ============

async def log_requests(request, call_next):
    """Log all incoming requests and their responses with timing."""
    start = time.time()
    client_host = request.client.host if request.client else "unknown"
    logger.info(f"→ {request.method} {request.url.path} from {client_host}")
    try:
        response = await call_next(request)
        duration = (time.time() - start) * 1000
        logger.info(f"← {request.method} {request.url.path} {response.status_code} ({duration:.1f}ms)")
        return response
    except Exception as e:
        duration = (time.time() - start) * 1000
        logger.error(f"← {request.method} {request.url.path} ERROR ({duration:.1f}ms): {e}")
        raise

# ============ Rate Limiting ============
request_history: Dict[str, List[float]] = {}

def rate_limit(max_requests: int = RATE_LIMIT_REQUESTS, window: int = RATE_LIMIT_WINDOW):
    def decorator(func):
        @wraps(func)
        async def wrapper(request: Request, *args, **kwargs):
            client_ip = request.client.host
            now = time.time()
            
            if client_ip in request_history:
                request_history[client_ip] = [
                    t for t in request_history[client_ip]
                    if now - t < window
                ]
            else:
                request_history[client_ip] = []
            
            if len(request_history[client_ip]) >= max_requests:
                logger.warning(f"Rate limit exceeded for {client_ip}")
                raise HTTPException(
                    status_code=429,
                    detail=f"Rate limit exceeded. Max {max_requests} requests per {window} seconds."
                )
            
            request_history[client_ip].append(now)
            return await func(request, *args, **kwargs)
        return wrapper
    return decorator

