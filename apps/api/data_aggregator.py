"""
Mantle DeFAI Trader - Data Aggregator
统一数据聚合层：统一数据模型 + 定时刷新 + Redis/内存缓存

功能：
1. 统一数据模型 AggregatedData
2. 聚合多个数据源（DeFiLlama、Mantle RPC、WhaleMonitor）
3. Redis 缓存（可用时）/ 内存缓存降级
4. 定时刷新调度器（3分钟）
5. 优雅降级：任何子数据源失败不导致整体失败
"""

import asyncio
import json
import os
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from loguru import logger

# Database layer
from db import db_manager, db_get, db_set

# DeFiLlama client (new)
from defillama_client import DeFiLlamaClient

# On-chain collector
from onchain_collector import (
    MantleDataCollector,
    OnChainDataCollector,
)

# Whale monitor — optional, may not exist yet
WHALE_MONITOR_AVAILABLE = False
WhaleMonitor = None
try:
    from whale_monitor import WhaleMonitor as _WhaleMonitor
    WhaleMonitor = _WhaleMonitor
    WHALE_MONITOR_AVAILABLE = True
    logger.info("WhaleMonitor module loaded successfully")
except Exception as e:
    logger.warning(f"WhaleMonitor not available: {e}")

# Redis — optional
try:
    import redis.asyncio as aioredis
    REDIS_AVAILABLE = True
except Exception as e:
    logger.warning(f"aioredis not available: {e}")
    REDIS_AVAILABLE = False


# ============ Configuration ============
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379")
CACHE_TTL_SECONDS = int(os.getenv("AGGREGATOR_CACHE_TTL", "900"))
REFRESH_INTERVAL_SECONDS = int(os.getenv("AGGREGATOR_REFRESH_INTERVAL", "900"))
CACHE_KEY_PREFIX = "mantle:defai:"


# ============ Unified Data Model ============

@dataclass
class AggregatedData:
    """统一聚合数据模型"""
    timestamp: str
    chain: str
    tvl: float
    tvl_change_24h: float
    protocol_count: int
    top_protocols: List[dict]
    gas_price_gwei: float
    block_number: int
    avg_block_time: float
    network_utilization: float
    large_transfers: List[dict]
    fund_flow: Optional[dict]


# ============ Cache Layer ============

class _MemoryCache:
    """内存缓存，带 TTL"""

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

    async def delete(self, key: str):
        async with self._lock:
            self._store.pop(key, None)

    async def clear(self):
        async with self._lock:
            self._store.clear()


class _RedisCache:
    """Redis 缓存封装"""

    def __init__(self, url: str = REDIS_URL, ttl: int = CACHE_TTL_SECONDS):
        self._url = url
        self._ttl = ttl
        self._redis: Optional[Any] = None
        self._connected = False

    async def connect(self) -> bool:
        if not REDIS_AVAILABLE:
            return False
        try:
            self._redis = aioredis.from_url(self._url, decode_responses=True)
            await self._redis.ping()
            self._connected = True
            logger.info(f"Redis connected: {self._url}")
            return True
        except Exception as e:
            logger.warning(f"Redis connection failed: {e}")
            self._connected = False
            return False

    def _make_key(self, key: str) -> str:
        return f"{CACHE_KEY_PREFIX}{key}"

    async def get(self, key: str) -> Optional[Any]:
        if not self._connected or self._redis is None:
            return None
        try:
            raw = await self._redis.get(self._make_key(key))
            if raw is None:
                return None
            return json.loads(raw)
        except Exception as e:
            logger.warning(f"Redis get error: {e}")
            return None

    async def set(self, key: str, data: Any):
        if not self._connected or self._redis is None:
            return
        try:
            await self._redis.setex(
                self._make_key(key),
                self._ttl,
                json.dumps(data, default=str),
            )
        except Exception as e:
            logger.warning(f"Redis set error: {e}")

    async def delete(self, key: str):
        if not self._connected or self._redis is None:
            return
        try:
            await self._redis.delete(self._make_key(key))
        except Exception as e:
            logger.warning(f"Redis delete error: {e}")

    async def close(self):
        if self._redis:
            try:
                await self._redis.close()
            except Exception:
                pass


