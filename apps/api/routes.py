"""
All API endpoints registered via FastAPI APIRouter.
"""

import asyncio
import json
import os
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Any
from loguru import logger

from fastapi import APIRouter, HTTPException, Request, Body
from web3 import Web3

# External modules
import time
from db import db_get, db_set, db_manager, db_get_transactions, db_get_elliott_wave, db_save_elliott_wave, db_get_all_elliott_waves, db_get_recent_onchain_signals
from onchain_collector import OnChainDataCollector, DataRefreshScheduler
from defillama_client import DeFiLlamaClient
from data_aggregator import DataAggregator, AggregatorScheduler, create_aggregator

# Internal modules
from core import (
    cache, sanitize_for_json, rate_limit, CACHE_TTL,
    Timeframe, SentimentRequest, SwapQuoteRequest, SwapBuildTxRequest, WalletValidateRequest,
    get_client_ip, WHITELIST,
)
from clients import (
    analyzer, router, onchain_collector, onchain_scheduler,
    llama_client, whale_monitor, MantleProvider,
    WMNT, USDC, USDT, LB_ROUTER, LB_ROUTER_ABI, MANTLE_CHAIN_ID,
)
from state import data_aggregator, aggregator_scheduler
from background import fetch_mantle_trends, fetch_defillama_mantle_tvl_history
from chain_indexer import get_chain_indexer
from trend_scheduler import get_trend_scheduler
from kimi_analyzer import get_kimi_analyzer
from moralis_client import MoralisClient
from trend_aggregator import _is_stablecoin
from token_mapping import get_recommended_symbols, get_source_symbol, get_recommended_tokens_for_monitoring
from backtest import backtest_symbol, run_batch_backtest, get_backtest_summary, _enrich_with_backtest
from contract_client import registry

api_router = APIRouter()


def _build_projections(candidate: Dict[str, Any], klines: List[Dict]) -> List[Dict[str, Any]]:
    """Build default projections based on wave structure with confidence scores."""
    projections = []
    last_price = float(klines[-1]["close"])
    wave_direction = candidate.get("direction", "up")
    waves = candidate.get("waves", [])

    if waves and len(waves) >= 2:
        avg_wave_size = sum(abs(w["end_price"] - w["start_price"]) for w in waves) / len(waves)
        if wave_direction == "up":
            projections = [
                {"scenario": "bullish", "description": "Extension", "target_price": round(last_price + avg_wave_size * 1.618, 2), "confidence": 0.5},
                {"scenario": "bearish", "description": "Correction", "target_price": round(last_price - avg_wave_size * 0.618, 2), "confidence": 0.3},
                {"scenario": "neutral", "description": "Consolidation", "target_price": round(last_price, 2), "confidence": 0.2},
            ]
        else:
            projections = [
                {"scenario": "bearish", "description": "Extension", "target_price": round(last_price - avg_wave_size * 1.618, 2), "confidence": 0.5},
                {"scenario": "bullish", "description": "Bounce", "target_price": round(last_price + avg_wave_size * 0.618, 2), "confidence": 0.3},
                {"scenario": "neutral", "description": "Consolidation", "target_price": round(last_price, 2), "confidence": 0.2},
            ]

    return projections


def require_whitelist(request: Request):
    """Require IP whitelist for sensitive endpoints.
    DEBUG=true 时自动跳过白名单检查，方便本地开发测试。
    """
    from core import DEBUG_MODE
    if DEBUG_MODE:
        return
    client_ip = get_client_ip(request)
    if client_ip not in WHITELIST:
        raise HTTPException(status_code=403, detail="Access denied: IP not in whitelist")

@api_router.get("/", tags=["Root"], summary="API Root", description="Returns basic API status and metadata.")
async def root():
    return {
        "status": "ok",
        "service": "Mantle DeFAI Trader API",
        "version": "1.2.0",
        "features": [
            "sentiment_analysis",
            "on_chain_data",
            "dex_quotes",
            "wallet",
            "swap_execution",
        ],
        "timestamp": datetime.now().isoformat()
    }

@api_router.get("/health", tags=["Health"], summary="Health Check", description="Returns service health status including external dependency connectivity.")
async def health():
    db_stats = await db_manager.get_stats() if db_manager else {"available": False}
    return {
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "services": {
            "binance": "ok",
            "mantle": "connected" if analyzer.mantle._connected else "disconnected",
            "on_chain_collector": "active" if onchain_scheduler.running else "inactive",
            "database": "ok" if db_stats.get("available") else "unavailable",
        }
    }

@api_router.post("/api/sentiment/analyze", tags=["Sentiment"], summary="Analyze Market Sentiment", description="Analyze market sentiment with Mantle on-chain data. Supports timeframe selection and force refresh. Primarily used by background tasks.")
@rate_limit()
async def analyze_sentiment(request: Request, req: SentimentRequest):
    try:
        client_ip = get_client_ip(request)
        is_whitelisted = client_ip in WHITELIST

        # If not force refresh, check DB cache first before expensive computation
        if not req.force_refresh:
            db_data = await db_get("sentiment")
            if db_data is not None:
                result = sanitize_for_json(db_data)
                return {"success": True, "data": result}

        # Force refresh or DB miss: compute fresh data
        result = await analyzer.analyze(req.timeframe.value, req.limit, req.force_refresh)
        # Enrich with backtest data for recommended long/short tokens
        result = await _enrich_with_backtest(result, req.timeframe.value)
        # Persist FULL data to database for fast retrieval
        try:
            await db_set("sentiment", result, ttl_seconds=15000)
        except Exception as db_err:
            logger.warning(f"Failed to persist sentiment to DB: {db_err}")
        # Position report (long/short) is now visible to all users
        return {"success": True, "data": result}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Sentiment analysis failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))

def _trim_backtest_results_for_api(data: Dict[str, Any]) -> Dict[str, Any]:
    """Trim verbose backtest_result fields to reduce /api/sentiment/latest payload size.

    Keeps only the fields the frontend actually needs and limits recent_signals to the
    latest 3 entries.  Does not mutate cached/DB source data.
    """
    if not isinstance(data, dict):
        return data

    result = dict(data)
    backtest_results = result.get("backtest_results")
    if not backtest_results:
        return result

    stats_keep = {
        "total_signals",
        "win_rate",
        "avg_pnl",
        "avg_net_pnl",
        "profit_factor",
        "max_pnl",
        "min_pnl",
        "insufficient_data",
    }

    def _trim_stats(stats: Any) -> Any:
        if not isinstance(stats, dict):
            return stats
        # stats may be a flat dict or a nested dict of bucket -> stats.
        trimmed_stats: Dict[str, Any] = {}
        for key, value in stats.items():
            if isinstance(value, dict):
                trimmed_stats[key] = {k: v for k, v in value.items() if k in stats_keep}
            elif key in stats_keep:
                trimmed_stats[key] = value
        return trimmed_stats

    current_signal_keep = {
        "symbol",
        "timeframe",
        "direction",
        "pattern",
        "duration",
        "strength",
        "current_price",
        "recommendation",
        "similar_state_stats",
    }

    recent_signal_keep = {
        "symbol",
        "timeframe",
        "direction",
        "pattern",
        "duration",
        "entry_price",
        "exit_price",
        "pnl_pct",
        "pnl",
        "exit_at",
        "strength",
        "confidence",
        "ma_alignment",
    }

    def _trim_entry(entry: Any) -> Any:
        if not isinstance(entry, dict):
            return entry

        trimmed: Dict[str, Any] = {k: v for k, v in entry.items() if k in {"symbol", "timeframe", "total_signals"}}

        if "stats" in entry:
            trimmed["stats"] = _trim_stats(entry["stats"])

        if "current_signal" in entry and isinstance(entry["current_signal"], dict):
            cs = entry["current_signal"]
            trimmed["current_signal"] = {k: v for k, v in cs.items() if k in current_signal_keep}
            if "similar_state_stats" in cs:
                trimmed["current_signal"]["similar_state_stats"] = _trim_stats(cs["similar_state_stats"])

        if "recent_signals" in entry and isinstance(entry["recent_signals"], list):
            recent = entry["recent_signals"][-3:] if len(entry["recent_signals"]) > 3 else entry["recent_signals"]
            trimmed["recent_signals"] = [
                {k: v for k, v in sig.items() if k in recent_signal_keep}
                for sig in recent
                if isinstance(sig, dict)
            ]

        return trimmed

    if isinstance(backtest_results, dict):
        result["backtest_results"] = {k: _trim_entry(v) for k, v in backtest_results.items()}
    elif isinstance(backtest_results, list):
        result["backtest_results"] = [_trim_entry(v) for v in backtest_results]

    return result


