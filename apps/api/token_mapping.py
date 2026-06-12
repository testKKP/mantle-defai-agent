"""
Token Mapping Module — Maps sentiment analysis symbols to multi-chain contract addresses.

The sentiment analyzer (`SentimentAnalyzer` in `clients.py`) recommends long/short
positions using Binance symbols (e.g. "BTCUSDT" → "BTC"). This module bridges those
symbols to on-chain contract addresses across Ethereum, BNB Chain, Mantle, Solana, etc.
"""

from typing import Dict, List, Optional, Set, Any
from loguru import logger

from db import db_get


# ============================================================================
# Token Address Map — Binance base symbol → multi-chain contract addresses
# ============================================================================

TOKEN_ADDRESS_MAP: Dict[str, List[Dict[str, Any]]] = {
    "BTC": [
        {"chain": "ethereum", "address": "0x2260FAC5E5542a773Aa44fBCfeDf7C193bc2C599", "symbol_alias": "WBTC", "decimals": 8},
        {"chain": "bnb", "address": "0x7130d2A12B9BCbFAe4f2634d864A1Ee1Ce3Ead9c", "symbol_alias": "BTCB", "decimals": 18},
        {"chain": "polygon", "address": "0x1BFD67037B42Cf73acF2047067bd4F2C47D9BfD6", "symbol_alias": "WBTC", "decimals": 8},
        {"chain": "arbitrum", "address": "0x2f2a2543B76A4166549F7aaB2e75Bef0aefC5B0f", "symbol_alias": "WBTC", "decimals": 8},
        {"chain": "optimism", "address": "0x68f180fcCe6836688e9084f035309E29Bf0A2095", "symbol_alias": "WBTC", "decimals": 8},
        {"chain": "base", "address": "0xcbB7C0000aB88B473b1f5aFd7ef5ce03bD1C97cD", "symbol_alias": "cbBTC", "decimals": 8},
    ],
    "ETH": [
        {"chain": "ethereum", "address": "0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2", "symbol_alias": "WETH", "decimals": 18},
        {"chain": "bnb", "address": "0x2170Ed0880ac9A755fd29B2688956BD959F933F8", "symbol_alias": "ETH", "decimals": 18},
        {"chain": "polygon", "address": "0x7ceB23fD6bC0adD59E62ac25578270cFf1b9f619", "symbol_alias": "WETH", "decimals": 18},
        {"chain": "arbitrum", "address": "0x82aF49447D8a07e3bd95BD0d56f35241523fBab1", "symbol_alias": "WETH", "decimals": 18},
        {"chain": "optimism", "address": "0x4200000000000000000000000000000000000006", "symbol_alias": "WETH", "decimals": 18},
        {"chain": "base", "address": "0x4200000000000000000000000000000000000006", "symbol_alias": "WETH", "decimals": 18},
    ],
    "SOL": [
        {"chain": "solana", "address": "So11111111111111111111111111111111111111112", "symbol_alias": "SOL", "decimals": 9},
    ],
    "BNB": [
        {"chain": "bnb", "address": "0xbb4CdB9CBd36B01bD1cBaEBF2De08d9173bc095c", "symbol_alias": "WBNB", "decimals": 18},
    ],
    "XRP": [
        {"chain": "ethereum", "address": "0x39fBBABf11738317a448031930706cd3e612e1B1", "symbol_alias": "XRP", "decimals": 18},
    ],
    "DOGE": [
        {"chain": "ethereum", "address": "0x4206931337dc273a630d328dA6441786BfaD668f", "symbol_alias": "DOGE", "decimals": 8},
    ],
    "ADA": [
        {"chain": "ethereum", "address": "0x3EE2200Efb3400fAbB9AacF31297cBdD1d435D47", "symbol_alias": "ADA", "decimals": 6},
    ],
    "AVAX": [
        {"chain": "ethereum", "address": "0x85f138bfEE4ef8e540890CFb48F620571d67Eda3", "symbol_alias": "AVAX", "decimals": 18},
        {"chain": "bnb", "address": "0x1CE0c2827e2eF14D5C4f29a091d735A204794041", "symbol_alias": "AVAX", "decimals": 18},
    ],
    "LINK": [
        {"chain": "ethereum", "address": "0x514910771AF9Ca656af840dff83E8264EcF986CA", "symbol_alias": "LINK", "decimals": 18},
        {"chain": "bnb", "address": "0xF8A0BF9cF54Bb92F17374d9e9A321E6a111a51bD", "symbol_alias": "LINK", "decimals": 18},
        {"chain": "polygon", "address": "0x53E0bca35eC356BD5ddDFebbD1Fc0fD03FaBad39", "symbol_alias": "LINK", "decimals": 18},
        {"chain": "arbitrum", "address": "0xf97f4df75117a78c1A5a0DBb814Af92458539FB4", "symbol_alias": "LINK", "decimals": 18},
    ],
    "DOT": [
        {"chain": "ethereum", "address": "0xF319E1EdE157d9B47cf91c11B69Ef535477b08A0", "symbol_alias": "DOT", "decimals": 10},
    ],
    "MATIC": [
        {"chain": "ethereum", "address": "0x7D1AfA7B718fb893dB30A3aBc0Cfc608AaCfeBB0", "symbol_alias": "MATIC", "decimals": 18},
        {"chain": "bnb", "address": "0xCC42724C6683B7E57334c4E856f4c9965ed682bD", "symbol_alias": "MATIC", "decimals": 18},
        {"chain": "polygon", "address": "0x0d500B1d8E8eF31E21C99d1Db9A6444d3ADf1270", "symbol_alias": "WMATIC", "decimals": 18},
    ],
    "LTC": [
        {"chain": "ethereum", "address": "0x9D73D207FBD798eB5C37b1cE5Ef93D6343d4C27e", "symbol_alias": "LTC", "decimals": 18},
    ],
    "UNI": [
        {"chain": "ethereum", "address": "0x1f9840a85d5aF5bf1D1762F925BDADdC4201F984", "symbol_alias": "UNI", "decimals": 18},
        {"chain": "bnb", "address": "0xBf5140A22578168FD562DCcF235E5D43A02ce9B1", "symbol_alias": "UNI", "decimals": 18},
        {"chain": "polygon", "address": "0x4535b3bC62713874eE79384bD520A4D395Bb1fd7", "symbol_alias": "UNI", "decimals": 18},
        {"chain": "arbitrum", "address": "0xFa7F8980b0f205E441ecFfbF9E0Df8722E258e22", "symbol_alias": "UNI", "decimals": 18},
    ],
    "ATOM": [
        {"chain": "ethereum", "address": "0x8D983cb9388EaC77af0474fA441C4815500Cb7BB", "symbol_alias": "ATOM", "decimals": 6},
    ],
    "ETC": [
        {"chain": "ethereum", "address": "0x3d6545b08693daE087E957cb1180ee38B9e3c25E", "symbol_alias": "ETC", "decimals": 18},
    ],
    "FIL": [
        {"chain": "ethereum", "address": "0x6e1A19F235bE7ED8E3369eF73b196C07257494DE", "symbol_alias": "FIL", "decimals": 18},
    ],
    "NEAR": [
        {"chain": "ethereum", "address": "0x85F17Cf997934a597031b2E18a9aB6ebD4B9f6a4", "symbol_alias": "NEAR", "decimals": 24},
    ],
    "ALGO": [
        {"chain": "ethereum", "address": "0x3b0f29983CfD4C1A4b566aF8bF3D98A991d19C11", "symbol_alias": "ALGO", "decimals": 6},
    ],
    "VET": [
        {"chain": "ethereum", "address": "0xD850942eF8811f2A866692A623011bDE52a462C1", "symbol_alias": "VET", "decimals": 18},
    ],
    "ICP": [
        {"chain": "ethereum", "address": "0xE2D479DCa29BB2d4EE53A7A7bB3b47e7a5B71A42", "symbol_alias": "ICP", "decimals": 18},
    ],
    "APT": [
        {"chain": "ethereum", "address": "0x5c56b0b1A40F11903B2fCdaab1Afe1E1C8f2B1C6", "symbol_alias": "APT", "decimals": 8},
    ],
    "ARB": [
        {"chain": "ethereum", "address": "0xB50721BCf8d664c30412Cfbc6cf7a15145234ad1", "symbol_alias": "ARB", "decimals": 18},
        {"chain": "bnb", "address": "0xaE6aab93cE9ab9dE94D3dAa5a9b09fE2D1e6E8a0", "symbol_alias": "ARB", "decimals": 18},
        {"chain": "arbitrum", "address": "0x912CE59144191C1204E64559FE8253a0e49E6548", "symbol_alias": "ARB", "decimals": 18},
    ],
    "OP": [
        {"chain": "ethereum", "address": "0x4200000000000000000000000000000000000042", "symbol_alias": "OP", "decimals": 18},
        {"chain": "optimism", "address": "0x4200000000000000000000000000000000000042", "symbol_alias": "OP", "decimals": 18},
    ],
    "SUI": [
        {"chain": "ethereum", "address": "0xC71cB29F5DA2D8C62F7E1C5F0E42C8d9d3C8E1A1", "symbol_alias": "SUI", "decimals": 9},
    ],
    "SEI": [
        {"chain": "ethereum", "address": "0x55C08E741C8dE637EEdBaE59476553Da4170a39b", "symbol_alias": "SEI", "decimals": 18},
    ],
    "TIA": [
        {"chain": "ethereum", "address": "0x335D0c22fD35232F5f44cE1b1C08c72E351FfD5b", "symbol_alias": "TIA", "decimals": 6},
    ],
    "PYTH": [
        {"chain": "ethereum", "address": "0xE4D5c6aE46C3f5E8cD6A28dc1E62d52f1C8c6A9b", "symbol_alias": "PYTH", "decimals": 6},
        {"chain": "solana", "address": "HZ1JovNiVvGrGNiiYvEozEVgZ58xaU3RKwX8eACQBCt", "symbol_alias": "PYTH", "decimals": 6},
    ],
    "JUP": [
        {"chain": "solana", "address": "JUPyiwrYJFskUPiHa7hkeR8VUtAeFoSYbKedZNsDvCN", "symbol_alias": "JUP", "decimals": 6},
    ],
    "WIF": [
        {"chain": "solana", "address": "EKpQGSJtjMFqKZ9KQanSqYXRcF8fBopzLHYxdM65zcjm", "symbol_alias": "WIF", "decimals": 6},
    ],
    "BONK": [
        {"chain": "solana", "address": "DezXAZ8z7PnrnRJjz3wXBoRgixCa6xjnB7YaB1pPB263", "symbol_alias": "BONK", "decimals": 5},
    ],
}


