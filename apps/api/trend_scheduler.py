"""
链上趋势分析定时调度器
每小时采集 → 分析 → 每12h汇总 → 每3天大汇总
"""
import asyncio
import json
from datetime import datetime, timedelta
from typing import Optional, Dict, List, Any
from loguru import logger

from chain_indexer import get_chain_indexer
from token_classifier import get_token_classifier
from db import (
    db_save_transaction, db_get_transactions,
    db_save_hourly_analysis, db_get_latest_hourly_analysis,
    db_save_half_day_summary, db_get_latest_half_day_summary,
    db_save_big_summary, db_get_latest_big_summary,
    db_cleanup_old_transactions,
)
from core import HourlyAnalysis, HalfDaySummary, BigSummary
from kimi_analyzer import get_kimi_analyzer


class TrendScheduler:
    """
    链上趋势分析调度器
    - 每小时：采集交易 → 分类 → 分析 → 保存
    - 每12小时：汇总12个 hourly → Kimi 分析 → 保存
    - 每3天：汇总6个 half_day + 72个 hourly → Kimi 深度分析 → 保存
    """

    def __init__(self):
        self.running = False
        self._stop_event = asyncio.Event()
        self.last_hourly_run: Optional[datetime] = None
        self.last_half_day_run: Optional[datetime] = None
        self.last_big_run: Optional[datetime] = None

    async def start(self):
        """启动调度器主循环"""
        self.running = True
        logger.info("[TrendScheduler] Started")

        while self.running:
            try:
                now = datetime.utcnow()

                # 每小时运行（整点触发）
                if self.last_hourly_run is None or (now - self.last_hourly_run).total_seconds() >= 3600:
                    await self._run_hourly_analysis()
                    self.last_hourly_run = now

                # 每12小时运行（00:00 和 12:00 UTC 附近）
                if self.last_half_day_run is None or (now - self.last_half_day_run).total_seconds() >= 43200:
                    await self._run_half_day_summary()
                    self.last_half_day_run = now

                # 每3天运行
                if self.last_big_run is None or (now - self.last_big_run).total_seconds() >= 259200:
                    await self._run_big_summary()
                    self.last_big_run = now

                # 清理半年前的老数据（每天一次，简化：每次循环检查）
                if now.hour == 0 and now.minute < 5:
                    cutoff = (now - timedelta(days=180)).isoformat()
                    await db_cleanup_old_transactions(cutoff)

                # 等待1分钟再检查
                await asyncio.wait_for(self._stop_event.wait(), timeout=60)

            except asyncio.TimeoutError:
                continue
            except Exception as e:
                logger.error(f"[TrendScheduler] Error in main loop: {e}")
                await asyncio.sleep(60)

        logger.info("[TrendScheduler] Stopped")

    async def stop(self):
        """停止调度器"""
        self.running = False
        self._stop_event.set()

    # ========== 每小时分析 ==========

    async def _run_hourly_analysis(self):
        """每小时运行：采集最近1小时交易 → 分类 → 聚合分析 → 保存"""
        logger.info("[TrendScheduler] Running hourly analysis...")
        try:
            # 1. 采集最近1小时交易
            indexer = await get_chain_indexer()
            txs = await indexer.collect_all_chains(hours_back=1, evm_limit_per_chain=100)
            logger.info(f"[TrendScheduler] Collected {len(txs)} transactions")

            # 1a. 采集推荐币种的多链转账
            recommended_txs = await indexer.collect_recommended_token_transfers(hours_back=1, limit_per_token=100)
            if recommended_txs:
                logger.info(f"[TrendScheduler] Collected {len(recommended_txs)} recommended token transfers")
                txs = txs + recommended_txs

            if not txs:
                return

            # 1.5 用 Moralis 填充 USD 价格
            if indexer.moralis.api_key:
                try:
                    txs = await indexer.moralis.enrich_transactions_with_price(txs)
                    logger.info(f"[TrendScheduler] Enriched {len(txs)} transactions with Moralis prices")
                except Exception as e:
                    logger.warning(f"[TrendScheduler] Moralis price enrichment failed: {e}")

            # 3. 代币分类
            classifier = await get_token_classifier()
            txs = await classifier.batch_classify(txs)

            # 4. 保存到数据库
            for tx in txs:
                try:
                    await db_save_transaction(tx)
                except Exception as e:
                    logger.debug(f"[TrendScheduler] Save tx error: {e}")

            # 5. 聚合统计
            stats = self._aggregate_hourly(txs)
            hour_timestamp = datetime.utcnow().replace(minute=0, second=0, microsecond=0)

            # 6. 调用 Kimi 进行 AI 分析
            try:
                kimi = await get_kimi_analyzer()
                kimi_result = await kimi.analyze_hourly(
                    hour_timestamp=hour_timestamp,
                    top_tokens=stats["top_tokens"],
                    top_categories=stats["top_categories"],
                    total_volume=stats["total_volume_usd"],
                    tx_count=stats["tx_count"],
                )
                analysis = {
                    "hour_timestamp": hour_timestamp.isoformat(),
                    "chain": None,  # 全部链汇总
                    "top_tokens": stats["top_tokens"],
                    "top_categories": stats["top_categories"],
                    "hot_narrative": kimi_result["hot_narrative"],
                    "trend_direction": kimi_result["trend_direction"],
                    "total_volume_usd": stats["total_volume_usd"],
                    "tx_count": stats["tx_count"],
                    "kimi_analysis": json.dumps(kimi_result, ensure_ascii=False),
                }
                logger.info(f"[TrendScheduler] Kimi hourly analysis done: {kimi_result.get('trend_direction', 'neutral')}")
            except Exception as e:
                logger.warning(f"[TrendScheduler] Kimi hourly analysis failed, using fallback: {e}")
                analysis = {
                    "hour_timestamp": hour_timestamp.isoformat(),
                    "chain": None,
                    "top_tokens": stats["top_tokens"],
                    "top_categories": stats["top_categories"],
                    "hot_narrative": stats.get("hot_narrative", ""),
                    "trend_direction": stats.get("trend_direction", "neutral"),
                    "total_volume_usd": stats["total_volume_usd"],
                    "tx_count": stats["tx_count"],
                    "kimi_analysis": "",
                }

            await db_save_hourly_analysis(analysis)
            logger.info(f"[TrendScheduler] Hourly analysis saved: {stats['tx_count']} txs, vol={stats['total_volume_usd']}")

        except Exception as e:
            logger.error(f"[TrendScheduler] Hourly analysis error: {e}")

    def _aggregate_hourly(self, txs: List[Dict[str, Any]]) -> Dict[str, Any]:
        """聚合统计最近一小时的交易"""
        from collections import defaultdict

        # Token 统计
        token_stats = defaultdict(lambda: {"count": 0, "volume": 0.0})
        category_stats = defaultdict(lambda: {"count": 0, "volume": 0.0})
        total_volume = 0.0

        for tx in txs:
            symbol = tx.get("token_symbol", "UNKNOWN")
            amount = tx.get("token_amount_usd") or tx.get("token_amount", 0) or 0
            category = tx.get("category") or "Unknown"

            token_stats[symbol]["count"] += 1
            token_stats[symbol]["volume"] += amount
            category_stats[category]["count"] += 1
            category_stats[category]["volume"] += amount
            total_volume += amount

        # Top tokens（按交易量排序）
        top_tokens = sorted(
            [{"symbol": k, **v} for k, v in token_stats.items()],
            key=lambda x: x["volume"],
            reverse=True,
        )[:10]

        # Top categories
        top_categories = sorted(
            [{"category": k, **v} for k, v in category_stats.items()],
            key=lambda x: x["volume"],
            reverse=True,
        )[:10]

        # 简单趋势判断：看 DeFi / AI 占比
        defi_vol = sum(c["volume"] for c in top_categories if c["category"] == "DeFi")
        ai_vol = sum(c["volume"] for c in top_categories if c["category"] == "AI")
        if total_volume > 0:
            if defi_vol / total_volume > 0.4:
                trend = "bullish"
            elif ai_vol / total_volume > 0.3:
                trend = "bullish"
            else:
                trend = "neutral"
        else:
            trend = "neutral"

        return {
            "tx_count": len(txs),
            "total_volume_usd": round(total_volume, 2),
            "top_tokens": top_tokens,
            "top_categories": top_categories,
            "hot_narrative": "",  # 待 Kimi 填充
            "trend_direction": trend,
        }

    # ========== 12小时汇总 ==========

    async def _run_half_day_summary(self):
        """每12小时运行：汇总12个 hourly_analysis"""
        logger.info("[TrendScheduler] Running half-day summary...")
        try:
            # 读取最近12小时的分析
            hourlies = await db_get_latest_hourly_analysis(chain=None, limit=12)
            if not hourlies:
                return

            # 汇总
            total_volume = sum(h.get("total_volume_usd", 0) or 0 for h in hourlies)
            total_tx = sum(h.get("tx_count", 0) or 0 for h in hourlies)

            # 合并 category 统计
            from collections import defaultdict
            cat_merge = defaultdict(lambda: {"count": 0, "volume": 0.0})
            for h in hourlies:
                cats = h.get("top_categories", [])
                for c in cats:
                    cat = c.get("category", "Unknown")
                    cat_merge[cat]["count"] += c.get("count", 0)
                    cat_merge[cat]["volume"] += c.get("volume", 0)

            category_breakdown = sorted(
                [{"category": k, **v} for k, v in cat_merge.items()],
                key=lambda x: x["volume"],
                reverse=True,
            )[:10]

            now = datetime.utcnow()
            period_start = now - timedelta(hours=12)
            period_end = now

            # 调用 Kimi 进行 12h 汇总分析
            kimi_summary = ""
            try:
                kimi = await get_kimi_analyzer()
                kimi_summary = await kimi.analyze_half_day(
                    period_start=period_start,
                    period_end=period_end,
                    category_breakdown=category_breakdown,
                    total_volume=total_volume,
                    hourly_summaries=hourlies,
                )
                logger.info(f"[TrendScheduler] Kimi half-day summary done, length={len(kimi_summary)}")
            except Exception as e:
                logger.warning(f"[TrendScheduler] Kimi half-day summary failed, using fallback: {e}")

            summary = {
                "period_start": period_start.isoformat(),
                "period_end": period_end.isoformat(),
                "chains": ["mantle", "ethereum", "bnb", "solana"],
                "total_volume_usd": round(total_volume, 2),
                "category_breakdown": category_breakdown,
                "top_movers": [],
                "kimi_summary": kimi_summary,
            }
            await db_save_half_day_summary(summary)
            logger.info(f"[TrendScheduler] Half-day summary saved: {total_tx} txs, vol={total_volume}")

        except Exception as e:
            logger.error(f"[TrendScheduler] Half-day summary error: {e}")

    # ========== 3天大汇总 ==========

    async def _run_big_summary(self):
        """每3天运行：深度汇总"""
        logger.info("[TrendScheduler] Running big summary...")
        try:
            # 读取最近6个 half_day + 最近72个 hourly
            half_days = await db_get_latest_half_day_summary(limit=6)
            hourlies = await db_get_latest_hourly_analysis(chain=None, limit=72)

            if not half_days and not hourlies:
                return

            now = datetime.utcnow()
            period_start = now - timedelta(days=3)
            period_end = now

            # 调用 Kimi 进行 3天深度分析
            deep_analysis = ""
            try:
                kimi = await get_kimi_analyzer()
                deep_analysis = await kimi.analyze_big_summary(
                    period_start=period_start,
                    period_end=period_end,
                    half_day_summaries=half_days,
                    hourly_summaries=hourlies,
                )
                logger.info(f"[TrendScheduler] Kimi big summary done, length={len(deep_analysis)}")
            except Exception as e:
                logger.warning(f"[TrendScheduler] Kimi big summary failed, using fallback: {e}")

            summary = {
                "period_start": period_start.isoformat(),
                "period_end": period_end.isoformat(),
                "chains": ["mantle", "ethereum", "bnb", "solana"],
                "narrative_trends": "",
                "category_rotation": "",
                "top_performers": [],
                "kimi_deep_analysis": deep_analysis,
            }
            await db_save_big_summary(summary)
            logger.info("[TrendScheduler] Big summary saved")

        except Exception as e:
            logger.error(f"[TrendScheduler] Big summary error: {e}")


# 全局单例
_trend_scheduler: Optional[TrendScheduler] = None

async def get_trend_scheduler() -> TrendScheduler:
    global _trend_scheduler
    if _trend_scheduler is None:
        _trend_scheduler = TrendScheduler()
    return _trend_scheduler
