"""
Mantle DeFAI Trader - DeFiLlama API Client
DeFiLlama 数据客户端，支持 TVL、协议列表、历史 TVL 查询

特性：
- 异步 aiohttp 客户端（与项目现有依赖一致）
- 内存缓存（3 分钟 TTL）
- 指数退避重试（最多 3 次）
- 类型注解
"""

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

import aiohttp

logger = logging.getLogger(__name__)

# ============ Configuration ============
DEFILLAMA_BASE_URL = "https://api.llama.fi"
CACHE_TTL_SECONDS = 900  # 15 minutes
MAX_RETRIES = 3


# ============ Data Models ============

@dataclass
class ProtocolSummary:
    """协议摘要信息"""
    slug: str
    name: str
    category: str
    tvl: float
    tvl_change_1d: float
    tvl_change_7d: float
    mcap: Optional[float] = None


@dataclass
class ChainTvlData:
    """链 TVL 数据"""
    name: str
    tvl: float
    token_symbol: Optional[str] = None
    cmc_id: Optional[str] = None
    gecko_id: Optional[str] = None


@dataclass
class HistoricalTvlPoint:
    """历史 TVL 数据点"""
    date: str
    tvl: float


@dataclass
class ProtocolDetail:
    """协议详细信息"""
    slug: str
    name: str
    description: Optional[str] = None
    url: Optional[str] = None
    logo: Optional[str] = None
    twitter: Optional[str] = None
    category: Optional[str] = None
    chains: List[str] = field(default_factory=list)
    current_tvl: float = 0.0
    historical_tvl: List[HistoricalTvlPoint] = field(default_factory=list)


# ============ Cache ============

class _MemoryCache:
    """简单的内存缓存，带 TTL"""

    def __init__(self, ttl: int = CACHE_TTL_SECONDS):
        self._ttl = ttl
        self._store: Dict[str, Dict[str, Any]] = {}
        self._lock = asyncio.Lock()

    async def get(self, key: str) -> Optional[Any]:
        async with self._lock:
            entry = self._store.get(key)
            if entry is None:
                return None
            if datetime.utcnow() - entry["time"] >= timedelta(seconds=self._ttl):
                del self._store[key]
                return None
            return entry["data"]

    async def set(self, key: str, data: Any):
        async with self._lock:
            self._store[key] = {"data": data, "time": datetime.utcnow()}

    async def invalidate(self, key: str):
        async with self._lock:
            self._store.pop(key, None)

    async def clear(self):
        async with self._lock:
            self._store.clear()


# ============ Client ============

