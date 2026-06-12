"""
Background refresh tasks and on-chain data trend helpers.
"""

import asyncio
import aiohttp
import base64
import hashlib
import json
import os
from datetime import datetime, timedelta, timezone
from typing import List, Dict, Optional, Any
from loguru import logger
from fastapi import HTTPException

# External imports
from onchain_collector import OnChainDataCollector, DataRefreshScheduler
from defillama_client import DeFiLlamaClient
from data_aggregator import DataAggregator, AggregatorScheduler, create_aggregator
from db import db_set, db_get, db_get_elliott_wave, db_save_onchain_signal
from backtest import _enrich_with_backtest

# Internal imports
from core import sanitize_for_json
from clients import analyzer, onchain_collector, llama_client, MantleProvider
import state
from state import data_aggregator, aggregator_scheduler
from crypto_utils import hash_signal
from contract_client import registry, w3

# Module-level counter for signal submission throttling (every 4 cycles = 60 min)
_signal_submit_counter = 3  # Submit on next refresh (immediate)

# ============ Unified Background Refresh ============

async def _run_unified_refresh():
    """Background task: refresh all data every hour and persist to database."""
    # Wait a bit for initial pre-warm to complete
    await asyncio.sleep(60)

    while state._unified_refresh_running:
        try:
            logger.info("[UnifiedRefresh] Starting full data refresh...")

            # 1. Sentiment
            try:
                sentiment = await analyzer.analyze()
                sentiment = await _enrich_with_backtest(sentiment, "1d")
                await db_set("sentiment", sentiment, ttl_seconds=3960)
                logger.info("[UnifiedRefresh] Sentiment refreshed")

                # Submit high-confidence encrypted signals to on-chain registry (hourly)
                global _signal_submit_counter
                _signal_submit_counter += 1
                if _signal_submit_counter % 4 == 0:
                    try:
                        await _submit_signals_to_registry(sentiment)
                    except Exception as e:
                        logger.warning(f"[UnifiedRefresh] On-chain signal submission failed: {e}")
            except Exception as e:
                logger.warning(f"[UnifiedRefresh] Sentiment failed: {e}")

            # 2. On-chain all
            try:
                onchain_data = await onchain_collector.get_all_data()
                await db_set("onchain_all", onchain_data, ttl_seconds=900)
                logger.info("[UnifiedRefresh] On-chain all refreshed")
            except Exception as e:
                logger.warning(f"[UnifiedRefresh] On-chain all failed: {e}")

            # 3. Overview
            try:
                overview = await onchain_collector.get_overview()
                await db_set("onchain_overview", overview, ttl_seconds=900)
                logger.info("[UnifiedRefresh] Overview refreshed")
            except Exception as e:
                logger.warning(f"[UnifiedRefresh] Overview failed: {e}")

            # 4. Block
            try:
                block = onchain_collector.get_block_data()
                if block:
                    await db_set("onchain_block", block, ttl_seconds=900)
                    logger.info("[UnifiedRefresh] Block refreshed")
            except Exception as e:
                logger.warning(f"[UnifiedRefresh] Block failed: {e}")

            # 5. Gas
            try:
                gas = onchain_collector.get_gas_data()
                if gas:
                    await db_set("onchain_gas", gas, ttl_seconds=900)
                    logger.info("[UnifiedRefresh] Gas refreshed")
            except Exception as e:
                logger.warning(f"[UnifiedRefresh] Gas failed: {e}")

            # 6. Network
            try:
                stats = onchain_collector.get_network_stats()
                await db_set("onchain_network", stats, ttl_seconds=900)
                logger.info("[UnifiedRefresh] Network refreshed")
            except Exception as e:
                logger.warning(f"[UnifiedRefresh] Network failed: {e}")

            # 7. Protocols
            try:
                protocols = await llama_client.get_mantle_protocols()
                await db_set("onchain_protocols", {
                    "protocols": [
                        {
                            "slug": p.slug,
                            "name": p.name,
                            "category": p.category,
                            "tvl": p.tvl,
                            "tvl_change_1d": p.tvl_change_1d,
                            "tvl_change_7d": p.tvl_change_7d,
                            "mcap": p.mcap,
                        }
                        for p in protocols
                    ],
                    "count": len(protocols),
                    "timestamp": datetime.now().isoformat(),
                }, ttl_seconds=900)
                logger.info("[UnifiedRefresh] Protocols refreshed")
            except Exception as e:
                logger.warning(f"[UnifiedRefresh] Protocols failed: {e}")

            # 8. TVL
            try:
                tvl = await llama_client.get_chain_tvl("Mantle")
                await db_set("onchain_tvl", {
                    "chain": "Mantle",
                    "tvl": tvl,
                    "timestamp": datetime.now().isoformat(),
                }, ttl_seconds=900)
                logger.info("[UnifiedRefresh] TVL refreshed")
            except Exception as e:
                logger.warning(f"[UnifiedRefresh] TVL failed: {e}")

            # 9. Aggregated
            try:
                if data_aggregator is not None:
                    agg = await data_aggregator.collect_all(force_refresh=True)
                    # collect_all already persists to DB via data_aggregator
                    logger.info("[UnifiedRefresh] Aggregated refreshed")
            except Exception as e:
                logger.warning(f"[UnifiedRefresh] Aggregated failed: {e}")

            # 10. Trends
            try:
                trends = await fetch_mantle_trends()
                await db_set("mantle_trends", trends, ttl_seconds=900)
                logger.info("[UnifiedRefresh] Trends refreshed")
            except Exception as e:
                logger.warning(f"[UnifiedRefresh] Trends failed: {e}")

            # 11. TVL History (30 days)
            try:
                tvl_history = await fetch_defillama_mantle_tvl_history(30)
                await db_set("mantle_tvl_history_30", {
                    "chain": "Mantle",
                    "days": 30,
                    "history": tvl_history,
                }, ttl_seconds=900)
                logger.info("[UnifiedRefresh] TVL history refreshed")
            except Exception as e:
                logger.warning(f"[UnifiedRefresh] TVL history failed: {e}")

            logger.info("[UnifiedRefresh] Full refresh complete. Sleeping 1 hour...")
        except Exception as e:
            logger.error(f"[UnifiedRefresh] Unexpected error: {e}")

        # Sleep for 1 hour or until stopped
        for _ in range(3600):
            if not state._unified_refresh_running:
                break
            await asyncio.sleep(1)