@api_router.get("/api/sentiment/latest", tags=["Sentiment"], summary="Get Latest Sentiment", description="Get cached sentiment data from database. Background tasks refresh every hour with full enrichment.")
@rate_limit()
async def get_latest_sentiment(request: Request, wallet_address: Optional[str] = None):
    try:
        # 1. Try database first (background tasks refresh every 4 hours with enrichment)
        db_data = await db_get("sentiment")
        if db_data is not None:
            result = sanitize_for_json(db_data)
            # 如果没有 backtest_results，尝试 enrichment
            if not result.get("backtest_results"):
                try:
                    result = await _enrich_with_backtest(result, "1d")
                    # 将 enrichment 结果保存回缓存
                    await db_set("sentiment", result, ttl_seconds=15000)
                except Exception as enrich_err:
                    logger.warning(f"Backtest enrichment failed in get_latest_sentiment: {enrich_err}")
            result = _trim_backtest_results_for_api(result)
            has_backtest = bool(result.get("backtest_results"))
            return {
                "success": True,
                "data": result,
                "cached": True,
                "source": "db",
                "has_backtest": has_backtest,
            }

        # 2. Fallback to in-memory cache
        cached = await cache.get("sentiment", "1h", 50)
        if cached:
            result = sanitize_for_json(cached)
            result = _trim_backtest_results_for_api(result)
            has_backtest = bool(result.get("backtest_results"))
            return {
                "success": True,
                "data": result,
                "cached": True,
                "source": "memory",
                "has_backtest": has_backtest,
            }

        # 3. Cache miss: never compute live from frontend request; background refresh will populate cache
        logger.info("Sentiment cache miss; returning preparing message")
        return {
            "success": True,
            "data": {"message": "Data is being prepared, please refresh later"},
            "cached": False,
            "source": "empty",
            "has_backtest": False,
        }
    except Exception as e:
        logger.error(f"Failed to get latest sentiment: {e}")
        return {"success": False, "message": str(e)}

