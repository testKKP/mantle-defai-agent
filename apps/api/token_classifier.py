"""
Token classification using CoinGecko API
"""
import asyncio
import aiohttp
from datetime import datetime
from typing import Optional, Dict, Any, List
from loguru import logger
from db import db_get_token_metadata, db_save_token_metadata
from moralis_client import MoralisClient

# CoinGecko 免费 API（无需 key，速率限制 10-30 req/min）
COINGECKO_BASE = "https://api.coingecko.com/api/v3"

# 稳定币白名单：直接返回 "DeFi"
STABLECOIN_SYMBOLS = {
    "USDT", "USDC", "DAI", "BUSD", "TUSD", "FDUSD", "USDD", "FRAX", "GUSD", "PAX", "USDP"
}

# 分类映射：将 CoinGecko 的 category 映射到我们的标准分类
CATEGORY_MAPPING = {
    # AI
    "artificial-intelligence": "AI",
    "ai": "AI",
    "ai-agents": "AI",
    "big-data": "AI",

    # DeFi
    "decentralized-finance-defi": "DeFi",
    "defi": "DeFi",
    "liquid-staking-tokens": "DeFi",
    "yield-farming": "DeFi",
    "dex": "DeFi",
    "lending": "DeFi",
    "derivatives": "DeFi",
    "stablecoins": "DeFi",
    "usd-stablecoin": "DeFi",
    "wrapped-tokens": "DeFi",
    "seigniorage": "DeFi",
    "perpetuals": "DeFi",
    "launchpad": "DeFi",
    "insurance": "DeFi",
    "restaking": "DeFi",
    "prediction-market": "DeFi",
    "centralized-exchange-token-cex": "DeFi",
    "decentralized-exchange-dex-token": "DeFi",
    "exchange-based-tokens": "DeFi",
    "payments": "DeFi",
    "remittances": "DeFi",

    # RWA
    "real-world-assets-rwa": "RWA",
    "rwa": "RWA",
    "real-world-assets": "RWA",
    "asset-backed-tokens": "RWA",
    "tokenized-stock": "RWA",
    "etf": "RWA",

    # Meme
    "meme": "Meme",
    "memecoin": "Meme",
    "dog-themed-coins": "Meme",
    "cat-themed-coins": "Meme",
    "frog-themed-coins": "Meme",

    # Gaming
    "gaming": "Gaming",
    "gamefi": "Gaming",
    "play-to-earn": "Gaming",
    "metaverse": "Gaming",
    "vr-ar": "Gaming",
    "entertainment": "Gaming",
    "sports": "Gaming",
    "gambling": "Gaming",

    # Layer1
    "layer-1": "Layer1",
    "ethereum-ecosystem": "Layer1",
    "solana-ecosystem": "Layer1",
    "bitcoin-ecosystem": "Layer1",
    "cosmos-ecosystem": "Layer1",
    "binance-smart-chain-ecosystem": "Layer1",
    "avalanche-ecosystem": "Layer1",
    "fantom-ecosystem": "Layer1",
    "tron-ecosystem": "Layer1",
    "aptos-ecosystem": "Layer1",
    "sui-ecosystem": "Layer1",
    "cardano-ecosystem": "Layer1",
    "near-ecosystem": "Layer1",

    # Layer2
    "layer-2": "Layer2",
    "polygon-ecosystem": "Layer2",
    "arbitrum-ecosystem": "Layer2",
    "optimism-ecosystem": "Layer2",
    "mantle-ecosystem": "Layer2",
    "base-ecosystem": "Layer2",
    "rollup": "Layer2",
    "sidechain": "Layer2",

    # Infra
    "infrastructure": "Infra",
    "privacy-coins": "Infra",
    "oracles": "Infra",
    "bridges": "Infra",
    "identity": "Infra",
    "zero-knowledge-zk": "Infra",
    "masternodes": "Infra",
    "smart-contract-platform": "Infra",
    "blockchain-platform": "Infra",
    "interoperability": "Infra",
    "storage": "Infra",
    "computing": "Infra",
    "dao": "Infra",
    "governance": "Infra",
    "scaling": "Infra",
    "modular-blockchain": "Infra",
    "data-availability": "Infra",
    "sequencer": "Infra",
    "depin": "Infra",
    "energy": "Infra",
    "environment": "Infra",
    "healthcare": "Infra",
    "logistics": "Infra",
    "education": "Infra",
    "iot": "Infra",
    "cybersecurity": "Infra",

    # NFT
    "nft": "NFT",
    "nft-marketplace": "NFT",
    "collectibles": "NFT",
    "music": "NFT",
    "art": "NFT",
    "photography": "NFT",
    "fractionalized-nft": "NFT",

    # SocialFi
    "socialfi": "SocialFi",
    "fan-token": "SocialFi",
    "communication": "SocialFi",
    "content-creation": "SocialFi",
}


