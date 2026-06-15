"""
Background refresh tasks and on-chain data trend helpers.
"""

import asyncio
import aiohttp
import json
import os
from datetime import datetime, timedelta, timezone, time
from typing import List, Dict, Optional, Any, Set
from loguru import logger
from fastapi import HTTPException

# External imports
from onchain_collector import OnChainDataCollector, DataRefreshScheduler
from defillama_client import DeFiLlamaClient
from data_aggregator import DataAggregator, AggregatorScheduler, create_aggregator
from db import db_set, db_get_elliott_wave
from backtest import _enrich_with_backtest

# Internal imports
from core import sanitize_for_json
from clients import analyzer, onchain_collector, llama_client, MantleProvider
import state
from state import data_aggregator, aggregator_scheduler
from crypto_utils import encrypt_signal, hash_signal, pack_encrypted_signal
from contract_client import registry

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
                await db_set("sentiment", sentiment, ttl_seconds=15000)
                logger.info("[UnifiedRefresh] Sentiment refreshed")

                # Submit high-confidence encrypted signals to on-chain registry
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

            logger.info("[UnifiedRefresh] Full refresh complete. Sleeping 4 hours...")
        except Exception as e:
            logger.error(f"[UnifiedRefresh] Unexpected error: {e}")

        # Sleep for 4 hours or until stopped
        for _ in range(14400):
            if not state._unified_refresh_running:
                break
            await asyncio.sleep(1)


async def _submit_signals_to_registry(sentiment: dict):
    """Extract medium/high-confidence signals and submit encrypted batch to on-chain registry."""
    if not registry.configured:
        logger.debug("[RegistrySubmission] Registry not configured, skipping")
        return

    position_report = sentiment.get("position_report", {})
    backtest_results = sentiment.get("backtest_results", {})
    signals_to_submit = []

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

                # Build Elliott Wave section (skip if no valid candidate)
                elliott_wave = None
                if ew_candidate and isinstance(ew_candidate, dict):
                    projections = []
                    if isinstance(ew_candidate.get("projections"), list):
                        for proj in ew_candidate["projections"]:
                            if isinstance(proj, dict):
                                projections.append({
                                    "scenario": proj.get("scenario"),
                                    "target_price": proj.get("target_price"),
                                    "confidence": proj.get("confidence"),
                                    "stop_loss": proj.get("stop_loss"),
                                })

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
                        "projections": projections if projections else None,
                    }
                    elliott_wave = {k: v for k, v in elliott_wave.items() if v is not None}
                    if not elliott_wave:
                        elliott_wave = None

                # Build Backtest section
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
                sentiment_section = {
                    "sentiment_index": sentiment.get("sentiment_index"),
                    "market_bias": sentiment.get("market_bias"),
                }
                sentiment_section = {k: v for k, v in sentiment_section.items() if v is not None}
                if not sentiment_section:
                    sentiment_section = None

                payload = {
                    "version": "2.0",
                    "timestamp": datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
                    "agent_id": "mantle-defai-agent-v2.0",
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

                plaintext = json.dumps(payload)
                data_hash = hash_signal(plaintext)
                ciphertext, nonce = encrypt_signal(plaintext)
                encrypted_data = pack_encrypted_signal(ciphertext, nonce)

                signals_to_submit.append({
                    "symbol": symbol,
                    "timeframe": timeframe,
                    "encrypted_data": encrypted_data,
                    "data_hash": data_hash,
                })

    if not signals_to_submit:
        logger.info("[RegistrySubmission] No medium/high-confidence signals to submit")
        return

    # Run blocking web3 call in thread pool
    tx_hash = await asyncio.to_thread(registry.submit_signals_batch, signals_to_submit)
    if tx_hash:
        logger.info(f"[RegistrySubmission] Submitted {len(signals_to_submit)} signals, tx: {tx_hash}")
        logger.info(f"[RegistrySubmission] Payload summary: {len(signals_to_submit)} signals, version 2.0")
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
    logger.info("Elliott Wave scheduler started (interval: 14400s, ttl: 15000s)")

    while _ew_scheduler_running:
        try:
            await _compute_elliott_waves_for_recommended()
        except Exception as e:
            logger.error(f"Elliott Wave scheduler error: {e}")

        # 等待 4 小时，支持优雅停止（每秒检查一次）
        for _ in range(14400):
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


# Global flag for Elliott Wave cleanup scheduler lifecycle
_ew_cleanup_scheduler_running = False

async def _run_elliott_wave_screenshot_cleanup():
    """每天早上 8 点（北京时间 / UTC 00:00）清理前天的 Elliott Wave 截图。"""
    import os
    import re
    from datetime import datetime, timezone
    from db import db_cleanup_expired_elliott_waves

    screenshots_dir = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "tests", "screenshots"
    )
    # 防御性创建目录：如果目录不存在则创建，而不是直接退出
    os.makedirs(screenshots_dir, exist_ok=True)

    # 1. 清理数据库过期记录
    try:
        db_removed = await db_cleanup_expired_elliott_waves()
    except Exception as e:
        logger.error(f"Elliott Wave cleanup: failed to cleanup expired DB entries: {e}")
        db_removed = 0

    # 2. 计算"今天"的 UTC 日期
    today = datetime.now(timezone.utc).date()

    # 3. 扫描并删除前天及更早的 ew_*.png（严格只删除文件，不碰目录）
    removed = 0
    removed_files: List[str] = []
    pattern = re.compile(r"^ew_[A-Z0-9]+_(?:1d|4h|1w)_(\d{8})_\d{6}(?:_raw|_kimi)?\.png$")

    for filename in os.listdir(screenshots_dir):
        if not filename.startswith("ew_") or not filename.endswith(".png"):
            continue
        m = pattern.match(filename)
        if not m:
            continue
        file_path = os.path.join(screenshots_dir, filename)
        if not os.path.isfile(file_path):
            # 安全防御：只处理常规文件，绝不删除目录
            logger.warning(f"Elliott Wave cleanup: skipped non-file entry {filename}")
            continue
        file_date = datetime.strptime(m.group(1), "%Y%m%d").date()
        if file_date < today:  # 只删今天之前的
            try:
                os.remove(file_path)
                removed += 1
                removed_files.append(filename)
                logger.info(f"Elliott Wave cleanup: removed {filename}")
            except Exception as e:
                logger.warning(f"Elliott Wave cleanup: failed to remove {filename}: {e}")

    if removed > 0:
        logger.info(f"Elliott Wave daily cleanup complete: removed {removed} files ({', '.join(removed_files)}), {db_removed} DB rows")
    else:
        logger.info(f"Elliott Wave daily cleanup complete: removed 0 files, {db_removed} DB rows")