async def _get_block_with_retry(w3, block_number: int, retries: int = 5, delay: float = 2.0):
    """Fetch a block by number with retries to handle RPC load-balancer transient failures."""
    for attempt in range(retries):
        try:
            return await asyncio.to_thread(w3.eth.get_block, block_number)
        except Exception as e:
            if attempt < retries - 1:
                logger.warning(f"[RegistrySubmission] get_block attempt {attempt + 1} failed: {e}, retrying...")
                await asyncio.sleep(delay)
            else:
                raise


async def _submit_signals_to_registry(sentiment: dict):
    """Extract medium/high-confidence signals and submit plaintext batch to on-chain registry."""
    if not registry.configured:
        logger.debug("[RegistrySubmission] Registry not configured, skipping")
        return

    position_report = sentiment.get("position_report", {})
    backtest_results = sentiment.get("backtest_results", {})
    signals_to_submit = []

    # Fetch on-chain context from DB cache
    onchain_overview = None
    onchain_block = None
    onchain_gas = None
    onchain_network = None
    try:
        onchain_overview = await db_get("onchain_overview")
    except Exception:
        pass
    try:
        onchain_block = await db_get("onchain_block")
    except Exception:
        pass
    try:
        onchain_gas = await db_get("onchain_gas")
    except Exception:
        pass
    try:
        onchain_network = await db_get("onchain_network")
    except Exception:
        pass
    # Build onchain context
    overview = onchain_overview if onchain_overview and isinstance(onchain_overview, dict) else None
    gas_data = onchain_gas if onchain_gas and isinstance(onchain_gas, dict) else None
    block_data = onchain_block if onchain_block and isinstance(onchain_block, dict) else None
    protocol_data = onchain_network if onchain_network and isinstance(onchain_network, dict) else None

    mantle_tvl = None
    if overview:
        mantle_tvl = overview.get("total_tvl") or overview.get("tvl")
    if mantle_tvl is None:
        try:
            onchain_tvl = await db_get("onchain_tvl")
            if onchain_tvl and isinstance(onchain_tvl, dict):
                mantle_tvl = onchain_tvl.get("tvl")
        except Exception:
            pass

    onchain_context = {
        "mantle_tvl": mantle_tvl,
        "tvl_change_24h": overview.get("tvl_change_24h") if overview else None,
        "gas_gwei": gas_data.get("gwei") if gas_data else None,
        "block_number": block_data.get("number") if block_data else None,
        "protocol_count": protocol_data.get("count") if protocol_data else None,
    }
    onchain_context = {k: v for k, v in onchain_context.items() if v is not None}
    if not onchain_context:
        onchain_context = None

    # Build position report summary (counts only, not full signal lists)
    position_report_payload = {}
    for tf in ["1d", "4h", "1w"]:
        report = position_report.get(tf, {})
        tf_summary = {}
        if report.get("long"):
            tf_summary["long_count"] = len(report["long"])
        if report.get("short"):
            tf_summary["short_count"] = len(report["short"])
        if report.get("watch"):
            tf_summary["watch"] = report["watch"]
        if tf_summary:
            position_report_payload[tf] = tf_summary
    if not position_report_payload:
        position_report_payload = None

    # Compute full_data_hash from complete sentiment data (consistent with frontend)
    try:
        clean_sentiment = {k: v for k, v in sentiment.items() if not k.startswith('_')}
        full_data_str = json.dumps(clean_sentiment, ensure_ascii=False, default=str)
        full_data_hash = hashlib.sha256(full_data_str.encode('utf-8')).hexdigest()
    except Exception:
        full_data_hash = None

    for timeframe in ("1d", "4h", "1w"):
        tf_report = position_report.get(timeframe, {})
        for direction in ("long", "short"):
            for signal in tf_report.get(direction, []):
                confidence = signal.get("confidence", "")
                if confidence not in ("high", "medium"):
                    continue
                symbol = signal.get("symbol", "")
                if not symbol:
                    continue

                # Fetch Elliott Wave data
                ew_data = None
                try:
                    ew_data = await db_get_elliott_wave(symbol, timeframe)
                except Exception:
                    pass

                ew_candidate = None
                if ew_data and isinstance(ew_data.get("candidates"), list) and ew_data["candidates"]:
                    ew_candidate = ew_data["candidates"][0]

                # Read chart file, compute sha256 hash, do not embed base64
                chart_hash = None
                chart_path = None
                if ew_data and isinstance(ew_data, dict):
                    chart_paths = ew_data.get("chart_paths", [])
                    if chart_paths and len(chart_paths) > 0:
                        chart_path_val = chart_paths[0]
                        chart_filename = os.path.basename(chart_path_val)
                        full_path = os.path.join(
                            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                            "tests", "screenshots", chart_filename
                        )
                        if os.path.exists(full_path):
                            try:
                                import hashlib
                                with open(full_path, "rb") as f:
                                    file_content = f.read()
                                    chart_hash = hashlib.sha256(file_content).hexdigest()
                                chart_path = chart_path_val
                            except Exception:
                                pass

                # Build Elliott Wave section (skip if no valid candidate)
                elliott_wave = None
                if ew_candidate and isinstance(ew_candidate, dict):
                    overall_confidence = None
                    if ew_data and isinstance(ew_data, dict):
                        kimi_analysis = ew_data.get("kimi_analysis")
                        if isinstance(kimi_analysis, dict):
                            overall_confidence = kimi_analysis.get("overall_confidence")
                        if overall_confidence is None:
                            overall_confidence = ew_candidate.get("score")

                    elliott_wave = {
                        "wave_pattern": ew_candidate.get("wave_pattern"),
                        "current_wave": ew_candidate.get("current_wave"),
                        "direction": ew_candidate.get("direction"),
                        "score": overall_confidence,
                    }
                    if chart_hash:
                        elliott_wave["chart_hash"] = chart_hash
                    if chart_path:
                        elliott_wave["chart_path"] = chart_path
                    elliott_wave = {k: v for k, v in elliott_wave.items() if v is not None}
                    if not elliott_wave:
                        elliott_wave = None

                # Build compact Backtest section
                bt_key = f"{symbol.replace('USDT', '').upper()}_{timeframe}"
                bt_result = backtest_results.get(bt_key, {})
                backtest = None
                if isinstance(bt_result, dict):
                    bt_stats = bt_result.get("stats")
                    if isinstance(bt_stats, dict):
                        backtest = {
                            "win_rate": bt_stats.get("win_rate"),
                            "avg_pnl": bt_stats.get("avg_pnl"),
                            "profit_factor": bt_stats.get("profit_factor"),
                            "total_signals": bt_result.get("total_signals"),
                        }
                        backtest = {k: v for k, v in backtest.items() if v is not None}
                        if not backtest:
                            backtest = None

                # Build Sentiment section
                fng_data = sentiment.get("fng")
                if not isinstance(fng_data, dict):
                    fng_data = {}
                sentiment_section = {
                    "sentiment_index": sentiment.get("sentiment_index"),
                    "market_bias": sentiment.get("market_bias"),
                    "bias_strength": sentiment.get("bias_strength"),
                    "fng_value": fng_data.get("value"),
                    "fng_label": fng_data.get("value_classification"),
                    "bullish_count": sentiment.get("bullish_count"),
                    "bearish_count": sentiment.get("bearish_count"),
                    "neutral_count": sentiment.get("neutral_count"),
                }
                sentiment_section = {k: v for k, v in sentiment_section.items() if v is not None}
                if not sentiment_section:
                    sentiment_section = None

                payload = {
                    "version": "2.1",
                    "timestamp": datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
                    "agent_id": "mantle-defai-agent-v2.1",
                    "decision": {
                        "symbol": symbol,
                        "timeframe": timeframe,
                        "direction": direction,
                        "confidence": confidence,
                        "reason": signal.get("reason", ""),
                    },
                }
                if elliott_wave:
                    payload["elliott_wave"] = elliott_wave
                if backtest:
                    payload["backtest"] = backtest
                if sentiment_section:
                    payload["sentiment"] = sentiment_section
                if position_report_payload:
                    payload["position_report"] = position_report_payload
                if onchain_context:
                    payload["onchain_context"] = onchain_context
                if full_data_hash:
                    payload["full_data_hash"] = full_data_hash

                # Payload size check
                plaintext = json.dumps(payload)
                logger.info(f"[RegistrySubmission] Payload size: {len(plaintext)} bytes")

                data_hash = hash_signal(plaintext)

                signals_to_submit.append({
                    "symbol": symbol,
                    "timeframe": timeframe,
                    "data": plaintext,
                    "data_hash": data_hash,
                })

    if not signals_to_submit:
        logger.info("[RegistrySubmission] No medium/high-confidence signals to submit")
        return

    # Run blocking web3 call in thread pool
    tx_hash = await asyncio.to_thread(registry.submit_signals_batch, signals_to_submit)
    if tx_hash:
        logger.info(f"[RegistrySubmission] Submitted {len(signals_to_submit)} signals, tx: {tx_hash}")
        logger.info(f"[RegistrySubmission] Payload summary: {len(signals_to_submit)} signals, version 2.1")
        # Wait for receipt and persist to DB
        try:
            receipt = await asyncio.to_thread(
                w3.eth.wait_for_transaction_receipt, tx_hash, timeout=60
            )
            block_number = receipt.blockNumber
            try:
                block = await _get_block_with_retry(w3, block_number)
                block_timestamp = int(block.timestamp)
            except Exception as e:
                logger.error(f"[RegistrySubmission] Failed to get block after retries, using UTC fallback: {e}")
                block_timestamp = int(datetime.utcnow().replace(tzinfo=timezone.utc).timestamp())

            for sig in signals_to_submit:
                await db_save_onchain_signal(
                    tx_hash=tx_hash,
                    block_number=block_number,
                    symbol=sig["symbol"],
                    timeframe=sig["timeframe"],
                    data=sig["data"],
                    data_hash=sig["data_hash"],
                    timestamp=block_timestamp,
                )
            logger.info(
                f"[RegistrySubmission] Saved {len(signals_to_submit)} signals to DB (block #{block_number})"
            )
        except Exception as e:
            logger.error(f"[RegistrySubmission] Failed to persist submission records: {e}")
    else:
        logger.warning("[RegistrySubmission] Batch submission returned no tx hash")


