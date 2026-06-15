#!/usr/bin/env python3
"""
Split apps/api/main.py into modular files.
Generates:
  - apps/api/core.py       (config, models, cache, middleware)
  - apps/api/clients.py    (binance, ma, mantle, dex, sentiment + global instances)
  - apps/api/state.py      (runtime mutable state)
  - apps/api/background.py (background refresh + trend helpers)
  - apps/api/routes.py     (all API endpoints via APIRouter)
  - apps/api/main.py       (slim entry point)
"""
import os
import re
import shutil

SRC = "apps/api/main.py"
BAK = "apps/api/main.py.bak"

def read_lines(path):
    with open(path, "r") as f:
        return f.read().splitlines()

def write_file(path, lines):
    os.makedirs(os.path.dirname(path) if os.path.dirname(path) else ".", exist_ok=True)
    with open(path, "w") as f:
        f.write("\n".join(lines) + "\n")
    print(f"  Wrote {path} ({len(lines)} lines)")

lines = read_lines(SRC)

# ── 1. Identify sections ──────────────────────────────────────────────
section_re = re.compile(r"^# =+ (.+?) =+$")
sections = []          # [(name, start_line_idx, end_line_idx), ...]
current_name = None
current_start = 0

for i, line in enumerate(lines):
    m = section_re.match(line)
    if m:
        if current_name:
            sections.append((current_name, current_start, i))
        current_name = m.group(1).strip()
        current_start = i

if current_name:
    sections.append((current_name, current_start, len(lines)))

sec = {name: (s, e) for name, s, e in sections}

# Preamble = everything before first section marker
preamble_end = sections[0][1] if sections else len(lines)
preamble = lines[:preamble_end]

# ── 2. Build each module ──────────────────────────────────────────────

# ----- core.py -----
core_lines = []
# Header
core_lines.append('"""')
core_lines.append('Core utilities, configuration, Pydantic models, cache, and rate limiting.')
core_lines.append('This module has NO side-effects (no global service initialization).')
core_lines.append('"""')
core_lines.append("")

# Imports from preamble (filter out on-chain collector / defillama / db / whale / routing)
for line in preamble:
    if "onchain_collector" in line or "defillama_client" in line or "data_aggregator" in line or "db import" in line or "whale_monitor" in line or "routing_wizard" in line:
        continue
    if line.strip() == "":
        core_lines.append(line)
        continue
    core_lines.append(line)

# Add sections
core_sections = [
    "Numpy JSON Serialization Helper",
    "Configuration",
    "Models",
    "ERC20 & Router ABIs",
    "Cache Manager",
    "Rate Limiting",
]
for name in core_sections:
    s, e = sec[name]
    core_lines.extend(lines[s:e])

write_file("apps/api/core.py", core_lines)

# ----- clients.py -----
clients_lines = []
clients_lines.append('"""')
clients_lines.append('External API clients and data providers (Binance, Mantle, DEX, Sentiment).')
clients_lines.append('Global service instances are created at the bottom.')
clients_lines.append('"""')
clients_lines.append("")

# Imports
clients_lines.append("import asyncio")
clients_lines.append("import aiohttp")
clients_lines.append("import numpy as np")
clients_lines.append("from typing import List, Dict, Optional, Any")
clients_lines.append("from datetime import datetime")
clients_lines.append("from loguru import logger")
clients_lines.append("from fastapi import HTTPException")
clients_lines.append("from web3 import Web3")
clients_lines.append("")
clients_lines.append("from core import (")
clients_lines.append("    BINANCE_API_URL, DATA_API_URL, MANTLE_RPC_URL, MANTLE_CHAIN_ID,")
clients_lines.append("    WMNT, USDC, USDT, LB_QUOTER, LB_ROUTER, LB_FACTORY,")
clients_lines.append("    TOKEN_DECIMALS, CACHE_TTL, MAX_CACHE_SIZE,")
clients_lines.append("    ERC20_ABI, LB_ROUTER_ABI,")
clients_lines.append("    sanitize_for_json, cache,")
clients_lines.append(")")
clients_lines.append("")

client_sections = [
    "Binance API Client",
    "Moving Average Calculator",
    "Mantle On-Chain Provider",
    "DEX Quote Provider",
    "Sentiment Analysis",
    "Global Instances",
]
for name in client_sections:
    s, e = sec[name]
    clients_lines.extend(lines[s:e])