async def _run_elliott_wave_cleanup_scheduler():
    """每天 UTC 00:00（北京时间 08:00）执行一次清理。"""
    global _ew_cleanup_scheduler_running
    _ew_cleanup_scheduler_running = True
    logger.info("Elliott Wave cleanup scheduler started (daily at 00:00 UTC / 08:00 CST)")

    while _ew_cleanup_scheduler_running:
        now = datetime.now(timezone.utc)
        # 计算下一个 UTC 00:00
        next_run = datetime.combine(now.date(), time(0, 0), tzinfo=timezone.utc)
        if now >= next_run:
            next_run += timedelta(days=1)
        wait_seconds = (next_run - now).total_seconds()

        logger.info(f"Elliott Wave cleanup: next run at {next_run.isoformat()}, waiting {wait_seconds:.0f}s")

        # 等待到下次执行时间，每秒检查停止标志
        for _ in range(int(wait_seconds)):
            if not _ew_cleanup_scheduler_running:
                break
            await asyncio.sleep(1)

        if not _ew_cleanup_scheduler_running:
            break

        try:
            await _run_elliott_wave_screenshot_cleanup()
        except Exception as e:
            logger.error(f"Elliott Wave cleanup scheduler error: {e}")

    logger.info("Elliott Wave cleanup scheduler stopped gracefully")


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
    daily_report = position_report.get("1d", {})
    long_signals = daily_report.get("long", [])

    # 提取 symbol，去重
    symbols = set()
    for s in long_signals:
        sym = s.get("symbol", "")
        if sym:
            symbols.add(sym.upper().replace("USDT", ""))

    symbols = list(symbols)[:10]  # 最多处理 10 个
    if not symbols:
        logger.info("Elliott Wave: no recommended symbols to analyze")
        return

    logger.info(f"Elliott Wave: analyzing {len(symbols)} symbols: {symbols}")

    tf = "1d"

    # 2. 逐个计算
    for symbol in symbols:
        try:
            async with BinanceClient() as client:
                klines = await client.get_klines(f"{symbol}USDT", tf, 200)
            if not klines or len(klines) < 50:
                logger.warning(f"Elliott Wave: insufficient klines for {symbol}")
                continue

            analyzer = ElliottWaveAnalyzer(deviation=0.10, min_span_ratio=0.10)
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

                # === 调用 Kimi CLI 进行分析 ===
                try:
                    from kimi_vision import analyze_elliott_wave_with_kimi, analyze_elliott_wave_text_only
                    kimi_result = None
                    kimi_structure = None

                    if symbol in ("BTC", "ETH"):
                        # Visual mode for top-tier assets: generate raw chart first
                        raw_chart_filename = f"ew_{symbol}_{tf}_{timestamp}_raw.png"
                        raw_chart_path = os.path.join(screenshots_dir, raw_chart_filename)
                        from chart_generator import plot_raw_candlestick
                        plot_raw_candlestick(klines, f"{symbol}USDT", tf, raw_chart_path, pivots=candidate.get("zigzag_pivots"))

                        try:
                            kimi_result = await asyncio.wait_for(
                                analyze_elliott_wave_with_kimi(
                                    chart_path=raw_chart_path,
                                    symbol=symbol,
                                    timeframe=tf,
                                    wave_candidate=candidate,
                                ),
                                timeout=150,
                            )
                            if kimi_result and not kimi_result.get("error"):
                                kimi_structure = kimi_result.get("kimi_structure")
                        except asyncio.TimeoutError:
                            logger.warning(f"Elliott Wave: [{tf}] Kimi visual analysis timed out for {symbol}, using algorithm result")
                        except Exception as e:
                            logger.error(f"Elliott Wave: [{tf}] Kimi visual analysis failed for {symbol}: {e}")
                    else:
                        # Text-only fast mode for altcoins
                        try:
                            kimi_result = await asyncio.wait_for(
                                analyze_elliott_wave_text_only(
                                    candidate=candidate,
                                    symbol=symbol,
                                    timeframe=tf,
                                ),
                                timeout=60,
                            )
                            if kimi_result and not kimi_result.get("error"):
                                kimi_structure = kimi_result.get("kimi_structure")
                        except asyncio.TimeoutError:
                            logger.warning(f"Elliott Wave: [{tf}] Kimi text analysis timed out for {symbol}, using algorithm result")
                        except Exception as e:
                            logger.error(f"Elliott Wave: [{tf}] Kimi text analysis failed for {symbol}: {e}")

                    if kimi_result and kimi_result.get("error"):
                        logger.warning(
                            f"Elliott Wave: Kimi analysis failed for {symbol}: "
                            f"{kimi_result.get('error')}, using algorithm result"
                        )
                    else:
                        # 如果 Kimi 返回有效浪型结构（waves >= 2），替换算法结果
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

                            if symbol in ("BTC", "ETH"):
                                logger.info(f"Elliott Wave: [visual] generated Kimi annotated chart for {symbol}: {kimi_chart_filename}")
                            else:
                                logger.info(f"Elliott Wave: [text] generated Kimi annotated chart for {symbol}: {kimi_chart_filename}")

                            # 如果 Kimi 有 projections，使用 Kimi 的
                            if kimi_result.get("projections"):
                                candidate["projections"] = kimi_result["projections"]
                                candidate["projection_chart_path"] = f"/screenshots/{kimi_chart_filename}"

                    # 附加完整 Kimi 分析并重新生成带支撑阻力的统一图
                    if kimi_result:
                        candidate["kimi_analysis"] = kimi_result
                        try:
                            plot_elliott_wave_unified(
                                klines,
                                candidate,
                                candidate.get("projections", projections),
                                f"{symbol}USDT",
                                tf,
                                chart_path,
                            )
                        except Exception as plot_err:
                            logger.warning(
                                f"Elliott Wave: failed to regenerate unified chart with Kimi SR for {symbol}: {plot_err}"
                            )

                except Exception as e:
                    logger.error(f"Elliott Wave: unexpected error during Kimi analysis for {symbol}: {e}")

            # 保存到数据库
            await db_save_elliott_wave(
                symbol=symbol,
                timeframe=tf,
                candidates=candidates,
                chart_paths=chart_paths,
                klines_count=len(klines),
                kimi_analysis=kimi_result,
            )
            logger.info(f"Elliott Wave: saved cache for {symbol}")

        except Exception as e:
            logger.error(f"Elliott Wave: failed to analyze {symbol}: {e}")
