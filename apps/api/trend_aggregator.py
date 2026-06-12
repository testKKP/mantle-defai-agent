"""
链上趋势聚合算法模块
从 chain_transactions 数据聚合出：链分布、赛道分布、趋势标的、大额交易
"""

import math
from typing import List, Dict, Any, Set, Optional
from collections import defaultdict


# 稳定币列表（token_symbol 不区分大小写）
STABLECOINS = {"USDT", "USDC", "DAI", "BUSD", "TUSD", "FDUSD", "USDD", "FRAX", "GUSD", "PAX", "USDP"}

# 热门赛道（category 不区分大小写）
HOT_CATEGORIES = {"AI", "MEME", "GAMING"}


def _is_stablecoin(token_symbol: str) -> bool:
    """判断是否为稳定币。"""
    return token_symbol.upper() in STABLECOINS if token_symbol else False


def _safe_float(value: Any, default: float = 0.0) -> float:
    """安全转换为 float。"""
    if value is None:
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _safe_int(value: Any, default: int = 0) -> int:
    """安全转换为 int。"""
    if value is None:
        return default
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _round2(value: float) -> float:
    """保留两位小数。"""
    return round(value, 2)


def _usd_value(tx: Dict[str, Any]) -> float:
    """
    获取交易的 USD 价值。
    稳定币直接使用 token_amount；其他使用 token_amount_usd。
    """
    token_symbol = tx.get("token_symbol", "")
    token_amount = _safe_float(tx.get("token_amount"))
    token_amount_usd = _safe_float(tx.get("token_amount_usd"))

    if _is_stablecoin(token_symbol):
        return token_amount if token_amount > 0 else token_amount_usd
    return token_amount_usd if token_amount_usd > 0 else token_amount


