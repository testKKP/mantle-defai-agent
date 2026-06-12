"""
Backtest engine — Similar-State Matching Backtest.

Logic:
1. Fetch historical klines (1000 max from Binance)
2. Slide window of 500 candles
3. At each point:
   a. Detect if 5-MA alignment exists (bullish_all / bearish_all)
   b. Count how many consecutive candles this alignment has lasted (trend_duration)
   c. Only record signals when alignment is STRONG/MEDIUM/WEAK (not NONE)
   d. Look ahead 10 candles for exit price
   e. Record: pattern, trend_duration, entry_price, exit_price, pnl
4. Group results by (pattern, trend_duration_bucket)
5. For current live signals, match their (pattern, trend_duration) to historical stats
"""

import asyncio
import re
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Any, Tuple
from collections import defaultdict
from loguru import logger

from clients import BinanceClient, analyzer, MACalculator
from db import db_save_signal, db_update_signal_exit, db_get_backtest_stats

# 持有期：固定10根K线（不是10天）
HOLD_KLINES = 10

# 不同 timefame 的回测参数配置
def get_backtest_params(timeframe: str) -> tuple[int, int, int]:
    """
    根据 timeframe 获取回测参数。
    
    Returns:
        (window_size, ma_period, min_klines)
    """
    if timeframe in ("1w", "1week"):
        # 周线：数据量有限，使用较小的窗口
        return 100, 20, 130  # 100 + 10 + 20
    # 默认：1h, 4h, 1d 等
    return 500, 120, 630  # 500 + 10 + 120


# trend_duration 分桶（用于聚合相似状态）
def duration_bucket(duration: int) -> str:
    """将连续持续天数分桶，用于匹配相似状态"""
    if duration <= 1:
        return "1"
    elif duration <= 3:
        return "2-3"
    elif duration <= 5:
        return "4-5"
    elif duration <= 10:
        return "6-10"
    elif duration <= 20:
        return "11-20"
    else:
        return "20+"


def compute_trend_duration(klines: List[dict], ma_period: int = 120) -> List[Dict[str, Any]]:
    """
    遍历K线，计算每根K线处的五线排列状态及其连续持续天数。
    
    Args:
        klines: K线数据列表
        ma_period: MA 周期，决定从哪根K线开始遍历（默认120）
    
    返回: List[dict]
    - idx: K线索引
    - pattern: "bullish_all" | "bearish_all" | "loose_bullish" | "loose_bearish" | "none"
    - duration: 连续持续天数（含当前）
    - strength: STRONG / MEDIUM / WEAK / NONE
    - alignment: 包含 score, mas 等
    - price: 当前收盘价
    - timestamp: 当前K线收盘时间
    
    对于每个idx，如果当前是bullish_all或loose_bullish，返回的duration表示这个状态已经连续了多少根K线（含当前）。
    """
    results = []
    ma_calc = MACalculator()
    
    current_pattern = None
    current_duration = 0
    
    for i in range(ma_period, len(klines)):  # 从第 ma_period 根开始，确保 MA 可用
        window = klines[:i+1]  # 0到i（含i）
        prices = [k["close"] for k in window]
        mas = ma_calc.calculate(prices)
        alignment = ma_calc.analyze_alignment(mas, prices[-1])
        
        pattern = alignment["alignment"]  # bullish / bearish / neutral
        strength = alignment["strength"]   # STRONG / MEDIUM / WEAK / NONE
        
        # 严格模式：全部5条MA有值 + 完美排列 + 价格突破全部MA
        has_all_5 = len(mas) >= 5 and all(mas.get(k) is not None for k in ["MA5", "MA10", "MA20", "MA60", "MA120"])
        
        if has_all_5 and pattern == "bullish" and alignment.get("price_above_all", False):
            detected = "bullish_all"
        elif has_all_5 and pattern == "bearish" and alignment.get("price_below_all", False):
            detected = "bearish_all"
        # 宽松模式：至少MA5/10/20有值 + 价格高于/低于这3条
        elif len(mas) >= 3 and all(mas.get(k) is not None for k in ["MA5", "MA10", "MA20"]):
            ma5 = mas.get("MA5")
            ma10 = mas.get("MA10")
            ma20 = mas.get("MA20")
            price = prices[-1]
            if pattern == "bullish" and price > ma5 > ma10 > ma20:
                detected = "loose_bullish"
            elif pattern == "bearish" and price < ma5 < ma10 < ma20:
                detected = "loose_bearish"
            else:
                detected = "none"
        else:
            detected = "none"
        
        if detected == current_pattern and detected != "none":
            current_duration += 1
        else:
            current_pattern = detected
            current_duration = 1 if detected != "none" else 0
        
        # 宽松模式信号强制标记为 WEAK
        display_strength = strength
        if detected in ("loose_bullish", "loose_bearish"):
            display_strength = "WEAK"
        
        results.append({
            "idx": i,
            "pattern": detected,
            "duration": current_duration if detected != "none" else 0,
            "strength": display_strength,
            "alignment": alignment,
            "price": klines[i]["close"],
            "timestamp": klines[i]["close_time"],
        })
    
    return results


