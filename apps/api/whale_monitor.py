"""
Mantle DeFAI Trader - Whale Monitor
大额转账监控 & 稳定币流动追踪

功能：
1. 大额转账监控 - 扫描最近 N 个区块，检测 MNT/USDC/USDT 大额转账
2. 稳定币流动追踪 - 统计 USDC/USDT 总流入/流出
3. 内存缓存，3 分钟 TTL
"""

import asyncio
import json
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, asdict, field
from datetime import datetime, timedelta
from loguru import logger
from functools import wraps

from web3 import Web3

# ============ Configuration ============
MANTLE_RPC_URL = "https://rpc.mantle.xyz"

# Token Addresses
USDC = "0x09Bc4E0D864854c6aFB6eB9A9cdF58aC190D0dF9"
USDT = "0x201EBa5CC46D216Ce6DC03F6a759e8E766e956aE"
WMNT = "0x78c1b0C915c4FAA5FffA6CAbf0219DA63d7f4cb8"

# Token decimals
TOKEN_DECIMALS = {
    WMNT.lower(): 18,
    USDC.lower(): 6,
    USDT.lower(): 6,
}

# Thresholds
MNT_THRESHOLD = 100  # 100 MNT
STABLECOIN_THRESHOLD = 100_000  # 100,000 USDC/USDT

# Cache TTL
CACHE_TTL_SECONDS = 900  # 15 minutes

# ERC20 Transfer event signature
TRANSFER_EVENT_SIGNATURE = Web3.keccak(text="Transfer(address,address,uint256)").hex()

# ERC20 minimal ABI for decoding
ERC20_MINIMAL_ABI = [
    {
        "anonymous": False,
        "inputs": [
            {"indexed": True, "name": "from", "type": "address"},
            {"indexed": True, "name": "to", "type": "address"},
            {"indexed": False, "name": "value", "type": "uint256"},
        ],
        "name": "Transfer",
        "type": "event",
    }
]


# ============ Data Models ============

@dataclass
class WhaleTransfer:
    """大额转账记录"""
    tx_hash: str
    from_address: str
    to_address: str
    amount: float
    token: str
    token_address: str
    value_usd: float
    timestamp: int
    block_number: int


@dataclass
class FundFlowResult:
    """稳定币资金流向结果"""
    token: str
    token_address: str
    total_inflow: float
    total_outflow: float
    net_flow: float
    large_transfers: List[WhaleTransfer] = field(default_factory=list)


@dataclass
class WhaleScanResult:
    """大额转账扫描结果"""
    transfers: List[WhaleTransfer]
    scanned_blocks: int
    start_block: int
    end_block: int
    timestamp: str


# ============ Simple Cache ============

class WhaleCache:
    """内存缓存，带 TTL"""

    def __init__(self, ttl: int = CACHE_TTL_SECONDS):
        self._cache: Dict[str, Dict[str, Any]] = {}
        self._ttl = ttl
        self._lock = asyncio.Lock()

    async def get(self, key: str) -> Optional[Any]:
        async with self._lock:
            entry = self._cache.get(key)
            if not entry:
                return None
            if datetime.utcnow() - entry["time"] < timedelta(seconds=self._ttl):
                return entry["data"]
            del self._cache[key]
            return None

    async def set(self, key: str, data: Any):
        async with self._lock:
            self._cache[key] = {
                "data": data,
                "time": datetime.utcnow(),
            }

    async def invalidate(self, key: str = None):
        async with self._lock:
            if key:
                self._cache.pop(key, None)
            else:
                self._cache.clear()


# ============ Whale Monitor ============

