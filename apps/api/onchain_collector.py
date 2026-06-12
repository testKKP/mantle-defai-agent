"""
Mantle DeFAI Trader - On-Chain Data Collector
基础链上数据接入模块

功能：
1. DeFiLlama API - 获取 Mantle 生态协议数据
2. Mantle RPC - 获取区块、Gas、交易数据
3. 数据缓存与定时刷新
4. AI 分析数据准备

刷新频率：3分钟
"""

import asyncio
import aiohttp
import json
from typing import Dict, List, Optional
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta
from loguru import logger
import os

# Web3 for Mantle
from web3 import Web3


# ============ Configuration ============
DEFILLAMA_API_URL = "https://api.llama.fi"
MANTLE_RPC_URL = os.getenv("MANTLE_RPC_URL", "https://rpc.mantle.xyz")
CACHE_TTL = 900  # 15 minutes

# Mantle Contract Addresses
USDC = "0x09Bc4E0D864854c6aFB6eB9A9cdF58aC190D0dF9"
USDT = "0x201EBa5CC46D216Ce6DC03F6a759e8E766e956aE"

# Stablecoins to track
STABLECOINS = {
    "USDC": USDC,
    "USDT": USDT,
}


# ============ Data Models ============

@dataclass
class ProtocolData:
    """DeFi 协议数据"""
    protocol_id: str
    protocol_name: str
    chain: str
    category: str
    tvl: float
    tvl_change_24h: float
    volume_24h: float
    volume_change_24h: float
    fees_24h: float
    timestamp: str

@dataclass
class ChainOverview:
    """链上概览数据"""
    chain: str
    total_tvl: float
    total_volume_24h: float
    total_fees_24h: float
    protocol_count: int
    timestamp: str

@dataclass
class BlockData:
    """区块数据"""
    number: int
    hash: str
    timestamp: int
    timestamp_iso: str
    gas_used: int
    gas_limit: int
    gas_utilization: float
    tx_count: int
    size: int

@dataclass
class GasData:
    """Gas 数据"""
    wei: int
    gwei: float
    mnt: float
    timestamp: str

@dataclass
class LargeTransfer:
    """大额转账"""
    tx_hash: str
    timestamp: str
    from_address: str
    to_address: str
    token: str
    amount: float
    value_usd: float
    from_label: Optional[str] = None
    to_label: Optional[str] = None

@dataclass
class FundFlow:
    """资金流向数据"""
    timestamp: str
    period: str
    exchange_inflow: float
    exchange_outflow: float
    net_flow: float
    large_transfers: List[LargeTransfer]


# ============ DeFiLlama Client ============