# ============ Trend Data Helpers ============

async def fetch_mantle_trends() -> dict:
    """Collect recent Mantle block data and aggregate into 24h hourly trends."""
    provider = MantleProvider()
    if not provider._connected:
        raise HTTPException(status_code=503, detail="Mantle RPC not connected")

    w3 = provider.w3
    latest_block = w3.eth.get_block('latest')
    latest_number = latest_block.number

    # Collect recent blocks (estimate ~2s block time on Mantle => ~1800 blocks for 1h)
    # We'll sample blocks to get ~24 hours of data
    # Target: collect enough blocks to cover 24h, then aggregate by hour
    blocks_per_hour = 1800  # ~2s block time
    target_blocks = blocks_per_hour * 24  # ~24h worth
    sample_interval = max(1, target_blocks // 500)  # sample at most ~500 blocks to avoid timeout

    async def _fetch_block(w3, block_num: int, fetch_gas: bool):
        try:
            block = await asyncio.to_thread(w3.eth.get_block, block_num)
            gas_price = await asyncio.to_thread(lambda: w3.eth.gas_price) if fetch_gas else None
            return {
                "number": block.number,
                "timestamp": block.timestamp,
                "tx_count": len(block.transactions),
                "gas_used": block.gasUsed,
                "gas_limit": block.gasLimit,
                "gas_price_wei": gas_price,
            }
        except Exception:
            return None

    # Build list of blocks to fetch
    block_tasks = []
    for i in range(0, target_blocks, sample_interval):
        block_num = latest_number - i
        if block_num < 0:
            break
        block_tasks.append((block_num, True))  # fetch gas_price for all sampled blocks

    # Fetch concurrently in batches to avoid RPC rate limits
    batch_size = 50
    block_data_list = []
    for i in range(0, len(block_tasks), batch_size):
        batch = block_tasks[i:i + batch_size]
        results = await asyncio.gather(*[_fetch_block(w3, num, fetch_gas) for num, fetch_gas in batch])
        for result in results:
            if result is not None:
                block_data_list.append(result)

    if not block_data_list:
        raise HTTPException(status_code=503, detail="Failed to fetch block data for trends")

    # Sort by timestamp
    block_data_list.sort(key=lambda x: x["timestamp"])

    # Aggregate by hour
    hourly_data: Dict[str, dict] = {}
    for b in block_data_list:
        hour_key = datetime.utcfromtimestamp(b["timestamp"]).strftime("%Y-%m-%d %H:00")
        if hour_key not in hourly_data:
            hourly_data[hour_key] = {
                "tx_counts": [],
                "gas_prices": [],
                "block_numbers": [],
                "timestamp": b["timestamp"],
            }
        hourly_data[hour_key]["tx_counts"].append(b["tx_count"])
        hourly_data[hour_key]["block_numbers"].append(b["number"])
        if b["gas_price_wei"] is not None:
            hourly_data[hour_key]["gas_prices"].append(b["gas_price_wei"])

    # Build result arrays (last 24 hours, fill missing with None or interpolation)
    now = datetime.utcnow()
    block_activity = []
    gas_trend = []
    timestamps = []

    for i in range(23, -1, -1):
        hour_dt = now.replace(minute=0, second=0, microsecond=0) - timedelta(hours=i)
        hour_key = hour_dt.strftime("%Y-%m-%d %H:00")
        timestamps.append(hour_dt.isoformat())

        if hour_key in hourly_data:
            avg_tx = round(sum(hourly_data[hour_key]["tx_counts"]) / len(hourly_data[hour_key]["tx_counts"]), 1)
            block_activity.append(avg_tx)
            if hourly_data[hour_key]["gas_prices"]:
                avg_gas = round(sum(hourly_data[hour_key]["gas_prices"]) / len(hourly_data[hour_key]["gas_prices"]) / 1e9, 4)
                gas_trend.append(avg_gas)
            else:
                gas_trend.append(None)
        else:
            block_activity.append(None)
            gas_trend.append(None)

    return {
        "block_activity": block_activity,
        "gas_trend": gas_trend,
        "timestamps": timestamps,
    }


async def fetch_defillama_mantle_tvl_history(days: int = 30) -> List[dict]:
    """Fetch Mantle chain historical TVL from DeFiLlama API."""
    url = "https://api.llama.fi/v2/historicalChainTvl/Mantle"
    timeout = aiohttp.ClientTimeout(total=30, connect=10)

    async with aiohttp.ClientSession(timeout=timeout) as session:
        async with session.get(url, headers={"Accept": "application/json"}) as resp:
            resp.raise_for_status()
            data = await resp.json()

    if not isinstance(data, list):
        raise HTTPException(status_code=503, detail="Unexpected DeFiLlama response format")

    # data is list of {date: timestamp, tvl: float}
    history = []
    for point in data:
        ts = point.get("date")
        tvl = point.get("tvl")
        if ts is not None and tvl is not None:
            history.append({
                "date": datetime.utcfromtimestamp(int(ts)).strftime("%Y-%m-%d"),
                "tvl": float(tvl),
            })

    # Return last N days
    return history[-days:] if len(history) > days else history


# Global flag for Elliott Wave scheduler lifecycle
_ew_scheduler_running = False


async def _run_elliott_wave_scheduler():
    """每小时自动计算推荐做多/做空币种的日线级别艾略特波浪。
    
    包含自动重启机制：如果内部循环因异常退出，会等待 30 秒后自动重启。
    服务 shutdown 时通过 _ew_scheduler_running = False 优雅停止。
    """
    global _ew_scheduler_running
    _ew_scheduler_running = True
    logger.info("Elliott Wave scheduler started (interval: 3600s)")

    while _ew_scheduler_running:
        try:
            await _compute_elliott_waves_for_recommended()
        except Exception as e:
            logger.error(f"Elliott Wave scheduler error: {e}")

        # 等待 1 小时，支持优雅停止（每秒检查一次）
        for _ in range(3600):
            if not _ew_scheduler_running:
                break
            await asyncio.sleep(1)

    logger.info("Elliott Wave scheduler stopped gracefully")


async def _run_elliott_wave_scheduler_with_restart():
    """带自动重启的 Elliott Wave scheduler 包装器。
    
    如果 _run_elliott_wave_scheduler 因未捕获异常退出，
    等待 30 秒后自动重启，确保服务长期稳定运行。
    """
    global _ew_scheduler_running
    while True:
        try:
            await _run_elliott_wave_scheduler()
        except asyncio.CancelledError:
            logger.info("Elliott Wave scheduler wrapper cancelled")
            _ew_scheduler_running = False
            raise
        except Exception as e:
            logger.error(f"Elliott Wave scheduler crashed, restarting in 30s: {e}")
            _ew_scheduler_running = False
            await asyncio.sleep(30)


async def _compute_elliott_waves_for_recommended():
    """从 sentiment position_report 获取推荐币种，计算波浪并存入缓存。"""
    import os
    from datetime import datetime, timezone
    from elliott_wave import ElliottWaveAnalyzer
    from chart_generator import plot_elliott_wave
    from clients import BinanceClient
    from db import db_get, db_save_elliott_wave

    # 1. 获取 sentiment 缓存
    sentiment_data = await db_get("sentiment")
    if not sentiment_data:
        logger.warning("Elliott Wave: no sentiment data available")
        return

    position_report = sentiment_data.get("position_report", {})

    for tf in ["1d", "4h", "1w"]:
        daily_report = position_report.get(tf, {})
        long_signals = daily_report.get("long", [])
        short_signals = daily_report.get("short", [])

        # 提取 symbol，去重
        symbols = set()
        for s in long_signals + short_signals:
            sym = s.get("symbol", "")
            if sym:
                symbols.add(sym.upper().replace("USDT", ""))

        symbols = list(symbols)[:30]  # 最多处理 30 个
        if not symbols:
            logger.info(f"Elliott Wave: [{tf}] no recommended symbols to analyze")
            continue

        logger.info(f"Elliott Wave: [{tf}] analyzing {len(symbols)} symbols: {symbols}")

        # 2. 逐个计算
        for symbol in symbols:
            try:
                async with BinanceClient() as client:
                    klines = await client.get_klines(f"{symbol}USDT", tf, 500)
                if not klines or len(klines) < 50:
                    logger.warning(f"Elliott Wave: [{tf}] insufficient klines for {symbol}")
                    continue

                analyzer = ElliottWaveAnalyzer(deviation=0.10, min_span_ratio=0.15)
                candidates = analyzer.analyze(klines, top_n=3)

                # 生成图表
                chart_paths = []
                timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
                screenshots_dir = os.path.join(
                    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                    "tests", "screenshots"
                )
                os.makedirs(screenshots_dir, exist_ok=True)

                # 只给最高分 candidate 生成一张统一图
                kimi_result = None
                if candidates:
                    candidate = candidates[0]
                    # 生成走势预测数据（基于波浪结构直接计算，不依赖AI）
                    projections = []
                    last_price = float(klines[-1]["close"])
                    wave_direction = candidate.get("direction", "up")
                    waves = candidate.get("waves", [])

                    if waves and len(waves) >= 2:
                        avg_wave_size = sum(abs(w["end_price"] - w["start_price"]) for w in waves) / len(waves)
                        if wave_direction == "up":
                            projections = [
                                {"scenario": "bullish", "description": "Extension", "target_price": round(last_price + avg_wave_size * 1.618, 2)},
                                {"scenario": "bearish", "description": "Correction", "target_price": round(last_price - avg_wave_size * 0.618, 2)},
                                {"scenario": "neutral", "description": "Consolidation", "target_price": round(last_price, 2)},
                            ]
                        else:
                            projections = [
                                {"scenario": "bearish", "description": "Extension", "target_price": round(last_price - avg_wave_size * 1.618, 2)},
                                {"scenario": "bullish", "description": "Bounce", "target_price": round(last_price + avg_wave_size * 0.618, 2)},
                                {"scenario": "neutral", "description": "Consolidation", "target_price": round(last_price, 2)},
                            ]

                    chart_filename = f"ew_{symbol}_{tf}_{timestamp}.png"
                    chart_path = os.path.join(screenshots_dir, chart_filename)
                    from chart_generator import plot_elliott_wave_unified
                    plot_elliott_wave_unified(klines, candidate, projections, f"{symbol}USDT", tf, chart_path)
                    candidate["chart_path"] = f"/screenshots/{chart_filename}"
                    chart_paths.append(f"/screenshots/{chart_filename}")

                    if projections:
                        candidate["projections"] = projections
                        candidate["projection_chart_path"] = f"/screenshots/{chart_filename}"  # 向后兼容，指向统一图

                    # === 调用 Kimi CLI 进行视觉分析 ===
                    try:
                        raw_chart_filename = f"ew_{symbol}_{tf}_{timestamp}_raw.png"
                        raw_chart_path = os.path.join(screenshots_dir, raw_chart_filename)
                        from chart_generator import plot_raw_candlestick
                        plot_raw_candlestick(klines, f"{symbol}USDT", tf, raw_chart_path)

                        from kimi_vision import analyze_elliott_wave_with_kimi
                        kimi_result = await asyncio.wait_for(
                            analyze_elliott_wave_with_kimi(
                                chart_path=raw_chart_path,
                                symbol=symbol,
                                timeframe=tf,
                                wave_candidate=candidate,
                            ),
                            timeout=90,
                        )

                        # 如果 Kimi 返回有效浪型结构（waves >= 2），替换算法结果
                        kimi_structure = kimi_result.get("kimi_structure") if kimi_result else None
                        if kimi_structure and len(kimi_structure.get("waves", [])) >= 2:
                            candidate["waves"] = kimi_structure["waves"]
                            candidate["wave_pattern"] = kimi_structure.get("wave_pattern", candidate.get("wave_pattern"))
                            candidate["direction"] = kimi_structure.get("direction", candidate.get("direction"))
                            candidate["current_wave"] = kimi_structure.get("current_wave", candidate.get("current_wave"))
                            candidate["kimi_annotated"] = True

                            # 重新生成 Kimi 标注图
                            kimi_chart_filename = f"ew_{symbol}_{tf}_{timestamp}_kimi.png"
                            kimi_chart_path = os.path.join(screenshots_dir, kimi_chart_filename)
                            from chart_generator import plot_kimi_annotated_wave
                            plot_kimi_annotated_wave(klines, kimi_structure, f"{symbol}USDT", tf, kimi_chart_path)
                            candidate["chart_path"] = f"/screenshots/{kimi_chart_filename}"
                            chart_paths = [f"/screenshots/{kimi_chart_filename}"]

                            # 如果 Kimi 有 projections，使用 Kimi 的
                            if kimi_result.get("projections"):
                                candidate["projections"] = kimi_result["projections"]
                                candidate["projection_chart_path"] = f"/screenshots/{kimi_chart_filename}"

                    except asyncio.TimeoutError:
                        logger.warning(f"Elliott Wave: [{tf}] Kimi analysis timed out for {symbol}, using algorithm result")
                    except Exception as e:
                        logger.error(f"Elliott Wave: [{tf}] Kimi analysis failed for {symbol}: {e}")

                # 保存到数据库
                await db_save_elliott_wave(
                    symbol=symbol,
                    timeframe=tf,
                    candidates=candidates,
                    chart_paths=chart_paths,
                    klines_count=len(klines),
                    kimi_analysis=kimi_result,
                    ttl=86400,
                )
                logger.info(f"Elliott Wave: [{tf}] saved cache for {symbol}")

            except Exception as e:
                logger.error(f"Elliott Wave: [{tf}] failed to analyze {symbol}: {e}")
