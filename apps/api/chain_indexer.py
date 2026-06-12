"""
Mantle DeFAI Trader - Multi-Chain Transaction Indexer
多链交易数据采集器

Supports: Mantle, Ethereum, BNB Chain (via Blockscout), Solana (via Solscan)
"""

import aiohttp
import asyncio
from typing import List, Dict, Optional, Any
from datetime import datetime, timedelta
from loguru import logger

from moralis_client import MoralisClient
from token_mapping import get_recommended_tokens_for_monitoring

# ============ Configuration ============

BLOCKSCOUT_URLS = {
    "mantle": "https://explorer.mantle.xyz/api",
    "ethereum": "https://eth.blockscout.com/api",
    "bnb": "https://bnb.blockscout.com/api",
    "polygon": "https://polygon.blockscout.com/api",
    "arbitrum": "https://arbitrum.blockscout.com/api",
    "optimism": "https://optimism.blockscout.com/api",
    "base": "https://base.blockscout.com/api",
}

SOLSCAN_BASE = "https://public-api.solscan.io"

# Popular token addresses for fallback queries (when no contract_address given)
POPULAR_TOKENS = {
    "ethereum": [
        "0xA0b86a33E6441e3C1E6a2d3e3e8B0B8F5B9E4C6D",  # placeholder - will try anyway
        "0xdAC17F958D2ee523a2206206994597C13D831ec7",  # USDT
        "0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48",  # USDC
    ],
    "bnb": [
        "0x55d398326f99059fF775485246999027B3197955",  # USDT
        "0xe9e7CEA3DedcA5984780Bafc599bD69ADd087D56",  # BUSD
    ],
    "mantle": [
        "0x09Bc4E0D864854c6aFB6eB9A9cdF58aC190D0dF9",  # USDC
        "0x201EBa5CC46D216Ce6DC03F6a759e8E766e956aE",  # USDT
        "0x78c1b0C915c4FAA5FffA6CAbf0219DA63d7f4cb8",  # WMNT
    ],
    "polygon": [
        "0x2791Bca1f2de4661ED88A30C99A7a9449Aa84174",  # USDC
        "0xc2132D05D31c914a87C6611C10748AEb04B58e8F",  # USDT
        "0x7ceB23fD6bC0adD59E62ac25578270cFf1b9f619",  # WETH
        "0x1BFD67037B42Cf73acF2047067bd4F2C47D9BfD6",  # WBTC
        "0x0d500B1d8E8eF31E21C99d1Db9A6444d3ADf1270",  # WMATIC
    ],
    "arbitrum": [
        "0xFF970A61A04b1cA14834A43f5dE4533eBDDB5CC8",  # USDC
        "0xFd086bC7CD5C481DCC9C85ebE478A1C0b69FCbb9",  # USDT
        "0x82aF49447D8a07e3bd95BD0d56f35241523fBab1",  # WETH
        "0x2f2a2543B76A4166549F7aaB2e75Bef0aefC5B0f",  # WBTC
        "0x912CE59144191C1204E64559FE8253a0e49E6548",  # ARB
    ],
    "optimism": [
        "0x7F5c764cBc14f9669B88837ca1490cCa17c31607",  # USDC
        "0x94b008aA00579c1307B0EF2c499aD98a8ce58e58",  # USDT
        "0x4200000000000000000000000000000000000006",  # WETH
        "0x4200000000000000000000000000000000000042",  # OP
    ],
    "base": [
        "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913",  # USDC
        "0xfde4C96c8593536E31F229EA8f37b2ADa2699bb2",  # USDT
        "0x4200000000000000000000000000000000000006",  # WETH
    ],
    "solana": [
        "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",  # USDC
        "Es9vMFrzaCERmJfrF4H2FYD4KCoNkY11McCe8BenwNYB",  # USDT
        "So11111111111111111111111111111111111111112",   # SOL
    ],
}

def _is_placeholder_address(address: str) -> bool:
    """检查地址是否为占位符"""
    if not address or address.startswith("0x0000") or address.startswith("0xdddd") or address.startswith("0xDEAD"):
        return True
    if len(address) < 20:
        return True
    return False