class DeFiLlamaClient:
    """DeFiLlama API 客户端"""
    
    BASE_URL = "https://api.llama.fi"
    
    def __init__(self):
        self.session: Optional[aiohttp.ClientSession] = None
    
    async def __aenter__(self):
        timeout = aiohttp.ClientTimeout(total=30, connect=10)
        self.session = aiohttp.ClientSession(timeout=timeout)
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.session:
            await self.session.close()
    
    async def _get(self, endpoint: str) -> dict:
        """发送 GET 请求"""
        url = f"{self.BASE_URL}{endpoint}"
        try:
            async with self.session.get(url) as resp:
                resp.raise_for_status()
                return await resp.json()
        except aiohttp.ClientResponseError as e:
            logger.error(f"DeFiLlama API error: {e.status} {e.message}")
            raise
        except Exception as e:
            logger.error(f"DeFiLlama request failed: {e}")
            raise
    
    async def get_protocols(self) -> List[dict]:
        """获取所有协议列表"""
        return await self._get("/protocols")
    
    async def get_protocol(self, slug: str) -> dict:
        """获取单个协议详细数据"""
        return await self._get(f"/protocol/{slug}")
    
    async def get_chain_tvl(self, chain: str = "Mantle") -> float:
        """获取链上总 TVL"""
        chains = await self._get("/chains")
        for c in chains:
            if c["name"].lower() == chain.lower():
                return c.get("tvl", 0)
        return 0
    
    async def get_dex_volume(self, chain: str = "Mantle") -> dict:
        """获取 DEX 交易量概览"""
        return await self._get(
            f"/overview/dexs/{chain}?"
            f"excludeTotalDataChart=true&"
            f"excludeTotalDataChartBreakdown=true&"
            f"dataType=dailyVolume"
        )
    
    async def get_fees_overview(self, chain: str = "Mantle") -> dict:
        """获取费用收入概览"""
        return await self._get(
            f"/overview/fees/{chain}?"
            f"excludeTotalDataChart=true&"
            f"excludeTotalDataChartBreakdown=true"
        )
    
    async def get_dex_protocols_volume(self, chain: str = "Mantle") -> Dict[str, float]:
        """获取 DEX 协议的交易量数据"""
        try:
            dex_data = await self.get_dex_volume(chain)
            if not isinstance(dex_data, dict):
                return {}
            
            volume_map = {}
            # DeFiLlama DEX overview 返回每个 protocol 的 24h volume
            protocols_data = dex_data.get("protocols", [])
            for proto in protocols_data:
                name = proto.get("name", "")
                slug = proto.get("slug", proto.get("name", "")).lower().replace(" ", "-")
                vol = float(proto.get("total24h", 0) or proto.get("volume_24h", 0) or 0)
                if vol > 0:
                    volume_map[slug] = vol
            
            return volume_map
        except Exception as e:
            logger.warning(f"Failed to get DEX volume data: {e}")
            return {}
    
    async def get_fees_protocols_data(self, chain: str = "Mantle") -> Dict[str, float]:
        """获取协议费用数据"""
        try:
            fees_data = await self.get_fees_overview(chain)
            if not isinstance(fees_data, dict):
                return {}
            
            fees_map = {}
            protocols_data = fees_data.get("protocols", [])
            for proto in protocols_data:
                name = proto.get("name", "")
                slug = proto.get("slug", proto.get("name", "")).lower().replace(" ", "-")
                fees = float(proto.get("total24h", 0) or proto.get("fees_24h", 0) or 0)
                if fees > 0:
                    fees_map[slug] = fees
            
            return fees_map
        except Exception as e:
            logger.warning(f"Failed to get fees data: {e}")
            return {}
    
    async def get_mantle_protocols(self) -> List[ProtocolData]:
        """获取 Mantle 上所有协议数据"""
        protocols = await self.get_protocols()
        mantle_protocols = []
        
        # 并行获取 DEX 交易量和费用数据
        dex_volume_task = self.get_dex_protocols_volume("Mantle")
        fees_task = self.get_fees_protocols_data("Mantle")
        
        try:
            dex_volumes, fees_data = await asyncio.gather(
                dex_volume_task, fees_task, return_exceptions=True
            )
            if isinstance(dex_volumes, Exception):
                logger.warning(f"DEX volume fetch failed: {dex_volumes}")
                dex_volumes = {}
            if isinstance(fees_data, Exception):
                logger.warning(f"Fees fetch failed: {fees_data}")
                fees_data = {}
        except Exception as e:
            logger.warning(f"Failed to get volume/fees data: {e}")
            dex_volumes = {}
            fees_data = {}
        
        for p in protocols:
            chains = p.get("chains", [])
            if "Mantle" in chains:
                # 过滤 CEX（中心化交易所）协议
                category = p.get('category', 'Unknown')
                if category.lower() in ('cex', 'exchange'):
                    continue
                
                # 获取 Mantle 链上的 TVL
                chain_tvls = p.get("chainTvls", {})
                mantle_tvl = chain_tvls.get("Mantle", 0)
                
                # 获取变化率
                change_1d = p.get("change_1d", 0) or 0
                
                # 匹配交易量和费用数据
                slug = p.get("slug", "")
                volume_24h = dex_volumes.get(slug, 0) if isinstance(dex_volumes, dict) else 0
                fees_24h = fees_data.get(slug, 0) if isinstance(fees_data, dict) else 0
                
                # 如果没有精确匹配，尝试用 Mantle TVL 占比估算
                category = p.get("category", "Unknown")
                if volume_24h == 0 and category in ("Dexs", "Derivatives"):
                    total_volume = float(p.get("volume_24h", 0) or 0)
                    total_tvl = float(p.get("tvl", 0) or 0)
                    if total_volume > 0 and total_tvl > 0 and mantle_tvl > 0:
                        mantle_ratio = mantle_tvl / total_tvl
                        volume_24h = total_volume * mantle_ratio
                
                if fees_24h == 0:
                    total_fees = float(p.get("fees_24h", 0) or 0)
                    total_tvl = float(p.get("tvl", 0) or 0)
                    if total_fees > 0 and total_tvl > 0 and mantle_tvl > 0:
                        mantle_ratio = mantle_tvl / total_tvl
                        fees_24h = total_fees * mantle_ratio
                
                protocol_data = ProtocolData(
                    protocol_id=slug,
                    protocol_name=p.get("name", ""),
                    chain="Mantle",
                    category=category,
                    tvl=mantle_tvl,
                    tvl_change_24h=change_1d,
                    volume_24h=volume_24h,
                    volume_change_24h=0,  # DeFiLlama 不提供单链维度
                    fees_24h=fees_24h,
                    timestamp=datetime.utcnow().isoformat()
                )
                mantle_protocols.append(protocol_data)
        
        # 按 TVL 排序
        mantle_protocols.sort(key=lambda x: x.tvl, reverse=True)
        return mantle_protocols
    
    async def get_mantle_overview(self) -> ChainOverview:
        """获取 Mantle 链概览"""
        # 获取 DEX 交易量
        dex_data = await self.get_dex_volume("Mantle")
        
        # 获取费用数据
        fees_data = await self.get_fees_overview("Mantle")
        
        # 获取协议列表
        protocols = await self.get_mantle_protocols()
        
        total_tvl = sum(p.tvl for p in protocols)
        
        # 从 DEX 数据中提取交易量
        total_volume = 0
        if isinstance(dex_data, dict):
            total_volume = dex_data.get("total24h", 0) or dex_data.get("totalVolume24h", 0)
        
        # 从费用数据中提取费用
        total_fees = 0
        if isinstance(fees_data, dict):
            total_fees = fees_data.get("total24h", 0) or fees_data.get("totalFees24h", 0)
        
        return ChainOverview(
            chain="Mantle",
            total_tvl=total_tvl,
            total_volume_24h=total_volume,
            total_fees_24h=total_fees,
            protocol_count=len(protocols),
            timestamp=datetime.utcnow().isoformat()
        )


