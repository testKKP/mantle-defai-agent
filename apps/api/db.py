"""
Mantle DeFAI Trader - Database Layer
SQLite-based persistent cache with async support.

All non-realtime data (sentiment, protocols, TVL, overview, block, gas,
network, trends, tvl_history, aggregated) is stored here and refreshed
every 15 minutes by background schedulers. API endpoints read from this
database (with an optional in-memory hot cache on top).
"""

import asyncio
import json
import os
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from loguru import logger

try:
    import aiosqlite
    AIOSQLITE_AVAILABLE = True
except Exception as e:
    logger.warning(f"aiosqlite not available: {e}")
    AIOSQLITE_AVAILABLE = False

# Database file path
DB_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
DB_PATH = os.path.join(DB_DIR, "cache.db")

# Default TTL for cached entries (15 minutes = 900 seconds)
DEFAULT_CACHE_TTL_SECONDS = int(os.getenv("DB_CACHE_TTL", "900"))

# ============ Schema ============

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS cached_data (
    key TEXT PRIMARY KEY,
    data TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    expires_at TEXT
);

CREATE INDEX IF NOT EXISTS idx_expires ON cached_data(expires_at);
CREATE INDEX IF NOT EXISTS idx_updated ON cached_data(updated_at);

CREATE TABLE IF NOT EXISTS signal_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol TEXT NOT NULL,
    timeframe TEXT NOT NULL,
    direction TEXT NOT NULL,
    confidence TEXT NOT NULL,
    strength TEXT NOT NULL,
    entry_price REAL NOT NULL,
    timestamp TEXT NOT NULL,
    primary_pattern TEXT,
    secondary_patterns TEXT,
    exit_price REAL,
    exit_timestamp TEXT,
    pnl_pct REAL,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_signal_symbol_tf ON signal_history(symbol, timeframe);
CREATE INDEX IF NOT EXISTS idx_signal_strength ON signal_history(strength);
CREATE INDEX IF NOT EXISTS idx_signal_timestamp ON signal_history(timestamp);

-- ============ On-Chain Trend Analysis Tables ============

-- 链上交易记录（半年滚动数据）
CREATE TABLE IF NOT EXISTS chain_transactions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    chain TEXT NOT NULL,
    tx_hash TEXT NOT NULL,
    block_number INTEGER,
    block_time TEXT NOT NULL,
    from_address TEXT,
    to_address TEXT,
    token_address TEXT,
    token_symbol TEXT,
    token_amount REAL,
    token_amount_usd REAL,
    tx_type TEXT,
    category TEXT,
    protocol TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(chain, tx_hash, token_address)
);
CREATE INDEX IF NOT EXISTS idx_tx_chain_time ON chain_transactions(chain, block_time);
CREATE INDEX IF NOT EXISTS idx_tx_category ON chain_transactions(category);

-- 代币元数据
CREATE TABLE IF NOT EXISTS token_metadata (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    chain TEXT NOT NULL,
    token_address TEXT NOT NULL,
    token_symbol TEXT NOT NULL,
    token_name TEXT,
    category TEXT,
    protocol TEXT,
    decimals INTEGER,
    updated_at TEXT,
    UNIQUE(chain, token_address)
);
CREATE INDEX IF NOT EXISTS idx_token_category ON token_metadata(category);