class TokenClassifier:
    """代币分类器 — 从 CoinGecko / Moralis 获取代币元数据和分类"""

    def __init__(self, session: Optional[aiohttp.ClientSession] = None):
        self.session = session or aiohttp.ClientSession()
        self.base_url = COINGECKO_BASE
        self._category_cache: Dict[str, str] = {}  # symbol -> category
        self.moralis = MoralisClient()

    async def close(self):
        if self.session:
            await self.session.close()

    async def fetch_coingecko(self, endpoint: str, params: Optional[Dict] = None) -> Optional[Any]:
        """调用 CoinGecko API"""
        url = f"{self.base_url}{endpoint}"
        try:
            async with self.session.get(url, params=params, timeout=aiohttp.ClientTimeout(total=30)) as resp:
                if resp.status == 429:
                    logger.warning("[TokenClassifier] CoinGecko rate limited")
                    return None
                if resp.status != 200:
                    logger.warning(f"[TokenClassifier] CoinGecko HTTP {resp.status}")
                    return None
                return await resp.json()
        except Exception as e:
            logger.error(f"[TokenClassifier] CoinGecko fetch error: {e}")
            return None

    async def classify_token(self, chain: str, token_address: str, token_symbol: str) -> Optional[str]:
        """
        获取代币分类。优先级：稳定币白名单 -> 内存缓存 -> Moralis -> 本地DB -> CoinGecko
        """
        symbol_upper = token_symbol.upper()

        # 0. 稳定币白名单快速返回
        if symbol_upper in STABLECOIN_SYMBOLS:
            self._category_cache[symbol_upper] = "DeFi"
            return "DeFi"

        # 1. 检查内存缓存
        if symbol_upper in self._category_cache:
            return self._category_cache[symbol_upper]

        # 2. 尝试 Moralis
        if self.moralis.api_key:
            category = await self._fetch_category_from_moralis(chain, token_address)
            if category:
                self._category_cache[symbol_upper] = category
                await db_save_token_metadata({
                    "chain": chain,
                    "token_address": token_address,
                    "token_symbol": token_symbol,
                    "category": category,
                    "updated_at": datetime.utcnow().isoformat(),
                })
                return category

        # 3. 检查数据库
        meta = await db_get_token_metadata(chain, token_address)
        if meta and meta.get("category"):
            self._category_cache[symbol_upper] = meta["category"]
            return meta["category"]

        # 4. 查询 CoinGecko（通过 contract address）
        # Ethereum 地址可以直接查，其他链需要映射 chain_id
        category = await self._fetch_category_from_coingecko(chain, token_address)
        if category:
            self._category_cache[symbol_upper] = category
            # 保存到数据库
            await db_save_token_metadata({
                "chain": chain,
                "token_address": token_address,
                "token_symbol": token_symbol,
                "category": category,
                "updated_at": datetime.utcnow().isoformat(),
            })
            return category

        return None

    async def _fetch_category_from_moralis(self, chain: str, token_address: str) -> Optional[str]:
        """从 Moralis 获取代币分类"""
        try:
            meta = await self.moralis.get_token_metadata(chain, token_address)
            if not meta:
                return None
            # Moralis 可能返回 categories 或 category 字段
            categories = meta.get("categories") or []
            if isinstance(categories, str):
                categories = [categories]
            for cat in categories:
                raw_cat = str(cat).lower().replace(" ", "-").replace("_", "-")
                mapped = CATEGORY_MAPPING.get(raw_cat)
                if mapped:
                    return mapped
            # 尝试单数 category 字段
            single_cat = meta.get("category")
            if single_cat:
                raw_cat = str(single_cat).lower().replace(" ", "-").replace("_", "-")
                mapped = CATEGORY_MAPPING.get(raw_cat)
                if mapped:
                    return mapped
            return None
        except Exception as e:
            logger.warning(f"[TokenClassifier] Moralis category fetch error: {e}")
            return None

    async def _fetch_category_from_coingecko(self, chain: str, token_address: str) -> Optional[str]:
        """从 CoinGecko 获取代币分类"""
        # CoinGecko 的 asset_platform 映射
        platform_map = {
            "ethereum": "ethereum",
            "bnb": "binance-smart-chain",
            "mantle": "mantle",
        }
        platform = platform_map.get(chain)
        if not platform:
            return None

        data = await self.fetch_coingecko(
            f"/coins/{platform}/contract/{token_address}"
        )
        if not data:
            return None

        categories = data.get("categories", [])
        for cat in categories:
            raw_cat = cat.lower().replace(" ", "-").replace("_", "-")
            mapped = CATEGORY_MAPPING.get(raw_cat)
            if mapped:
                return mapped

        # fallback: 无匹配时返回 "Other"
        return "Other"

    async def batch_classify(self, transactions: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        批量给交易列表中的代币分类。
        注意 CoinGecko 速率限制，这里用简单串行 + sleep 控制。
        """
        for tx in transactions:
            if tx.get("category"):
                continue
            symbol = tx.get("token_symbol")
            address = tx.get("token_address")
            chain = tx.get("chain")
            if not symbol or not address:
                continue

            category = await self.classify_token(chain, address, symbol)
            if category:
                tx["category"] = category

            # 简单速率控制
            await asyncio.sleep(0.5)

        return transactions


# 全局单例
_classifier: Optional[TokenClassifier] = None

async def get_token_classifier() -> TokenClassifier:
    global _classifier
    if _classifier is None:
        _classifier = TokenClassifier()
    return _classifier