def aggregate_chain_distribution(txs: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """按链聚合交易分布（饼状图数据）。"""
    if not txs:
        return []

    chain_stats = defaultdict(lambda: {"tx_count": 0, "volume": 0.0})
    for tx in txs:
        chain = tx.get("chain", "Unknown")
        chain_stats[chain]["tx_count"] += 1
        chain_stats[chain]["volume"] += _usd_value(tx)

    total_tx = sum(s["tx_count"] for s in chain_stats.values())
    result = []
    for chain, stats in sorted(chain_stats.items(), key=lambda x: x[1]["tx_count"], reverse=True):
        result.append({
            "name": chain,
            "value": stats["tx_count"],
            "tx_count": stats["tx_count"],
            "volume": _round2(stats["volume"]),
            "percentage": _round2(stats["tx_count"] / total_tx * 100) if total_tx > 0 else 0.0,
        })
    return result


def aggregate_category_distribution(txs: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """按赛道(category)聚合交易分布（饼状图数据）。"""
    if not txs:
        return []

    cat_stats = defaultdict(lambda: {"tx_count": 0, "volume": 0.0})
    for tx in txs:
        category = tx.get("category", "Unknown")
        if not category:
            category = "Unknown"
        cat_stats[category]["tx_count"] += 1
        cat_stats[category]["volume"] += _usd_value(tx)

    total_tx = sum(s["tx_count"] for s in cat_stats.values())
    result = []
    for cat, stats in sorted(cat_stats.items(), key=lambda x: x[1]["tx_count"], reverse=True):
        result.append({
            "name": cat,
            "value": stats["tx_count"],
            "tx_count": stats["tx_count"],
            "volume": _round2(stats["volume"]),
            "percentage": _round2(stats["tx_count"] / total_tx * 100) if total_tx > 0 else 0.0,
        })
    return result


def compute_trend_targets(txs: List[Dict[str, Any]], top_n: int = 10) -> List[Dict[str, Any]]:
    """
    趋势标的评分算法。

    对每对 (chain, token_symbol) 计算：
    - tx_count: 交易笔数
    - total_amount: 总 token_amount（稳定币按 1:1 估算 USD 价值）
    - swap_count: swap 交易笔数
    - swap_ratio: swap_count / tx_count
    - unique_from: 唯一 from_address 数
    - unique_to: 唯一 to_address 数
    - unique_addrs: max(unique_from, unique_to)
    - category: 取最常见的分类

    评分（0-100）：
    1. 交易活跃度 (20分): tx_count / max_tx_count * 20
    2. 资金体量 (35分): log1p(total_amount) / log1p(max_amount) * 35
    3. 协议交互度 (20分): swap_ratio * 20
    4. 地址活跃度 (15分): unique_addrs / max_addrs * 15
    5. 赛道热度 (10分): 热门赛道(AI/Meme/Gaming) = 10, 其他 = 5
    """
    if not txs:
        return []

    # 按 (chain, token_symbol) 分组聚合
    target_stats = defaultdict(lambda: {
        "tx_count": 0,
        "total_amount": 0.0,
        "swap_count": 0,
        "from_addrs": set(),
        "to_addrs": set(),
        "categories": defaultdict(int),
    })

    for tx in txs:
        chain = tx.get("chain", "Unknown")
        token = tx.get("token_symbol", "Unknown")
        if not token:
            token = "Unknown"
        key = (chain, token)

        target_stats[key]["tx_count"] += 1
        target_stats[key]["total_amount"] += _usd_value(tx)

        tx_type = tx.get("tx_type", "")
        if tx_type and str(tx_type).upper() == "SWAP":
            target_stats[key]["swap_count"] += 1

        from_addr = tx.get("from_address")
        if from_addr:
            target_stats[key]["from_addrs"].add(from_addr)

        to_addr = tx.get("to_address")
        if to_addr:
            target_stats[key]["to_addrs"].add(to_addr)

        category = tx.get("category", "Unknown")
        if category:
            target_stats[key]["categories"][category] += 1

    if not target_stats:
        return []

    # 计算全局最大值用于归一化
    max_tx_count = max(s["tx_count"] for s in target_stats.values())
    max_amount = max(s["total_amount"] for s in target_stats.values())
    max_addrs = max(
        max(len(s["from_addrs"]), len(s["to_addrs"]))
        for s in target_stats.values()
    )

    # 避免除零
    max_tx_count = max(max_tx_count, 1)
    max_amount = max(max_amount, 1.0)
    max_addrs = max(max_addrs, 1)

    results = []
    for (chain, token), stats in target_stats.items():
        tx_count = stats["tx_count"]
        total_amount = stats["total_amount"]
        swap_count = stats["swap_count"]
        swap_ratio = swap_count / tx_count if tx_count > 0 else 0.0
        unique_from = len(stats["from_addrs"])
        unique_to = len(stats["to_addrs"])
        unique_addrs = max(unique_from, unique_to)

        # 取最常见的分类
        categories = stats["categories"]
        category = max(categories, key=categories.get) if categories else "Unknown"

        # 评分
        score_activity = (tx_count / max_tx_count) * 20
        score_volume = (math.log1p(total_amount) / math.log1p(max_amount)) * 35
        score_swap = swap_ratio * 20
        score_addrs = (unique_addrs / max_addrs) * 15
        score_category = 10 if category.upper() in HOT_CATEGORIES else 5

        total_score = score_activity + score_volume + score_swap + score_addrs + score_category
        total_score = min(total_score, 100.0)

        results.append({
            "chain": chain,
            "token_symbol": token,
            "tx_count": tx_count,
            "total_amount": _round2(total_amount),
            "swap_count": swap_count,
            "swap_ratio": _round2(swap_ratio),
            "unique_from": unique_from,
            "unique_to": unique_to,
            "unique_addresses": unique_addrs,
            "category": category,
            "trend_score": _round2(total_score),
        })

    # 按评分降序排列，取 Top N
    results.sort(key=lambda x: x["trend_score"], reverse=True)
    top_results = results[:top_n]

    # 添加 rank 字段
    for i, item in enumerate(top_results, start=1):
        item["rank"] = i

    return top_results


def filter_large_transactions(
    txs: List[Dict[str, Any]],
    threshold: float = 10000,
    exclude_stablecoin_transfers: bool = True,
    recommended_only: bool = False,
    recommended_symbols: Optional[Set[str]] = None,
) -> List[Dict[str, Any]]:
    """
    筛选大额交易。
    - token_amount_usd > threshold
    - 或 token_amount > threshold（稳定币）
    按金额降序排列
    """
    if not txs:
        return []

    large = []
    for tx in txs:
        token_symbol = tx.get("token_symbol", "")
        token_amount = _safe_float(tx.get("token_amount"))
        token_amount_usd = _safe_float(tx.get("token_amount_usd"))

        is_large = False
        if token_amount_usd > threshold:
            is_large = True
        elif _is_stablecoin(token_symbol) and token_amount > threshold:
            is_large = True

        if exclude_stablecoin_transfers:
            tx_type = tx.get("tx_type", "")
            if not tx_type:
                tx_type = "transfer"
            if str(tx_type).lower() == "transfer" and _is_stablecoin(token_symbol):
                continue

        if recommended_only and recommended_symbols:
            source_symbol = tx.get("source_symbol")
            if not source_symbol:
                from token_mapping import get_source_symbol
                source_symbol = get_source_symbol(token_symbol)
            if not source_symbol or source_symbol.upper() not in {s.upper() for s in recommended_symbols}:
                continue

        if is_large:
            large.append({
                "chain": tx.get("chain", ""),
                "tx_hash": tx.get("tx_hash", ""),
                "block_time": tx.get("block_time", ""),
                "from_address": tx.get("from_address", ""),
                "to_address": tx.get("to_address", ""),
                "token_symbol": token_symbol,
                "token_amount": _round2(token_amount),
                "token_amount_usd": _round2(token_amount_usd),
                "tx_type": tx.get("tx_type", ""),
                "category": tx.get("category", ""),
                "protocol": tx.get("protocol", ""),
                "usd_value": _round2(_usd_value(tx)),
            })

    large.sort(key=lambda x: x["usd_value"], reverse=True)
    return large


def compute_summary(txs: List[Dict[str, Any]], hours: int) -> Dict[str, Any]:
    """汇总统计。"""
    if not txs:
        return {
            "total_tx": 0,
            "total_volume": 0.0,
            "unique_tokens": 0,
            "unique_chains": 0,
            "time_range_hours": hours,
        }

    total_volume = 0.0
    unique_tokens = set()
    unique_chains = set()

    for tx in txs:
        total_volume += _usd_value(tx)
        token = tx.get("token_symbol")
        if token:
            unique_tokens.add(token)
        chain = tx.get("chain")
        if chain:
            unique_chains.add(chain)

    return {
        "total_tx": len(txs),
        "total_volume": _round2(total_volume),
        "unique_tokens": len(unique_tokens),
        "unique_chains": len(unique_chains),
        "time_range_hours": hours,
    }


def build_trend_aggregates(txs: List[Dict[str, Any]], hours: int = 24) -> Dict[str, Any]:
    """主入口：构建完整聚合结果。"""
    return {
        "chain_distribution": aggregate_chain_distribution(txs),
        "category_distribution": aggregate_category_distribution(txs),
        "top_targets": compute_trend_targets(txs, top_n=10),
        "large_transactions": filter_large_transactions(
            txs,
            threshold=10000,
            exclude_stablecoin_transfers=False,
            recommended_only=False,
        ),
        "summary": compute_summary(txs, hours),
    }