-- 每小时趋势分析
CREATE TABLE IF NOT EXISTS hourly_analysis (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    hour_timestamp TEXT NOT NULL,
    chain TEXT,
    top_tokens TEXT,
    top_categories TEXT,
    hot_narrative TEXT,
    trend_direction TEXT,
    total_volume_usd REAL,
    tx_count INTEGER,
    kimi_analysis TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_hourly_time ON hourly_analysis(hour_timestamp);

-- 12小时汇总
CREATE TABLE IF NOT EXISTS half_day_summary (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    period_start TEXT NOT NULL,
    period_end TEXT NOT NULL,
    chains TEXT,
    total_volume_usd REAL,
    category_breakdown TEXT,
    top_movers TEXT,
    kimi_summary TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

-- 3天大汇总
CREATE TABLE IF NOT EXISTS big_summary (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    period_start TEXT NOT NULL,
    period_end TEXT NOT NULL,
    chains TEXT,
    narrative_trends TEXT,
    category_rotation TEXT,
    top_performers TEXT,
    kimi_deep_analysis TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

-- ============ Elliott Wave Cache ============
CREATE TABLE IF NOT EXISTS elliott_wave_cache (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol TEXT NOT NULL,
    timeframe TEXT NOT NULL DEFAULT '1d',
    candidates TEXT NOT NULL,
    chart_paths TEXT,
    kimi_analysis TEXT,
    klines_count INTEGER,
    computed_at TIMESTAMP NOT NULL,
    expires_at TIMESTAMP NOT NULL,
    UNIQUE(symbol, timeframe)
);
CREATE INDEX IF NOT EXISTS idx_ew_cache_symbol ON elliott_wave_cache(symbol, timeframe);
CREATE INDEX IF NOT EXISTS idx_ew_cache_expires ON elliott_wave_cache(expires_at);

-- ============ On-Chain Signal Submissions ============
CREATE TABLE IF NOT EXISTS onchain_signal_submissions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    tx_hash TEXT NOT NULL,
    block_number INTEGER NOT NULL,
    symbol TEXT NOT NULL,
    timeframe TEXT NOT NULL,
    data TEXT NOT NULL,
    data_hash TEXT NOT NULL,
    timestamp INTEGER NOT NULL,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_ocs_block ON onchain_signal_submissions(block_number DESC);
CREATE INDEX IF NOT EXISTS idx_ocs_timestamp ON onchain_signal_submissions(timestamp DESC, id DESC);
CREATE INDEX IF NOT EXISTS idx_ocs_symbol_tf ON onchain_signal_submissions(symbol, timeframe);
"""


class DatabaseManager:
    """Async SQLite database manager for persistent caching."""

    def __init__(self, db_path: str = DB_PATH):
        self.db_path = db_path
        self._lock = asyncio.Lock()
        self._initialized = False

    async def initialize(self):
        """Initialize the database: create directory and tables."""
        if self._initialized:
            return
        if not AIOSQLITE_AVAILABLE:
            logger.error("aiosqlite is not available; database caching disabled")
            return

        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)

        async with aiosqlite.connect(self.db_path) as db:
            await db.executescript(SCHEMA_SQL)
            await db.commit()

        self._initialized = True
        logger.info(f"Database initialized at {self.db_path}")

    async def get(self, key: str) -> Optional[Dict[str, Any]]:
        """Get a cached entry by key. Returns None if not found or expired."""
        if not self._initialized or not AIOSQLITE_AVAILABLE:
            return None

        try:
            async with self._lock:
                async with aiosqlite.connect(self.db_path) as db:
                    db.row_factory = aiosqlite.Row
                    async with db.execute(
                        "SELECT data, expires_at FROM cached_data WHERE key = ?",
                        (key,),
                    ) as cursor:
                        row = await cursor.fetchone()
                        if row is None:
                            return None

                        # Check expiration
                        expires_at = row["expires_at"]
                        if expires_at:
                            try:
                                expires_dt = datetime.fromisoformat(expires_at)
                                if datetime.utcnow() > expires_dt:
                                    # Expired — delete and return None
                                    await db.execute(
                                        "DELETE FROM cached_data WHERE key = ?", (key,)
                                    )
                                    await db.commit()
                                    return None
                            except Exception:
                                pass  # malformed date, treat as valid

                        # Parse JSON data
                        try:
                            return json.loads(row["data"])
                        except json.JSONDecodeError:
                            logger.warning(f"Corrupted JSON for key={key}")
                            return None
        except Exception as e:
            logger.error(f"DB get error for key={key}: {e}")
            return None

    async def set(
        self,
        key: str,
        data: Any,
        ttl_seconds: int = DEFAULT_CACHE_TTL_SECONDS,
    ):
        """Store data under a key with optional TTL."""
        if not self._initialized or not AIOSQLITE_AVAILABLE:
            return

        now = datetime.utcnow()
        expires_at = (now + timedelta(seconds=ttl_seconds)).isoformat() if ttl_seconds > 0 else None
        json_data = json.dumps(data, default=str, ensure_ascii=False)

        try:
            async with self._lock:
                async with aiosqlite.connect(self.db_path) as db:
                    await db.execute(
                        """
                        INSERT INTO cached_data (key, data, updated_at, expires_at)
                        VALUES (?, ?, ?, ?)
                        ON CONFLICT(key) DO UPDATE SET
                            data = excluded.data,
                            updated_at = excluded.updated_at,
                            expires_at = excluded.expires_at
                        """,
                        (key, json_data, now.isoformat(), expires_at),
                    )
                    await db.commit()
        except Exception as e:
            logger.error(f"DB set error for key={key}: {e}")

    async def delete(self, key: str):
        """Delete a cached entry."""
        if not self._initialized or not AIOSQLITE_AVAILABLE:
            return
        try:
            async with self._lock:
                async with aiosqlite.connect(self.db_path) as db:
                    await db.execute("DELETE FROM cached_data WHERE key = ?", (key,))
                    await db.commit()
        except Exception as e:
            logger.error(f"DB delete error for key={key}: {e}")

    async def cleanup_expired(self):
        """Remove all expired entries."""
        if not self._initialized or not AIOSQLITE_AVAILABLE:
            return
        try:
            now_iso = datetime.utcnow().isoformat()
            async with self._lock:
                async with aiosqlite.connect(self.db_path) as db:
                    cursor = await db.execute(
                        "DELETE FROM cached_data WHERE expires_at IS NOT NULL AND expires_at < ?",
                        (now_iso,),
                    )
                    await db.commit()
                    if cursor.rowcount > 0:
                        logger.info(f"DB cleanup: removed {cursor.rowcount} expired entries")
        except Exception as e:
            logger.error(f"DB cleanup error: {e}")

    async def get_keys(self) -> List[str]:
        """Get all keys in the database."""
        if not self._initialized or not AIOSQLITE_AVAILABLE:
            return []
        try:
            async with aiosqlite.connect(self.db_path) as db:
                async with db.execute("SELECT key FROM cached_data") as cursor:
                    rows = await cursor.fetchall()
                    return [r[0] for r in rows]
        except Exception as e:
            logger.error(f"DB get_keys error: {e}")
            return []

    async def get_stats(self) -> Dict[str, Any]:
        """Get database statistics."""
        if not self._initialized or not AIOSQLITE_AVAILABLE:
            return {"available": False, "entries": 0}
        try:
            async with aiosqlite.connect(self.db_path) as db:
                async with db.execute("SELECT COUNT(*) FROM cached_data") as cursor:
                    total = (await cursor.fetchone())[0]
                now_iso = datetime.utcnow().isoformat()
                async with db.execute(
                    "SELECT COUNT(*) FROM cached_data WHERE expires_at IS NOT NULL AND expires_at < ?",
                    (now_iso,),
                ) as cursor:
                    expired = (await cursor.fetchone())[0]
                return {
                    "available": True,
                    "entries": total,
                    "expired": expired,
                    "path": self.db_path,
                }
        except Exception as e:
            logger.error(f"DB stats error: {e}")
            return {"available": False, "entries": 0, "error": str(e)}


# Global singleton
db_manager = DatabaseManager()

# Convenience functions for use in main.py

async def db_get(key: str) -> Optional[Dict[str, Any]]:
    return await db_manager.get(key)


async def db_set(key: str, data: Any, ttl_seconds: int = DEFAULT_CACHE_TTL_SECONDS):
    await db_manager.set(key, data, ttl_seconds)


async def db_delete(key: str):
    await db_manager.delete(key)


async def init_database():
    await db_manager.initialize()


# ============ Signal History Helpers ============

async def db_save_signal(
    symbol: str,
    timeframe: str,
    direction: str,
    confidence: str,
    strength: str,
    entry_price: float,
    timestamp: str,
    primary_pattern: Optional[str] = None,
    secondary_patterns: Optional[List[str]] = None,
) -> Optional[int]:
    """Save a trading signal to signal_history table. Returns inserted row id."""
    if not db_manager._initialized or not AIOSQLITE_AVAILABLE:
        return None
    try:
        async with db_manager._lock:
            async with aiosqlite.connect(db_manager.db_path) as db:
                cursor = await db.execute(
                    """
                    INSERT INTO signal_history (
                        symbol, timeframe, direction, confidence, strength,
                        entry_price, timestamp, primary_pattern, secondary_patterns
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        symbol, timeframe, direction, confidence, strength,
                        entry_price, timestamp, primary_pattern,
                        json.dumps(secondary_patterns or [], ensure_ascii=False),
                    ),
                )
                await db.commit()
                return cursor.lastrowid
    except Exception as e:
        logger.error(f"db_save_signal error: {e}")
        return None


async def db_get_signals(
    symbol: Optional[str] = None,
    timeframe: Optional[str] = None,
    strength: Optional[str] = None,
    direction: Optional[str] = None,
    closed_only: Optional[bool] = None,
    limit: int = 500,
    offset: int = 0,
) -> List[Dict[str, Any]]:
    """Query signal history with optional filters."""
    if not db_manager._initialized or not AIOSQLITE_AVAILABLE:
        return []
    conditions = []
    params: List[Any] = []
    if symbol:
        conditions.append("symbol = ?")
        params.append(symbol)
    if timeframe:
        conditions.append("timeframe = ?")
        params.append(timeframe)
    if strength:
        conditions.append("strength = ?")
        params.append(strength)
    if direction:
        conditions.append("direction = ?")
        params.append(direction)
    if closed_only is True:
        conditions.append("exit_price IS NOT NULL")
    elif closed_only is False:
        conditions.append("exit_price IS NULL")

    where_clause = "WHERE " + " AND ".join(conditions) if conditions else ""
    query = f"""
        SELECT id, symbol, timeframe, direction, confidence, strength,
               entry_price, timestamp, primary_pattern, secondary_patterns,
               exit_price, exit_timestamp, pnl_pct, created_at
        FROM signal_history
        {where_clause}
        ORDER BY timestamp DESC
        LIMIT ? OFFSET ?
    """
    params.extend([limit, offset])

    try:
        async with db_manager._lock:
            async with aiosqlite.connect(db_manager.db_path) as db:
                db.row_factory = aiosqlite.Row
                async with db.execute(query, params) as cursor:
                    rows = await cursor.fetchall()
                    result = []
                    for row in rows:
                        d = dict(row)
                        try:
                            d["secondary_patterns"] = json.loads(d.get("secondary_patterns", "[]") or "[]")
                        except json.JSONDecodeError:
                            d["secondary_patterns"] = []
                        result.append(d)
                    return result
    except Exception as e:
        logger.error(f"db_get_signals error: {e}")
        return []


async def db_update_signal_exit(
    signal_id: int,
    exit_price: float,
    exit_timestamp: str,
    pnl_pct: float,
) -> bool:
    """Update a signal with exit price and PnL."""
    if not db_manager._initialized or not AIOSQLITE_AVAILABLE:
        return False
    try:
        async with db_manager._lock:
            async with aiosqlite.connect(db_manager.db_path) as db:
                await db.execute(
                    """
                    UPDATE signal_history
                    SET exit_price = ?, exit_timestamp = ?, pnl_pct = ?
                    WHERE id = ?
                    """,
                    (exit_price, exit_timestamp, pnl_pct, signal_id),
                )
                await db.commit()
                return True
    except Exception as e:
        logger.error(f"db_update_signal_exit error: {e}")
        return False


async def db_get_backtest_stats(
    symbol: Optional[str] = None,
    timeframe: Optional[str] = None,
) -> Dict[str, Any]:
    """Get backtest statistics grouped by (symbol, timeframe, strength, direction).
    Returns a nested dict: {symbol: {timeframe: {strength: stats_dict}}}.
    """
    if not db_manager._initialized or not AIOSQLITE_AVAILABLE:
        return {}

    conditions = ["exit_price IS NOT NULL"]
    params: List[Any] = []
    if symbol:
        conditions.append("symbol = ?")
        params.append(symbol)
    if timeframe:
        conditions.append("timeframe = ?")
        params.append(timeframe)

    where_clause = "WHERE " + " AND ".join(conditions)
    query = f"""
        SELECT symbol, timeframe, strength, direction,
               COUNT(*) as total_signals,
               SUM(CASE WHEN pnl_pct > 0 THEN 1 ELSE 0 END) as profitable,
               SUM(CASE WHEN pnl_pct <= 0 THEN 1 ELSE 0 END) as loss,
               AVG(pnl_pct) as avg_pnl,
               MAX(pnl_pct) as max_pnl,
               MIN(pnl_pct) as min_pnl
        FROM signal_history
        {where_clause}
        GROUP BY symbol, timeframe, strength, direction
        ORDER BY symbol, timeframe, strength
    """

    try:
        async with db_manager._lock:
            async with aiosqlite.connect(db_manager.db_path) as db:
                db.row_factory = aiosqlite.Row
                async with db.execute(query, params) as cursor:
                    rows = await cursor.fetchall()
                    stats: Dict[str, Any] = {}
                    for row in rows:
                        sym = row["symbol"]
                        tf = row["timeframe"]
                        st = row["strength"]
                        total = row["total_signals"] or 0
                        profitable = row["profitable"] or 0
                        loss = row["loss"] or 0
                        win_rate = (profitable / total * 100) if total > 0 else 0
                        stats.setdefault(sym, {}).setdefault(tf, {})[st] = {
                            "total_signals": total,
                            "profitable": profitable,
                            "loss": loss,
                            "win_rate": round(win_rate, 2),
                            "avg_pnl": round(row["avg_pnl"] or 0, 4),
                            "max_pnl": round(row["max_pnl"] or 0, 4),
                            "min_pnl": round(row["min_pnl"] or 0, 4),
                        }
                    return stats
    except Exception as e:
        logger.error(f"db_get_backtest_stats error: {e}")
        return {}


# ============ On-Chain Trend Analysis Helpers ============

async def db_save_transaction(tx_dict: Dict[str, Any]) -> Optional[int]:
    """Save a single chain transaction. Returns inserted row id."""
    if not db_manager._initialized or not AIOSQLITE_AVAILABLE:
        return None
    try:
        async with db_manager._lock:
            async with aiosqlite.connect(db_manager.db_path) as db:
                cursor = await db.execute(
                    """
                    INSERT INTO chain_transactions (
                        chain, tx_hash, block_number, block_time,
                        from_address, to_address, token_address, token_symbol,
                        token_amount, token_amount_usd, tx_type, category, protocol
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(chain, tx_hash, token_address) DO UPDATE SET
                        block_number = excluded.block_number,
                        block_time = excluded.block_time,
                        from_address = excluded.from_address,
                        to_address = excluded.to_address,
                        token_symbol = excluded.token_symbol,
                        token_amount = excluded.token_amount,
                        token_amount_usd = excluded.token_amount_usd,
                        tx_type = excluded.tx_type,
                        category = excluded.category,
                        protocol = excluded.protocol
                    """,
                    (
                        tx_dict.get("chain"),
                        tx_dict.get("tx_hash"),
                        tx_dict.get("block_number"),
                        tx_dict.get("block_time"),
                        tx_dict.get("from_address"),
                        tx_dict.get("to_address"),
                        tx_dict.get("token_address"),
                        tx_dict.get("token_symbol"),
                        tx_dict.get("token_amount"),
                        tx_dict.get("token_amount_usd"),
                        tx_dict.get("tx_type"),
                        tx_dict.get("category"),
                        tx_dict.get("protocol"),
                    ),
                )
                await db.commit()
                return cursor.lastrowid
    except Exception as e:
        logger.error(f"db_save_transaction error: {e}")
        return None


async def db_get_transactions(
    chain: Optional[str] = None,
    start_time: Optional[str] = None,
    end_time: Optional[str] = None,
    limit: int = 1000,
) -> List[Dict[str, Any]]:
    """Query chain transactions with optional filters."""
    if not db_manager._initialized or not AIOSQLITE_AVAILABLE:
        return []
    conditions = []
    params: List[Any] = []
    if chain:
        conditions.append("chain = ?")
        params.append(chain)
    if start_time:
        conditions.append("block_time >= ?")
        params.append(start_time)
    if end_time:
        conditions.append("block_time <= ?")
        params.append(end_time)

    where_clause = "WHERE " + " AND ".join(conditions) if conditions else ""
    query = f"""
        SELECT id, chain, tx_hash, block_number, block_time,
               from_address, to_address, token_address, token_symbol,
               token_amount, token_amount_usd, tx_type, category, protocol, created_at
        FROM chain_transactions
        {where_clause}
        ORDER BY block_time DESC
        LIMIT ?
    """
    params.append(limit)

    try:
        async with db_manager._lock:
            async with aiosqlite.connect(db_manager.db_path) as db:
                db.row_factory = aiosqlite.Row
                async with db.execute(query, params) as cursor:
                    rows = await cursor.fetchall()
                    return [dict(row) for row in rows]
    except Exception as e:
        logger.error(f"db_get_transactions error: {e}")
        return []


async def db_save_token_metadata(token_dict: Dict[str, Any]) -> Optional[int]:
    """Save or update token metadata. Returns inserted row id."""
    if not db_manager._initialized or not AIOSQLITE_AVAILABLE:
        return None
    try:
        async with db_manager._lock:
            async with aiosqlite.connect(db_manager.db_path) as db:
                cursor = await db.execute(
                    """
                    INSERT INTO token_metadata (
                        chain, token_address, token_symbol, token_name,
                        category, protocol, decimals, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(chain, token_address) DO UPDATE SET
                        token_symbol = excluded.token_symbol,
                        token_name = excluded.token_name,
                        category = excluded.category,
                        protocol = excluded.protocol,
                        decimals = excluded.decimals,
                        updated_at = excluded.updated_at
                    """,
                    (
                        token_dict.get("chain"),
                        token_dict.get("token_address"),
                        token_dict.get("token_symbol"),
                        token_dict.get("token_name"),
                        token_dict.get("category"),
                        token_dict.get("protocol"),
                        token_dict.get("decimals"),
                        token_dict.get("updated_at") or datetime.utcnow().isoformat(),
                    ),
                )
                await db.commit()
                return cursor.lastrowid
    except Exception as e:
        logger.error(f"db_save_token_metadata error: {e}")
        return None


async def db_get_token_metadata(
    chain: str, token_address: str
) -> Optional[Dict[str, Any]]:
    """Get token metadata by chain and token address."""
    if not db_manager._initialized or not AIOSQLITE_AVAILABLE:
        return None
    try:
        async with db_manager._lock:
            async with aiosqlite.connect(db_manager.db_path) as db:
                db.row_factory = aiosqlite.Row
                async with db.execute(
                    """
                    SELECT id, chain, token_address, token_symbol, token_name,
                           category, protocol, decimals, updated_at
                    FROM token_metadata
                    WHERE chain = ? AND token_address = ?
                    """,
                    (chain, token_address),
                ) as cursor:
                    row = await cursor.fetchone()
                    return dict(row) if row else None
    except Exception as e:
        logger.error(f"db_get_token_metadata error: {e}")
        return None


async def db_save_hourly_analysis(analysis_dict: Dict[str, Any]) -> Optional[int]:
    """Save hourly trend analysis. Returns inserted row id."""
    if not db_manager._initialized or not AIOSQLITE_AVAILABLE:
        return None
    try:
        async with db_manager._lock:
            async with aiosqlite.connect(db_manager.db_path) as db:
                cursor = await db.execute(
                    """
                    INSERT INTO hourly_analysis (
                        hour_timestamp, chain, top_tokens, top_categories,
                        hot_narrative, trend_direction, total_volume_usd,
                        tx_count, kimi_analysis
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        analysis_dict.get("hour_timestamp"),
                        analysis_dict.get("chain"),
                        json.dumps(analysis_dict.get("top_tokens") or [], ensure_ascii=False),
                        json.dumps(analysis_dict.get("top_categories") or [], ensure_ascii=False),
                        analysis_dict.get("hot_narrative"),
                        analysis_dict.get("trend_direction"),
                        analysis_dict.get("total_volume_usd"),
                        analysis_dict.get("tx_count"),
                        analysis_dict.get("kimi_analysis"),
                    ),
                )
                await db.commit()
                return cursor.lastrowid
    except Exception as e:
        logger.error(f"db_save_hourly_analysis error: {e}")
        return None


async def db_get_latest_hourly_analysis(
    chain: Optional[str] = None, limit: int = 24
) -> List[Dict[str, Any]]:
    """Get latest hourly analysis entries."""
    if not db_manager._initialized or not AIOSQLITE_AVAILABLE:
        return []
    conditions = []
    params: List[Any] = []
    if chain:
        conditions.append("chain = ?")
        params.append(chain)

    where_clause = "WHERE " + " AND ".join(conditions) if conditions else ""
    query = f"""
        SELECT id, hour_timestamp, chain, top_tokens, top_categories,
               hot_narrative, trend_direction, total_volume_usd,
               tx_count, kimi_analysis, created_at
        FROM hourly_analysis
        {where_clause}
        ORDER BY hour_timestamp DESC
        LIMIT ?
    """
    params.append(limit)

    try:
        async with db_manager._lock:
            async with aiosqlite.connect(db_manager.db_path) as db:
                db.row_factory = aiosqlite.Row
                async with db.execute(query, params) as cursor:
                    rows = await cursor.fetchall()
                    result = []
                    for row in rows:
                        d = dict(row)
                        for key in ("top_tokens", "top_categories"):
                            try:
                                d[key] = json.loads(d.get(key, "[]") or "[]")
                            except json.JSONDecodeError:
                                d[key] = []
                        result.append(d)
                    return result
    except Exception as e:
        logger.error(f"db_get_latest_hourly_analysis error: {e}")
        return []


async def db_save_half_day_summary(summary_dict: Dict[str, Any]) -> Optional[int]:
    """Save 12-hour summary. Returns inserted row id."""
    if not db_manager._initialized or not AIOSQLITE_AVAILABLE:
        return None
    try:
        async with db_manager._lock:
            async with aiosqlite.connect(db_manager.db_path) as db:
                cursor = await db.execute(
                    """
                    INSERT INTO half_day_summary (
                        period_start, period_end, chains,
                        total_volume_usd, category_breakdown, top_movers, kimi_summary
                    ) VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        summary_dict.get("period_start"),
                        summary_dict.get("period_end"),
                        json.dumps(summary_dict.get("chains") or [], ensure_ascii=False),
                        summary_dict.get("total_volume_usd"),
                        json.dumps(summary_dict.get("category_breakdown") or {}, ensure_ascii=False),
                        json.dumps(summary_dict.get("top_movers") or [], ensure_ascii=False),
                        summary_dict.get("kimi_summary"),
                    ),
                )
                await db.commit()
                return cursor.lastrowid
    except Exception as e:
        logger.error(f"db_save_half_day_summary error: {e}")
        return None


async def db_get_latest_half_day_summary(limit: int = 10) -> List[Dict[str, Any]]:
    """Get latest 12-hour summaries."""
    if not db_manager._initialized or not AIOSQLITE_AVAILABLE:
        return []
    try:
        async with db_manager._lock:
            async with aiosqlite.connect(db_manager.db_path) as db:
                db.row_factory = aiosqlite.Row
                async with db.execute(
                    """
                    SELECT id, period_start, period_end, chains, total_volume_usd,
                           category_breakdown, top_movers, kimi_summary, created_at
                    FROM half_day_summary
                    ORDER BY period_start DESC
                    LIMIT ?
                    """,
                    (limit,),
                ) as cursor:
                    rows = await cursor.fetchall()
                    result = []
                    for row in rows:
                        d = dict(row)
                        try:
                            d["chains"] = json.loads(d.get("chains", "[]") or "[]")
                        except json.JSONDecodeError:
                            d["chains"] = []
                        try:
                            d["category_breakdown"] = json.loads(d.get("category_breakdown", "{}") or "{}")
                        except json.JSONDecodeError:
                            d["category_breakdown"] = {}
                        try:
                            d["top_movers"] = json.loads(d.get("top_movers", "[]") or "[]")
                        except json.JSONDecodeError:
                            d["top_movers"] = []
                        result.append(d)
                    return result
    except Exception as e:
        logger.error(f"db_get_latest_half_day_summary error: {e}")
        return []


async def db_save_big_summary(summary_dict: Dict[str, Any]) -> Optional[int]:
    """Save 3-day big summary. Returns inserted row id."""
    if not db_manager._initialized or not AIOSQLITE_AVAILABLE:
        return None
    try:
        async with db_manager._lock:
            async with aiosqlite.connect(db_manager.db_path) as db:
                cursor = await db.execute(
                    """
                    INSERT INTO big_summary (
                        period_start, period_end, chains,
                        narrative_trends, category_rotation, top_performers, kimi_deep_analysis
                    ) VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        summary_dict.get("period_start"),
                        summary_dict.get("period_end"),
                        json.dumps(summary_dict.get("chains") or [], ensure_ascii=False),
                        summary_dict.get("narrative_trends"),
                        summary_dict.get("category_rotation"),
                        json.dumps(summary_dict.get("top_performers") or [], ensure_ascii=False),
                        summary_dict.get("kimi_deep_analysis"),
                    ),
                )
                await db.commit()
                return cursor.lastrowid
    except Exception as e:
        logger.error(f"db_save_big_summary error: {e}")
        return None


async def db_get_latest_big_summary(limit: int = 5) -> List[Dict[str, Any]]:
    """Get latest 3-day big summaries."""
    if not db_manager._initialized or not AIOSQLITE_AVAILABLE:
        return []
    try:
        async with db_manager._lock:
            async with aiosqlite.connect(db_manager.db_path) as db:
                db.row_factory = aiosqlite.Row
                async with db.execute(
                    """
                    SELECT id, period_start, period_end, chains, narrative_trends,
                           category_rotation, top_performers, kimi_deep_analysis, created_at
                    FROM big_summary
                    ORDER BY period_start DESC
                    LIMIT ?
                    """,
                    (limit,),
                ) as cursor:
                    rows = await cursor.fetchall()
                    result = []
                    for row in rows:
                        d = dict(row)
                        try:
                            d["chains"] = json.loads(d.get("chains", "[]") or "[]")
                        except json.JSONDecodeError:
                            d["chains"] = []
                        try:
                            d["top_performers"] = json.loads(d.get("top_performers", "[]") or "[]")
                        except json.JSONDecodeError:
                            d["top_performers"] = []
                        result.append(d)
                    return result
    except Exception as e:
        logger.error(f"db_get_latest_big_summary error: {e}")
        return []


async def db_cleanup_old_transactions(before_date: Optional[str] = None) -> int:
    """Delete chain transactions older than the given date.
    If before_date is not provided, defaults to 6 months ago.
    Returns the number of rows deleted.
    """
    if not db_manager._initialized or not AIOSQLITE_AVAILABLE:
        return 0
    if before_date is None:
        before_date = (datetime.utcnow() - timedelta(days=180)).isoformat()
    try:
        async with db_manager._lock:
            async with aiosqlite.connect(db_manager.db_path) as db:
                cursor = await db.execute(
                    "DELETE FROM chain_transactions WHERE block_time < ?",
                    (before_date,),
                )
                await db.commit()
                if cursor.rowcount and cursor.rowcount > 0:
                    logger.info(f"DB cleanup: removed {cursor.rowcount} old transactions")
                return cursor.rowcount or 0
    except Exception as e:
        logger.error(f"db_cleanup_old_transactions error: {e}")
        return 0


# ============ Elliott Wave Cache Helpers ============

async def db_save_elliott_wave(
    symbol: str,
    timeframe: str,
    candidates: list,
    chart_paths: list,
    klines_count: int,
    kimi_analysis: dict = None,
    ttl: int = 15000,
) -> None:
    """Save Elliott Wave analysis result to cache."""
    if not db_manager._initialized or not AIOSQLITE_AVAILABLE:
        return
    try:
        now = datetime.utcnow()
        expires_at = (now + timedelta(seconds=ttl)).isoformat()

        # 直接保存传入的 chart_paths，不再做文件存在性过滤
        saved_chart_paths = chart_paths or []

        async with db_manager._lock:
            async with aiosqlite.connect(db_manager.db_path) as db:
                await db.execute(
                    """
                    INSERT INTO elliott_wave_cache (
                        symbol, timeframe, candidates, chart_paths, kimi_analysis,
                        klines_count, computed_at, expires_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(symbol, timeframe) DO UPDATE SET
                        candidates = excluded.candidates,
                        chart_paths = excluded.chart_paths,
                        kimi_analysis = COALESCE(excluded.kimi_analysis, kimi_analysis),
                        klines_count = excluded.klines_count,
                        computed_at = excluded.computed_at,
                        expires_at = excluded.expires_at
                    """,
                    (
                        symbol,
                        timeframe,
                        json.dumps(candidates, default=str, ensure_ascii=False),
                        json.dumps(saved_chart_paths, default=str, ensure_ascii=False),
                        json.dumps(kimi_analysis, default=str, ensure_ascii=False) if kimi_analysis else None,
                        klines_count,
                        now.isoformat(),
                        expires_at,
                    ),
                )
                await db.commit()
    except Exception as e:
        logger.error(f"db_save_elliott_wave error: {e}")


async def db_get_elliott_wave(symbol: str, timeframe: str = "1d") -> dict | None:
    """Get cached Elliott Wave result. Returns None if not found or expired."""
    if not db_manager._initialized or not AIOSQLITE_AVAILABLE:
        return None
    try:
        async with db_manager._lock:
            async with aiosqlite.connect(db_manager.db_path) as db:
                db.row_factory = aiosqlite.Row
                async with db.execute(
                    """
                    SELECT id, symbol, timeframe, candidates, chart_paths, kimi_analysis,
                           klines_count, computed_at, expires_at
                    FROM elliott_wave_cache
                    WHERE symbol = ? AND timeframe = ?
                    """,
                    (symbol, timeframe),
                ) as cursor:
                    row = await cursor.fetchone()
                    if row is None:
                        return None

                    # Check expiration
                    expires_at = row["expires_at"]
                    if expires_at:
                        try:
                            expires_dt = datetime.fromisoformat(expires_at)
                            if datetime.utcnow() > expires_dt:
                                return None
                        except Exception:
                            pass

                    result = dict(row)
                    for key in ("candidates", "chart_paths"):
                        try:
                            result[key] = json.loads(result.get(key, "[]") or "[]")
                        except json.JSONDecodeError:
                            result[key] = []
                    try:
                        result["kimi_analysis"] = json.loads(result.get("kimi_analysis", "{}") or "{}")
                    except json.JSONDecodeError:
                        result["kimi_analysis"] = {}
                    return result
    except Exception as e:
        logger.error(f"db_get_elliott_wave error: {e}")
        return None


async def db_get_all_elliott_waves(timeframe: str = "1d") -> list[dict]:
    """Get all non-expired cached Elliott Wave results."""
    if not db_manager._initialized or not AIOSQLITE_AVAILABLE:
        return []
    try:
        now_iso = datetime.utcnow().isoformat()
        async with db_manager._lock:
            async with aiosqlite.connect(db_manager.db_path) as db:
                db.row_factory = aiosqlite.Row
                async with db.execute(
                    """
                    SELECT id, symbol, timeframe, candidates, chart_paths, kimi_analysis,
                           klines_count, computed_at, expires_at
                    FROM elliott_wave_cache
                    WHERE timeframe = ? AND expires_at > ?
                    ORDER BY computed_at DESC
                    """,
                    (timeframe, now_iso),
                ) as cursor:
                    rows = await cursor.fetchall()
                    result = []
                    for row in rows:
                        d = dict(row)
                        for key in ("candidates", "chart_paths"):
                            try:
                                d[key] = json.loads(d.get(key, "[]") or "[]")
                            except json.JSONDecodeError:
                                d[key] = []
                        try:
                            d["kimi_analysis"] = json.loads(d.get("kimi_analysis", "{}") or "{}")
                        except json.JSONDecodeError:
                            d["kimi_analysis"] = {}
                        result.append(d)
                    return result
    except Exception as e:
        logger.error(f"db_get_all_elliott_waves error: {e}")
        return []


# ============ On-Chain Signal Submission Helpers ============

# 零停机迁移兜底：旧数据库可能缺少 onchain_signal_submissions 表，SCHEMA_SQL 中已包含该表定义
_ONCHAIN_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS onchain_signal_submissions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    tx_hash TEXT NOT NULL,
    block_number INTEGER NOT NULL,
    symbol TEXT NOT NULL,
    timeframe TEXT NOT NULL,
    data TEXT NOT NULL,
    data_hash TEXT NOT NULL,
    timestamp INTEGER NOT NULL,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_ocs_block ON onchain_signal_submissions(block_number DESC);
CREATE INDEX IF NOT EXISTS idx_ocs_timestamp ON onchain_signal_submissions(timestamp DESC, id DESC);
CREATE INDEX IF NOT EXISTS idx_ocs_symbol_tf ON onchain_signal_submissions(symbol, timeframe);
"""


async def _ensure_onchain_tables():
    """Ensure onchain_signal_submissions table exists (zero-downtime fallback for legacy DBs). Table is already defined in SCHEMA_SQL, this is idempotent."""
    if not db_manager._initialized or not AIOSQLITE_AVAILABLE:
        return
    try:
        async with db_manager._lock:
            async with aiosqlite.connect(db_manager.db_path) as db:
                await db.executescript(_ONCHAIN_TABLE_SQL)
                await db.commit()
    except Exception as e:
        logger.error(f"_ensure_onchain_tables error: {e}")


async def db_save_onchain_signal(
    tx_hash: str,
    block_number: int,
    symbol: str,
    timeframe: str,
    data: str,
    data_hash: str,
    timestamp: int,
) -> Optional[int]:
    """Save an on-chain signal submission record. Returns inserted row id."""
    await _ensure_onchain_tables()
    if not db_manager._initialized:
        logger.warning("db_save_onchain_signal: db_manager not initialized, skipping")
        return None
    if not AIOSQLITE_AVAILABLE:
        return None
    try:
        async with db_manager._lock:
            async with aiosqlite.connect(db_manager.db_path) as db:
                cursor = await db.execute(
                    """
                    INSERT INTO onchain_signal_submissions (
                        tx_hash, block_number, symbol, timeframe,
                        data, data_hash, timestamp
                    ) VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (tx_hash, block_number, symbol, timeframe, data, data_hash, timestamp),
                )
                await db.commit()
                return cursor.lastrowid
    except Exception as e:
        logger.error(f"db_save_onchain_signal error: {e}")
        return None


async def db_get_recent_onchain_signals(limit: int = 100) -> List[Dict[str, Any]]:
    """Get recent on-chain signal submissions ordered by block_number DESC."""
    await _ensure_onchain_tables()
    if not db_manager._initialized or not AIOSQLITE_AVAILABLE:
        return []
    try:
        async with db_manager._lock:
            async with aiosqlite.connect(db_manager.db_path) as db:
                db.row_factory = aiosqlite.Row
                async with db.execute(
                    """
                    SELECT id, tx_hash, block_number, symbol, timeframe,
                           data, data_hash, timestamp, created_at
                    FROM onchain_signal_submissions
                    ORDER BY timestamp DESC, id DESC
                    LIMIT ?
                    """,
                    (limit,),
                ) as cursor:
                    rows = await cursor.fetchall()
                    return [dict(row) for row in rows]
    except Exception as e:
        logger.error(f"db_get_recent_onchain_signals error: {e}")
        return []


async def db_get_active_elliott_wave_chart_paths() -> List[str]:
    """Get chart_paths of all non-expired Elliott Wave cache entries."""
    if not db_manager._initialized or not AIOSQLITE_AVAILABLE:
        return []
    try:
        now_iso = datetime.utcnow().isoformat()
        async with db_manager._lock:
            async with aiosqlite.connect(db_manager.db_path) as db:
                async with db.execute(
                    "SELECT chart_paths FROM elliott_wave_cache WHERE expires_at > ?",
                    (now_iso,),
                ) as cursor:
                    rows = await cursor.fetchall()
                    result: List[str] = []
                    for row in rows:
                        try:
                            paths = json.loads(row[0] or "[]")
                            if isinstance(paths, list):
                                result.extend(paths)
                        except json.JSONDecodeError:
                            pass
                    return result
    except Exception as e:
        logger.error(f"db_get_active_elliott_wave_chart_paths error: {e}")
        return []


async def db_cleanup_expired_elliott_waves() -> int:
    """Delete expired Elliott Wave cache entries. Returns deleted count."""
    if not db_manager._initialized or not AIOSQLITE_AVAILABLE:
        return 0
    try:
        now_iso = datetime.utcnow().isoformat()
        async with db_manager._lock:
            async with aiosqlite.connect(db_manager.db_path) as db:
                cursor = await db.execute(
                    "DELETE FROM elliott_wave_cache WHERE expires_at < ?",
                    (now_iso,),
                )
                await db.commit()
                if cursor.rowcount and cursor.rowcount > 0:
                    logger.info(f"DB cleanup: removed {cursor.rowcount} expired Elliott Wave entries")
                return cursor.rowcount or 0
    except Exception as e:
        logger.error(f"db_cleanup_expired_elliott_waves error: {e}")
        return 0
