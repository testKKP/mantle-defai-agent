"""
Kimi CLI 分析器 — 调用 Kimi CLI 对链上数据进行 AI 趋势分析
"""
import asyncio
import subprocess
import json
import tempfile
import os
from typing import Optional, Dict, Any, List
from datetime import datetime
from loguru import logger


class KimiAnalyzer:
    """调用 Kimi CLI 进行链上趋势分析"""

    def __init__(self, timeout: int = 120):
        self.timeout = timeout

    async def analyze_hourly(
        self,
        hour_timestamp: datetime,
        top_tokens: List[Dict],
        top_categories: List[Dict],
        total_volume: float,
        tx_count: int,
        chain: Optional[str] = None,
    ) -> Dict[str, str]:
        """
        每小时趋势分析。
        传入聚合后的统计数据，让 Kimi 判断趋势方向、提炼叙事。
        """
        prompt = self._build_hourly_prompt(hour_timestamp, top_tokens, top_categories, total_volume, tx_count, chain)
        result = await self._call_kimi(prompt)
        return self._parse_hourly_result(result)

    async def analyze_half_day(
        self,
        period_start: datetime,
        period_end: datetime,
        category_breakdown: List[Dict],
        total_volume: float,
        hourly_summaries: List[Dict],
    ) -> str:
        """12小时汇总分析"""
        prompt = self._build_half_day_prompt(period_start, period_end, category_breakdown, total_volume, hourly_summaries)
        return await self._call_kimi(prompt)

    async def analyze_big_summary(
        self,
        period_start: datetime,
        period_end: datetime,
        half_day_summaries: List[Dict],
        hourly_summaries: List[Dict],
    ) -> str:
        """3天大汇总深度分析"""
        prompt = self._build_big_prompt(period_start, period_end, half_day_summaries, hourly_summaries)
        return await self._call_kimi(prompt)

    async def analyze_targets(
        self,
        top_targets: List[Dict[str, Any]],
        chain_distribution: List[Dict[str, Any]],
        category_distribution: List[Dict[str, Any]],
        summary: Dict[str, Any],
        sentiment_data: Optional[Dict[str, Any]] = None,
    ) -> str:
        """AI 分析趋势标的，融入市场情绪数据"""
        prompt = self._build_targets_prompt(
            top_targets, chain_distribution, category_distribution, summary, sentiment_data
        )
        result = await self._call_kimi(prompt)
        if not result or not result.strip():
            return "AI 分析服务暂时不可用，请稍后重试。"
        return result

    def _build_hourly_prompt(
        self,
        hour_timestamp: datetime,
        top_tokens: List[Dict],
        top_categories: List[Dict],
        total_volume: float,
        tx_count: int,
        chain: Optional[str],
    ) -> str:
        chain_str = f" ({chain})" if chain else ""
        return f"""你是链上数据分析专家。请根据以下{hour_timestamp.strftime('%Y-%m-%d %H:%M')} UTC 的链上交易数据，给出趋势判断和叙事分析。

数据概览：
- 交易笔数：{tx_count}
- 总交易量：${total_volume:,.2f} USD
- 链：{chain_str or "多链"}

Top 代币（按交易量）：
{json.dumps(top_tokens[:5], ensure_ascii=False, indent=2)}

Top 赛道（按交易量）：
{json.dumps(top_categories[:5], ensure_ascii=False, indent=2)}

请输出 JSON 格式：
{{
  "trend_direction": "bullish|bearish|neutral",
  "confidence": "high|medium|low",
  "hot_narrative": "当前最热的叙事/主题，1-2句话",
  "key_insight": "关键洞察，2-3句话",
  "risk_signal": "是否有风险信号，1句话（如有）"
}}

只输出 JSON，不要其他文字。"""

    def _build_half_day_prompt(
        self,
        period_start: datetime,
        period_end: datetime,
        category_breakdown: List[Dict],
        total_volume: float,
        hourly_summaries: List[Dict],
    ) -> str:
        return f"""你是链上数据分析专家。请分析 {period_start.strftime('%Y-%m-%d %H:%M')} 到 {period_end.strftime('%Y-%m-%d %H:%M')} UTC 这12小时的链上趋势。

总交易量：${total_volume:,.2f} USD

赛道分布：
{json.dumps(category_breakdown[:8], ensure_ascii=False, indent=2)}

最近几小时趋势方向：
{json.dumps([{"hour": h.get("hour_timestamp"), "direction": h.get("trend_direction", "neutral")} for h in hourly_summaries[-6:]], ensure_ascii=False, indent=2)}

请输出一段 200-300 字的趋势总结，包含：
1. 整体市场方向
2. 热点赛道轮动
3. 值得关注的信号
4. 短期展望

用中文输出。"""

    def _build_big_prompt(
        self,
        period_start: datetime,
        period_end: datetime,
        half_day_summaries: List[Dict],
        hourly_summaries: List[Dict],
    ) -> str:
        return f"""你是链上数据分析专家。请深度分析 {period_start.strftime('%Y-%m-%d')} 到 {period_end.strftime('%Y-%m-%d')} 这3天的链上数据。

12小时汇总趋势：
{json.dumps([{"period": s.get("period_start"), "summary": s.get("kimi_summary", "")[:200]} for s in half_day_summaries[-6:]], ensure_ascii=False, indent=2)}

请输出一段 400-600 字的深度分析报告，包含：
1. 叙事演变（哪些叙事兴起/消退）
2. 赛道轮动周期分析
3. 资金流动方向
4. 未来3-7天展望
5. 风险提示

用中文输出，风格专业但易懂。"""

    def _build_targets_prompt(
        self,
        top_targets: List[Dict[str, Any]],
        chain_distribution: List[Dict[str, Any]],
        category_distribution: List[Dict[str, Any]],
        summary: Dict[str, Any],
        sentiment_data: Optional[Dict[str, Any]] = None,
    ) -> str:
        """构建趋势标分析的 prompt 模板"""
        time_range = summary.get("time_range_hours", 24)
        total_tx = summary.get("total_tx", 0)
        total_volume = summary.get("total_volume", 0.0)
        unique_tokens = summary.get("unique_tokens", 0)
        unique_chains = summary.get("unique_chains", 0)

        # 格式化 Top 标的
        top_formatted = []
        for t in top_targets[:10]:
            top_formatted.append({
                "排名": t.get("rank", 0),
                "链": t.get("chain", "未知"),
                "代币": t.get("token_symbol", "未知"),
                "交易笔数": t.get("tx_count", 0),
                "交易量(USD)": t.get("total_amount", 0),
                "Swap占比": t.get("swap_ratio", 0),
                "独立地址数": t.get("unique_addresses", 0),
                "趋势评分": t.get("trend_score", 0),
                "赛道": t.get("category", "未分类"),
            })

        # 格式化链分布
        chain_formatted = []
        for c in chain_distribution:
            chain_formatted.append({
                "链": c.get("name", "未知"),
                "占比": c.get("value", 0),
                "交易笔数": c.get("tx_count", 0),
                "交易量(USD)": c.get("volume", 0),
            })

        # 格式化赛道分布
        category_formatted = []
        for cat in category_distribution:
            category_formatted.append({
                "赛道": cat.get("name", "未知"),
                "占比": cat.get("value", 0),
                "交易笔数": cat.get("tx_count", 0),
                "交易量(USD)": cat.get("volume", 0),
            })

        # 构建情绪数据段落
        sentiment_section = ""
        if sentiment_data:
            bias = sentiment_data.get("market_bias", "unknown")
            bias_strength = sentiment_data.get("bias_strength", "unknown")
            sentiment_index = sentiment_data.get("sentiment_index", "N/A")
            btc_change = sentiment_data.get("btc_change_24h", "N/A")
            fng = sentiment_data.get("fng", {})
            fng_value = fng.get("value", "N/A") if isinstance(fng, dict) else "N/A"
            fng_class = fng.get("classification", "N/A") if isinstance(fng, dict) else "N/A"
            
            bullish = sentiment_data.get("bullish_count", 0)
            bearish = sentiment_data.get("bearish_count", 0)
            neutral = sentiment_data.get("neutral_count", 0)
            
            top_bullish = sentiment_data.get("top_bullish", [])
            top_bearish = sentiment_data.get("top_bearish", [])
            
            bullish_str = ", ".join([f"{b['symbol']}({b.get('score', 0):.1f})" for b in top_bullish[:3]]) if top_bullish else "无"
            bearish_str = ", ".join([f"{b['symbol']}({b.get('score', 0):.1f})" for b in top_bearish[:3]]) if top_bearish else "无"
            
            sentiment_section = f"""

### 市场情绪参考
- 整体情绪指数: {sentiment_index}/100
- 市场偏向: {bias}（强度: {bias_strength}）
- 恐惧贪婪指数(FNG): {fng_value}（{fng_class}）
- BTC 24h 涨跌: {btc_change}%
- 多空信号分布: 做多{bullish}个, 做空{bearish}个, 观望{neutral}个
- 做多信号前三: {bullish_str}
- 做空信号前三: {bearish_str}
"""

        return f"""你是链上数据分析专家。请根据以下基于 BNB/Solana/ETH 等多链链上交易数据的趋势标的分析请求，给出专业、深入的分析意见。

【数据说明】
- 数据来源：多链（BNB Chain / Solana / Ethereum）链上真实交易数据
- 时间范围：最近 {time_range} 小时
- 趋势标的已按综合评分（交易量、交易笔数、独立地址数、Swap 活跃度等）排序

【汇总统计】
- 总交易笔数：{total_tx}
- 总交易量：${total_volume:,.2f} USD
- 独立代币数：{unique_tokens}
- 活跃链数：{unique_chains}
{sentiment_section}
【Top 趋势标的】（已按综合评分排序）
{json.dumps(top_formatted[:5], ensure_ascii=False, indent=2)}

【链上分布】
{json.dumps(chain_formatted, ensure_ascii=False, indent=2)}

【赛道分布】
{json.dumps(category_formatted[:8], ensure_ascii=False, indent=2)}

【分析要求】
请输出一段 300-500 字的纯文本中文分析，必须包含以下内容：
1. 整体市场方向：基于数据判断当前市场是 bullish / bearish / neutral，并给出理由
2. Top 3 标的点评：对排名前 3 的标的逐一给出投资价值评估，说明其热度来源和潜在风险
3. 赛道轮动观察：分析赛道分布变化，哪些赛道正在崛起、哪些在消退，是否有明显的资金轮动迹象
4. 短期（24h）风险提示：给出基于当前数据的短期风险提示，包括但不限于波动性风险、流动性风险、集中度风险
5. 情绪联动分析：结合当前市场情绪数据（FNG指数、BTC涨跌、多空信号分布），判断链上趋势是否与宏观情绪一致。如果链上活跃币种与情绪推荐的做多/做空信号方向一致，增强置信度；如果方向矛盾，降低评级

【输出格式】
- 纯文本中文，不要 Markdown、不要 JSON、不要列表符号
- 风格专业但易懂，像给交易者的简报
- 字数控制在 300-500 字之间"""


    async def _call_kimi(self, prompt: str) -> str:
        """调用 Kimi CLI"""
        temp_path = None
        try:
            # 将 prompt 写入临时文件
            with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False, encoding='utf-8') as f:
                f.write(prompt)
                temp_path = f.name

            # 调用 Kimi CLI
            cmd = [
                "kimi",
                "--quiet",
                "-p", f"file://{temp_path}"
            ]

            logger.info(f"[KimiAnalyzer] Calling Kimi CLI...")

            # 使用 asyncio.to_thread 避免阻塞事件循环
            result = await asyncio.to_thread(
                subprocess.run,
                cmd,
                capture_output=True,
                text=True,
                timeout=self.timeout,
            )

            if result.returncode != 0:
                logger.error(f"[KimiAnalyzer] Kimi CLI error: {result.stderr}")
                return ""

            output = result.stdout.strip()
            logger.info(f"[KimiAnalyzer] Kimi response length: {len(output)}")
            return output

        except subprocess.TimeoutExpired:
            logger.error(f"[KimiAnalyzer] Kimi CLI timeout ({self.timeout}s)")
            return ""
        except FileNotFoundError:
            logger.error("[KimiAnalyzer] Kimi CLI not found. Please install kim CLI.")
            return ""
        except Exception as e:
            logger.error(f"[KimiAnalyzer] Error calling Kimi: {e}")
            return ""
        finally:
            # 清理临时文件
            if temp_path and os.path.exists(temp_path):
                try:
                    os.unlink(temp_path)
                except Exception:
                    pass

    def _parse_hourly_result(self, raw: str) -> Dict[str, str]:
        """解析 Kimi 返回的 JSON"""
        if not raw:
            return {
                "trend_direction": "neutral",
                "confidence": "low",
                "hot_narrative": "",
                "key_insight": "",
                "risk_signal": "",
            }

        # 尝试提取 JSON 部分
        try:
            # 找 JSON 块
            start = raw.find("{")
            end = raw.rfind("}")
            if start != -1 and end != -1 and end > start:
                json_str = raw[start:end+1]
                parsed = json.loads(json_str)
                return {
                    "trend_direction": parsed.get("trend_direction", "neutral"),
                    "confidence": parsed.get("confidence", "low"),
                    "hot_narrative": parsed.get("hot_narrative", ""),
                    "key_insight": parsed.get("key_insight", ""),
                    "risk_signal": parsed.get("risk_signal", ""),
                }
        except Exception as e:
            logger.warning(f"[KimiAnalyzer] Failed to parse JSON: {e}")

        # 回退：返回原始文本作为 narrative
        return {
            "trend_direction": "neutral",
            "confidence": "low",
            "hot_narrative": raw[:500],
            "key_insight": "",
            "risk_signal": "",
        }


# 全局单例
_kimi_analyzer: Optional[KimiAnalyzer] = None

async def get_kimi_analyzer() -> KimiAnalyzer:
    global _kimi_analyzer
    if _kimi_analyzer is None:
        _kimi_analyzer = KimiAnalyzer()
    return _kimi_analyzer