# Popular protocol contract addresses for tx classification
PROTOCOL_ADDRESSES = {
    "ethereum": {
        # Uniswap
        "0x7a250d5630B4cF539739dF2C5dAcb4c659F2488D": "Uniswap V2",
        "0xE592427A0AEce92De3Edee1F18E0157C05861564": "Uniswap V3",
        "0x68b3465833fb72A70ecDF485E0e4C7bD8665Fc45": "Uniswap V3 Router",
        "0x1F98431c8aD98523631AE4a59f267346ea31F984": "Uniswap V3 Factory",
        # SushiSwap
        "0xd9e1cE17f2641f24aE83637ab66a2cca9C378B9F": "SushiSwap",
        "0x1b02dA8Cb0d097eB8D57A175b88c7D8b47997506": "SushiSwap V2",
        # Curve
        "0xbEbc44782C7dB0a1A60Cb6fe97d0b483032FF1C7": "Curve 3pool",
        "0xD51a44d3FaE010294C616388b506AcdA1bfAAe46": "Curve tricrypto",
        # Balancer
        "0xBA12222222228d8Ba445958a75a0704d566BF2C8": "Balancer",
        # 1inch
        "0x1111111254eeb25477b68fb85ed929f73a960582": "1inch",
        # 0x
        "0xDef1C0ded9bec7F1a1670819833240f027b25EfF": "0x",
        # KyberSwap
        "0x617Dee16B86534a5d792A4d7A62FB491B544111E": "KyberSwap",
        # DODO
        "0xa356867fDCEa8e71AEaF87805808803806231FdC": "DODO",
    },
    "bnb": {
        "0x10ED43C718714eb63d5aA57B78B54704E256024E": "PancakeSwap V2",
        "0x13f4EA83D0bd40E75C8222255bc855a974568Dd4": "PancakeSwap V3",
        "0x1b02dA8Cb0d097eB8D57A175b88c7D8b47997506": "SushiSwap",
        "0x3a6d8cA21D1CF76F653A67577FA0D27453350dD8": "Biswap",
        "0xcF0feBd3f17CEf5b47B0cD257aCf02D0243cF3E2": "ApeSwap",
        "0x1111111254eeb25477b68fb85ed929f73a960582": "1inch",
        "0x617Dee16B86534a5d792A4d7A62FB491B544111E": "KyberSwap",
    },
    "mantle": {
        "0x48d0F097DB66c8FbfdF23C96cD7Eaf1c4AE8Eea9": "Merchant Moe",
        "0x7A9716671C2896604FcAfD94440D140e5531C7B8": "FusionX",
        "0xDC71A854D6fD4220541b6eCb4a832968B09e22d5": "Agni Finance",
        "0x0c863F04e4423Aad4e6c7495B73125fEr47B34a8": "iZiSwap",
        "0x8536d534Bd46F04c3A85B077E1F3c3B4C1bB07C1": "Odos",
    },
    "polygon": {
        "0xa5E0829CaCEd8fFDD4De3c43696c57F7D7A678ff": "QuickSwap",
        "0x1b02dA8Cb0d097eB8D57A175b88c7D8b47997506": "SushiSwap",
        "0xbEbc44782C7dB0a1A60Cb6fe97d0b483032FF1C7": "Curve",
        "0x794a61358D6845594F94dc1DB02A252b5b4814aD": "Aave V3",
        "0x1111111254eeb25477b68fb85ed929f73a960582": "1inch",
    },
    "arbitrum": {
        "0xc31e54c7a869b9fcbecc14363cf510d1c41fa443": "Camelot",
        "0x7bf5f5ee74685ddfa859ae6b630911d3197a7d24": "TraderJoe",
        "0x1b02dA8Cb0d097eB8D57A175b88c7D8b47997506": "SushiSwap",
        "0xbEbc44782C7dB0a1A60Cb6fe97d0b483032FF1C7": "Curve",
        "0x489ee077994B6658eAfA855C308275EAd8097C4A": "GMX",
        "0x1111111254eeb25477b68fb85ed929f73a960582": "1inch",
    },
    "optimism": {
        "0x9c12939390052919aF3155f41bf4160fd3666A6f": "Velodrome",
        "0x1b02dA8Cb0d097eB8D57A175b88c7D8b47997506": "SushiSwap",
        "0xbEbc44782C7dB0a1A60Cb6fe97d0b483032FF1C7": "Curve",
        "0x1111111254eeb25477b68fb85ed929f73a960582": "1inch",
    },
    "base": {
        "0xcF77c3f7ae10dbdEEd57beB0dfC24E824D2f6b8D": "Aerodrome",
        "0x1b02dA8Cb0d097eB8D57A175b88c7D8b47997506": "SushiSwap",
        "0xbEbc44782C7dB0a1A60Cb6fe97d0b483032FF1C7": "Curve",
        "0x68b3465833fb72A70ecDF485E0e4C7bD8665Fc45": "BaseSwap",
        "0x1111111254eeb25477b68fb85ed929f73a960582": "1inch",
    },
}

