"""
Mantle DeFAI Trader - Production-Ready Backend API
FastAPI backend with modular architecture.
"""

import os
import asyncio
from contextlib import asynccontextmanager

# Load environment variables before any module imports that depend on them
from dotenv import load_dotenv
_env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), '.env')
load_dotenv(_env_path)

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from loguru import logger

# Database & external modules
from db import init_database, db_set
from onchain_collector import OnChainDataCollector, DataRefreshScheduler
from defillama_client import DeFiLlamaClient
from data_aggregator import DataAggregator, AggregatorScheduler, create_aggregator

# Internal modules
from core import cache
from clients import analyzer, onchain_collector, onchain_scheduler, llama_client
from routes import api_router
from routing_wizard import routing_router
import state
from state import data_aggregator, aggregator_scheduler, _unified_refresh_task, trend_scheduler
from background import _run_unified_refresh
from trend_scheduler import get_trend_scheduler

# ============ Logging Setup ============
logger.remove()
logger.add("logs/api.log", rotation="10 MB", retention="7 days", level="INFO",
    format="{time:YYYY-MM-DD HH:mm:ss} | {level} | {name} | {message}")
logger.add(lambda msg: print(msg, end=""),
    level="DEBUG" if os.getenv("DEBUG", "false").lower() == "true" else "INFO",
    format="{time:HH:mm:ss} | {level} | {message}")

# ============ FastAPI App ============

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan events (startup/shutdown)."""
    global data_aggregator, aggregator_scheduler, _unified_refresh_task, trend_scheduler, _ew_scheduler_task
    logger.info("=" * 50)
    logger.info("Mantle DeFAI Trader API v1.2.0 starting...")

    # Initialize database
    try:
        await init_database()
        logger.info("Database initialized")
    except Exception as e:
        logger.warning(f"Database init failed: {e}")

    # Pre-warm caches
    try:
        sentiment_result = await asyncio.wait_for(analyzer.analyze(), timeout=120)
        await db_set("sentiment", sentiment_result, ttl_seconds=3960)
        logger.info("Pre-warmed sentiment cache")
        # Enrich with backtest in background so service starts fast
        # but backtest data becomes available shortly after startup
        async def _bg_enrich():
            try:
                from backtest import _enrich_with_backtest
                enriched = await _enrich_with_backtest(sentiment_result, "1d")
                await db_set("sentiment", enriched, ttl_seconds=3960)
                logger.info("Pre-warm backtest enrichment completed")
            except Exception as enrich_err:
                logger.warning(f"Pre-warm backtest enrichment failed: {enrich_err}")
        asyncio.create_task(_bg_enrich())
    except Exception as e:
        logger.warning(f"Pre-warm sentiment failed: {e}")

    try:
        onchain_data = await onchain_collector.get_all_data()
        await db_set("onchain_all", onchain_data, ttl_seconds=900)
        logger.info("Pre-warmed on-chain data cache")
    except Exception as e:
        logger.warning(f"Pre-warm on-chain failed: {e}")

    # Start background schedulers
    try:
        asyncio.create_task(onchain_scheduler.start())
        logger.info("Started on-chain scheduler (1 hour)")
    except Exception as e:
        logger.warning(f"Failed to start scheduler: {e}")

    try:
        data_aggregator = await create_aggregator()
        aggregator_scheduler = AggregatorScheduler(data_aggregator, interval=900)
        asyncio.create_task(aggregator_scheduler.start())
        logger.info("Started aggregator scheduler (1 hour)")
    except Exception as e:
        logger.warning(f"Failed to start aggregator: {e}")

    # Start unified refresh
    try:
        state.set_unified_refresh_running(True)
        _unified_refresh_task = asyncio.create_task(_run_unified_refresh())
        logger.info("Started unified refresh scheduler (1 hour)")
    except Exception as e:
        logger.warning(f"Failed to start unified refresh: {e}")

    # Start trend scheduler
    try:
        trend_scheduler = await get_trend_scheduler()
        asyncio.create_task(trend_scheduler.start())
        logger.info("Started trend scheduler (hourly)")
    except Exception as e:
        logger.warning(f"Failed to start trend scheduler: {e}")

    # Start Elliott Wave scheduler (with auto-restart wrapper)
    try:
        from background import _run_elliott_wave_scheduler_with_restart
        _ew_scheduler_task = asyncio.create_task(_run_elliott_wave_scheduler_with_restart())
        logger.info("Started Elliott Wave scheduler (hourly, auto-restart enabled)")
    except Exception as e:
        logger.warning(f"Failed to start Elliott Wave scheduler: {e}")

    yield

    # Shutdown
    logger.info("Shutting down Mantle DeFAI Trader API...")
    state.set_unified_refresh_running(False)
    if _unified_refresh_task and not _unified_refresh_task.done():
        _unified_refresh_task.cancel()
    onchain_scheduler.stop()
    if aggregator_scheduler is not None:
        aggregator_scheduler.stop()
    await cache.invalidate()
    if data_aggregator is not None:
        await data_aggregator.close()

    # Stop trend scheduler
    try:
        if trend_scheduler is not None:
            await trend_scheduler.stop()
            logger.info("Trend scheduler stopped")
    except Exception as e:
        logger.warning(f"Failed to stop trend scheduler: {e}")

    # Stop Elliott Wave scheduler
    try:
        from background import _ew_scheduler_running
        _ew_scheduler_running = False
        if '_ew_scheduler_task' in globals() and _ew_scheduler_task:
            _ew_scheduler_task.cancel()
            try:
                await asyncio.wait_for(_ew_scheduler_task, timeout=5)
            except asyncio.TimeoutError:
                logger.warning("Elliott Wave scheduler did not stop within 5s")
            except asyncio.CancelledError:
                pass
            logger.info("Elliott Wave scheduler stopped")
    except Exception as e:
        logger.warning(f"Failed to stop Elliott Wave scheduler: {e}")

    # Close chain indexer session
    try:
        from chain_indexer import get_chain_indexer
        indexer = await get_chain_indexer()
        await indexer.close()
        logger.info("Chain indexer session closed")
    except Exception as e:
        logger.warning(f"Failed to close chain indexer: {e}")

app = FastAPI(
    title="Mantle DeFAI Trader API",
    version="1.2.0",
    description="Production-ready API for Mantle DeFAI Trader.",
    docs_url="/docs" if os.getenv("DEBUG", "false").lower() == "true" else None,
    redoc_url="/redoc" if os.getenv("DEBUG", "false").lower() == "true" else None,
    lifespan=lifespan,
)

# Mount screenshots directory as static files
screenshots_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "tests", "screenshots")
os.makedirs(screenshots_dir, exist_ok=True)
app.mount("/screenshots", StaticFiles(directory=screenshots_dir), name="screenshots")

# CORS
_allowed_origins_raw = os.getenv("ALLOWED_ORIGINS", "http://localhost:5173,http://localhost:3000")
allowed_origins = [o.strip() for o in _allowed_origins_raw.split(",") if o.strip()] if _allowed_origins_raw else []
app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)

# Include routers
app.include_router(api_router)
app.include_router(routing_router)

# Request/Response logging middleware (imported from core)
from core import log_requests
app.middleware("http")(log_requests)

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", "8000"))
    host = os.getenv("HOST", "0.0.0.0")
    uvicorn.run(app, host=host, port=port)