@api_router.post("/api/sentiment/elliott-wave", tags=["Sentiment"], summary="Elliott Wave Analysis", description="Analyze Elliott Wave pattern for a given symbol using K-line data, generate annotated chart, and optionally use Kimi Vision for refinement.")
@rate_limit()
async def analyze_elliott_wave(request: Request, body: dict = Body(...)):
    start_time = time.time()

    try:
        body = body or {}
        symbol = body.get("symbol", "BTC").upper()
        timeframe = body.get("timeframe", "1d")
        limit = min(max(body.get("limit", 200), 50), 1000)
        include_kimi = body.get("include_kimi", True)
        force_refresh = body.get("force_refresh", False)

        # Check cache first (unless force_refresh)
        if not force_refresh:
            cached = await db_get_elliott_wave(symbol, timeframe)
            if cached:
                cached["is_cached"] = True
                cached["cached_at"] = cached.get("computed_at")
                return {"success": True, "data": cached}

        # 1. 获取 K 线数据
        from clients import BinanceClient
        symbol_pair = f"{symbol}USDT"
        async with BinanceClient() as client:
            klines = await client.get_klines(symbol_pair, interval=timeframe, limit=limit)

        if not klines or len(klines) < 50:
            return {"success": False, "message": f"Insufficient K-line data for {symbol}, got {len(klines) if klines else 0} candles"}

        # 2. 艾略特波浪分析
        from elliott_wave import ElliottWaveAnalyzer
        ew_analyzer = ElliottWaveAnalyzer(deviation=0.10, min_span_ratio=0.10)
        candidates = ew_analyzer.analyze(klines, top_n=3)

        # 预定义截图目录
        from chart_generator import plot_elliott_wave_unified, plot_raw_candlestick
        import os
        from datetime import datetime

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        screenshots_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "tests", "screenshots")
        os.makedirs(screenshots_dir, exist_ok=True)

        if not candidates:
            # 生成基础K线图，即使没有波浪模式
            raw_chart_filename = f"ew_{symbol}_{timeframe}_{timestamp}_raw.png"
            raw_chart_path = os.path.join(screenshots_dir, raw_chart_filename)
            plot_raw_candlestick(klines, symbol, timeframe, raw_chart_path)
            chart_paths = [f"/screenshots/{raw_chart_filename}"]
            try:
                await db_save_elliott_wave(
                    symbol=symbol,
                    timeframe=timeframe,
                    candidates=[],
                    chart_paths=chart_paths,
                    klines_count=len(klines),
                    kimi_analysis=None,
                )
            except Exception as cache_err:
                logger.warning(f"Failed to save Elliott Wave cache: {cache_err}")
            return {"success": True, "data": {"symbol": symbol, "timeframe": timeframe, "klines_count": len(klines), "candidates": [], "chart_paths": chart_paths, "message": "No Elliott Wave patterns found in current data"}}

        # 处理所有 candidates 的基础字段（保留完整列表供前端概率展示）
        enriched_candidates = []
        for candidate in candidates:
            if "current_wave" not in candidate:
                waves = candidate.get("waves", [])
                if waves:
                    last_wave = waves[-1]
                    label = last_wave.get("wave", "?")
                    candidate["current_wave"] = f"Wave {label}"
                else:
                    candidate["current_wave"] = "Unknown"
            enriched_candidates.append(candidate)

        # 只给最高分 candidate 生成一张统一图
        chart_paths = []
        if candidates:
            candidate = candidates[0]

            # 生成走势预测数据（基于波浪结构直接计算，不依赖AI）
            projections = _build_projections(candidate, klines)

            # 1. 生成统一图表（包含K线+波浪标注+走势预测+信息面板）
            chart_filename = f"ew_{symbol}_{timeframe}_{timestamp}.png"
            chart_path = os.path.join(screenshots_dir, chart_filename)
            plot_elliott_wave_unified(klines, candidate, projections, symbol, timeframe, chart_path)
            candidate["chart_path"] = f"/screenshots/{chart_filename}"
            chart_paths.append(f"/screenshots/{chart_filename}")

            if projections:
                candidate["projections"] = projections
                candidate["projection_chart_path"] = f"/screenshots/{chart_filename}"  # 向后兼容，指向统一图

            # 2. 调用Kimi分析（BTC/ETH走视觉模式，其他走快速文本模式）
            kimi_annotated = False
            if include_kimi:
                try:
                    from kimi_vision import analyze_elliott_wave_with_kimi, analyze_elliott_wave_text_only
                    kimi_result = None
                    kimi_structure = None
                    raw_chart_path = None

                    if symbol in ("BTC", "ETH"):
                        # Visual mode for top-tier assets: generate raw chart first
                        raw_chart_filename = f"ew_{symbol}_{timeframe}_{timestamp}_raw.png"
                        raw_chart_path = os.path.join(screenshots_dir, raw_chart_filename)
                        plot_raw_candlestick(klines, symbol, timeframe, raw_chart_path, pivots=candidate.get("zigzag_pivots"))

                        kimi_result = await asyncio.wait_for(
                            analyze_elliott_wave_with_kimi(
                                chart_path=raw_chart_path,
                                symbol=symbol,
                                timeframe=timeframe,
                                wave_candidate=candidate,
                            ),
                            timeout=360,
                        )
                    else:
                        # Text-only fast mode for altcoins
                        kimi_result = await asyncio.wait_for(
                            analyze_elliott_wave_text_only(
                                candidate=candidate,
                                symbol=symbol,
                                timeframe=timeframe,
                            ),
                            timeout=120,
                        )

                    candidate["kimi_analysis"] = kimi_result
                    kimi_structure = kimi_result.get("kimi_structure") if kimi_result else None

                    # 3. 如果Kimi返回有效浪型结构，用Kimi的重新画图
                    if kimi_structure and "waves" in kimi_structure:
                        from chart_generator import plot_kimi_annotated_wave
                        kimi_chart_filename = f"ew_{symbol}_{timeframe}_{timestamp}_kimi.png"
                        kimi_chart_path = os.path.join(screenshots_dir, kimi_chart_filename)
                        plot_kimi_annotated_wave(klines, kimi_structure, symbol, timeframe, kimi_chart_path)
                        # 覆盖chart_path为Kimi标注的图，chart_paths 只保留这一张
                        candidate["chart_path"] = f"/screenshots/{kimi_chart_filename}"
                        chart_paths = [f"/screenshots/{kimi_chart_filename}"]
                        candidate["kimi_annotated"] = True
                        candidate["kimi_wave_structure"] = kimi_structure

                        # 可选：用Kimi的waves替换算法的waves
                        if len(kimi_structure.get("waves", [])) >= 2:
                            candidate["waves"] = kimi_structure["waves"]
                            candidate["wave_pattern"] = kimi_structure.get("wave_pattern", candidate.get("wave_pattern"))
                            candidate["direction"] = kimi_structure.get("direction", candidate.get("direction"))
                            candidate["current_wave"] = kimi_structure.get("current_wave", "")
                        kimi_annotated = True

                    # 附加完整 Kimi 分析并重新生成带支撑阻力的统一图
                    if kimi_result:
                        try:
                            plot_elliott_wave_unified(
                                klines,
                                candidate,
                                candidate.get("projections", projections),
                                symbol,
                                timeframe,
                                chart_path,
                            )
                        except Exception as plot_err:
                            logger.warning(f"Failed to regenerate unified chart with Kimi SR: {plot_err}")
                except asyncio.TimeoutError:
                    logger.warning("Kimi Vision analysis timed out after 360s, using algorithm result")
                    candidate["kimi_analysis"] = {"error": "timeout"}
                except ImportError:
                    logger.warning("kimi_vision module not available, skipping Kimi analysis")
                except Exception as kimi_err:
                    logger.warning(f"Kimi analysis failed: {kimi_err}")
                    candidate["kimi_analysis"] = {"error": str(kimi_err)}

            if not kimi_annotated:
                candidate["kimi_annotated"] = False

        # Save to cache
        try:
            kimi_analysis_dict = enriched_candidates[0].get("kimi_analysis") if enriched_candidates else None
            await db_save_elliott_wave(
                symbol=symbol,
                timeframe=timeframe,
                candidates=enriched_candidates,
                chart_paths=chart_paths,
                klines_count=len(klines),
                kimi_analysis=kimi_analysis_dict,
            )
        except Exception as cache_err:
            logger.warning(f"Failed to save Elliott Wave cache: {cache_err}")

        elapsed_ms = int((time.time() - start_time) * 1000)

        return {
            "success": True,
            "data": {
                "symbol": symbol,
                "timeframe": timeframe,
                "klines_count": len(klines),
                "candidates": enriched_candidates,
                "chart_paths": chart_paths,
                "analysis_time_ms": elapsed_ms,
            }
        }

    except Exception as e:
        logger.error(f"Elliott Wave analysis failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@api_router.get("/api/sentiment/elliott-wave", tags=["Sentiment"], summary="Get Elliott Wave Cache", description="Get cached Elliott Wave analysis for a symbol.")
@rate_limit()
async def get_elliott_wave_cache(request: Request, symbol: str, timeframe: str = "1d"):
    try:
        cached = await db_get_elliott_wave(symbol, timeframe)
        if not cached:
            return {"success": False, "message": "No cached data found"}
        cached["is_cached"] = True
        cached["cached_at"] = cached.get("computed_at")
        return {"success": True, "data": cached}
    except Exception as e:
        logger.error(f"Failed to get Elliott Wave cache: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@api_router.get("/api/sentiment/elliott-wave/list", tags=["Sentiment"], summary="Get Elliott Wave List", description="Get list of all cached Elliott Wave symbols with charts.")
@rate_limit()
async def get_elliott_wave_list(request: Request, timeframe: str = "1d"):
    """Get list of all cached Elliott Wave symbols with charts."""
    try:
        waves = await db_get_all_elliott_waves(timeframe=timeframe)
        # 过滤有 chart_paths 的记录
        result = []
        for w in waves:
            chart_paths = w.get("chart_paths", [])
            if chart_paths and len(chart_paths) > 0:
                result.append({
                    "symbol": w["symbol"],
                    "timeframe": w.get("timeframe", timeframe),
                    "chart_paths": chart_paths,
                    "computed_at": w.get("computed_at"),
                    "wave_pattern": w.get("candidates", [{}])[0].get("wave_pattern") if w.get("candidates") else None,
                })
        return {"success": True, "count": len(result), "data": result}
    except Exception as e:
        logger.error(f"Failed to get Elliott Wave list: {e}")
        return {"success": False, "message": str(e)}


@api_router.post("/api/sentiment/elliott-wave/refresh", tags=["Sentiment"], summary="Refresh Elliott Wave Analysis", description="Force refresh Elliott Wave analysis for a symbol and update cache.")
@rate_limit()
async def refresh_elliott_wave(request: Request, body: dict = Body(...)):
    """Force recompute Elliott Wave and update cache."""
    start_time = time.time()
    try:
        body = body or {}
        symbol = body.get("symbol", "BTC").upper()
        timeframe = body.get("timeframe", "1d")
        limit = min(max(body.get("limit", 200), 50), 1000)
        include_kimi = body.get("include_kimi", True)

        # 1. 获取 K 线数据
        from clients import BinanceClient
        symbol_pair = f"{symbol}USDT"
        async with BinanceClient() as client:
            klines = await client.get_klines(symbol_pair, interval=timeframe, limit=limit)

        if not klines or len(klines) < 50:
            return {"success": False, "message": f"Insufficient K-line data for {symbol}, got {len(klines) if klines else 0} candles"}

        # 2. 艾略特波浪分析
        from elliott_wave import ElliottWaveAnalyzer
        ew_analyzer = ElliottWaveAnalyzer(deviation=0.10, min_span_ratio=0.10)
        candidates = ew_analyzer.analyze(klines, top_n=3)

        # 预定义截图目录
        from chart_generator import plot_elliott_wave_unified, plot_raw_candlestick
        import os
        from datetime import datetime

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        screenshots_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "tests", "screenshots")
        os.makedirs(screenshots_dir, exist_ok=True)

        if not candidates:
            # 生成基础K线图，即使没有波浪模式
            raw_chart_filename = f"ew_{symbol}_{timeframe}_{timestamp}_raw.png"
            raw_chart_path = os.path.join(screenshots_dir, raw_chart_filename)
            plot_raw_candlestick(klines, symbol, timeframe, raw_chart_path)
            chart_paths = [f"/screenshots/{raw_chart_filename}"]
            await db_save_elliott_wave(
                symbol=symbol,
                timeframe=timeframe,
                candidates=[],
                chart_paths=chart_paths,
                klines_count=len(klines),
                kimi_analysis=None,
            )
            return {"success": True, "data": {"symbol": symbol, "timeframe": timeframe, "klines_count": len(klines), "candidates": [], "chart_paths": chart_paths, "message": "No Elliott Wave patterns found in current data"}}

        # 处理所有 candidates 的基础字段（保留完整列表供前端概率展示）
        enriched_candidates = []
        for candidate in candidates:
            if "current_wave" not in candidate:
                waves = candidate.get("waves", [])
                if waves:
                    last_wave = waves[-1]
                    label = last_wave.get("wave", "?")
                    candidate["current_wave"] = f"Wave {label}"
                else:
                    candidate["current_wave"] = "Unknown"
            enriched_candidates.append(candidate)

        # 只给最高分 candidate 生成一张统一图
        chart_paths = []
        if candidates:
            candidate = candidates[0]

            # 生成走势预测数据（基于波浪结构直接计算，不依赖AI）
            projections = _build_projections(candidate, klines)

            # 1. 生成统一图表（包含K线+波浪标注+走势预测+信息面板）
            chart_filename = f"ew_{symbol}_{timeframe}_{timestamp}.png"
            chart_path = os.path.join(screenshots_dir, chart_filename)
            plot_elliott_wave_unified(klines, candidate, projections, symbol, timeframe, chart_path)
            candidate["chart_path"] = f"/screenshots/{chart_filename}"
            chart_paths.append(f"/screenshots/{chart_filename}")

            if projections:
                candidate["projections"] = projections
                candidate["projection_chart_path"] = f"/screenshots/{chart_filename}"  # 向后兼容，指向统一图

            # 2. 调用Kimi分析（BTC/ETH走视觉模式，其他走快速文本模式）
            kimi_annotated = False
            if include_kimi:
                try:
                    from kimi_vision import analyze_elliott_wave_with_kimi, analyze_elliott_wave_text_only
                    kimi_result = None
                    kimi_structure = None
                    raw_chart_path = None

                    if symbol in ("BTC", "ETH"):
                        # Visual mode for top-tier assets: generate raw chart first
                        raw_chart_filename = f"ew_{symbol}_{timeframe}_{timestamp}_raw.png"
                        raw_chart_path = os.path.join(screenshots_dir, raw_chart_filename)
                        plot_raw_candlestick(klines, symbol, timeframe, raw_chart_path, pivots=candidate.get("zigzag_pivots"))

                        kimi_result = await asyncio.wait_for(
                            analyze_elliott_wave_with_kimi(
                                chart_path=raw_chart_path,
                                symbol=symbol,
                                timeframe=timeframe,
                                wave_candidate=candidate,
                            ),
                            timeout=360,
                        )
                    else:
                        # Text-only fast mode for altcoins
                        kimi_result = await asyncio.wait_for(
                            analyze_elliott_wave_text_only(
                                candidate=candidate,
                                symbol=symbol,
                                timeframe=timeframe,
                            ),
                            timeout=120,
                        )

                    candidate["kimi_analysis"] = kimi_result
                    kimi_structure = kimi_result.get("kimi_structure") if kimi_result else None

                    # 3. 如果Kimi返回有效浪型结构，用Kimi的重新画图
                    if kimi_structure and "waves" in kimi_structure:
                        from chart_generator import plot_kimi_annotated_wave
                        kimi_chart_filename = f"ew_{symbol}_{timeframe}_{timestamp}_kimi.png"
                        kimi_chart_path = os.path.join(screenshots_dir, kimi_chart_filename)
                        plot_kimi_annotated_wave(klines, kimi_structure, symbol, timeframe, kimi_chart_path)
                        # 覆盖chart_path为Kimi标注的图，chart_paths 只保留这一张
                        candidate["chart_path"] = f"/screenshots/{kimi_chart_filename}"
                        chart_paths = [f"/screenshots/{kimi_chart_filename}"]
                        candidate["kimi_annotated"] = True
                        candidate["kimi_wave_structure"] = kimi_structure

                        # 可选：用Kimi的waves替换算法的waves
                        if len(kimi_structure.get("waves", [])) >= 2:
                            candidate["waves"] = kimi_structure["waves"]
                            candidate["wave_pattern"] = kimi_structure.get("wave_pattern", candidate.get("wave_pattern"))
                            candidate["direction"] = kimi_structure.get("direction", candidate.get("direction"))
                            candidate["current_wave"] = kimi_structure.get("current_wave", "")
                        kimi_annotated = True

                    # 附加完整 Kimi 分析并重新生成带支撑阻力的统一图
                    if kimi_result:
                        try:
                            plot_elliott_wave_unified(
                                klines,
                                candidate,
                                candidate.get("projections", projections),
                                symbol,
                                timeframe,
                                chart_path,
                            )
                        except Exception as plot_err:
                            logger.warning(f"Failed to regenerate unified chart with Kimi SR: {plot_err}")
                except asyncio.TimeoutError:
                    logger.warning("Kimi Vision analysis timed out after 360s, using algorithm result")
                    candidate["kimi_analysis"] = {"error": "timeout"}
                except ImportError:
                    logger.warning("kimi_vision module not available, skipping Kimi analysis")
                except Exception as kimi_err:
                    logger.warning(f"Kimi analysis failed: {kimi_err}")
                    candidate["kimi_analysis"] = {"error": str(kimi_err)}

            if not kimi_annotated:
                candidate["kimi_annotated"] = False

        # Save to cache
        kimi_analysis_dict = enriched_candidates[0].get("kimi_analysis") if enriched_candidates else None
        await db_save_elliott_wave(
            symbol=symbol,
            timeframe=timeframe,
            candidates=enriched_candidates,
            chart_paths=chart_paths,
            klines_count=len(klines),
            kimi_analysis=kimi_analysis_dict,
        )

        elapsed_ms = int((time.time() - start_time) * 1000)

        return {
            "success": True,
            "data": {
                "symbol": symbol,
                "timeframe": timeframe,
                "klines_count": len(klines),
                "candidates": enriched_candidates,
                "chart_paths": chart_paths,
                "analysis_time_ms": elapsed_ms,
                "refreshed": True,
            }
        }

    except Exception as e:
        logger.error(f"Elliott Wave refresh failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@api_router.post("/api/swap/quote", tags=["DEX"], summary="Get Swap Quote", description="Get a swap quote from Mantle DEX. Supports token symbols (MNT, USDC, USDT) or contract addresses.")
@rate_limit()
async def get_swap_quote(request: Request, req: SwapQuoteRequest):
    try:
        quote = router.get_quote(req.token_in, req.token_out, req.amount_in)
        return {"success": True, "data": quote}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Swap quote failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@api_router.post("/api/swap/build-tx", tags=["DEX"], summary="Build Swap Transaction", description="Build an unsigned swap transaction for Mantle DEX. Client signs and broadcasts via MetaMask.")
@rate_limit(max_requests=20, window=60)
async def build_swap_tx(request: Request, req: SwapBuildTxRequest):
    """
    Build an unsigned swap transaction.
    
    1. Validates inputs
    2. Checks sender balance
    3. Estimates gas (simulate call)
    4. Returns unsigned transaction parameters
    5. Client signs with MetaMask and broadcasts
    """
    provider = MantleProvider()
    if not provider._connected:
        raise HTTPException(status_code=503, detail="Mantle RPC not connected")
    
    w3 = provider.w3
    sender = Web3.to_checksum_address(req.sender_address)
    
    # Resolve tokens
    try:
        token_in_addr = router._resolve_token(req.token_in)
        token_out_addr = router._resolve_token(req.token_out)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Token resolution failed: {str(e)}")
    
    # Validate recipient
    try:
        recipient = Web3.to_checksum_address(req.recipient)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid recipient address")
    
    amount_in = int(req.amount_in)
    min_amount_out = int(req.min_amount_out)
    
    if amount_in <= 0:
        raise HTTPException(status_code=400, detail="amount_in must be greater than 0")
    if min_amount_out < 0:
        raise HTTPException(status_code=400, detail="min_amount_out must be >= 0")
    
    # Check balance
    is_native_in = req.token_in.upper() in ("MNT", "WMNT")
    
    try:
        if is_native_in:
            balance = w3.eth.get_balance(sender)
        else:
            balance = provider.get_token_balance(token_in_addr, sender)
        
        if balance is None:
            raise HTTPException(status_code=503, detail="Failed to query balance")
        
        if balance < amount_in:
            token_name = req.token_in.upper()
            decimals = provider.get_token_decimals(token_in_addr)
            human_balance = balance / (10 ** decimals)
            human_needed = amount_in / (10 ** decimals)
            raise HTTPException(
                status_code=400,
                detail=f"Insufficient {token_name} balance. Have: {human_balance:.6f}, Need: {human_needed:.6f}"
            )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Balance check failed: {e}")
        raise HTTPException(status_code=500, detail=f"Balance check failed: {str(e)}")
    
    # Build router contract
    router_contract = w3.eth.contract(
        address=Web3.to_checksum_address(LB_ROUTER),
        abi=LB_ROUTER_ABI
    )
    
    # Build path (simplified direct swap)
    path = [
        (token_in_addr, 20, 2),   # binStep=20, version=V2
        (token_out_addr, 20, 2),
    ]
    
    # Get nonce and gas price
    try:
        nonce = w3.eth.get_transaction_count(sender)
        gas_price = w3.eth.gas_price
    except Exception as e:
        logger.error(f"Failed to get nonce/gas: {e}")
        raise HTTPException(status_code=503, detail="Failed to get transaction parameters from RPC")
    
    # Build transaction
    try:
        if is_native_in:
            # MNT -> Token: swapExactNATIVEForTokens
            tx = router_contract.functions.swapExactNATIVEForTokens(
                min_amount_out,
                path,
                recipient,
                req.deadline
            ).build_transaction({
                "from": sender,
                "value": amount_in,
                "gas": 500000,
                "gasPrice": gas_price,
                "nonce": nonce,
                "chainId": MANTLE_CHAIN_ID,
            })
        else:
            # Token -> Token or Token -> MNT
            is_native_out = req.token_out.upper() in ("MNT", "WMNT")
            
            # Check allowance for ERC20 input
            if not is_native_in:
                allowance = provider.get_token_allowance(token_in_addr, sender, LB_ROUTER)
                if allowance < amount_in:
                    raise HTTPException(
                        status_code=400,
                        detail=f"Insufficient allowance for {req.token_in}. Please approve the router first. Allowance: {allowance}, Needed: {amount_in}"
                    )
            
            if is_native_out:
                # Token -> MNT: swapExactTokensForNATIVE
                tx = router_contract.functions.swapExactTokensForNATIVE(
                    amount_in,
                    min_amount_out,
                    path,
                    recipient,
                    req.deadline
                ).build_transaction({
                    "from": sender,
                    "gas": 500000,
                    "gasPrice": gas_price,
                    "nonce": nonce,
                    "chainId": MANTLE_CHAIN_ID,
                })
            else:
                # Token -> Token: swapExactTokensForTokens
                tx = router_contract.functions.swapExactTokensForTokens(
                    amount_in,
                    min_amount_out,
                    path,
                    recipient,
                    req.deadline
                ).build_transaction({
                    "from": sender,
                    "gas": 500000,
                    "gasPrice": gas_price,
                    "nonce": nonce,
                    "chainId": MANTLE_CHAIN_ID,
                })
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Transaction build failed: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to build transaction: {str(e)}")
    
    # Estimate gas (simulate call)
    try:
        estimated_gas = w3.eth.estimate_gas(tx)
        tx["gas"] = int(estimated_gas * 1.2)
        logger.info(f"Gas estimated: {estimated_gas}, with buffer: {tx['gas']}")
    except Exception as e:
        logger.error(f"Gas estimation failed: {e}")
        err_str = str(e).lower()
        if "insufficient funds" in err_str:
            raise HTTPException(status_code=400, detail="Insufficient MNT for gas fees")
        elif "allowance" in err_str or "transfer amount exceeds balance" in err_str:
            raise HTTPException(status_code=400, detail="Token allowance insufficient or balance too low")
        elif "slippage" in err_str or "too little received" in err_str:
            raise HTTPException(status_code=400, detail="Slippage exceeded. Try increasing min_amount_out or reducing amount.")
        else:
            raise HTTPException(status_code=400, detail=f"Transaction simulation failed: {str(e)}")
    
    # Return unsigned transaction for client to sign
    return {
        "success": True,
        "data": {
            "to": tx["to"],
            "data": tx["data"],
            "value": str(tx.get("value", 0)),
            "gasLimit": str(tx["gas"]),
            "gasPrice": str(gas_price),
            "nonce": nonce,
            "chainId": MANTLE_CHAIN_ID,
            "from": sender,
            "explorer_url": f"https://mantlescan.xyz/address/{sender}",
        },
        "message": "Transaction built successfully. Please sign with your wallet and broadcast.",
    }

@api_router.get("/api/wallet/balance/{address}", tags=["Wallet"], summary="Get Wallet Balance", description="Query MNT, USDC, and USDT balances for a wallet address.")
@rate_limit()
async def get_wallet_balance(request: Request, address: str):
    """Get wallet balances for MNT, USDC, USDT."""
    provider = MantleProvider()
    if not provider._connected:
        raise HTTPException(status_code=503, detail="Mantle RPC not connected")
    
    # Validate address
    try:
        checksum_addr = Web3.to_checksum_address(address)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid Ethereum address format")
    
    tokens = {
        "MNT": WMNT,
        "USDC": USDC,
        "USDT": USDT,
    }
    
    balances = {}
    try:
        for symbol, token_addr in tokens.items():
            raw_balance = provider.get_token_balance(token_addr, checksum_addr)
            if raw_balance is not None:
                decimals = provider.get_token_decimals(token_addr)
                human_balance = raw_balance / (10 ** decimals)
                balances[symbol] = str(round(human_balance, 6))
            else:
                balances[symbol] = "0"
    except Exception as e:
        logger.error(f"Balance query failed: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to query balances: {str(e)}")
    
    return {
        "success": True,
        "data": {
            "address": checksum_addr,
            "balances": balances,
        }
    }

@api_router.post("/api/wallet/validate", tags=["Wallet"], summary="Validate Address", description="Validate an Ethereum address format.")
async def validate_wallet_address(req: WalletValidateRequest):
    """Validate wallet address format."""
    try:
        is_valid = Web3.is_address(req.address)
        if is_valid:
            checksum = Web3.to_checksum_address(req.address)
            return {
                "success": True,
                "data": {
                    "valid": True,
                    "address": checksum,
                    "is_checksum": req.address == checksum,
                }
            }
        else:
            return {
                "success": True,
                "data": {
                    "valid": False,
                    "address": req.address,
                }
            }
    except Exception as e:
        return {
            "success": True,
            "data": {
                "valid": False,
                "address": req.address,
                "error": str(e),
            }
        }

@api_router.get("/api/mantle/block", tags=["Mantle"], summary="Get Latest Block", description="Get the latest Mantle block information including timestamp, gas usage, and transaction count.")
@rate_limit()
async def get_mantle_block(request: Request):
    try:
        provider = MantleProvider()
        block = provider.get_block_info()
        if block:
            return {"success": True, "data": sanitize_for_json(block)}
        else:
            raise HTTPException(status_code=503, detail="Failed to fetch block data")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@api_router.get("/api/mantle/gas", tags=["Mantle"], summary="Get Gas Price", description="Get current Mantle gas price in wei, gwei, and MNT.")
@rate_limit()
async def get_mantle_gas(request: Request):
    try:
        provider = MantleProvider()
        gas = provider.get_gas_price()
        if gas:
            return {"success": True, "data": sanitize_for_json(gas)}
        else:
            raise HTTPException(status_code=503, detail="Failed to fetch gas price")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@api_router.get("/api/mantle/network", tags=["Mantle"], summary="Get Network Stats", description="Get Mantle network statistics including average block time and network utilization.")
@rate_limit()
async def get_mantle_network(request: Request):
    try:
        provider = MantleProvider()
        stats = provider.get_network_stats()
        if stats:
            return {"success": True, "data": sanitize_for_json(stats)}
        else:
            raise HTTPException(status_code=503, detail="Failed to fetch network stats")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@api_router.get("/api/cache/stats", tags=["Admin"], summary="Cache Statistics", description="Get current cache and database statistics.")
async def get_cache_stats():
    db_stats = await db_manager.get_stats() if db_manager else {"available": False}
    return {
        "success": True,
        "data": {
            "memory_cache": {
                "cache_entries": len(cache._cache),
                "max_size": MAX_CACHE_SIZE,
                "ttl_seconds": CACHE_TTL,
            },
            "database": db_stats,
        }
    }

@api_router.post("/api/cache/invalidate", tags=["Admin"], summary="Invalidate Cache", description="Invalidate cache entries. Optionally specify a prefix to target specific cache namespace.")
async def invalidate_cache(prefix: str = None):
    await cache.invalidate(prefix)
    return {"success": True, "message": f"Cache invalidated for prefix: {prefix or 'all'}"}

# ============ On-Chain Data Endpoints ============

@api_router.get("/api/onchain/protocols", tags=["OnChain"], summary="Get Mantle Protocols", description="Get all DeFi protocols on Mantle with TVL and category data from persistent cache.")
@rate_limit()
async def get_onchain_protocols(request: Request, force_refresh: bool = False):
    """Get Mantle protocol data from database cache."""
    try:
        if not force_refresh:
            db_data = await db_get("onchain_protocols")
            if db_data is not None:
                return {"success": True, "data": db_data, "cached": True, "source": "db"}

        # Fetch fresh and persist
        if force_refresh:
            await llama_client.invalidate_cache("mantle_protocols")
        protocols = await llama_client.get_mantle_protocols()
        protocols = protocols[:10]
        result = {
            "protocols": [
                {
                    "slug": p.slug,
                    "name": p.name,
                    "category": p.category,
                    "tvl": p.tvl,
                    "tvl_change_24h": p.tvl_change_1d,
                    "tvl_change_7d": p.tvl_change_7d,
                    "mcap": p.mcap,
                }
                for p in protocols
            ],
            "count": len(protocols),
            "timestamp": datetime.now().isoformat(),
        }
        await db_set("onchain_protocols", result, ttl_seconds=900)
        return {"success": True, "data": result, "cached": False, "source": "live"}
    except Exception as e:
        logger.error(f"Failed to get protocols: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@api_router.get("/api/onchain/tvl", tags=["OnChain"], summary="Get Mantle TVL", description="Get Mantle chain total TVL from persistent cache.")
@rate_limit()
async def get_onchain_tvl(request: Request, force_refresh: bool = False):
    """Get Mantle chain TVL from database cache."""
    try:
        if not force_refresh:
            db_data = await db_get("onchain_tvl")
            if db_data is not None:
                return {"success": True, "data": db_data, "cached": True, "source": "db"}

        if force_refresh:
            await llama_client.invalidate_cache("chains")
        tvl = await llama_client.get_chain_tvl("Mantle")
        result = {
            "chain": "Mantle",
            "tvl": tvl,
            "timestamp": datetime.now().isoformat(),
        }
        await db_set("onchain_tvl", result, ttl_seconds=900)
        return {"success": True, "data": result, "cached": False, "source": "live"}
    except Exception as e:
        logger.error(f"Failed to get TVL: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@api_router.get("/api/onchain/overview", tags=["OnChain"], summary="Get Mantle Overview", description="Get Mantle chain overview from persistent cache.")
@rate_limit()
async def get_onchain_overview(request: Request, force_refresh: bool = False):
    """Get Mantle chain overview from database cache."""
    try:
        if not force_refresh:
            db_data = await db_get("onchain_overview")
            if db_data is not None:
                return {"success": True, "data": db_data, "cached": True, "source": "db"}

        overview = await onchain_collector.get_overview(force_refresh=force_refresh)
        await db_set("onchain_overview", overview, ttl_seconds=900)
        return {"success": True, "data": overview, "cached": False, "source": "live"}
    except Exception as e:
        logger.error(f"Failed to get overview: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@api_router.get("/api/onchain/block", tags=["OnChain"], summary="Get Latest Block", description="Get latest Mantle block data from persistent cache.")
@rate_limit()
async def get_onchain_block(request: Request):
    """Get latest block data from database cache."""
    try:
        db_data = await db_get("onchain_block")
        if db_data is not None:
            return {"success": True, "data": db_data, "cached": True, "source": "db"}

        block = onchain_collector.get_block_data()
        if block:
            await db_set("onchain_block", block, ttl_seconds=900)
            return {"success": True, "data": block, "cached": False, "source": "live"}
        else:
            raise HTTPException(status_code=503, detail="Failed to fetch block data")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@api_router.get("/api/onchain/gas", tags=["OnChain"], summary="Get Gas Price", description="Get current Mantle gas price from persistent cache.")
@rate_limit()
async def get_onchain_gas(request: Request):
    """Get current gas price from database cache."""
    try:
        db_data = await db_get("onchain_gas")
        if db_data is not None:
            return {"success": True, "data": db_data, "cached": True, "source": "db"}

        gas = onchain_collector.get_gas_data()
        if gas:
            await db_set("onchain_gas", gas, ttl_seconds=900)
            return {"success": True, "data": gas, "cached": False, "source": "live"}
        else:
            raise HTTPException(status_code=503, detail="Failed to fetch gas price")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@api_router.get("/api/onchain/network", tags=["OnChain"], summary="Get Network Stats", description="Get Mantle network statistics from persistent cache.")
@rate_limit()
async def get_onchain_network(request: Request):
    """Get network statistics from database cache."""
    try:
        db_data = await db_get("onchain_network")
        if db_data is not None:
            return {"success": True, "data": db_data, "cached": True, "source": "db"}

        stats = onchain_collector.get_network_stats()
        await db_set("onchain_network", stats, ttl_seconds=900)
        return {"success": True, "data": stats, "cached": False, "source": "live"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@api_router.get("/api/onchain/all", tags=["OnChain"], summary="Get All On-Chain Data", description="Get all on-chain data from persistent cache.")
@rate_limit()
async def get_onchain_all(request: Request, force_refresh: bool = False):
    """Get all on-chain data from database cache."""
    try:
        if not force_refresh:
            db_data = await db_get("onchain_all")
            if db_data is not None:
                return {
                    "success": True,
                    "data": db_data,
                    "timestamp": datetime.now().isoformat(),
                    "cached": True,
                    "source": "db",
                }

        data = await onchain_collector.get_all_data()
        await db_set("onchain_all", data, ttl_seconds=900)
        return {
            "success": True,
            "data": data,
            "timestamp": datetime.now().isoformat(),
            "cached": False,
            "source": "live",
        }
    except Exception as e:
        logger.error(f"Failed to get all data: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@api_router.get("/api/onchain/signals/recent", tags=["OnChain"], summary="Get Recent On-Chain Signals", description="Get recent signal submissions to the on-chain registry from the database. During the testnet beta, signals are publicly visible.")
@rate_limit()
async def get_recent_onchain_signals(request: Request, limit: int = 100, wallet_address: Optional[str] = None):
    """Get recent on-chain signal submissions from database.

    Testnet beta: this endpoint is publicly accessible. The optional
    wallet_address parameter is accepted for analytics/forward-compat but
    does not gate access. If provided, the response includes the wallet's
    subscription status so the UI can still show subscription state.
    """
    try:
        subscription_active = None
        if wallet_address:
            try:
                subscription_active = registry.is_subscribed(wallet_address)
            except Exception as e:
                logger.warning(f"[OnChainSignals] Failed to check subscription for {wallet_address}: {e}")
                subscription_active = False

        signals = await db_get_recent_onchain_signals(limit=min(max(limit, 1), 500))
        result = []
        for s in signals:
            item = dict(s)
            if isinstance(item.get("data"), str):
                try:
                    item["data"] = json.loads(item["data"])
                except json.JSONDecodeError:
                    pass
            result.append(sanitize_for_json(item))
        response = {
            "success": True,
            "count": len(result),
            "data": result,
        }
        if wallet_address is not None:
            response["subscription_active"] = bool(subscription_active)
            response["testnet_beta_public"] = True
        return response
    except Exception as e:
        logger.error(f"Failed to get recent on-chain signals: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@api_router.get("/api/onchain/trend-transactions", tags=["OnChain"], summary="Get Trend Transactions", description="Get cached on-chain trend transactions from the database.")
@rate_limit()
async def get_trend_transactions(request: Request, hours: int = 1, chain: Optional[str] = None):
    """Get cached on-chain trend transactions from database."""
    try:
        end_time = datetime.utcnow().isoformat()
        start_time = (datetime.utcnow() - timedelta(hours=hours)).isoformat()
        txs = await db_get_transactions(chain=chain, start_time=start_time, end_time=end_time, limit=100)
        # Fallback: if time-filtered query returns empty (can happen with mixed
        # timestamp formats in DB), return the latest 100 cached transactions.
        if not txs:
            txs = await db_get_transactions(chain=chain, start_time=None, end_time=None, limit=100)
        return {
            "success": True,
            "count": len(txs),
            "data": [sanitize_for_json(tx) for tx in txs],
        }
    except Exception as e:
        logger.error(f"Failed to get trend transactions: {e}")
        return {"success": True, "count": 0, "data": []}

@api_router.post("/api/onchain/analyze-now", tags=["OnChain"], summary="Trigger Hourly Analysis", description="Manually trigger the hourly trend analysis pipeline.")
@rate_limit()
async def trigger_hourly_analysis(request: Request):
    """手动触发一小时分析"""
    try:
        scheduler = await get_trend_scheduler()
        await scheduler._run_hourly_analysis()
        return {"success": True, "message": "Hourly analysis triggered"}
    except Exception as e:
        logger.error(f"Hourly analysis trigger failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@api_router.get("/api/onchain/analysis/hourly", tags=["OnChain"], summary="Get Hourly Analysis", description="Get recent hourly trend analysis results.")
@rate_limit()
async def get_hourly_analysis(request: Request, limit: int = 24):
    """获取最近每小时分析"""
    try:
        from db import db_get_latest_hourly_analysis
        rows = await db_get_latest_hourly_analysis(chain=None, limit=limit)
        return {"success": True, "count": len(rows), "data": rows}
    except Exception as e:
        logger.error(f"Hourly analysis fetch failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@api_router.get("/api/onchain/analysis/half-day", tags=["OnChain"], summary="Get Half-Day Summaries", description="Get recent 12-hour trend summaries.")
@rate_limit()
async def get_half_day_summaries(request: Request, limit: int = 10):
    """获取最近12小时汇总"""
    try:
        from db import db_get_latest_half_day_summary
        rows = await db_get_latest_half_day_summary(limit=limit)
        return {"success": True, "count": len(rows), "data": rows}
    except Exception as e:
        logger.error(f"Half-day summary fetch failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@api_router.get("/api/onchain/analysis/big", tags=["OnChain"], summary="Get Big Summaries", description="Get recent 3-day big trend summaries.")
@rate_limit()
async def get_big_summaries(request: Request, limit: int = 5):
    """获取最近3天大汇总"""
    try:
        from db import db_get_latest_big_summary
        rows = await db_get_latest_big_summary(limit=limit)
        return {"success": True, "count": len(rows), "data": rows}
    except Exception as e:
        logger.error(f"Big summary fetch failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@api_router.get("/api/onchain/large-transactions", tags=["OnChain"], summary="Get Large Transactions", description="Get pre-filtered large transactions (≥$10K) for sentiment-recommended tokens, excluding stablecoin transfers.")
@rate_limit()
async def get_large_transactions(
    request: Request,
    hours: int = 24,
    min_usd: float = 10000,
    symbol: Optional[str] = None,
    chain: Optional[str] = None,
    direction: Optional[str] = None,
):
    """Get pre-filtered large transactions for sentiment-recommended tokens."""
    try:
        # 1. Query transactions from DB
        end_time = datetime.utcnow().isoformat()
        start_time = (datetime.utcnow() - timedelta(hours=hours)).isoformat()
        txs = await db_get_transactions(chain=chain, start_time=start_time, end_time=end_time, limit=2000)
        if not txs:
            txs = await db_get_transactions(chain=chain, start_time=None, end_time=None, limit=2000)

        # 2. Get recommended symbols
        recommended = await get_recommended_symbols()

        # 3. Get direction mapping if direction filter is requested
        symbol_direction = {}
        if direction:
            rec_tokens = await get_recommended_tokens_for_monitoring()
            symbol_direction = {r["source_symbol"]: r["direction"] for r in rec_tokens}

        # 4. Filter logic
        large = []
        for tx in txs:
            # a. USD value filter
            usd = tx.get("token_amount_usd")
            if usd is None:
                continue
            try:
                usd_val = float(usd)
            except (ValueError, TypeError):
                continue
            if usd_val < min_usd:
                continue

            # b. Stablecoin exclusion
            token_symbol = tx.get("token_symbol", "")
            tx_type = tx.get("tx_type", "")
            if tx_type == "transfer" and _is_stablecoin(token_symbol):
                continue

            # c. Recommended token filter
            source_symbol = get_source_symbol(token_symbol)
            if not source_symbol or source_symbol not in recommended:
                continue

            # d. Symbol param filter
            if symbol and source_symbol != symbol.upper():
                continue

            # e. Direction param filter
            if direction and symbol_direction.get(source_symbol) != direction:
                continue

            # Attach metadata
            tx_dict = dict(tx)
            tx_dict["source_symbol"] = source_symbol
            large.append(tx_dict)

        # 5. Sort by token_amount_usd descending
        large.sort(key=lambda x: float(x.get("token_amount_usd", 0) or 0), reverse=True)

        return {"success": True, "count": len(large), "data": [sanitize_for_json(tx) for tx in large]}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Large transactions fetch failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@api_router.get("/api/onchain/monitor/summary", tags=["OnChain"], summary="Get Large Transaction Monitor Summary", description="Get summary of large transactions grouped by sentiment-recommended tokens.")
@rate_limit()
async def get_monitor_summary(request: Request, hours: int = 24):
    """Get summary of large transactions grouped by sentiment-recommended tokens."""
    try:
        # 1. Get recommended tokens
        recommended = await get_recommended_tokens_for_monitoring()

        # 2. Get large transactions (reuse filtering logic inline)
        end_time = datetime.utcnow().isoformat()
        start_time = (datetime.utcnow() - timedelta(hours=hours)).isoformat()
        txs = await db_get_transactions(chain=None, start_time=start_time, end_time=end_time, limit=2000)
        if not txs:
            txs = await db_get_transactions(chain=None, start_time=None, end_time=None, limit=2000)

        rec_symbols = await get_recommended_symbols()

        large_txs = []
        for tx in txs:
            usd = tx.get("token_amount_usd")
            if usd is None:
                continue
            try:
                usd_val = float(usd)
            except (ValueError, TypeError):
                continue
            if usd_val < 10000:
                continue

            token_symbol = tx.get("token_symbol", "")
            tx_type = tx.get("tx_type", "")
            if tx_type == "transfer" and _is_stablecoin(token_symbol):
                continue

            source_symbol = get_source_symbol(token_symbol)
            if not source_symbol or source_symbol not in rec_symbols:
                continue

            tx_dict = dict(tx)
            tx_dict["source_symbol"] = source_symbol
            large_txs.append(tx_dict)

        # 3. Aggregate by source_symbol
        summary = {}
        for tx in large_txs:
            sym = tx.get("source_symbol", "UNKNOWN")
            if sym not in summary:
                summary[sym] = {
                    "symbol": sym,
                    "chains": set(),
                    "total_tx_count": 0,
                    "total_volume_usd": 0.0,
                    "latest_tx_time": None,
                    "direction": None,
                    "confidence": None,
                    "reason": None,
                }
            summary[sym]["chains"].add(tx.get("chain", "unknown"))
            summary[sym]["total_tx_count"] += 1
            summary[sym]["total_volume_usd"] += tx.get("token_amount_usd", 0) or 0

            # Update latest_tx_time
            block_time = tx.get("block_time")
            if block_time:
                if summary[sym]["latest_tx_time"] is None or block_time > summary[sym]["latest_tx_time"]:
                    summary[sym]["latest_tx_time"] = block_time

        # 4. Merge recommendation info
        for rec in recommended:
            sym = rec["source_symbol"]
            if sym in summary:
                summary[sym]["direction"] = rec["direction"]
                summary[sym]["confidence"] = rec["confidence"]
                summary[sym]["reason"] = rec["reason"]

        # 5. Include recommended tokens with zero transactions
        for rec in recommended:
            sym = rec["source_symbol"]
            if sym not in summary:
                summary[sym] = {
                    "symbol": sym,
                    "chains": set(),
                    "total_tx_count": 0,
                    "total_volume_usd": 0.0,
                    "latest_tx_time": None,
                    "direction": rec.get("direction"),
                    "confidence": rec.get("confidence"),
                    "reason": rec.get("reason"),
                }

        # 6. Convert sets to lists and sort by volume descending
        for item in summary.values():
            item["chains"] = sorted(list(item["chains"]))

        results = sorted(summary.values(), key=lambda x: x["total_volume_usd"], reverse=True)

        return {"success": True, "data": results}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Monitor summary failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@api_router.get("/api/onchain/trend-aggregates", tags=["OnChain"], summary="Get Trend Aggregates", description="Get aggregated on-chain trend data: chain distribution, category distribution, top targets, and large transactions.")
@rate_limit()
async def get_trend_aggregates(request: Request, hours: int = 24):
    """获取链上趋势聚合数据（链分布、赛道分布、趋势标的、大额交易）"""
    try:
        from trend_aggregator import build_trend_aggregates
        end_time = datetime.utcnow().isoformat()
        start_time = (datetime.utcnow() - timedelta(hours=hours)).isoformat()
        txs = await db_get_transactions(chain=None, start_time=start_time, end_time=end_time, limit=1000)
        if not txs:
            txs = await db_get_transactions(chain=None, start_time=None, end_time=None, limit=1000)
        data = build_trend_aggregates(txs, hours=hours)
        return {"success": True, "data": data}
    except Exception as e:
        logger.error(f"Trend aggregates failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@api_router.post("/api/onchain/test-kimi", tags=["OnChain"], summary="Test Kimi Analysis", description="Test Kimi AI analysis with sample on-chain data.")
@rate_limit()
async def test_kimi_analysis(request: Request):
    """测试 Kimi 分析（传入样例数据）"""
    try:
        kimi = await get_kimi_analyzer()
        result = await kimi.analyze_hourly(
            hour_timestamp=datetime.utcnow(),
            top_tokens=[{"symbol": "USDC", "count": 30, "volume": 10000}],
            top_categories=[{"category": "DeFi", "count": 30, "volume": 10000}],
            total_volume=10000,
            tx_count=30,
        )
        return {"success": True, "result": result}
    except Exception as e:
        logger.error(f"Kimi test failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@api_router.post("/api/onchain/analyze-targets", tags=["OnChain"], summary="Analyze Trend Targets with AI", description="Analyze top trend targets using Kimi AI based on on-chain aggregated data.")
@rate_limit()
async def analyze_targets_with_ai(request: Request, body: dict = Body(...)):
    """AI 分析趋势标的"""
    try:
        from kimi_analyzer import get_kimi_analyzer
        from clients import SentimentAnalyzer
        
        kimi = await get_kimi_analyzer()
        top_targets = body.get("top_targets", [])
        chain_distribution = body.get("chain_distribution", [])
        category_distribution = body.get("category_distribution", [])
        summary = body.get("summary", {})
        
        # 获取情绪分析数据
        sentiment_data = None
        try:
            analyzer = SentimentAnalyzer()
            sentiment_result = await analyzer.analyze(timeframe="1d", limit=50)
            sentiment_data = {
                "sentiment_index": sentiment_result.get("sentiment_index"),
                "market_bias": sentiment_result.get("market_bias"),
                "bias_strength": sentiment_result.get("bias_strength"),
                "fng": sentiment_result.get("fng", {}),
                "btc_change_24h": sentiment_result.get("btc_change_24h"),
                "bullish_count": sentiment_result.get("bullish_count", 0),
                "bearish_count": sentiment_result.get("bearish_count", 0),
                "neutral_count": sentiment_result.get("neutral_count", 0),
                "top_bullish": sentiment_result.get("top_bullish", []),
                "top_bearish": sentiment_result.get("top_bearish", []),
            }
        except Exception as e:
            logger.warning(f"Sentiment data fetch failed for AI analysis: {e}")
        
        result = await kimi.analyze_targets(
            top_targets=top_targets,
            chain_distribution=chain_distribution,
            category_distribution=category_distribution,
            summary=summary,
            sentiment_data=sentiment_data,
        )
        return {"success": True, "analysis": result}
    except Exception as e:
        logger.error(f"Target analysis failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@api_router.post("/api/onchain/refresh", tags=["OnChain"], summary="Trigger Data Refresh", description="Manually trigger on-chain data refresh and persist to database.")
async def trigger_refresh(request: Request):
    """Manually trigger data refresh and persist to DB."""
    try:
        data = await onchain_collector.get_all_data()
        await db_set("onchain_all", data, ttl_seconds=900)

        # Also refresh sub-components
        try:
            protocols = await llama_client.get_mantle_protocols()
            await db_set("onchain_protocols", {
                "protocols": [{"slug": p.slug, "name": p.name, "category": p.category, "tvl": p.tvl,
                               "tvl_change_24h": p.tvl_change_1d, "tvl_change_7d": p.tvl_change_7d, "mcap": p.mcap}
                              for p in protocols],
                "count": len(protocols),
                "timestamp": datetime.now().isoformat(),
            }, ttl_seconds=900)
        except Exception:
            pass

        try:
            overview = await onchain_collector.get_overview()
            await db_set("onchain_overview", overview, ttl_seconds=900)
        except Exception:
            pass

        try:
            block = onchain_collector.get_block_data()
            if block:
                await db_set("onchain_block", block, ttl_seconds=900)
        except Exception:
            pass

        try:
            gas = onchain_collector.get_gas_data()
            if gas:
                await db_set("onchain_gas", gas, ttl_seconds=900)
        except Exception:
            pass

        try:
            stats = onchain_collector.get_network_stats()
            await db_set("onchain_network", stats, ttl_seconds=900)
        except Exception:
            pass

        # Refresh sentiment (store FULL data with backtest enrichment)
        try:
            sentiment = await analyzer.analyze()
            sentiment = await _enrich_with_backtest(sentiment, "1d")
            await db_set("sentiment", sentiment, ttl_seconds=15000)
        except Exception:
            pass

        # Refresh trends
        try:
            trends = await fetch_mantle_trends()
            await db_set("mantle_trends", trends, ttl_seconds=900)
        except Exception:
            pass

        # Refresh TVL history
        try:
            tvl_history = await fetch_defillama_mantle_tvl_history(30)
            await db_set("mantle_tvl_history", {"chain": "Mantle", "days": 30, "history": tvl_history}, ttl_seconds=900)
        except Exception:
            pass

        return {
            "success": True,
            "message": "Data refresh triggered and persisted to database",
            "data": {
                "timestamp": data.get("timestamp"),
                "protocols_count": len(data.get("protocols", [])),
            },
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@api_router.get("/api/onchain/aggregated", tags=["OnChain"], summary="Get Aggregated Data", description="Get unified aggregated on-chain data from persistent cache.")
@rate_limit()
async def get_aggregated_data(request: Request, force_refresh: bool = False):
    """Get unified aggregated data from database cache."""
    try:
        if not force_refresh:
            db_data = await db_get("aggregated_data")
            if db_data is not None:
                return {
                    "success": True,
                    "data": sanitize_for_json(db_data),
                    "timestamp": datetime.now().isoformat(),
                    "cached": True,
                    "source": "db",
                }

        if data_aggregator is None:
            raise HTTPException(status_code=503, detail="Data aggregator not initialized")
        result = await data_aggregator.collect_all(force_refresh=force_refresh)
        return {
            "success": True,
            "data": sanitize_for_json(asdict(result)),
            "timestamp": datetime.now().isoformat(),
            "cached": False,
            "source": "live",
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get aggregated data: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@api_router.get("/api/onchain/scheduler/status", tags=["OnChain"], summary="Scheduler Status", description="Get data refresh scheduler status for both on-chain collector and data aggregator.")
async def get_scheduler_status():
    """Get scheduler status."""
    status = {
        "success": True,
        "data": {
            "onchain_scheduler": {
                "running": onchain_scheduler.running,
                "interval_seconds": onchain_scheduler.interval,
                "last_refresh": onchain_scheduler.last_refresh.isoformat() if onchain_scheduler.last_refresh else None,
            },
        },
    }
    if aggregator_scheduler is not None:
        status["data"]["aggregator_scheduler"] = aggregator_scheduler.get_status()
    else:
        status["data"]["aggregator_scheduler"] = {
            "running": False,
            "interval_seconds": None,
            "last_refresh": None,
        }
    return status

@api_router.get("/api/onchain/whales", tags=["OnChain"], summary="Whale Transfers", description="Scan recent blocks for large transfers (≥100 MNT or ≥100,000 USDC/USDT).")
@rate_limit()
async def get_whale_transfers(request: Request, blocks: int = 10):
    """Get large transfer records from recent blocks."""
    if whale_monitor is None:
        raise HTTPException(status_code=503, detail="Whale monitor not available")
    try:
        result = await whale_monitor.get_large_transfers(num_blocks=blocks)
        return {
            "success": True,
            "data": {
                "transfers": [whale_monitor.to_dict(t) for t in result.transfers],
                "scanned_blocks": result.scanned_blocks,
                "start_block": result.start_block,
                "end_block": result.end_block,
                "timestamp": result.timestamp,
            },
        }
    except Exception as e:
        logger.error(f"Whale transfer scan failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@api_router.get("/api/onchain/fundflow", tags=["OnChain"], summary="Stablecoin Fund Flow", description="Track USDC/USDT inflow/outflow across recent blocks.")
@rate_limit()
async def get_fund_flow(request: Request, blocks: int = 10):
    """Get stablecoin fund flow analysis."""
    if whale_monitor is None:
        raise HTTPException(status_code=503, detail="Whale monitor not available")
    try:
        flows = await whale_monitor.get_fund_flow(num_blocks=blocks)
        return {
            "success": True,
            "data": {
                "flows": [whale_monitor.to_dict(f) for f in flows],
                "timestamp": datetime.utcnow().isoformat(),
            },
        }
    except Exception as e:
        logger.error(f"Fund flow analysis failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# ============ Alias Routes (for frontend compatibility) ============

@api_router.get("/api/market/overview", tags=["Market"], summary="Market Overview (Alias)", description="Alias for /api/onchain/overview")
@rate_limit()
async def get_market_overview(request: Request, force_refresh: bool = False):
    """Alias for /api/onchain/overview"""
    return await get_onchain_overview(request, force_refresh)

@api_router.get("/api/market/tokens", tags=["Market"], summary="Market Tokens (Alias)", description="Simplified token list from persistent cache.")
@rate_limit()
async def get_market_tokens(request: Request):
    """Return simplified token list from database cache."""
    try:
        db_data = await db_get("onchain_protocols")
        if db_data is not None:
            protocols = db_data.get("protocols", [])
            tokens = []
            for p in protocols:
                token = {
                    "symbol": p.get("slug", "").upper().replace("-", "_"),
                    "name": p.get("name", ""),
                    "tvl": p.get("tvl", 0),
                    "category": p.get("category", ""),
                }
                tokens.append(token)
            return {
                "success": True,
                "data": {
                    "tokens": tokens,
                    "count": len(tokens),
                    "timestamp": datetime.now().isoformat(),
                },
                "cached": True,
                "source": "db",
            }

        protocols = await llama_client.get_mantle_protocols()
        tokens = []
        for p in protocols:
            token = {
                "symbol": p.slug.upper().replace("-", "_"),
                "name": p.name,
                "tvl": p.tvl,
                "category": p.category,
            }
            tokens.append(token)
        return {
            "success": True,
            "data": {
                "tokens": tokens,
                "count": len(tokens),
                "timestamp": datetime.now().isoformat(),
            },
            "cached": False,
            "source": "live",
        }
    except Exception as e:
        logger.error(f"Failed to get market tokens: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@api_router.get("/api/market/trends", tags=["Market"], summary="Market Trends (Alias)", description="Alias for /api/mantle/trends")
@rate_limit()
async def get_market_trends(request: Request):
    """Alias for /api/mantle/trends"""
    return await get_mantle_trends(request)

@api_router.get("/api/protocols/tvl", tags=["Protocols"], summary="Protocols TVL (Alias)", description="Alias for /api/onchain/protocols")
@rate_limit()
async def get_protocols_tvl(request: Request, force_refresh: bool = False):
    """Alias for /api/onchain/protocols"""
    return await get_onchain_protocols(request, force_refresh)

@api_router.get("/api/whales/alerts", tags=["Whales"], summary="Whale Alerts (Alias)", description="Alias for /api/onchain/whales")
@rate_limit()
async def get_whales_alerts(request: Request, blocks: int = 10):
    """Alias for /api/onchain/whales"""
    return await get_whale_transfers(request, blocks)

@api_router.get("/api/sentiment/analysis", tags=["Sentiment"], summary="Sentiment Analysis (Alias)", description="Alias for /api/sentiment/latest (GET)")
@rate_limit()
async def get_sentiment_analysis(request: Request, wallet_address: Optional[str] = None):
    """Alias for /api/sentiment/latest (GET)"""
    return await get_latest_sentiment(request, wallet_address)

# ============ New API Endpoints ============

@api_router.get("/api/mantle/trends", tags=["Mantle"], summary="Get Mantle 24h Trends", description="Get 24-hour Mantle on-chain trend data from persistent cache.")
@rate_limit()
async def get_mantle_trends(request: Request):
    """Get 24-hour Mantle on-chain trend data from database cache."""
    try:
        db_data = await db_get("mantle_trends")
        if db_data is not None:
            return {
                "success": True,
                "data": db_data,
                "timestamp": datetime.now().isoformat(),
                "cached": True,
                "source": "db",
            }

        trends = await fetch_mantle_trends()
        await db_set("mantle_trends", trends, ttl_seconds=900)
        return {
            "success": True,
            "data": trends,
            "timestamp": datetime.now().isoformat(),
            "cached": False,
            "source": "live",
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get Mantle trends: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@api_router.get("/api/mantle/tvl/history", tags=["Mantle"], summary="Get Mantle TVL History", description="Get Mantle chain TVL historical data from persistent cache.")
@rate_limit()
async def get_mantle_tvl_history(request: Request, days: int = 30):
    """Get Mantle TVL history from database cache."""
    try:
        if days < 1 or days > 365:
            raise HTTPException(status_code=400, detail="days must be between 1 and 365")

        cache_key = f"mantle_tvl_history_{days}"
        db_data = await db_get(cache_key)
        if db_data is not None:
            return {
                "success": True,
                "data": db_data,
                "timestamp": datetime.now().isoformat(),
                "cached": True,
                "source": "db",
            }

        history = await fetch_defillama_mantle_tvl_history(days)
        result = {
            "chain": "Mantle",
            "days": days,
            "history": history,
        }
        await db_set(cache_key, result, ttl_seconds=900)
        return {
            "success": True,
            "data": result,
            "timestamp": datetime.now().isoformat(),
            "cached": False,
            "source": "live",
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get Mantle TVL history: {e}")
        raise HTTPException(status_code=500, detail=str(e))


if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", "8000"))
    host = os.getenv("HOST", "0.0.0.0")
    uvicorn.run(app, host=host, port=port)



# ============ Backtest Endpoints ============

@api_router.get("/api/sentiment/backtest/{symbol}/{timeframe}", tags=["Backtest"], summary="Get Backtest Result", description="Run similar-state matching backtest for a specific symbol.")
@rate_limit()
async def get_symbol_backtest(request: Request, symbol: str, timeframe: str):
    """Run similar-state matching backtest for a specific symbol and timeframe."""
    require_whitelist(request)
    try:
        result = await backtest_symbol(symbol.upper(), timeframe.lower())
        return {"success": True, "data": result}
    except Exception as e:
        logger.error(f"Backtest failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@api_router.get("/api/sentiment/backtest-batch/{timeframe}", tags=["Backtest"], summary="Batch Backtest", description="Batch backtest top 20 symbols and return recommendations.")
@rate_limit()
async def get_batch_backtest(request: Request, timeframe: str):
    require_whitelist(request)
    """Batch backtest top 20 symbols and return recommendations.
    
    Uses subprocess isolation to avoid event loop conflicts with background tasks.
    """
    import json
    import os
    
    try:
        script_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "batch_backtest_runner.py")
        proc = await asyncio.create_subprocess_exec(
            "python3", script_path, timeframe.lower(),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=120)
        
        if proc.returncode != 0:
            err = stderr.decode() if stderr else "Unknown error"
            logger.error(f"Batch backtest subprocess failed: {err}")
            raise HTTPException(status_code=500, detail=f"Batch backtest failed: {err}")
        
        output = stdout.decode()
        # The script may log to stdout before JSON, find the last JSON line
        lines = output.strip().split('\n')
        json_line = None
        for line in reversed(lines):
            line = line.strip()
            if line.startswith('{') and line.endswith('}'):
                json_line = line
                break
        
        if not json_line:
            logger.error(f"Batch backtest no JSON found in output: {output[:500]}")
            raise HTTPException(status_code=500, detail="Batch backtest returned invalid data")
        
        data = json.loads(json_line)
        return data
    except asyncio.TimeoutError:
        raise HTTPException(status_code=504, detail="Batch backtest timeout")
    except json.JSONDecodeError as e:
        logger.error(f"Batch backtest invalid JSON: {e}")
        raise HTTPException(status_code=500, detail="Batch backtest returned invalid data")
    except Exception as e:
        logger.error(f"Batch backtest failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@api_router.get("/api/sentiment/backtest/summary", tags=["Backtest"], summary="Backtest Summary", description="Get overall backtest summary from database.")
@rate_limit()
async def get_backtest_summary_endpoint(request: Request, timeframe: str = "1d"):
    """Get overall backtest summary."""
    require_whitelist(request)
    try:
        result = await get_backtest_summary(timeframe.lower())
        return {"success": True, "data": result}
    except Exception as e:
        logger.error(f"Backtest summary fetch failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@api_router.get("/api/onchain/moralis/status", tags=["OnChain"])
@rate_limit()
async def get_moralis_status(request: Request):
    """检查 Moralis API 状态和配额"""
    client = MoralisClient()
    return {
        "success": True,
        "enabled": bool(client.api_key),
        "api_key_prefix": client.api_key[:10] + "..." if client.api_key else None,
    }


# 临时调试：记录所有sentiment请求的client_ip
@api_router.get("/api/debug/ip", tags=["Debug"])
async def debug_ip(request: Request):
    client_ip = get_client_ip(request)
    return {
        "client_ip": client_ip,
        "whitelisted": client_ip in WHITELIST,
        "whitelist": WHITELIST,
        "headers": dict(request.headers),
    }