class DeFiLlamaClient:
    """DeFiLlama API 异步客户端

    提供以下功能：
    1. 获取所有链的 TVL 数据
    2. 获取 Mantle 链上的协议列表
    3. 获取指定协议的历史 TVL
    4. 自动缓存与重试
    """

    def __init__(self, base_url: str = DEFILLAMA_BASE_URL):
        self.base_url = base_url.rstrip("/")
        self._cache = _MemoryCache()
        self._session: Optional[aiohttp.ClientSession] = None

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            timeout = aiohttp.ClientTimeout(total=30, connect=10)
            self._session = aiohttp.ClientSession(
                timeout=timeout,
                headers={"Accept": "application/json"},
            )
        return self._session

    async def close(self):
        if self._session and not self._session.closed:
            await self._session.close()
            self._session = None

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()

    async def _request(self, endpoint: str, params: Optional[Dict[str, Any]] = None) -> Any:
        """发送 GET 请求，带指数退避重试"""
        session = await self._get_session()
        url = f"{self.base_url}{endpoint}"
        last_exception: Optional[Exception] = None

        for attempt in range(1, MAX_RETRIES + 1):
            try:
                async with session.get(url, params=params) as resp:
                    resp.raise_for_status()
                    return await resp.json()
            except aiohttp.ClientResponseError as e:
                logger.warning(
                    "DeFiLlama HTTP error (attempt %d/%d): %s %s",
                    attempt, MAX_RETRIES, e.status, e.message,
                )
                last_exception = e
                if e.status in (429, 500, 502, 503, 504):
                    if attempt < MAX_RETRIES:
                        wait = 2 ** (attempt - 1)
                        logger.info("Retrying in %ds...", wait)
                        await asyncio.sleep(wait)
                        continue
                raise
            except aiohttp.ClientError as e:
                logger.warning(
                    "DeFiLlama request error (attempt %d/%d): %s",
                    attempt, MAX_RETRIES, e,
                )
                last_exception = e
                if attempt < MAX_RETRIES:
                    wait = 2 ** (attempt - 1)
                    logger.info("Retrying in %ds...", wait)
                    await asyncio.sleep(wait)
                    continue
                raise

        # Should never reach here, but just in case
        raise last_exception or RuntimeError("Max retries exceeded")

    # ------------------------------------------------------------------
    # Public API Methods
    # ------------------------------------------------------------------

    async def get_chains(self, use_cache: bool = True) -> List[ChainTvlData]:
        """获取所有链的 TVL 数据（对应 /v2/chains）"""
        cache_key = "chains"
        if use_cache:
            cached = await self._cache.get(cache_key)
            if cached is not None:
                logger.debug("Cache hit: %s", cache_key)
                return cached

        data = await self._request("/v2/chains")
        if not isinstance(data, list):
            logger.error("Unexpected response type for /v2/chains: %s", type(data))
            return []

        result = [
            ChainTvlData(
                name=item.get("name", ""),
                tvl=float(item.get("tvl", 0) or 0),
                token_symbol=item.get("tokenSymbol"),
                cmc_id=item.get("cmcId"),
                gecko_id=item.get("gecko_id"),
            )
            for item in data
        ]

        if use_cache:
            await self._cache.set(cache_key, result)
        return result

    async def get_chain_tvl(self, chain: str = "Mantle", use_cache: bool = True) -> Optional[float]:
        """获取指定链的总 TVL"""
        chains = await self.get_chains(use_cache=use_cache)
        chain_lower = chain.lower()
        for c in chains:
            if c.name.lower() == chain_lower:
                return c.tvl
        return None

    async def get_protocols(self, use_cache: bool = True) -> List[ProtocolSummary]:
        """获取所有协议列表（对应 /v2/protocols）"""
        cache_key = "protocols"
        if use_cache:
            cached = await self._cache.get(cache_key)
            if cached is not None:
                logger.debug("Cache hit: %s", cache_key)
                return cached

        data = await self._request("/v2/protocols")
        if not isinstance(data, list):
            logger.error("Unexpected response type for /v2/protocols: %s", type(data))
            return []

        result = [
            ProtocolSummary(
                slug=item.get("slug", ""),
                name=item.get("name", ""),
                category=item.get("category", "Unknown"),
                tvl=float(item.get("tvl", 0) or 0),
                tvl_change_1d=float(item.get("change_1d", 0) or 0),
                tvl_change_7d=float(item.get("change_7d", 0) or 0),
                mcap=float(item.get("mcap", 0)) if item.get("mcap") else None,
            )
            for item in data
        ]

        if use_cache:
            await self._cache.set(cache_key, result)
        return result

    async def get_mantle_protocols(self, use_cache: bool = True) -> List[ProtocolSummary]:
        """获取 Mantle 链上的协议列表"""
        cache_key = "mantle_protocols"
        if use_cache:
            cached = await self._cache.get(cache_key)
            if cached is not None:
                logger.debug("Cache hit: %s", cache_key)
                return cached

        raw_data = await self._request("/v2/protocols")
        if not isinstance(raw_data, list):
            return []

        mantle_protocols: List[ProtocolSummary] = []
        for item in raw_data:
            chain_tvls = item.get("chainTvls", {})
            if "Mantle" in chain_tvls and chain_tvls["Mantle"] > 0:
                mantle_protocols.append(
                    ProtocolSummary(
                        slug=item.get("slug", ""),
                        name=item.get("name", ""),
                        category=item.get("category", "Unknown"),
                        tvl=float(chain_tvls.get("Mantle", 0)),
                        tvl_change_1d=float(item.get("change_1d", 0) or 0),
                        tvl_change_7d=float(item.get("change_7d", 0) or 0),
                        mcap=float(item.get("mcap", 0)) if item.get("mcap") else None,
                    )
                )

        # 按 TVL 降序排列
        mantle_protocols.sort(key=lambda p: p.tvl, reverse=True)

        if use_cache:
            await self._cache.set(cache_key, mantle_protocols)
        return mantle_protocols

    async def get_protocol_detail(self, slug: str, use_cache: bool = True) -> Optional[ProtocolDetail]:
        """获取指定协议的详细数据，包括历史 TVL（对应 /protocol/{slug}）"""
        cache_key = f"protocol:{slug}"
        if use_cache:
            cached = await self._cache.get(cache_key)
            if cached is not None:
                logger.debug("Cache hit: %s", cache_key)
                return cached

        data = await self._request(f"/protocol/{slug}")
        if not isinstance(data, dict):
            logger.error("Unexpected response type for /protocol/%s: %s", slug, type(data))
            return None

        # 解析历史 TVL
        historical: List[HistoricalTvlPoint] = []
        tvl_data = data.get("tvl", [])
        if isinstance(tvl_data, list):
            for point in tvl_data:
                if isinstance(point, dict):
                    ts = point.get("date")
                    tvl_val = point.get("totalLiquidityUSD")
                    if ts is not None and tvl_val is not None:
                        historical.append(
                            HistoricalTvlPoint(
                                date=datetime.utcfromtimestamp(int(ts)).isoformat(),
                                tvl=float(tvl_val),
                            )
                        )

        result = ProtocolDetail(
            slug=slug,
            name=data.get("name", ""),
            description=data.get("description"),
            url=data.get("url"),
            logo=data.get("logo"),
            twitter=data.get("twitter"),
            category=data.get("category"),
            chains=data.get("chains", []),
            current_tvl=float(data.get("tvl", 0) or 0),
            historical_tvl=historical,
        )

        if use_cache:
            await self._cache.set(cache_key, result)
        return result

    async def get_protocol_history_tvl(self, slug: str, use_cache: bool = True) -> List[HistoricalTvlPoint]:
        """获取指定协议的历史 TVL 列表"""
        detail = await self.get_protocol_detail(slug, use_cache=use_cache)
        if detail is None:
            return []
        return detail.historical_tvl

    # ------------------------------------------------------------------
    # Cache management
    # ------------------------------------------------------------------

    async def invalidate_cache(self, key: Optional[str] = None):
        """清除缓存"""
        if key:
            await self._cache.invalidate(key)
        else:
            await self._cache.clear()