# ============ Mantle RPC Client ============

class MantleDataCollector:
    """Mantle 链上数据收集器"""
    
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
        """连接到 Mantle RPC"""
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
        """确保连接可用"""
        if not self.w3 or not self.w3.is_connected():
            self._connect()
        return self._connected
    
    def get_latest_block(self) -> Optional[BlockData]:
        """获取最新区块数据"""
        if not self._ensure_connection():
            return None
        
        try:
            block = self.w3.eth.get_block('latest')
            return BlockData(
                number=block.number,
                hash=block.hash.hex(),
                timestamp=block.timestamp,
                timestamp_iso=datetime.fromtimestamp(block.timestamp).isoformat(),
                gas_used=block.gasUsed,
                gas_limit=block.gasLimit,
                gas_utilization=round(block.gasUsed / block.gasLimit * 100, 2) if block.gasLimit > 0 else 0,
                tx_count=len(block.transactions),
                size=block.size
            )
        except Exception as e:
            logger.error(f"Failed to get block: {e}")
            return None
    
    def get_gas_price(self) -> Optional[GasData]:
        """获取 Gas 价格"""
        if not self._ensure_connection():
            return None
        
        try:
            gas_price = self.w3.eth.gas_price
            return GasData(
                wei=gas_price,
                gwei=round(gas_price / 1e9, 4),
                mnt=round(gas_price / 1e18, 10),
                timestamp=datetime.utcnow().isoformat()
            )
        except Exception as e:
            logger.error(f"Failed to get gas price: {e}")
            return None
    
    def get_recent_blocks(self, count: int = 10) -> List[BlockData]:
        """获取最近多个区块"""
        if not self._ensure_connection():
            return []
        
        blocks = []
        try:
            latest = self.w3.eth.get_block('latest')
            for i in range(min(count, latest.number + 1)):
                try:
                    block = self.w3.eth.get_block(latest.number - i)
                    blocks.append(BlockData(
                        number=block.number,
                        hash=block.hash.hex(),
                        timestamp=block.timestamp,
                        timestamp_iso=datetime.fromtimestamp(block.timestamp).isoformat(),
                        gas_used=block.gasUsed,
                        gas_limit=block.gasLimit,
                        gas_utilization=round(block.gasUsed / block.gasLimit * 100, 2) if block.gasLimit > 0 else 0,
                        tx_count=len(block.transactions),
                        size=block.size
                    ))
                except Exception as e:
                    logger.warning(f"Failed to get block {latest.number - i}: {e}")
                    continue
        except Exception as e:
            logger.error(f"Failed to get recent blocks: {e}")
        
        return blocks
    
    def calculate_block_time(self, blocks: List[BlockData]) -> float:
        """计算平均出块时间"""
        if len(blocks) < 2:
            return 2.0  # Mantle 默认约 2 秒
        
        times = []
        for i in range(1, len(blocks)):
            dt = blocks[i-1].timestamp - blocks[i].timestamp
            times.append(dt)
        
        return sum(times) / len(times) if times else 2.0


