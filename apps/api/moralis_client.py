"""
Moralis API 客户端
用于获取代币价格、多链转账数据、代币元数据
"""

import os
from typing import List, Dict, Any, Optional
from datetime import datetime
from loguru import logger

# 加载 .env 文件
from dotenv import load_dotenv
# 尝试多个路径
_possible_env_paths = [
    os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), ".env"),
    os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env"),
    os.path.join(os.getcwd(), ".env"),
]
for _env_path in _possible_env_paths:
    if os.path.exists(_env_path):
        load_dotenv(_env_path)
        break

# 稳定币白名单：直接按 1:1 估算，不调用价格 API
STABLECOIN_SYMBOLS = {
    "USDT", "USDC", "DAI", "BUSD", "TUSD", "FDUSD", "USDD", "FRAX", "GUSD", "PAX", "USDP"
}


class MoralisClient:
    def __init__(self):
        self.api_key = os.getenv("MORALIS_API_KEY")
        if not self.api_key:
            logger.warning("MORALIS_API_KEY not set, Moralis features disabled")

    def _chain_to_moralis(self, chain: str) -> str:
        """将内部链名映射到 Moralis 链标识"""
        mapping = {
            "ethereum": "eth",
            "bnb": "bsc",
            "mantle": "mantle",
            "polygon": "polygon",
            "arbitrum": "arbitrum",
            "optimism": "optimism",
            "base": "base",
            "solana": "solana",
        }
        return mapping.get(chain, chain)

    async def get_token_price(self, chain: str, token_address: str) -> Optional[float]:
        """获取代币实时 USD 价格"""
        if not self.api_key:
            return None
        try:
            from moralis import evm_api
            params = {
                "chain": self._chain_to_moralis(chain),
                "address": token_address,
            }
            result = evm_api.token.get_token_price(api_key=self.api_key, params=params)
            price = result.get("usdPrice")
            if price is not None:
                return float(price)
            return None
        except Exception as e:
            logger.warning(f"[MoralisClient] get_token_price error: {e}")
            return None

    async def get_wallet_transfers(self, chain: str, wallet_address: str, limit: int = 100) -> List[Dict[str, Any]]:
        """获取钱包的 ERC20 转账记录"""
        if not self.api_key:
            return []
        try:
            from moralis import evm_api
            params = {
                "chain": self._chain_to_moralis(chain),
                "address": wallet_address,
                "limit": limit,
            }
            result = evm_api.token.get_wallet_token_transfers(api_key=self.api_key, params=params)
            # Moralis SDK 可能返回 dict（含 result 字段）或 list
            tx_list = result
            if isinstance(result, dict):
                tx_list = result.get("result", []) or result.get("data", [])
            if not isinstance(tx_list, list):
                logger.warning(f"[MoralisClient] get_wallet_token_transfers unexpected response type: {type(result)}, tx_list={type(tx_list)}")
                return []
            return [self._normalize_transfer(chain, item) for item in tx_list if item]
        except Exception as e:
            logger.warning(f"[MoralisClient] get_wallet_token_transfers error: {e}")
            return []

    async def get_token_transfers(self, chain: str, token_address: str, limit: int = 100) -> List[Dict[str, Any]]:
        """获取指定代币的转账记录"""
        if not self.api_key:
            return []
        try:
            from moralis import evm_api
            params = {
                "chain": self._chain_to_moralis(chain),
                "address": token_address,
                "limit": limit,
            }
            result = evm_api.token.get_token_transfers(api_key=self.api_key, params=params)
            # Moralis SDK 可能返回 dict（含 result 字段）或 list
            tx_list = result
            if isinstance(result, dict):
                tx_list = result.get("result", []) or result.get("data", [])
            if not isinstance(tx_list, list):
                logger.warning(f"[MoralisClient] get_token_transfers unexpected response type: {type(result)}, tx_list={type(tx_list)}")
                return []
            return [self._normalize_transfer(chain, item) for item in tx_list if item]
        except Exception as e:
            logger.warning(f"[MoralisClient] get_token_transfers error: {e}")
            return []

    async def get_token_metadata(self, chain: str, token_address: str) -> Optional[Dict[str, Any]]:
        """获取代币元数据（name, symbol, decimals, logo, category等）"""
        if not self.api_key:
            return None
        try:
            from moralis import evm_api
            params = {
                "chain": self._chain_to_moralis(chain),
                "addresses": [token_address],
            }
            result = evm_api.token.get_token_metadata(api_key=self.api_key, params=params)
            if isinstance(result, list) and result:
                return result[0]
            return None
        except Exception as e:
            logger.warning(f"[MoralisClient] get_token_metadata error: {e}")
            return None

    def _normalize_transfer(self, chain: str, item: Dict[str, Any]) -> Dict[str, Any]:
        """将 Moralis 转账记录转换为标准格式"""
        token_decimal = int(item.get("token_decimals", "0") or "0")
        amount_raw = item.get("value", "0") or "0"
        amount = (
            float(amount_raw) / (10 ** token_decimal)
            if token_decimal > 0
            else float(amount_raw)
        )

        # 解析 block_timestamp（ISO 格式）
        block_time = None
        ts_raw = item.get("block_timestamp")
        if ts_raw:
            try:
                # 处理 "2024-01-01T00:00:00.000Z" 或 "2024-01-01T00:00:00Z"
                ts_str = str(ts_raw).replace("Z", "+00:00")
                block_time = datetime.fromisoformat(ts_str)
            except Exception:
                block_time = None
        if block_time is None:
            block_time = datetime.utcnow()

        block_number = item.get("block_number")
        try:
            block_number = int(block_number) if block_number is not None else 0
        except (ValueError, TypeError):
            block_number = 0

        # 协议检测
        tx_type = "transfer"
        protocol = None
        try:
            from chain_indexer import detect_protocol
            to_addr = item.get("to_address") or item.get("to")
            from_addr = item.get("from_address") or item.get("from")
            tx_type, protocol = detect_protocol(chain, to_addr, from_addr)
        except Exception:
            pass  # 导入失败或检测失败时不影响主流程

        return {
            "chain": chain,
            "tx_hash": item.get("transaction_hash") or item.get("tx_hash"),
            "block_number": block_number,
            "block_time": block_time,
            "from_address": item.get("from_address") or item.get("from"),
            "to_address": item.get("to_address") or item.get("to"),
            "token_address": item.get("address") or item.get("token_address"),
            "token_symbol": item.get("token_symbol") or "UNKNOWN",
            "token_amount": amount,
            "token_amount_usd": None,
            "tx_type": tx_type,
            "category": None,
            "protocol": protocol,
        }

    async def enrich_transactions_with_price(self, txs: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        给交易列表补充 USD 价格
        对每对(chain, token_address)批量查询价格，避免重复调用
        稳定币直接按1:1估算，不调用API
        返回补充了 token_amount_usd 的交易列表
        """
        if not txs:
            return txs

        # 收集需要查询价格的唯一 (chain, token_address, token_symbol)
        price_cache: Dict[tuple, Optional[float]] = {}
        to_query: set = set()

        for tx in txs:
            symbol = (tx.get("token_symbol") or "UNKNOWN").upper()
            chain = tx.get("chain", "")
            token_address = tx.get("token_address")
            if not chain or not token_address:
                continue

            key = (chain, token_address)

            # 稳定币直接按 1:1
            if symbol in STABLECOIN_SYMBOLS:
                price_cache[key] = 1.0
                continue

            if key not in price_cache:
                to_query.add(key)

        # 批量查询价格（串行，避免速率限制）
        for chain, token_address in to_query:
            if not self.api_key:
                break
            try:
                price = await self.get_token_price(chain, token_address)
                price_cache[(chain, token_address)] = price
            except Exception as e:
                logger.debug(f"[MoralisClient] Price query failed for {chain}/{token_address}: {e}")
                price_cache[(chain, token_address)] = None

        # 填充价格到交易列表
        for tx in txs:
            chain = tx.get("chain", "")
            token_address = tx.get("token_address")
            if not chain or not token_address:
                continue

            key = (chain, token_address)
            price = price_cache.get(key)
            if price is not None:
                amount = tx.get("token_amount") or 0
                try:
                    tx["token_amount_usd"] = float(amount) * price
                except (ValueError, TypeError):
                    tx["token_amount_usd"] = None

        return txs