# ============================================================================
# Auto-generated reverse mapping: chain symbol_alias → source symbol
# ============================================================================

SYMBOL_TO_SOURCE: Dict[str, str] = {}
for _source_symbol, _entries in TOKEN_ADDRESS_MAP.items():
    for _entry in _entries:
        _alias = _entry.get("symbol_alias")
        if _alias:
            SYMBOL_TO_SOURCE[_alias] = _source_symbol


# ============================================================================
# Public API
# ============================================================================

async def get_recommended_tokens_for_monitoring(timeframe: str = "1d") -> List[Dict[str, Any]]:
    """从情绪分析获取推荐币种，返回带链信息的多链 token 列表

    Args:
        timeframe: 时间框架，默认 "1d"（日线）。可选 "1d", "4h", "1w"
    """
    try:
        sentiment_data = await db_get("sentiment")
    except Exception as e:
        logger.warning(f"Failed to fetch sentiment from database: {e}")
        return []

    if not sentiment_data or not isinstance(sentiment_data, dict):
        logger.debug("No sentiment data available in database yet")
        return []

    position_report = sentiment_data.get("position_report")
    if not position_report or not isinstance(position_report, dict):
        logger.warning("Sentiment data exists but has no 'position_report' field")
        return []

    monitoring_list: List[Dict[str, Any]] = []

    for tf, report in position_report.items():
        if timeframe and tf != timeframe:
            continue
        if not isinstance(report, dict):
            continue

        for direction in ("long", "short"):
            recommendations = report.get(direction)
            if not isinstance(recommendations, list):
                continue

            for rec in recommendations:
                if not isinstance(rec, dict):
                    continue

                symbol = rec.get("symbol", "").upper()
                if not symbol:
                    continue

                mapped = TOKEN_ADDRESS_MAP.get(symbol)
                if not mapped:
                    logger.warning(
                        f"No token mapping found for recommended symbol: {symbol} "
                        f"(timeframe={tf}, direction={direction})"
                    )
                    continue

                for entry in mapped:
                    monitoring_list.append({
                        "source_symbol": symbol,
                        "chain": entry["chain"],
                        "address": entry["address"],
                        "symbol_alias": entry["symbol_alias"],
                        "decimals": entry["decimals"],
                        "direction": direction,
                        "confidence": rec.get("confidence", "low"),
                        "reason": rec.get("reason", ""),
                    })

    logger.info(
        f"Built monitoring list with {len(monitoring_list)} entries "
        f"from sentiment position report"
    )
    return monitoring_list


async def get_recommended_symbols(timeframe: str = "1d") -> Set[str]:
    """返回去重后的推荐 symbol 集合

    Args:
        timeframe: 时间框架，默认 "1d"（日线）。可选 "1d", "4h", "1w"
    """
    tokens = await get_recommended_tokens_for_monitoring(timeframe=timeframe)
    return {t["source_symbol"] for t in tokens}


def get_source_symbol(chain_symbol: str) -> Optional[str]:
    """
    Reverse lookup: given a chain-level token symbol (e.g. "WBTC", "WETH"),
    return the original sentiment-analysis base symbol (e.g. "BTC", "ETH").

    Returns ``None`` if the symbol is not recognised.
    """
    if not chain_symbol:
        return None
    return SYMBOL_TO_SOURCE.get(chain_symbol.upper())