# ============ Convenience Functions ============

async def get_mantle_tvl() -> Optional[float]:
    """便捷函数：获取 Mantle 链总 TVL"""
    async with DeFiLlamaClient() as client:
        return await client.get_chain_tvl("Mantle")


async def get_mantle_protocols() -> List[ProtocolSummary]:
    """便捷函数：获取 Mantle 链协议列表"""
    async with DeFiLlamaClient() as client:
        return await client.get_mantle_protocols()


# ============ Main (for quick testing) ============

async def _main():
    logging.basicConfig(level=logging.INFO)
    async with DeFiLlamaClient() as client:
        print("Fetching Mantle TVL...")
        tvl = await client.get_chain_tvl("Mantle")
        print(f"Mantle TVL: ${tvl:,.2f}" if tvl else "Mantle TVL: N/A")

        print("\nFetching Mantle protocols...")
        protocols = await client.get_mantle_protocols()
        print(f"Found {len(protocols)} protocols on Mantle")
        for p in protocols[:5]:
            print(f"  - {p.name}: ${p.tvl:,.2f} ({p.category})")

        if protocols:
            slug = protocols[0].slug
            print(f"\nFetching history for {slug}...")
            history = await client.get_protocol_history_tvl(slug)
            print(f"  Historical TVL points: {len(history)}")
            if history:
                print(f"  Latest: ${history[-1].tvl:,.2f} @ {history[-1].date}")


if __name__ == "__main__":
    asyncio.run(_main())