# ============ Data Cache ============

class DataCache:
    """内存数据缓存"""
    
    def __init__(self, ttl: int = CACHE_TTL):
        self._cache: Dict[str, dict] = {}
        self._ttl = ttl
    
    def get(self, key: str) -> Optional[dict]:
        """获取缓存数据"""
        if key in self._cache:
            entry = self._cache[key]
            if datetime.utcnow() - entry["time"] < timedelta(seconds=self._ttl):
                return entry["data"]
            else:
                del self._cache[key]
        return None
    
    def set(self, key: str, data: dict):
        """设置缓存数据"""
        self._cache[key] = {
            "data": data,
            "time": datetime.utcnow()
        }
    
    def invalidate(self, key: str = None):
        """清除缓存"""
        if key:
            self._cache.pop(key, None)
        else:
            self._cache.clear()


# ============ Data Collector Service ============

class OnChainDataCollector:
    """链上数据收集服务"""
    
    def __init__(self):
        self.cache = DataCache()
        self.mantle = MantleDataCollector()
    
    async def get_protocols(self, force_refresh: bool = False) -> List[dict]:
        """获取 Mantle 协议数据"""
        cache_key = "mantle_protocols"
        
        if not force_refresh:
            cached = self.cache.get(cache_key)
            if cached:
                logger.info("Returning cached protocol data")
                return cached
        
        async with DeFiLlamaClient() as client:
            protocols = await client.get_mantle_protocols()
            result = [asdict(p) for p in protocols]
            self.cache.set(cache_key, result)
            return result
    
    async def get_overview(self, force_refresh: bool = False) -> dict:
        """获取 Mantle 链概览"""
        cache_key = "mantle_overview"
        
        if not force_refresh:
            cached = self.cache.get(cache_key)
            if cached:
                return cached
        
        async with DeFiLlamaClient() as client:
            overview = await client.get_mantle_overview()
            result = asdict(overview)
            self.cache.set(cache_key, result)
            return result
    
    def get_block_data(self) -> Optional[dict]:
        """获取最新区块数据"""
        block = self.mantle.get_latest_block()
        if block:
            return asdict(block)
        return None
    
    def get_gas_data(self) -> Optional[dict]:
        """获取 Gas 数据"""
        gas = self.mantle.get_gas_price()
        if gas:
            return asdict(gas)
        return None
    
    def get_network_stats(self) -> dict:
        """获取网络统计"""
        blocks = self.mantle.get_recent_blocks(10)
        avg_block_time = self.mantle.calculate_block_time(blocks)
        
        latest_block = blocks[0] if blocks else None
        
        return {
            "latest_block": latest_block.number if latest_block else 0,
            "avg_block_time_sec": round(avg_block_time, 2),
            "tx_count_latest": latest_block.tx_count if latest_block else 0,
            "gas_utilization": latest_block.gas_utilization if latest_block else 0,
            "timestamp": datetime.utcnow().isoformat()
        }
    
    async def get_all_data(self) -> dict:
        """获取所有数据（用于定时刷新）"""
        logger.info("Collecting all on-chain data...")
        
        # 并行获取数据
        protocols_task = self.get_protocols()
        overview_task = self.get_overview()
        
        protocols, overview = await asyncio.gather(
            protocols_task, 
            overview_task,
            return_exceptions=True
        )
        
        # RPC 数据（同步）
        block_data = self.get_block_data()
        gas_data = self.get_gas_data()
        network_stats = self.get_network_stats()
        
        result = {
            "timestamp": datetime.utcnow().isoformat(),
            "chain": "Mantle",
            "overview": overview if not isinstance(overview, Exception) else None,
            "protocols": protocols if not isinstance(protocols, Exception) else [],
            "block": block_data,
            "gas": gas_data,
            "network": network_stats,
        }
        
        # 缓存完整数据
        self.cache.set("full_data", result)
        
        logger.info("Data collection complete")
        return result