write_file("apps/api/clients.py", clients_lines)

# ----- state.py -----
state_lines = [
    '"""Runtime mutable state shared across modules."""',
    "",
    "# Data aggregator (initialized in lifespan)",
    "data_aggregator = None",
    "aggregator_scheduler = None",
    "",
    "# Unified DB refresh scheduler",
    "_unified_refresh_task = None",
    "_unified_refresh_running = False",
]
write_file("apps/api/state.py", state_lines)

# ----- background.py -----
bg_lines = []
bg_lines.append('"""')
bg_lines.append('Background refresh tasks and on-chain data trend helpers.')
bg_lines.append('"""')
bg_lines.append("")
bg_lines.append("import asyncio")
bg_lines.append("from datetime import datetime, timedelta")
bg_lines.append("from typing import List, Dict, Optional, Any")
bg_lines.append("from loguru import logger")
bg_lines.append("from fastapi import HTTPException")
bg_lines.append("")
bg_lines.append("# External imports")
bg_lines.append("from onchain_collector import OnChainDataCollector, DataRefreshScheduler")
bg_lines.append("from defillama_client import DeFiLlamaClient")
bg_lines.append("from data_aggregator import DataAggregator, AggregatorScheduler, create_aggregator")
bg_lines.append("from db import db_set")
bg_lines.append("")
bg_lines.append("# Internal imports")
bg_lines.append("from core import sanitize_for_json")
bg_lines.append("from clients import analyzer, onchain_collector, llama_client")
bg_lines.append("from state import data_aggregator, aggregator_scheduler, _unified_refresh_running")
bg_lines.append("")

bg_sections = [
    "Unified Background Refresh",
    "Trend Data Helpers",
]
for name in bg_sections:
    s, e = sec[name]
    bg_lines.extend(lines[s:e])

write_file("apps/api/background.py", bg_lines)

# ----- routes.py -----
routes_lines = []
routes_lines.append('"""')
routes_lines.append('All API endpoints registered via FastAPI APIRouter.')
routes_lines.append('"""')
routes_lines.append("")
routes_lines.append("from datetime import datetime")
routes_lines.append("from typing import List, Dict, Optional, Any")
routes_lines.append("from loguru import logger")
routes_lines.append("")
routes_lines.append("from fastapi import APIRouter, HTTPException, Request")
routes_lines.append("")
routes_lines.append("# External modules")
routes_lines.append("from db import db_get, db_manager")
routes_lines.append("from onchain_collector import OnChainDataCollector, DataRefreshScheduler")
routes_lines.append("from defillama_client import DeFiLlamaClient")
routes_lines.append("from data_aggregator import DataAggregator, AggregatorScheduler, create_aggregator")
routes_lines.append("")
routes_lines.append("# Internal modules")
routes_lines.append("from core import (")
routes_lines.append("    cache, sanitize_for_json, rate_limit,")
routes_lines.append("    Timeframe, SentimentRequest, SwapQuoteRequest, SwapExecuteRequest, WalletValidateRequest,")
routes_lines.append(")")
routes_lines.append("from clients import (")
routes_lines.append("    analyzer, router, onchain_collector, onchain_scheduler,")
routes_lines.append("    llama_client, whale_monitor, MantleProvider,")
routes_lines.append(")")
routes_lines.append("from state import data_aggregator, aggregator_scheduler")
routes_lines.append("from background import fetch_mantle_trends, fetch_defillama_mantle_tvl_history")
routes_lines.append("")
routes_lines.append("api_router = APIRouter()")
routes_lines.append("")

# Root & Health endpoints (before On-Chain Data Endpoints)
root_start = 1738   # @app.get("/") line
root_end = sec["On-Chain Data Endpoints"][0]
for line in lines[root_start:root_end]:
    routes_lines.append(line)

# On-Chain Data Endpoints
s, e = sec["On-Chain Data Endpoints"]
routes_lines.extend(lines[s:e])

# Alias Routes
s, e = sec["Alias Routes (for frontend compatibility)"]
routes_lines.extend(lines[s:e])