async def backtest_symbol(symbol: str, timeframe: str, client: Optional[BinanceClient] = None, days_history: int = 90) -> Dict[str, Any]:
    """
    Similar-State Matching Backtest.
    
    Args:
        symbol: 交易对，如 BTCUSDT
        timeframe: K线周期，如 1d, 4h, 1h
        client: 可选的BinanceClient实例（批量回测时复用）
        days_history: 历史数据天数（保留参数兼容）
    """
    
    if client is not None:
        klines = await client.get_klines(symbol, timeframe, limit=1000)
    else:
        async with BinanceClient() as client:
            klines = await client.get_klines(symbol, timeframe, limit=1000)
    
    window_size, ma_period, min_klines = get_backtest_params(timeframe)
    
    if not klines or len(klines) < min_klines:
        return {
            "symbol": symbol,
            "timeframe": timeframe,
            "stats": {},
            "current_signal": None,
            "recent_signals": [],
            "message": "Insufficient historical data",
        }
    
    # 计算每根K线的趋势状态和持续天数
    trend_states = compute_trend_duration(klines, ma_period)
    
    signals: List[Dict[str, Any]] = []
    
    for state in trend_states:
        if state["pattern"] == "none" or state["strength"] in ("NONE", ""):
            continue
        
        idx = state["idx"]
        if idx + HOLD_KLINES >= len(klines):
            continue
        
        entry_price = state["price"]
        exit_price = klines[idx + HOLD_KLINES]["close"]
        
        if state["pattern"] in ("bullish_all", "loose_bullish"):
            pnl = (exit_price - entry_price) / entry_price * 100
            direction = "long"
        else:  # bearish_all / loose_bearish
            pnl = (entry_price - exit_price) / entry_price * 100
            direction = "short"
        
        # 扣除交易成本（双边0.2%手续费 + 0.1%滑点）
        net_pnl = pnl - 0.3
        
        signals.append({
            "symbol": symbol,
            "timeframe": timeframe,
            "direction": direction,
            "pattern": state["pattern"],
            "duration": state["duration"],
            "duration_bucket": duration_bucket(state["duration"]),
            "strength": state["strength"],
            "entry_price": round(entry_price, 4),
            "exit_price": round(exit_price, 4),
            "pnl_pct": round(pnl, 4),
            "net_pnl_pct": round(net_pnl, 4),
            "entry_time": datetime.fromtimestamp(state["timestamp"] // 1000).isoformat(),
            "exit_time": datetime.fromtimestamp(klines[idx + HOLD_KLINES]["close_time"] // 1000).isoformat(),
        })
    
    # 按 (pattern, duration_bucket) 分组统计
    stats = _aggregate_similar_state_stats(signals)
    
    # 获取当前最新信号状态
    current_state = trend_states[-1] if trend_states else None
    current_signal = None
    if current_state and current_state["pattern"] != "none" and current_state["strength"] not in ("NONE", ""):
        bucket = duration_bucket(current_state["duration"])
        pattern = current_state["pattern"]
        
        # 查找历史上相似状态的统计
        pattern_key = f"{pattern}_{bucket}"
        similar_stats = stats.get(pattern_key, {})
        
        direction = "long" if pattern in ("bullish_all", "loose_bullish") else "short"
        current_signal = {
            "symbol": symbol,
            "timeframe": timeframe,
            "direction": direction,
            "pattern": pattern,
            "duration": current_state["duration"],
            "duration_bucket": bucket,
            "strength": current_state["strength"],
            "current_price": round(current_state["price"], 4),
            "similar_state_stats": similar_stats,
            "recommendation": _generate_recommendation(similar_stats, direction),
        }
    
    return {
        "symbol": symbol,
        "timeframe": timeframe,
        "total_signals": len(signals),
        "stats": stats,
        "current_signal": current_signal,
        "recent_signals": signals[-20:][::-1],
    }


def _aggregate_similar_state_stats(signals: List[Dict[str, Any]]) -> Dict[str, Any]:
    """按 (pattern, duration_bucket) 分组统计；桶级样本不足时回退到 pattern 级聚合"""
    bucket_groups = defaultdict(list)
    pattern_groups = defaultdict(list)
    for s in signals:
        key = f"{s['pattern']}_{s['duration_bucket']}"
        bucket_groups[key].append(s)
        pattern_groups[s["pattern"]].append(s)
    
    def _calc_stats(group: List[Dict[str, Any]]) -> Dict[str, Any]:
        total = len(group)
        if total < 3:
            return {
                "total_signals": total,
                "insufficient_data": True,
                "win_rate": None,
                "avg_pnl": None,
                "avg_net_pnl": None,
                "max_pnl": None,
                "min_pnl": None,
                "profit_factor": None,
                "avg_win": None,
                "avg_loss": None,
            }
        
        profits = [s["net_pnl_pct"] for s in group if s["net_pnl_pct"] > 0]
        losses = [s["net_pnl_pct"] for s in group if s["net_pnl_pct"] <= 0]
        pnls = [s["net_pnl_pct"] for s in group]
        
        avg_win = sum(profits) / len(profits) if profits else 0
        avg_loss = sum(losses) / len(losses) if losses else 0
        if avg_loss != 0:
            profit_factor = abs(avg_win / avg_loss)
        elif profits:
            profit_factor = None  # All wins, no losses — ratio undefined
        else:
            profit_factor = 0.0
        
        return {
            "total_signals": total,
            "insufficient_data": total < 20,  # <20 标记为统计不显著
            "win_rate": round(len(profits) / total * 100, 2),
            "avg_pnl": round(sum(pnls) / total, 4),
            "avg_net_pnl": round(sum(pnls) / total, 4),
            "max_pnl": round(max(pnls), 4),
            "min_pnl": round(min(pnls), 4),
            "profit_factor": round(profit_factor, 2) if profit_factor is not None else None,
            "avg_win": round(avg_win, 4),
            "avg_loss": round(avg_loss, 4),
        }
    
    stats = {}
    for key, group in bucket_groups.items():
        bucket_stats = _calc_stats(group)
        if bucket_stats["total_signals"] < 3:
            # 桶级样本不足，回退到 pattern 级聚合
            pattern = "_".join(key.split("_")[:-1])
            pattern_stats = _calc_stats(pattern_groups.get(pattern, []))
            stats[key] = {
                **pattern_stats,
                "insufficient_data": pattern_stats["insufficient_data"],
            }
        else:
            stats[key] = bucket_stats
    
    return stats


def _generate_recommendation(similar_stats: Dict[str, Any], direction: str) -> Dict[str, Any]:
    """基于相似状态统计生成交易建议"""
    if not similar_stats or similar_stats.get("insufficient_data"):
        return {
            "action": "watch",
            "confidence": "low",
            "score": 0,
            "reason": "历史样本不足，无法评估",
        }
    
    win_rate = similar_stats.get("win_rate", 0)
    avg_net_pnl = similar_stats.get("avg_net_pnl", 0)
    profit_factor = similar_stats.get("profit_factor", 0)
    total = similar_stats.get("total_signals", 0)
    
    # 综合评分
    score = 0
    if win_rate >= 55:
        score += 40
    elif win_rate >= 45:
        score += 20
    
    if avg_net_pnl > 0:
        score += 30
    elif avg_net_pnl > -1:
        score += 10
    
    if profit_factor >= 1.5:
        score += 30
    elif profit_factor >= 1.0:
        score += 15
    
    if total >= 50:
        score += 10
    
    if score >= 80:
        action = "strong_" + direction
        confidence = "high"
    elif score >= 50:
        action = direction
        confidence = "medium"
    else:
        action = "watch"
        confidence = "low"
    
    reason_parts = []
    if win_rate >= 55:
        reason_parts.append(f"历史胜率{win_rate}%")
    if avg_net_pnl > 0:
        reason_parts.append(f"平均收益{avg_net_pnl:.2f}%")
    if profit_factor >= 1.5:
        reason_parts.append(f"盈亏比{profit_factor}")
    
    reason = "；".join(reason_parts) if reason_parts else "历史表现一般，建议观望"
    
    return {
        "action": action,
        "confidence": confidence,
        "score": score,
        "reason": reason,
    }


# ============ 批量回测与持久化 ============

TOP_SYMBOLS = [
    "BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT",
    "DOGEUSDT", "ADAUSDT", "AVAXUSDT", "DOTUSDT", "LINKUSDT",
    "MATICUSDT", "LTCUSDT", "BCHUSDT", "UNIUSDT", "ATOMUSDT",
    "ETCUSDT", "XLMUSDT", "FILUSDT", "ALGOUSDT", "VETUSDT",
]


async def run_batch_backtest(timeframe: str = "1d") -> Dict[str, Any]:
    """
    批量回测前20个币种，将结果持久化到数据库。
    返回所有币种的当前信号和建议列表。
    每个币种独立创建client避免与后台任务冲突。
    """
    all_results = []
    all_current_signals = []
    persist_tasks = []

    for symbol in TOP_SYMBOLS:
        try:
            result = await backtest_symbol(symbol, timeframe)
            all_results.append(result)

            if result.get("current_signal"):
                all_current_signals.append(result["current_signal"])

            # 收集持久化任务，稍后统一 await，避免 fire-and-forget 导致数据丢失
            persist_tasks.append(asyncio.create_task(_persist_signals_async(result.get("recent_signals", [])[:50])))

            await asyncio.sleep(0.3)  # 避免Rate Limit
        except Exception as e:
            logger.error(f"Backtest failed for {symbol}: {e}")

    # 等待所有信号持久化完成（最多 60 秒超时）
    if persist_tasks:
        try:
            await asyncio.wait_for(asyncio.gather(*persist_tasks, return_exceptions=True), timeout=60)
            logger.info(f"Batch backtest: persisted signals for {len(persist_tasks)} symbols")
        except asyncio.TimeoutError:
            logger.warning("Batch backtest signal persistence timed out after 60s")
        except Exception as e:
            logger.warning(f"Batch backtest signal persistence failed: {e}")

    # 按推荐评分排序
    recommendations = sorted(
        [s for s in all_current_signals if s.get("recommendation", {}).get("score", 0) >= 50],
        key=lambda x: x["recommendation"]["score"],
        reverse=True,
    )

    return {
        "timeframe": timeframe,
        "total_symbols_tested": len(all_results),
        "symbols_with_signals": len(all_current_signals),
        "recommendations": recommendations,
        "all_signals": all_current_signals,
        "timestamp": datetime.utcnow().isoformat(),
    }


async def _persist_signals_async(signals: List[Dict[str, Any]]):
    """后台异步持久化回测信号到数据库"""
    try:
        for sig in signals:
            try:
                # 防御性检查：跳过缺少关键字段的信号
                required_keys = [
                    "symbol", "timeframe", "direction", "strength",
                    "entry_price", "entry_time", "pattern", "duration",
                    "exit_price", "exit_time", "net_pnl_pct",
                ]
                if not all(k in sig for k in required_keys):
                    logger.debug(f"Skipping signal with missing fields: {sig.get('symbol', '?')}")
                    continue
                
                signal_id = await db_save_signal(
                    symbol=sig["symbol"],
                    timeframe=sig["timeframe"],
                    direction=sig["direction"],
                    confidence="medium",
                    strength=sig["strength"],
                    entry_price=sig["entry_price"],
                    timestamp=sig["entry_time"],
                    primary_pattern=sig["pattern"],
                    secondary_patterns=[f"duration:{sig['duration']}"],
                )
                if signal_id:
                    await db_update_signal_exit(
                        signal_id=signal_id,
                        exit_price=sig["exit_price"],
                        exit_timestamp=sig["exit_time"],
                        pnl_pct=sig["net_pnl_pct"],
                    )
            except Exception as e:
                logger.warning(f"Failed to persist signal {sig.get('symbol')}: {e}")
    except Exception as e:
        logger.warning(f"Persist signals task failed: {e}")


async def get_backtest_summary(timeframe: str = "1d") -> Dict[str, Any]:
    """从数据库获取汇总统计"""
    try:
        db_stats = await db_get_backtest_stats(timeframe=timeframe)
    except Exception as e:
        logger.warning(f"DB stats failed: {e}")
        db_stats = {}
    
    return {
        "timeframe": timeframe,
        "db_stats_available": bool(db_stats),
        "stats": db_stats,
        "timestamp": datetime.utcnow().isoformat(),
    }


async def _enrich_with_backtest(result: dict, timeframe: str = "1d") -> dict:
    """Run backtest for all recommended long/short tokens and sentiment signals.
    
    This is intended to be called by background refresh tasks so that
    the cached sentiment data stored in the DB is already fully enriched.
    Frontend request handlers should return DB data directly without
    re-running this expensive operation.
    """
    try:
        position_report = result.get("position_report", {})
        signals = result.get("signals", [])
        backtest_results = {}
        total_symbols = 0
        
        # Collect all (symbol, timeframe) pairs from position_report and sentiment signals
        pairs = set()
        for tf in ["1d", "4h", "1w"]:
            report = position_report.get(tf, {})
            for item in report.get("long", []) + report.get("short", []):
                sym = item.get("symbol", "")
                if sym:
                    pairs.add((re.sub(r"USDT$", "", sym.upper()), tf))
        for sig in signals:
            sym = sig.get("symbol", "")
            tf = sig.get("timeframe", "")
            if sym and tf:
                pairs.add((re.sub(r"USDT$", "", sym.upper()), tf))
        
        for tf in ["1d", "4h", "1w"]:
            symbols = [s for s, t in pairs if t == tf]
            total_symbols += len(symbols)
            
            for sym in symbols:
                binance_sym = sym if sym.upper().endswith("USDT") else f"{sym}USDT"
                key = f"{sym}_{tf}"
                if key not in backtest_results:
                    try:
                        bt = await backtest_symbol(binance_sym, tf)
                        backtest_results[key] = bt
                        logger.info(f"Backtest enrichment success: {binance_sym}/{tf}, signals={bt.get('total_signals', 0)}")
                    except Exception as e:
                        logger.warning(f"Backtest enrichment failed for {binance_sym}/{tf}: {e}")
                    await asyncio.sleep(0.3)
        
        if backtest_results:
            result["backtest_results"] = backtest_results
            logger.info(f"Backtest enrichment complete: {len(backtest_results)} results for {total_symbols} symbols")
        else:
            logger.info(f"Backtest enrichment: no results generated for {total_symbols} symbols")
    except Exception as e:
        logger.warning(f"Backtest enrichment error: {e}")
    return result