class WhaleMonitor:
    """大额转账监控 & 稳定币流动追踪"""

    def __init__(self, rpc_url: str = MANTLE_RPC_URL):
        self.rpc_urls = [
            rpc_url,
            "https://mantle-rpc.publicnode.com",
            "https://mantle.drpc.org",
        ]
        self.w3: Optional[Web3] = None
        self._connected = False
        self._current_rpc_index = 0
        self._cache = WhaleCache()
        self._scanned_blocks: set = set()
        self._connect()

    def _connect(self):
        """连接到 Mantle RPC（带 fallback）"""
        for i, url in enumerate(self.rpc_urls[self._current_rpc_index :], self._current_rpc_index):
            try:
                w3 = Web3(Web3.HTTPProvider(url, request_kwargs={"timeout": 5}))
                if w3.is_connected():
                    self.w3 = w3
                    self._connected = True
                    self._current_rpc_index = i
                    logger.info(f"[WhaleMonitor] Connected to Mantle RPC: {url}")
                    return
            except Exception as e:
                logger.warning(f"[WhaleMonitor] Failed to connect to {url}: {e}")

        self._connected = False
        logger.error("[WhaleMonitor] All Mantle RPCs failed")

    def _ensure_connection(self) -> bool:
        if not self.w3 or not self.w3.is_connected():
            self._connect()
        return self._connected

    def _get_token_decimals(self, token_address: str) -> int:
        return TOKEN_DECIMALS.get(token_address.lower(), 18)

    def _format_amount(self, raw_amount: int, token_address: str) -> float:
        decimals = self._get_token_decimals(token_address)
        return raw_amount / (10 ** decimals)

    def _get_token_symbol(self, token_address: str) -> str:
        addr_lower = token_address.lower()
        if addr_lower == WMNT.lower():
            return "MNT"
        if addr_lower == USDC.lower():
            return "USDC"
        if addr_lower == USDT.lower():
            return "USDT"
        return "UNKNOWN"

    def _decode_transfer_log(self, log: Dict) -> Optional[Dict]:
        """解析 ERC20 Transfer 事件日志"""
        try:
            topics = log.get("topics", [])
            if len(topics) < 3:
                return None

            # topic[0] = event signature
            if topics[0].hex() != TRANSFER_EVENT_SIGNATURE:
                return None

            # indexed params: from, to
            from_addr = "0x" + topics[1].hex()[-40:]
            to_addr = "0x" + topics[2].hex()[-40:]

            # non-indexed param: value
            data = log.get("data", "0x")
            if isinstance(data, str):
                value = int(data, 16) if data.startswith("0x") else int(data)
            else:
                value = int(data.hex(), 16)

            return {
                "from": Web3.to_checksum_address(from_addr),
                "to": Web3.to_checksum_address(to_addr),
                "value": value,
                "token_address": log.get("address", ""),
            }
        except Exception as e:
            logger.debug(f"[WhaleMonitor] Failed to decode log: {e}")
            return None

    def _is_large_transfer(self, token_address: str, amount: float) -> bool:
        """判断是否为大额转账"""
        addr_lower = token_address.lower()
        if addr_lower == WMNT.lower():
            return amount >= MNT_THRESHOLD
        if addr_lower in (USDC.lower(), USDT.lower()):
            return amount >= STABLECOIN_THRESHOLD
        return False

    def _get_token_price_usd(self, token_symbol: str) -> float:
        """获取代币 USD 价格（简化版，使用固定价格）"""
        # 实际项目中可以从 price oracle 或 Binance API 获取
        prices = {
            "MNT": 0.8,
            "USDC": 1.0,
            "USDT": 1.0,
        }
        return prices.get(token_symbol, 0.0)

    def scan_blocks(self, num_blocks: int = 10) -> WhaleScanResult:
        """扫描最近 N 个区块的大额转账"""
        if not self._ensure_connection():
            logger.error("[WhaleMonitor] RPC not connected")
            return WhaleScanResult(
                transfers=[],
                scanned_blocks=0,
                start_block=0,
                end_block=0,
                timestamp=datetime.utcnow().isoformat(),
            )

        try:
            latest_block = self.w3.eth.get_block("latest")
            end_block = latest_block.number
            start_block = max(end_block - num_blocks + 1, 0)

            transfers: List[WhaleTransfer] = []
            scanned_count = 0

            for block_num in range(start_block, end_block + 1):
                # 避免重复扫描
                if block_num in self._scanned_blocks:
                    continue

                try:
                    block = self.w3.eth.get_block(block_num, full_transactions=True)
                    scanned_count += 1
                    self._scanned_blocks.add(block_num)

                    # 清理旧扫描记录，防止内存无限增长
                    if len(self._scanned_blocks) > 500:
                        self._scanned_blocks = set(
                            sorted(self._scanned_blocks)[-250:]
                        )

                    # 1. 检查原生 MNT 转账
                    for tx in block.transactions:
                        if tx.value and tx.value > 0:
                            amount = self._format_amount(tx.value, WMNT)
                            if amount >= MNT_THRESHOLD:
                                token_symbol = "MNT"
                                price_usd = self._get_token_price_usd(token_symbol)
                                transfers.append(
                                    WhaleTransfer(
                                        tx_hash=tx.hash.hex(),
                                        from_address=tx["from"],
                                        to_address=tx.to,
                                        amount=round(amount, 6),
                                        token=token_symbol,
                                        token_address=WMNT,
                                        value_usd=round(amount * price_usd, 2),
                                        timestamp=block.timestamp,
                                        block_number=block_num,
                                    )
                                )

                    # 2. 检查 ERC20 Transfer 事件
                    # 获取区块的 logs（通过 filter）
                    try:
                        logs = self.w3.eth.get_logs(
                            {
                                "fromBlock": block_num,
                                "toBlock": block_num,
                                "topics": [TRANSFER_EVENT_SIGNATURE],
                            }
                        )
                        for log in logs:
                            decoded = self._decode_transfer_log(log)
                            if not decoded:
                                continue

                            token_addr = decoded["token_address"]
                            if token_addr.lower() not in (
                                USDC.lower(),
                                USDT.lower(),
                            ):
                                continue

                            amount = self._format_amount(
                                decoded["value"], token_addr
                            )
                            if amount < STABLECOIN_THRESHOLD:
                                continue

                            token_symbol = self._get_token_symbol(token_addr)
                            price_usd = self._get_token_price_usd(token_symbol)

                            transfers.append(
                                WhaleTransfer(
                                    tx_hash=log.get(
                                        "transactionHash", ""
                                    ).hex()
                                    if hasattr(log.get("transactionHash", ""), "hex")
                                    else str(log.get("transactionHash", "")),
                                    from_address=decoded["from"],
                                    to_address=decoded["to"],
                                    amount=round(amount, 6),
                                    token=token_symbol,
                                    token_address=token_addr,
                                    value_usd=round(amount * price_usd, 2),
                                    timestamp=block.timestamp,
                                    block_number=block_num,
                                )
                            )
                    except Exception as e:
                        logger.warning(
                            f"[WhaleMonitor] Failed to get logs for block {block_num}: {e}"
                        )

                except Exception as e:
                    logger.warning(
                        f"[WhaleMonitor] Failed to scan block {block_num}: {e}"
                    )
                    continue

            # 按金额排序
            transfers.sort(key=lambda x: x.value_usd, reverse=True)

            result = WhaleScanResult(
                transfers=transfers,
                scanned_blocks=scanned_count,
                start_block=start_block,
                end_block=end_block,
                timestamp=datetime.utcnow().isoformat(),
            )

            logger.info(
                f"[WhaleMonitor] Scanned {scanned_count} blocks, found {len(transfers)} large transfers"
            )
            return result

        except Exception as e:
            logger.error(f"[WhaleMonitor] Scan failed: {e}")
            return WhaleScanResult(
                transfers=[],
                scanned_blocks=0,
                start_block=0,
                end_block=0,
                timestamp=datetime.utcnow().isoformat(),
            )

    async def get_large_transfers(self, num_blocks: int = 10) -> WhaleScanResult:
        """获取大额转账列表（带缓存）"""
        cache_key = f"whale_transfers_{num_blocks}"
        cached = await self._cache.get(cache_key)
        if cached:
            logger.info("[WhaleMonitor] Returning cached whale transfers")
            return cached

        # web3.py 是同步的，在线程池中执行
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(None, self.scan_blocks, num_blocks)

        await self._cache.set(cache_key, result)
        return result

    async def get_fund_flow(self, num_blocks: int = 10) -> List[FundFlowResult]:
        """获取稳定币资金流向（带缓存）"""
        cache_key = f"fund_flow_{num_blocks}"
        cached = await self._cache.get(cache_key)
        if cached:
            logger.info("[WhaleMonitor] Returning cached fund flow")
            return cached

        # 先获取大额转账数据
        scan_result = await self.get_large_transfers(num_blocks)

        # 按 token 分组统计
        usdc_transfers = [
            t for t in scan_result.transfers if t.token == "USDC"
        ]
        usdt_transfers = [
            t for t in scan_result.transfers if t.token == "USDT"
        ]

        # 识别交易所地址（简化版 - 使用已知交易所地址）
        # 实际项目中可以从数据库或 API 获取
        exchange_addresses = self._get_exchange_addresses()

        results = []
        for token_name, token_addr, transfers in [
            ("USDC", USDC, usdc_transfers),
            ("USDT", USDT, usdt_transfers),
        ]:
            total_inflow = 0.0
            total_outflow = 0.0
            large_txs = []

            for t in transfers:
                is_from_exchange = t.from_address.lower() in exchange_addresses
                is_to_exchange = t.to_address.lower() in exchange_addresses

                if is_from_exchange and not is_to_exchange:
                    # 从交易所流出 = 市场流入
                    total_inflow += t.amount
                elif is_to_exchange and not is_from_exchange:
                    # 流入交易所 = 市场流出
                    total_outflow += t.amount

                large_txs.append(t)

            results.append(
                FundFlowResult(
                    token=token_name,
                    token_address=token_addr,
                    total_inflow=round(total_inflow, 2),
                    total_outflow=round(total_outflow, 2),
                    net_flow=round(total_inflow - total_outflow, 2),
                    large_transfers=large_txs[:20],  # 最多返回 20 条
                )
            )

        await self._cache.set(cache_key, results)
        return results

    def _get_exchange_addresses(self) -> set:
        """获取已知交易所地址（Mantle 链上）"""
        # 这些是示例地址，实际使用时应更新为真实的 Mantle 交易所地址
        # 或从数据库/API 动态获取
        return {
            # 示例占位地址
            "0x0000000000000000000000000000000000000000".lower(),
        }

    def to_dict(self, obj: Any) -> Any:
        """将 dataclass 转换为可 JSON 序列化的 dict"""
        if hasattr(obj, "__dataclass_fields__"):
            result = {}
            for k, v in asdict(obj).items():
                result[k] = self.to_dict(v)
            return result
        elif isinstance(obj, list):
            return [self.to_dict(item) for item in obj]
        elif isinstance(obj, dict):
            return {k: self.to_dict(v) for k, v in obj.items()}
        return obj


# ============ Singleton ============

whale_monitor = WhaleMonitor()


# ============ Main (for testing) ============

async def main():
    monitor = WhaleMonitor()
    print("=" * 60)
    print("🐋 Whale Monitor Test")
    print("=" * 60)

    # 测试大额转账扫描
    print("\n📊 Scanning for large transfers...")
    result = await monitor.get_large_transfers(num_blocks=5)
    print(f"Scanned blocks: {result.start_block} - {result.end_block}")
    print(f"Found {len(result.transfers)} large transfers")

    for t in result.transfers[:5]:
        print(
            f"  {t.token}: {t.amount:,.2f} (${t.value_usd:,.2f}) "
            f"from {t.from_address[:12]}... to {t.to_address[:12]}... "
            f"[Block {t.block_number}]"
        )

    # 测试资金流向
    print("\n💰 Fund Flow Analysis...")
    flows = await monitor.get_fund_flow(num_blocks=5)
    for flow in flows:
        print(f"\n  {flow.token}:")
        print(f"    Inflow:  ${flow.total_inflow:,.2f}")
        print(f"    Outflow: ${flow.total_outflow:,.2f}")
        print(f"    Net:     ${flow.net_flow:,.2f}")

    print("\n" + "=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