class CacheLayer:
    """缓存层：优先 Redis，降级到内存"""

    def __init__(self):
        self._redis = _RedisCache()
        self._memory = _MemoryCache()
        self._use_redis = False

    async def initialize(self):
        self._use_redis = await self._redis.connect()
        if not self._use_redis:
            logger.info("Using in-memory cache (Redis unavailable)")

    async def get(self, key: str) -> Optional[Any]:
        if self._use_redis:
            data = await self._redis.get(key)
            if data is not None:
                return data
        return await self._memory.get(key)

    async def set(self, key: str, data: Any):
        if self._use_redis:
            await self._redis.set(key, data)
        await self._memory.set(key, data)

    async def delete(self, key: str):
        if self._use_redis:
            await self._redis.delete(key)
        await self._memory.delete(key)

    async def close(self):
        await self._redis.close()


# ============ Data Aggregator ============

class DataAggregator:
    """统一数据聚合器

    聚合多个数据源：
    - DeFiLlama: TVL、协议数据
    - Mantle RPC: 区块、Gas、网络统计
    - WhaleMonitor: 大额转账（可选）
    """

    def __init__(self):
        self.cache = CacheLayer()
        self.llama = DeFiLlamaClient()
        self.mantle_collector = MantleDataCollector()
        self.onchain = OnChainDataCollector()
        self.whale_monitor: Optional[Any] = None
        if WHALE_MONITOR_AVAILABLE and WhaleMonitor is not None:
            try:
                self.whale_monitor = WhaleMonitor()
                logger.info("WhaleMonitor initialized")
            except Exception as e:
                logger.warning(f"WhaleMonitor init failed: {e}")

    async def initialize(self):
        await self.cache.initialize()

    async def close(self):
        await self.cache.close()
        await self.llama.close()

    # ------------------------------------------------------------------
    # Data collection helpers (with graceful degradation)
    # ------------------------------------------------------------------

    async def _fetch_llama_data(self) -> Dict[str, Any]:
        """获取 DeFiLlama 数据"""
        result = {
            "tvl": 0.0,
            "tvl_change_24h": 0.0,
            "protocol_count": 0,
            "top_protocols": [],
        }
        try:
            # Chain TVL
            tvl = await self.llama.get_chain_tvl("Mantle", use_cache=False)
            if tvl is not None:
                result["tvl"] = tvl

            # Protocols
            protocols = await self.llama.get_mantle_protocols(use_cache=False)
            result["protocol_count"] = len(protocols)

            if protocols:
                # TVL change from top protocol (approximate)
                top = protocols[0]
                result["tvl_change_24h"] = top.tvl_change_1d

                # Top 5 protocols
                result["top_protocols"] = [
                    {
                        "slug": p.slug,
                        "name": p.name,
                        "category": p.category,
                        "tvl": p.tvl,
                        "tvl_change_1d": p.tvl_change_1d,
                        "tvl_change_7d": p.tvl_change_7d,
                    }
                    for p in protocols[:5]
                ]
        except Exception as e:
            logger.error(f"DeFiLlama data fetch failed: {e}")
        return result

    def _fetch_mantle_data(self) -> Dict[str, Any]:
        """获取 Mantle RPC 数据（同步调用）"""
        result = {
            "gas_price_gwei": 0.0,
            "block_number": 0,
            "avg_block_time": 2.0,
            "network_utilization": 0.0,
        }
        try:
            gas = self.mantle_collector.get_gas_price()
            if gas:
                result["gas_price_gwei"] = gas.gwei

            block = self.mantle_collector.get_latest_block()
            if block:
                result["block_number"] = block.number
                result["network_utilization"] = block.gas_utilization

            blocks = self.mantle_collector.get_recent_blocks(10)
            result["avg_block_time"] = self.mantle_collector.calculate_block_time(blocks)
        except Exception as e:
            logger.error(f"Mantle RPC data fetch failed: {e}")
        return result

    async def _fetch_whale_data(self) -> Dict[str, Any]:
        """获取 WhaleMonitor 数据（可选）"""
        result = {
            "large_transfers": [],
            "fund_flow": None,
        }
        if self.whale_monitor is None:
            return result

        try:
            # 尝试调用常见接口（根据实际 whale_monitor 调整）
            if hasattr(self.whale_monitor, "get_large_transfers"):
                transfers = await self.whale_monitor.get_large_transfers()
                if transfers:
                    result["large_transfers"] = transfers
            elif hasattr(self.whale_monitor, "get_recent_transfers"):
                transfers = await self.whale_monitor.get_recent_transfers()
                if transfers:
                    result["large_transfers"] = transfers

            if hasattr(self.whale_monitor, "get_fund_flow"):
                flow = await self.whale_monitor.get_fund_flow()
                if flow:
                    result["fund_flow"] = flow
            elif hasattr(self.whale_monitor, "get_stablecoin_flow"):
                flow = await self.whale_monitor.get_stablecoin_flow()
                if flow:
                    result["fund_flow"] = flow
        except Exception as e:
            logger.warning(f"WhaleMonitor data fetch failed: {e}")
        return result

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def collect_all(self, force_refresh: bool = False) -> AggregatedData:
        """收集所有数据并聚合为统一模型

        Args:
            force_refresh: 是否强制刷新缓存

        Returns:
            AggregatedData 实例
        """
        cache_key = "aggregated_data"

        if not force_refresh:
            cached = await self.cache.get(cache_key)
            if cached is not None:
                logger.debug("Returning cached aggregated data")
                try:
                    # 尝试从 dict 恢复（兼容序列化后的数据）
                    if isinstance(cached, dict):
                        return AggregatedData(**cached)
                    return cached
                except Exception:
                    pass  # 缓存损坏，重新获取

        # 并行获取各数据源
        llama_task = self._fetch_llama_data()
        mantle_task = asyncio.to_thread(self._fetch_mantle_data)
        whale_task = self._fetch_whale_data()

        llama_data, mantle_data, whale_data = await asyncio.gather(
            llama_task,
            mantle_task,
            whale_task,
            return_exceptions=True,
        )

        # 处理异常结果
        if isinstance(llama_data, Exception):
            logger.error(f"LLAMA task failed: {llama_data}")
            llama_data = {"tvl": 0.0, "tvl_change_24h": 0.0, "protocol_count": 0, "top_protocols": []}
        if isinstance(mantle_data, Exception):
            logger.error(f"MANTLE task failed: {mantle_data}")
            mantle_data = {"gas_price_gwei": 0.0, "block_number": 0, "avg_block_time": 2.0, "network_utilization": 0.0}
        if isinstance(whale_data, Exception):
            logger.warning(f"WHALE task failed: {whale_data}")
            whale_data = {"large_transfers": [], "fund_flow": None}

        aggregated = AggregatedData(
            timestamp=datetime.utcnow().isoformat(),
            chain="Mantle",
            tvl=llama_data.get("tvl", 0.0),
            tvl_change_24h=llama_data.get("tvl_change_24h", 0.0),
            protocol_count=llama_data.get("protocol_count", 0),
            top_protocols=llama_data.get("top_protocols", []),
            gas_price_gwei=mantle_data.get("gas_price_gwei", 0.0),
            block_number=mantle_data.get("block_number", 0),
            avg_block_time=mantle_data.get("avg_block_time", 2.0),
            network_utilization=mantle_data.get("network_utilization", 0.0),
            large_transfers=whale_data.get("large_transfers", []),
            fund_flow=whale_data.get("fund_flow"),
        )

        # 写入缓存（内存 + 数据库）
        data_dict = asdict(aggregated)
        await self.cache.set(cache_key, data_dict)
        try:
            await db_set(cache_key, data_dict, ttl_seconds=REFRESH_INTERVAL_SECONDS * 2)
            logger.info("Aggregated data refreshed and persisted to DB + cache")
        except Exception as e:
            logger.warning(f"Failed to write aggregated data to DB: {e}")

        return aggregated

    async def get_cached_data(self) -> Optional[AggregatedData]:
        """获取缓存的聚合数据（不触发刷新）

        优先从数据库读取，其次从内存缓存读取。
        """
        # 1. Try database first (persistent)
        try:
            db_data = await db_get("aggregated_data")
            if db_data is not None:
                if isinstance(db_data, dict):
                    try:
                        return AggregatedData(**db_data)
                    except Exception:
                        pass
        except Exception as e:
            logger.debug(f"DB read for aggregated_data failed: {e}")

        # 2. Fallback to in-memory cache
        cached = await self.cache.get("aggregated_data")
        if cached is None:
            return None
        if isinstance(cached, AggregatedData):
            return cached
        if isinstance(cached, dict):
            try:
                return AggregatedData(**cached)
            except Exception:
                return None
        return None