def detect_protocol(chain: str, to_addr: Optional[str], from_addr: Optional[str]) -> tuple:
    """检测交易类型和协议名称。返回 (tx_type, protocol)

    通过匹配 to_address 或 from_address 与已知 DEX/协议合约地址，
    判断交易是否为 swap 以及发生在哪个协议。
    """
    if not to_addr and not from_addr:
        return "transfer", None

    to_lower = (to_addr or "").lower()
    from_lower = (from_addr or "").lower()

    chain_protocols = PROTOCOL_ADDRESSES.get(chain, {})
    for addr, name in chain_protocols.items():
        addr_lower = addr.lower()
        if to_lower == addr_lower or from_lower == addr_lower:
            return "swap", name

    return "transfer", None

# Hot wallets for Moralis monitoring
HOT_WALLETS = {
    "ethereum": [],
    "bnb": [],
    "mantle": [],
}

class ChainIndexer:
    """Multi-chain transaction data collector using Blockscout and Solscan APIs."""

    def __init__(self, session: Optional[aiohttp.ClientSession] = None):
        self.session = session or aiohttp.ClientSession()
        self.blockscout_urls = BLOCKSCOUT_URLS
        self.solscan_base = SOLSCAN_BASE
        self.moralis = MoralisClient()
        self._tx_hash_protocol_cache: Dict[str, tuple] = {}

    async def close(self):
        """Close the aiohttp session."""
        if self.session:
            await self.session.close()

    # ========== Blockscout (EVM Chains) ==========

    async def fetch_blockscout(self, chain: str, params: Dict[str, str]) -> Optional[List[Dict]]:
        """Call Blockscout API for a given EVM chain."""
        url = self.blockscout_urls.get(chain)
        if not url:
            logger.warning(f"[ChainIndexer] Unsupported chain for Blockscout: {chain}")
            return None
        try:
            async with self.session.get(
                url, params=params, timeout=aiohttp.ClientTimeout(total=30)
            ) as resp:
                if resp.status != 200:
                    logger.warning(f"[ChainIndexer] Blockscout {chain} HTTP {resp.status}")
                    return None
                data = await resp.json()
                if data.get("status") == "1" and "result" in data:
                    return data["result"]
                return None
        except Exception as e:
            logger.error(f"[ChainIndexer] Blockscout {chain} fetch error: {e}")
            return None

    async def get_latest_block(self, chain: str) -> Optional[int]:
        """Get latest block number from Blockscout."""
        result = await self.fetch_blockscout(chain, {
            "module": "proxy",
            "action": "eth_blockNumber",
        })
        if result:
            try:
                return int(result, 16)
            except (ValueError, TypeError):
                pass
        return None

    async def get_token_transfers(
        self,
        chain: str,
        contract_address: Optional[str] = None,
        start_block: Optional[int] = None,
        end_block: Optional[int] = None,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        """Fetch ERC-20 token transfers from Blockscout."""
        # If no contract address provided, query popular tokens in parallel
        if not contract_address:
            tokens = POPULAR_TOKENS.get(chain, [])
            if not tokens:
                return []
            tasks = [
                self.get_token_transfers(
                    chain=chain,
                    contract_address=addr,
                    start_block=start_block,
                    end_block=end_block,
                    limit=max(limit // len(tokens), 10),
                )
                for addr in tokens
            ]
            results = await asyncio.gather(*tasks, return_exceptions=True)
            all_txs = []
            for r in results:
                if isinstance(r, list):
                    all_txs.extend(r)
            # Sort by block time desc
            all_txs.sort(key=lambda x: x.get("block_time", datetime.min), reverse=True)
            return all_txs[:limit]

        params = {
            "module": "account",
            "action": "tokentx",
            "sort": "desc",
            "page": "1",
            "offset": str(limit),
        }
        params["contractaddress"] = contract_address
        if start_block is not None:
            params["startblock"] = str(start_block)
        if end_block is not None:
            params["endblock"] = str(end_block)

        result = await self.fetch_blockscout(chain, params)
        if not result:
            return []

        txs = []
        for item in result:
            try:
                tx = await self._parse_evm_transfer(chain, item)
                if tx:
                    txs.append(tx)
            except Exception as e:
                logger.debug(f"[ChainIndexer] Parse error: {e}")
                continue
        return txs

    async def fetch_transaction_by_hash(self, chain: str, tx_hash: str) -> Optional[Dict[str, Any]]:
        """通过 Blockscout proxy API 获取原始交易信息"""
        url = self.blockscout_urls.get(chain)
        if not url:
            return None
        try:
            params = {
                "module": "proxy",
                "action": "eth_getTransactionByHash",
                "txhash": tx_hash,
            }
            async with self.session.get(url, params=params, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                if resp.status != 200:
                    return None
                data = await resp.json()
                if data.get("result") and isinstance(data["result"], dict):
                    return data["result"]
                return None
        except Exception as e:
            logger.debug(f"[ChainIndexer] fetch tx by hash error: {e}")
            return None

    async def detect_protocol_by_tx_hash(self, chain: str, tx_hash: str) -> tuple:
        """通过 tx_hash 查询原始交易，检测协议。返回 (tx_type, protocol)"""
        cache_key = f"{chain}:{tx_hash}"
        if cache_key in self._tx_hash_protocol_cache:
            return self._tx_hash_protocol_cache[cache_key]

        tx = await self.fetch_transaction_by_hash(chain, tx_hash)
        if not tx:
            return "transfer", None

        to_addr = tx.get("to", "")
        from_addr = tx.get("from", "")
        tx_type, protocol = detect_protocol(chain, to_addr, from_addr)

        self._tx_hash_protocol_cache[cache_key] = (tx_type, protocol)
        return tx_type, protocol

    async def _parse_evm_transfer(self, chain: str, item: Dict) -> Optional[Dict[str, Any]]:
        """Parse a single Blockscout transfer record into standard dict format."""
        token_decimal = int(item.get("tokenDecimal", "0") or "0")
        amount_raw = item.get("value", "0")
        amount = (
            float(amount_raw) / (10 ** token_decimal)
            if token_decimal > 0
            else float(amount_raw)
        )

        tx_type, protocol = detect_protocol(chain, item.get("to"), item.get("from"))

        # 如果精确匹配失败，尝试通过 tx_hash 查询原始交易
        tx_hash = item.get("hash")
        if tx_type == "transfer" and tx_hash:
            try:
                tx_type, protocol = await self.detect_protocol_by_tx_hash(chain, tx_hash)
            except Exception:
                pass

        return {
            "chain": chain,
            "tx_hash": tx_hash,
            "block_number": int(item.get("blockNumber", "0") or "0"),
            "block_time": datetime.fromtimestamp(int(item.get("timeStamp", "0") or "0")),
            "from_address": item.get("from"),
            "to_address": item.get("to"),
            "token_address": item.get("contractAddress"),
            "token_symbol": item.get("tokenSymbol") or "UNKNOWN",
            "token_amount": amount,
            "token_amount_usd": None,
            "tx_type": tx_type,
            "category": None,
            "protocol": protocol,
        }

    # ========== Moralis (补充采集) ==========

    async def fetch_moralis_transfers(
        self, chain: str, token_address: str, limit: int = 100
    ) -> List[Dict[str, Any]]:
        """通过 Moralis 获取代币转账记录"""
        return await self.moralis.get_token_transfers(chain, token_address, limit)

    async def fetch_moralis_wallet_transfers(
        self, chain: str, limit: int = 100
    ) -> List[Dict[str, Any]]:
        """通过 Moralis 获取热点钱包转账记录"""
        wallets = HOT_WALLETS.get(chain, [])
        if not wallets:
            return []
        all_txs = []
        for wallet in wallets:
            txs = await self.moralis.get_wallet_transfers(chain, wallet, limit)
            all_txs.extend(txs)
        return all_txs

    # ========== Solana (Solscan) ==========

    async def fetch_solscan(self, endpoint: str, params: Optional[Dict] = None) -> Optional[Any]:
        """Call Solscan Public API."""
        url = f"{self.solscan_base}{endpoint}"
        try:
            async with self.session.get(
                url, params=params, timeout=aiohttp.ClientTimeout(total=30)
            ) as resp:
                if resp.status != 200:
                    logger.warning(f"[ChainIndexer] Solscan HTTP {resp.status}")
                    return None
                return await resp.json()
        except Exception as e:
            logger.error(f"[ChainIndexer] Solscan fetch error: {e}")
            return None

    async def get_solana_transactions(
        self,
        token_address: Optional[str] = None,
        hours_back: int = 1,
        limit: int = 50,
    ) -> List[Dict[str, Any]]:
        """Fetch recent Solana transactions via Solscan (simplified)."""
        if not token_address:
            logger.info("[ChainIndexer] Solana: no token_address provided, skipping")
            return []

        data = await self.fetch_solscan("/account/transactions", {
            "address": token_address,
            "limit": limit,
        })
        if not data:
            return []

        txs = []
        cutoff = datetime.utcnow() - timedelta(hours=hours_back)
        for item in data:
            try:
                block_time = datetime.fromtimestamp(item.get("blockTime", 0) or 0)
                if block_time < cutoff:
                    continue
                signers = item.get("signer", [])
                txs.append({
                    "chain": "solana",
                    "tx_hash": item.get("txHash"),
                    "block_number": item.get("slot"),
                    "block_time": block_time,
                    "from_address": signers[0] if isinstance(signers, list) and signers else None,
                    "to_address": None,
                    "token_address": token_address,
                    "token_symbol": None,
                    "token_amount": None,
                    "token_amount_usd": None,
                    "tx_type": "transfer",
                    "category": None,
                    "protocol": None,
                })
            except Exception as e:
                logger.debug(f"[ChainIndexer] Solana parse error: {e}")
                continue
        return txs

    # ========== 基于情绪分析的推荐币种多链采集 ==========

    async def collect_recommended_token_transfers(
        self, hours_back: int = 1, limit_per_token: int = 100
    ) -> List[Dict[str, Any]]:
        """
        基于情绪分析推荐币种，采集多链大额转账。

        流程：
        1. 从 token_mapping 获取当前推荐的做多/做空币种列表
        2. 对每个币种在每个链上的合约地址，调用 Moralis get_token_transfers
        3. 过滤出 hours_back 时间范围内的交易
        4. 在结果中附加 source_symbol, direction, confidence 元数据
        5. 返回统一格式的交易列表
        """
        recommended = await get_recommended_tokens_for_monitoring()
        if not recommended:
            logger.info("[ChainIndexer] No recommended tokens for monitoring, returning empty list")
            return []

        cutoff = datetime.utcnow() - timedelta(hours=hours_back)
        semaphore = asyncio.Semaphore(5)
        all_txs: List[Dict[str, Any]] = []

        async def _fetch_one(entry: Dict[str, Any]) -> List[Dict[str, Any]]:
            token_address = entry.get("address", "")
            chain = entry.get("chain", "")
            symbol_alias = entry.get("symbol_alias", "UNKNOWN")
            source_symbol = entry.get("source_symbol", "")
            direction = entry.get("direction", "")
            confidence = entry.get("confidence", "low")

            if _is_placeholder_address(token_address):
                logger.warning(
                    f"[ChainIndexer] Skipping placeholder address for {source_symbol} "
                    f"on {chain}: {token_address}"
                )
                return []

            async with semaphore:
                try:
                    txs = await self.moralis.get_token_transfers(
                        chain, token_address, limit=limit_per_token
                    )
                except Exception as e:
                    logger.warning(
                        f"[ChainIndexer] Moralis fetch failed for {source_symbol} "
                        f"({symbol_alias}) on {chain}: {e}"
                    )
                    return []

            # 过滤时间范围并附加元数据
            result: List[Dict[str, Any]] = []
            for tx in txs:
                block_time = tx.get("block_time")
                if not block_time or block_time < cutoff:
                    continue
                tx["source_symbol"] = source_symbol
                tx["direction"] = direction
                tx["confidence"] = confidence
                tx["token_symbol"] = symbol_alias
                result.append(tx)

            logger.debug(
                f"[ChainIndexer] Fetched {len(result)} txs for {source_symbol} "
                f"({symbol_alias}) on {chain} within last {hours_back}h"
            )
            return result

        tasks = [_fetch_one(entry) for entry in recommended]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        for r in results:
            if isinstance(r, list):
                all_txs.extend(r)
            elif isinstance(r, Exception):
                logger.warning(f"[ChainIndexer] Unexpected error during recommended token collection: {r}")

        logger.info(
            f"[ChainIndexer] Collected {len(all_txs)} recommended token transfers "
            f"from {len(recommended)} entries within last {hours_back}h"
        )
        return all_txs

    async def collect_large_transactions(self, hours_back: int = 1) -> List[Dict[str, Any]]:
        """采集大额交易（推荐币种多链转账）"""
        return await self.collect_recommended_token_transfers(hours_back=hours_back)

    # ========== Batch Collection ==========

    async def collect_all_chains(
        self,
        hours_back: int = 1,
        evm_limit_per_chain: int = 100,
    ) -> List[Dict[str, Any]]:
        """Collect recent transactions from all supported chains."""
        all_txs = []
        chains = ("mantle", "ethereum", "bnb", "polygon", "arbitrum", "optimism", "base")

        evm_tasks = []
        for chain in chains:
            task = self.get_token_transfers(
                chain=chain,
                start_block=None,
                end_block=None,
                limit=evm_limit_per_chain,
            )
            evm_tasks.append(task)

        evm_results = await asyncio.gather(*evm_tasks, return_exceptions=True)
        for i, result in enumerate(evm_results):
            chain = chains[i]
            if isinstance(result, Exception):
                logger.warning(f"[ChainIndexer] {chain} fetch failed: {result}")
            elif isinstance(result, list):
                logger.info(f"[ChainIndexer] {chain}: {len(result)} transactions")
                all_txs.extend(result)
            else:
                logger.warning(f"[ChainIndexer] {chain}: unexpected result type {type(result)}")

        # Solana 采集
        solana_tokens = POPULAR_TOKENS.get("solana", [])
        for token_addr in solana_tokens:
            try:
                sol_txs = await self.get_solana_transactions(token_addr, hours_back=hours_back)
                all_txs.extend(sol_txs)
            except Exception as e:
                logger.warning(f"[ChainIndexer] Solana fetch error for {token_addr}: {e}")

        # Moralis 补充采集
        if self.moralis.api_key:
            for chain in chains:
                # 代币转账补充
                tokens = POPULAR_TOKENS.get(chain, [])
                for token_addr in tokens:
                    try:
                        moralis_txs = await self.fetch_moralis_transfers(
                            chain, token_addr, limit=max(evm_limit_per_chain // 2, 10)
                        )
                        all_txs.extend(moralis_txs)
                    except Exception as e:
                        logger.debug(f"[ChainIndexer] Moralis transfer fetch error: {e}")

                # 热点钱包转账补充
                try:
                    wallet_txs = await self.fetch_moralis_wallet_transfers(chain, limit=50)
                    all_txs.extend(wallet_txs)
                except Exception as e:
                    logger.debug(f"[ChainIndexer] Moralis wallet fetch error: {e}")

            # 批量填充 USD 价格
            try:
                all_txs = await self.moralis.enrich_transactions_with_price(all_txs)
            except Exception as e:
                logger.debug(f"[ChainIndexer] Moralis price enrichment error: {e}")

        # 按 hours_back 过滤
        cutoff = datetime.utcnow() - timedelta(hours=hours_back)
        filtered = [tx for tx in all_txs if tx.get("block_time") and tx["block_time"] >= cutoff]
        logger.info(f"[ChainIndexer] Collected {len(all_txs)} raw, {len(filtered)} within {hours_back}h from all chains")
        return filtered


# ============ Singleton ============

_chain_indexer: Optional[ChainIndexer] = None


async def get_chain_indexer() -> ChainIndexer:
    """Global singleton getter for ChainIndexer (matches project patterns)."""
    global _chain_indexer
    if _chain_indexer is None:
        _chain_indexer = ChainIndexer()
    return _chain_indexer