# ============ Scheduler ============

class DataRefreshScheduler:
    """数据刷新调度器"""
    
    def __init__(self, collector: OnChainDataCollector, interval: int = 900):
        self.collector = collector
        self.interval = interval
        self.running = False
        self.last_refresh = None
    
    async def start(self):
        """启动定时刷新"""
        self.running = True
        logger.info(f"Starting data refresh scheduler (interval: {self.interval}s)")
        
        while self.running:
            try:
                await self.collector.get_all_data()
                self.last_refresh = datetime.utcnow()
                logger.info(f"Data refreshed at {self.last_refresh.isoformat()}")
            except Exception as e:
                logger.error(f"Data refresh failed: {e}")
            
            await asyncio.sleep(self.interval)
    
    def stop(self):
        """停止定时刷新"""
        self.running = False
        logger.info("Data refresh scheduler stopped")


# ============ Main ============

async def main():
    """测试数据收集"""
    collector = OnChainDataCollector()
    
    # 测试获取所有数据
    data = await collector.get_all_data()
    
    print("\n" + "="*50)
    print("Mantle On-Chain Data")
    print("="*50)
    
    # 概览
    overview = data.get("overview")
    if overview:
        print(f"\n📊 Chain Overview:")
        print(f"  Total TVL: ${overview.get('total_tvl', 0):,.2f}")
        print(f"  24h Volume: ${overview.get('total_volume_24h', 0):,.2f}")
        print(f"  24h Fees: ${overview.get('total_fees_24h', 0):,.2f}")
        print(f"  Protocols: {overview.get('protocol_count', 0)}")
    
    # 协议列表
    protocols = data.get("protocols", [])
    if protocols:
        print(f"\n🏦 Top Protocols:")
        for i, p in enumerate(protocols[:5], 1):
            print(f"  {i}. {p.get('protocol_name', 'Unknown')}: "
                  f"${p.get('tvl', 0):,.2f} ({p.get('category', 'Unknown')})")
    
    # 区块数据
    block = data.get("block")
    if block:
        print(f"\n⛏️  Latest Block:")
        print(f"  Number: {block.get('number')}")
        print(f"  Transactions: {block.get('tx_count')}")
        print(f"  Gas Utilization: {block.get('gas_utilization')}%")
    
    # Gas
    gas = data.get("gas")
    if gas:
        print(f"\n⛽ Gas Price:")
        print(f"  {gas.get('gwei')} gwei")
    
    # 网络统计
    network = data.get("network")
    if network:
        print(f"\n🌐 Network Stats:")
        print(f"  Avg Block Time: {network.get('avg_block_time_sec')}s")
    
    print("\n" + "="*50)


if __name__ == "__main__":
    asyncio.run(main())