# ============ Refresh Scheduler ============

class AggregatorScheduler:
    """聚合数据定时刷新调度器"""

    def __init__(
        self,
        aggregator: DataAggregator,
        interval: int = REFRESH_INTERVAL_SECONDS,
    ):
        self.aggregator = aggregator
        self.interval = interval
        self.running = False
        self.last_refresh: Optional[datetime] = None
        self._task: Optional[asyncio.Task] = None
        self._stop_event = asyncio.Event()

    async def start(self):
        """启动调度器：先预热一次，然后定时刷新"""
        if self.running:
            logger.warning("Aggregator scheduler already running")
            return

        self.running = True
        self._stop_event.clear()
        logger.info(f"Starting aggregator scheduler (interval: {self.interval}s)")

        # 预热
        try:
            await self.aggregator.collect_all(force_refresh=True)
            self.last_refresh = datetime.utcnow()
            logger.info("Aggregator pre-warm complete")
        except Exception as e:
            logger.error(f"Aggregator pre-warm failed: {e}")

        # 启动后台任务
        self._task = asyncio.create_task(self._run_loop())

    async def _run_loop(self):
        """后台刷新循环"""
        while self.running:
            try:
                # 等待 interval 秒或直到 stop 被调用
                try:
                    await asyncio.wait_for(
                        self._stop_event.wait(),
                        timeout=self.interval,
                    )
                except asyncio.TimeoutError:
                    pass

                if not self.running:
                    break

                await self.aggregator.collect_all(force_refresh=True)
                self.last_refresh = datetime.utcnow()
                logger.info(f"Aggregator refreshed at {self.last_refresh.isoformat()}")
            except Exception as e:
                logger.error(f"Aggregator refresh failed: {e}")

    def stop(self):
        """停止调度器"""
        if not self.running:
            return
        self.running = False
        self._stop_event.set()
        if self._task and not self._task.done():
            self._task.cancel()
        logger.info("Aggregator scheduler stopped")

    def get_status(self) -> Dict[str, Any]:
        """获取调度器状态"""
        return {
            "running": self.running,
            "interval_seconds": self.interval,
            "last_refresh": self.last_refresh.isoformat() if self.last_refresh else None,
            "whale_monitor_available": WHALE_MONITOR_AVAILABLE,
            "redis_available": REDIS_AVAILABLE,
        }


# ============ Convenience Functions ============

async def create_aggregator() -> DataAggregator:
    """工厂函数：创建并初始化聚合器"""
    agg = DataAggregator()
    await agg.initialize()
    return agg


# ============ Main (for quick testing) ============

async def _main():
    logger.info("Testing DataAggregator...")
    agg = await create_aggregator()
    try:
        data = await agg.collect_all(force_refresh=True)
        print("\n" + "=" * 50)
        print("Aggregated Data")
        print("=" * 50)
        print(f"Chain: {data.chain}")
        print(f"TVL: ${data.tvl:,.2f}")
        print(f"TVL Change 24h: {data.tvl_change_24h:.2f}%")
        print(f"Protocols: {data.protocol_count}")
        print(f"Top Protocols: {len(data.top_protocols)}")
        print(f"Gas Price: {data.gas_price_gwei} gwei")
        print(f"Block: {data.block_number}")
        print(f"Avg Block Time: {data.avg_block_time}s")
        print(f"Network Utilization: {data.network_utilization}%")
        print(f"Large Transfers: {len(data.large_transfers)}")
        print(f"Fund Flow: {data.fund_flow is not None}")
        print("=" * 50)
    finally:
        await agg.close()


if __name__ == "__main__":
    asyncio.run(_main())