# New API Endpoints
s, e = sec["New API Endpoints"]
routes_lines.extend(lines[s:e])

# Replace @app. with @api_router.
new_routes = []
for line in routes_lines:
    if "@app.get(" in line:
        line = line.replace("@app.get(", "@api_router.get(")
    elif "@app.post(" in line:
        line = line.replace("@app.post(", "@api_router.post(")
    new_routes.append(line)

write_file("apps/api/routes.py", new_routes)

# ----- main.py -----
main_lines = []
main_lines.append('"""')
main_lines.append('Mantle DeFAI Trader - Production-Ready Backend API')
main_lines.append('FastAPI backend with modular architecture.')
main_lines.append('"""')
main_lines.append("")
main_lines.append("import os")
main_lines.append("import asyncio")
main_lines.append("from contextlib import asynccontextmanager")
main_lines.append("")
main_lines.append("from fastapi import FastAPI")
main_lines.append("from fastapi.middleware.cors import CORSMiddleware")
main_lines.append("from loguru import logger")
main_lines.append("")
main_lines.append("# Database & external modules")
main_lines.append("from db import init_database, db_set")
main_lines.append("from onchain_collector import OnChainDataCollector, DataRefreshScheduler")
main_lines.append("from defillama_client import DeFiLlamaClient")
main_lines.append("from data_aggregator import DataAggregator, AggregatorScheduler, create_aggregator")
main_lines.append("")
main_lines.append("# Internal modules")
main_lines.append("from core import cache")
main_lines.append("from clients import analyzer, onchain_collector, onchain_scheduler, llama_client")
main_lines.append("from routes import api_router")
main_lines.append("from routing_wizard import routing_router")
main_lines.append("from state import data_aggregator, aggregator_scheduler, _unified_refresh_task, _unified_refresh_running")
main_lines.append("from background import _run_unified_refresh")
main_lines.append("")
main_lines.append("# ============ Logging Setup ============")
main_lines.append("logger.remove()")
main_lines.append('logger.add("logs/api.log", rotation="10 MB", retention="7 days", level="INFO",')
main_lines.append('    format="{time:YYYY-MM-DD HH:mm:ss} | {level} | {name} | {message}")')
main_lines.append('logger.add(lambda msg: print(msg, end=""),')
main_lines.append('    level="DEBUG" if os.getenv("DEBUG", "false").lower() == "true" else "INFO",')
main_lines.append('    format="{time:HH:mm:ss} | {level} | {message}")')
main_lines.append("")
main_lines.append("# ============ FastAPI App ============")
main_lines.append("")
main_lines.append("@asynccontextmanager")
main_lines.append("async def lifespan(app: FastAPI):")
main_lines.append('    """Application lifespan events (startup/shutdown)."""')
main_lines.append('    logger.info("=" * 50)')
main_lines.append('    logger.info("Mantle DeFAI Trader API v1.2.0 starting...")')
main_lines.append("")
main_lines.append("    # Initialize database")
main_lines.append("    try:")
main_lines.append("        await init_database()")
main_lines.append('        logger.info("Database initialized")')
main_lines.append("    except Exception as e:")
main_lines.append('        logger.warning(f"Database init failed: {e}")')
main_lines.append("")
main_lines.append("    # Pre-warm caches")
main_lines.append("    try:")
main_lines.append("        sentiment_result = await analyzer.analyze()")
main_lines.append('        await db_set("sentiment", sentiment_result, ttl_seconds=900)')
main_lines.append('        logger.info("Pre-warmed sentiment cache")')
main_lines.append("    except Exception as e:")
main_lines.append('        logger.warning(f"Pre-warm sentiment failed: {e}")')
main_lines.append("")
main_lines.append("    try:")
main_lines.append("        onchain_data = await onchain_collector.get_all_data()")
main_lines.append('        await db_set("onchain_all", onchain_data, ttl_seconds=900)')
main_lines.append('        logger.info("Pre-warmed on-chain data cache")')
main_lines.append("    except Exception as e:")
main_lines.append('        logger.warning(f"Pre-warm on-chain failed: {e}")')
main_lines.append("")
main_lines.append("    # Start background schedulers")
main_lines.append("    try:")
main_lines.append("        asyncio.create_task(onchain_scheduler.start())")
main_lines.append('        logger.info("Started on-chain scheduler (15 min)")')
main_lines.append("    except Exception as e:")
main_lines.append('        logger.warning(f"Failed to start scheduler: {e}")')
main_lines.append("")
main_lines.append("    try:")
main_lines.append("        global data_aggregator, aggregator_scheduler")
main_lines.append("        data_aggregator = await create_aggregator()")
main_lines.append("        aggregator_scheduler = AggregatorScheduler(data_aggregator, interval=900)")
main_lines.append("        asyncio.create_task(aggregator_scheduler.start())")
main_lines.append('        logger.info("Started aggregator scheduler (15 min)")')
main_lines.append("    except Exception as e:")
main_lines.append('        logger.warning(f"Failed to start aggregator: {e}")')
main_lines.append("")
main_lines.append("    # Start unified refresh")
main_lines.append("    try:")
main_lines.append("        global _unified_refresh_running, _unified_refresh_task")
main_lines.append("        _unified_refresh_running = True")
main_lines.append("        _unified_refresh_task = asyncio.create_task(_run_unified_refresh())")
main_lines.append('        logger.info("Started unified refresh scheduler (15 min)")')
main_lines.append("    except Exception as e:")
main_lines.append('        logger.warning(f"Failed to start unified refresh: {e}")')
main_lines.append("")
main_lines.append("    yield")
main_lines.append("")
main_lines.append("    # Shutdown")
main_lines.append('    logger.info("Shutting down Mantle DeFAI Trader API...")')
main_lines.append("    global _unified_refresh_running")
main_lines.append("    _unified_refresh_running = False")
main_lines.append("    if _unified_refresh_task and not _unified_refresh_task.done():")
main_lines.append("        _unified_refresh_task.cancel()")
main_lines.append("    onchain_scheduler.stop()")
main_lines.append("    if aggregator_scheduler is not None:")
main_lines.append("        aggregator_scheduler.stop()")
main_lines.append("    await cache.invalidate()")
main_lines.append("    if data_aggregator is not None:")
main_lines.append("        await data_aggregator.close()")
main_lines.append("")
main_lines.append('app = FastAPI(')
main_lines.append('    title="Mantle DeFAI Trader API",')
main_lines.append('    version="1.2.0",')
main_lines.append('    description="Production-ready API for Mantle DeFAI Trader.",')
main_lines.append('    docs_url="/docs" if os.getenv("DEBUG", "false").lower() == "true" else None,')
main_lines.append('    redoc_url="/redoc" if os.getenv("DEBUG", "false").lower() == "true" else None,')
main_lines.append('    lifespan=lifespan,')
main_lines.append(")")
main_lines.append("")
main_lines.append("# CORS")
main_lines.append('_allowed_origins_raw = os.getenv("ALLOWED_ORIGINS", "http://localhost:3000,http://localhost:5173")')
main_lines.append('allowed_origins = [o.strip() for o in _allowed_origins_raw.split(",") if o.strip()] if _allowed_origins_raw else []')
main_lines.append("app.add_middleware(")
main_lines.append("    CORSMiddleware,")
main_lines.append("    allow_origins=allowed_origins,")
main_lines.append("    allow_credentials=True,")
main_lines.append('    allow_methods=["GET", "POST"],')
main_lines.append('    allow_headers=["*"],')
main_lines.append(")")
main_lines.append("")
main_lines.append("# Include routers")
main_lines.append("app.include_router(api_router)")
main_lines.append("app.include_router(routing_router)")
main_lines.append("")
main_lines.append('# Request/Response logging middleware (imported from core)')
main_lines.append('from core import log_requests')
main_lines.append('app.middleware("http")(log_requests)')
main_lines.append("")
main_lines.append('if __name__ == "__main__":')
main_lines.append("    import uvicorn")
main_lines.append('    port = int(os.getenv("PORT", "8000"))')
main_lines.append('    host = os.getenv("HOST", "0.0.0.0")')
main_lines.append("    uvicorn.run(app, host=host, port=port)")

write_file("apps/api/main.py", main_lines)

# Backup original
shutil.copy2(SRC + ".bak" if os.path.exists(BAK) else SRC, BAK)
print(f"\nOriginal backed up to {BAK}")
print("Split complete!")
