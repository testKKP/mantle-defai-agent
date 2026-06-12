"""
Kimi Vision — 调用 Kimi CLI 进行 Elliott Wave 图表的视觉分析。

封装 Kimi CLI 的视觉分析能力，将生成的艾略特波浪图表传给 Kimi，
让 Kimi 确认浪型、指出错误、给出多种走势预测。
"""

import asyncio
import json
import math
import re
import subprocess
from typing import Any, Dict, List, Optional

from loguru import logger

DEFAULT_TIMEOUT = 180


async def analyze_elliott_wave_with_kimi(
    chart_path: str,
    symbol: str,
    timeframe: str,
    wave_candidate: Dict[str, Any],
) -> Dict[str, Any]:
    """
    调用 Kimi CLI 分析艾略特波浪图表。

    参数:
        chart_path: 图表文件路径（如 "tests/screenshots/ew_BTC_1d.png"）
        symbol: 币种，如 "BTC"
        timeframe: 时间框架，如 "1d"
        wave_candidate: 算法识别的波浪候选，包含 wave_pattern, waves,
                        fib_ratios, score 等

    返回:
        {
            "confirmed_wave": "1-2-3-4-5 impulse wave, currently in Wave 4 correction",
            "corrections": ["Wave 2 retrace is slightly deeper than ideal 50%"],
            "projections": [
                {"scenario": "bullish", "description": "...", "target_price": 75000, "confidence": 0.6},
                {"scenario": "bearish", "description": "...", "target_price": 58000, "confidence": 0.3},
                {"scenario": "neutral", "description": "...", "target_price": 65000, "confidence": 0.1},
            ],
            "key_fib_levels": [0.382, 0.5, 0.618],
            "overall_confidence": 0.72,
            "raw_analysis": "Kimi 原始返回的完整文本",
        }
    """
    prompt = _build_elliott_wave_prompt(symbol, timeframe, wave_candidate)
    raw_text = await _call_kimi_vision(chart_path, prompt, timeout=DEFAULT_TIMEOUT)

    if not raw_text:
        logger.warning("[KimiVision] Kimi returned empty response, falling back to defaults")
        return {
            "confirmed_wave": "",
            "corrections": [],
            "projections": [],
            "key_fib_levels": [],
            "overall_confidence": 0.0,
            "raw_analysis": "",
        }

    parsed = _parse_kimi_response(raw_text)

    # Try to parse wave structure from Kimi's response
    kimi_structure = _parse_kimi_wave_structure(raw_text)
    if kimi_structure:
        parsed["kimi_structure"] = kimi_structure
        if "waves" in kimi_structure:
            parsed["confirmed_wave"] = f"{kimi_structure.get('wave_pattern', '')} - Currently in {kimi_structure.get('current_wave', '')}"

    # Extract current wave probabilities from Kimi's response
    parsed["current_wave_probabilities"] = _extract_current_wave_probabilities(raw_text)

    # Normalize confidences
    if parsed.get("projections"):
        parsed["projections"] = _normalize_confidences(parsed["projections"])

    logger.info(f"[KimiVision] Parsed analysis for {symbol} {timeframe}: "
                f"confidence={parsed.get('overall_confidence', 0):.2f}, "
                f"projections={len(parsed.get('projections', []))}")
    return parsed


async def _call_kimi_vision(chart_path: str, prompt: str, timeout: int = 60) -> str:
    """
    调用 Kimi CLI 分析图片。

    在 prompt 中直接引用图片文件路径，让 Kimi 读取。
    命令: kimi --print --quiet -p "{full_prompt}"

    注意:
        - timeout 设为 60 秒（Kimi 分析图片需要一定时间）
        - 使用 asyncio.to_thread 将 subprocess 转为异步
        - 如果命令失败，记录错误并返回空字符串
    """
    full_prompt = f"{prompt}\n\nChart image: {chart_path}"

    try:
        result = await asyncio.wait_for(
            asyncio.to_thread(
                subprocess.run,
                ["kimi", "--print", "--quiet", "-p", full_prompt],
                capture_output=True,
                text=True,
                timeout=timeout,
            ),
            timeout=timeout + 5,
        )
        if result.returncode != 0:
            logger.warning(f"[KimiVision] Kimi CLI error: {result.stderr}")
            return ""
        return result.stdout
    except asyncio.TimeoutError:
        logger.warning("[KimiVision] Kimi CLI analysis timed out")
        return ""
    except Exception as e:
        logger.warning(f"[KimiVision] Kimi CLI analysis failed: {e}")
        return ""


def _build_elliott_wave_prompt(
    symbol: str, timeframe: str, wave_candidate: Dict[str, Any]
) -> str:
    """构建用于 Elliott Wave 图表分析的英文 Kimi prompt。"""
    return f"""You are a professional Elliott Wave Theory analyst. Please analyze the {symbol} {timeframe} chart.

## CRITICAL: Trend Phase Analysis Required
You MUST analyze the chart by identifying **multiple trend phases** across the data range. The chart may contain several distinct directional moves — uptrends, downtrends, and consolidation periods.

- Identify and label each **trend phase separately** based on its direction:
  - An **uptrend segment** should be labeled with ascending impulse waves (1-2-3-4-5)
  - A **downtrend segment** should be labeled with descending corrective or impulse waves (A-B-C or 1-2-3-4-5)
  - A **sideways segment** should be labeled with corrective patterns (A-B-C, W-X-Y, or triangle)
- The `waves` array must include ALL waves from ALL phases, ordered chronologically by `start_idx`
- Example: If the left side shows an uptrend (1-2-3-4-5) and the right side shows a downtrend (A-B-C), `waves` should contain: 1, 2, 3, 4, 5, A, B, C in that order
- Do NOT label tiny sub-waves or micro-movements as the primary wave count — those belong in the `sub_waves` array only
- Do NOT force a single 1-2-3-4-5 structure across the entire chart if the price action clearly changes direction mid-way
- Focus on the **major, identifiable trend phases** rather than minor fluctuations or noise

## Global Perspective Analysis
You MUST analyze the chart from a MACRO to MICRO perspective:

1. **Primary Trend Identification**: First determine the overall direction of the entire chart range. Is it an uptrend, downtrend, or range-bound?
2. **Key Levels**: Identify and annotate major support and resistance levels visible across the full chart
3. **Trend Channels**: Draw trendlines connecting major pivot highs and lows to establish trend channels
4. **Wave Hierarchy**: Start with the largest identifiable wave structure, then break down into smaller sub-waves
5. **Do NOT focus only on recent candles** — analyze the complete chart from left (oldest) to right (most recent)

The `projections` MUST include specific `support_levels` and `resistance_levels` derived from the wave structure and key chart levels.

Note: The chart uses logarithmic price scale. This makes percentage moves visually equal regardless of price level, which helps identify wave proportion relationships.

The chart shows raw candlestick data WITHOUT any pre-labeled waves. Please analyze the chart and identify the Elliott Wave structure yourself.

Please return your analysis in the following JSON format inside a markdown code block:

```json
{{
  "wave_pattern": "Impulse 1-2-3-4-5 + Corrective A-B-C",
  "direction": "mixed",
  "current_wave": "Wave C extending",
  "waves": [
    {{"label": "1", "start_idx": 10, "end_idx": 35, "start_price": 45000, "end_price": 52000, "type": "impulse"}},
    {{"label": "2", "start_idx": 35, "end_idx": 48, "start_price": 52000, "end_price": 48000, "type": "corrective"}},
    {{"label": "3", "start_idx": 48, "end_idx": 92, "start_price": 48000, "end_price": 68000, "type": "impulse"}},
    {{"label": "4", "start_idx": 92, "end_idx": 110, "start_price": 68000, "end_price": 62000, "type": "corrective"}},
    {{"label": "5", "start_idx": 110, "end_idx": 145, "start_price": 62000, "end_price": 75000, "type": "impulse"}},
    {{"label": "A", "start_idx": 145, "end_idx": 165, "start_price": 75000, "end_price": 68000, "type": "corrective"}},
    {{"label": "B", "start_idx": 165, "end_idx": 180, "start_price": 68000, "end_price": 72000, "type": "corrective"}},
    {{"label": "C", "start_idx": 180, "end_idx": 210, "start_price": 72000, "end_price": 60000, "type": "corrective"}}
  ],
  "sub_waves": [
    {{"label": "(i)", "start_idx": 48, "end_idx": 58, "parent_wave": "3"}},
    {{"label": "(ii)", "start_idx": 58, "end_idx": 65, "parent_wave": "3"}}
  ],
  "projections": [
    {{
      "scenario": "bullish",
      "description": "Wave C completes at 0.618 of Wave A, new impulse begins",
      "target_price": 78000,
      "confidence": 0.40,
      "trigger_condition": "Price holds above 68000 with volume expansion",
      "time_horizon": {{"short_term": "1-3 days", "medium_term": "1-2 weeks", "long_term": "1-3 months"}},
      "support_levels": [68000, 65000, 62000],
      "resistance_levels": [75000, 78000, 82000],
      "stop_loss": 64000
    }},
    {{
      "scenario": "bearish",
      "description": "Wave C extends to 1.618 of Wave A, deeper correction",
      "target_price": 58000,
      "confidence": 0.35,
      "trigger_condition": "Break below 65000 on strong volume",
      "time_horizon": {{"short_term": "1-3 days", "medium_term": "1-2 weeks", "long_term": "1-3 months"}},
      "support_levels": [62000, 58000, 55000],
      "resistance_levels": [65000, 68000, 72000],
      "stop_loss": 70000
    }},
    {{
      "scenario": "neutral",
      "description": "Sideways consolidation in a contracting triangle",
      "target_price": 65000,
      "confidence": 0.25,
      "trigger_condition": "Price stays within 62000-72000 range for 5+ candles",
      "time_horizon": {{"short_term": "1-3 days", "medium_term": "1-2 weeks", "long_term": "1-3 months"}},
      "support_levels": [62000, 60000],
      "resistance_levels": [72000, 75000],
      "stop_loss": 58000
    }}
  ],
  "annotations": "Left phase: Wave 3 is the longest and strongest, typical of a healthy impulse. Wave 4 correction is shallow and does not overlap Wave 1. Right phase: A-B-C corrective pattern following the completion of Wave 5.",
  "overall_confidence": 0.68
}}
```

### Additional Pattern Examples

**Double ZigZag (W-X-Y) Example:**
```json
{{
  "wave_pattern": "Double ZigZag W-X-Y",
  "direction": "down",
  "current_wave": "Wave Y extending",
  "waves": [
    {{"label": "W", "start_idx": 20, "end_idx": 55, "start_price": 75000, "end_price": 62000, "type": "corrective"}},
    {{"label": "X", "start_idx": 55, "end_idx": 78, "start_price": 62000, "end_price": 68000, "type": "corrective"}},
    {{"label": "Y", "start_idx": 78, "end_idx": 120, "start_price": 68000, "end_price": 52000, "type": "corrective"}}
  ],
  "sub_waves": [
    {{"label": "(a)", "start_idx": 20, "end_idx": 35, "parent_wave": "W"}},
    {{"label": "(b)", "start_idx": 35, "end_idx": 45, "parent_wave": "W"}},
    {{"label": "(c)", "start_idx": 45, "end_idx": 55, "parent_wave": "W"}}
  ],
  "projections": [
    {{
      "scenario": "bullish",
      "description": "Double ZigZag completes at 52000, new impulse begins",
      "target_price": 80000,
      "confidence": 0.45,
      "trigger_condition": "Price holds above 52000 with volume expansion",
      "time_horizon": {{"short_term": "1-3 days", "medium_term": "1-2 weeks", "long_term": "1-3 months"}},
      "support_levels": [52000, 50000, 48000],
      "resistance_levels": [68000, 75000, 80000],
      "stop_loss": 48000
    }},
    {{
      "scenario": "bearish",
      "description": "Y wave extends further, deeper correction to 45000",
      "target_price": 45000,
      "confidence": 0.35,
      "trigger_condition": "Break below 52000 on strong volume",
      "time_horizon": {{"short_term": "1-3 days", "medium_term": "1-2 weeks", "long_term": "1-3 months"}},
      "support_levels": [50000, 48000, 45000],
      "resistance_levels": [55000, 62000, 68000],
      "stop_loss": 70000
    }},
    {{
      "scenario": "neutral",
      "description": "Sideways consolidation after Double ZigZag completion",
      "target_price": 58000,
      "confidence": 0.20,
      "trigger_condition": "Price stays within 52000-62000 range for 5+ candles",
      "time_horizon": {{"short_term": "1-3 days", "medium_term": "1-2 weeks", "long_term": "1-3 months"}},
      "support_levels": [52000, 50000],
      "resistance_levels": [62000, 68000],
      "stop_loss": 48000
    }}
  ],
  "annotations": "Double ZigZag pattern: W is a sharp 5-3-5 decline, X retraces about 50% of W, Y extends the correction. The entire W-X-Y structure is a complex correction against the prior uptrend.",
  "overall_confidence": 0.62
}}
```

**Triangle (A-B-C-D-E) Example:**
```json
{{
  "wave_pattern": "Contracting Triangle A-B-C-D-E",
  "direction": "sideways",
  "current_wave": "Wave E forming",
  "waves": [
    {{"label": "A", "start_idx": 50, "end_idx": 70, "start_price": 70000, "end_price": 65000, "type": "corrective"}},
    {{"label": "B", "start_idx": 70, "end_idx": 88, "start_price": 65000, "end_price": 68000, "type": "corrective"}},
    {{"label": "C", "start_idx": 88, "end_idx": 105, "start_price": 68000, "end_price": 62000, "type": "corrective"}},
    {{"label": "D", "start_idx": 105, "end_idx": 122, "start_price": 62000, "end_price": 66000, "type": "corrective"}},
    {{"label": "E", "start_idx": 122, "end_idx": 140, "start_price": 66000, "end_price": 63500, "type": "corrective"}}
  ],
  "sub_waves": [],
  "projections": [
    {{
      "scenario": "bullish",
      "description": "Triangle completes at E, breakout to the upside resumes trend",
      "target_price": 78000,
      "confidence": 0.50,
      "trigger_condition": "Break above 68000 with volume expansion",
      "time_horizon": {{"short_term": "1-3 days", "medium_term": "1-2 weeks", "long_term": "1-3 months"}},
      "support_levels": [62000, 60000, 58000],
      "resistance_levels": [68000, 72000, 78000],
      "stop_loss": 60000
    }},
    {{
      "scenario": "bearish",
      "description": "Triangle breaks down, continuation of prior downtrend",
      "target_price": 55000,
      "confidence": 0.30,
      "trigger_condition": "Break below 62000 on strong volume",
      "time_horizon": {{"short_term": "1-3 days", "medium_term": "1-2 weeks", "long_term": "1-3 months"}},
      "support_levels": [60000, 58000, 55000],
      "resistance_levels": [65000, 68000, 70000],
      "stop_loss": 70000
    }},
    {{
      "scenario": "neutral",
      "description": "Triangle extends or converts into complex correction",
      "target_price": 65000,
      "confidence": 0.20,
      "trigger_condition": "Price stays within 62000-68000 range for 5+ candles",
      "time_horizon": {{"short_term": "1-3 days", "medium_term": "1-2 weeks", "long_term": "1-3 months"}},
      "support_levels": [62000, 60000],
      "resistance_levels": [68000, 70000],
      "stop_loss": 58000
    }}
  ],
  "annotations": "Contracting Triangle: Each wave (A-B-C-D-E) is a 3-wave structure. Successive waves get shorter — A is longest, E is shortest. The pattern indicates consolidation before trend continuation. Watch for breakout direction.",
  "overall_confidence": 0.58
}}
```

Important notes:
- The `waves` array must include ALL waves you identify, with exact start_idx and end_idx from the chart
- Each wave MUST include: label, start_idx, end_idx, start_price, end_price, type
- start_idx and end_idx are 0-based candle indices from left to right
- start_price and end_price are the actual prices at the start and end candle of each wave
- Labels can be: 1,2,3,4,5 (impulse), A,B,C (corrective), W,X,Y (double zigzag), (i),(ii),(iii),(iv),(v) (sub-waves)
- The projections confidence values MUST sum to 1.0 (100%)
- Be precise with indices and prices - I will use your wave structure to re-annotate the chart

Algorithm preliminary result (for reference only):
- Wave Pattern: {wave_candidate.get('wave_pattern', 'N/A')}
- Current Wave: {wave_candidate.get('current_wave', 'N/A')}
- Direction: {wave_candidate.get('direction', 'N/A')}
- Algorithm Score: {wave_candidate.get('score', 0):.0%}
- Current Wave Probabilities: {wave_candidate.get('current_wave_probabilities', {})}
- ZigZag Pivots: {wave_candidate.get('zigzag_pivots', [])}

## Elliott Wave Pattern Diversity
The chart may contain any of the following wave structures. Identify the one that best fits the price action:

### Impulse Waves
- **Standard Impulse (1-2-3-4-5)**: Five-wave move in the direction of the larger trend
  - Wave 3 can NEVER be the shortest among waves 1, 3, 5
  - Wave 4 must NOT overlap Wave 1's price zone (except slight overlap in leverage/futures markets)
- **Leading Diagonal**: 5-3-5-3-5 pattern at wave 1 or A positions
- **Ending Diagonal**: 3-3-3-3-3 pattern at wave 5 or C positions

### Simple Corrective Patterns
- **ZigZag (A-B-C, 5-3-5)**: Sharp correction against the trend
  - Wave A must be a 5-wave impulse, Wave B is a 3-wave correction retracing 38.2%-78.6% of A, Wave C is a 5-wave impulse
- **Flat (A-B-C, 3-3-5)**: Sideways correction
  - Wave A is a 3-wave, Wave B retraces 90%-105% of A (often near or beyond A's start), Wave C is a 5-wave
- **Triangle (A-B-C-D-E, 3-3-3-3-3)**: Contracting or expanding; indicates consolidation before trend continuation
  - Each of A-B-C-D-E must be a 3-wave structure. In a Contracting Triangle, each successive wave is shorter. In an Expanding Triangle, each successive wave is longer

### Complex Corrective Patterns
- **Double ZigZag (W-X-Y)**: Two ZigZag patterns connected by an X-wave (5-3-5-X-5-3-5)
  - W and Y are each 5-3-5 ZigZags. X is a 3-wave corrective connector
- **Triple ZigZag (W-X-Y-X-Z)**: Three ZigZag patterns connected by X-waves
- **Double Three / Triple Three**: Combination of different corrective types (e.g., Flat + Triangle)

### Combination Patterns
- **Platform + Triangle**: Flat correction followed by a triangle
- **ZigZag + Platform**: ZigZag followed by a flat/expanded flat
- Always label intermediate joining waves as X (or X, Y for triples)

## Strict Elliott Wave Rules (you MUST follow):
1. In an Impulse wave (1-2-3-4-5), Wave 3 can NEVER be the shortest among waves 1, 3, 5
2. Wave 4's price zone must NOT overlap Wave 1's price zone (except in leverage/futures markets where slight overlap is allowed)
3. Wave 2 typically retraces 38.2%-61.8% of Wave 1
4. Wave 3 is typically 1.618× the length of Wave 1 (extension)
5. Wave 5 is typically 0.618-1.0× Wave 1, or equal to Wave 1
6. In a Corrective wave (A-B-C), Wave B should not exceed the start of Wave A
7. Wave C is typically 0.618-1.618× Wave A
8. In a Triangle, each sub-wave (A,B,C,D,E) must be a 3-wave structure
9. In a Double/Triple ZigZag, the X-wave is a corrective connector and should NOT exceed the previous corrective pattern

## Current Wave Probability Analysis:
You MUST estimate the probability of which wave the market is currently in.
Format your response as:
- Current Wave (Most Likely): [wave name] — [probability]%
- Alternative 1: [wave name] — [probability]%
- Alternative 2: [wave name] — [probability]%

## ZigZag Reference (Auxiliary Only):
The chart may show pre-marked ZigZag pivot points (blue dashed lines). These are **algorithm-generated reference points ONLY** and serve as an auxiliary guide.

- You MUST make **independent judgments** on trend turning points — do NOT rely entirely on ZigZag pivots
- ZigZag with deviation=0.10 may **miss smaller-level turning points** or **mistake noise for significant pivots**
- Base your wave identification on **price patterns, volume structure, and time cycles** in addition to ZigZag
- If a ZigZag pivot **contradicts strict Elliott Wave rules**, the rules take precedence — override the pivot
- ZigZag works best for identifying major highs and lows; sub-wave pivots often require manual judgment

## Fundamental Analysis Integration:
If you have knowledge of the underlying fundamentals for {symbol}, please incorporate that into your analysis:

- Consider macro events, sector trends, on-chain data (for crypto), earnings (for equities), or policy changes that may influence price direction
- When fundamental outlook **aligns** with your Elliott Wave count, increase your `overall_confidence` accordingly
- When fundamentals **contradict** your wave count, lower confidence and explain the divergence in your `annotations`
- You may use SearchWeb to research the latest fundamentals if needed, but prioritize what is visible in the chart
- Example: If Wave 5 extension is identified but fundamentals show deteriorating demand, note this conflict and reduce bullish projection confidence
"""


def _parse_kimi_response(raw_text: str) -> Dict[str, Any]:
    """
    解析 Kimi 返回的自由文本，提取结构化数据。

    使用正则表达式提取:
        - Confirmed Wave Pattern
        - Corrections (列表)
        - Scenarios (bullish/bearish/neutral 的描述、目标价、置信度)
        - Key Fibonacci Levels
        - Overall Confidence

    如果解析失败，返回原始文本作为 raw_analysis，其他字段使用默认值。
    """
    result: Dict[str, Any] = {
        "confirmed_wave": "",
        "corrections": [],
        "projections": [],
        "key_fib_levels": [],
        "overall_confidence": 0.0,
        "raw_analysis": raw_text,
    }

    if not raw_text:
        return result

    # Extract confirmed wave pattern
    wave_match = re.search(
        r"\*\*Confirmed Wave Pattern\*\*[:\s]*(.+?)(?:\n\n|\n\*\*|$)",
        raw_text,
        re.IGNORECASE | re.DOTALL,
    )
    if wave_match:
        result["confirmed_wave"] = wave_match.group(1).strip()
    else:
        # Fallback without bold markers
        wave_match = re.search(
            r"Confirmed Wave Pattern[:\s]*(.+?)(?:\n\n|\n[A-Z]|$)",
            raw_text,
            re.IGNORECASE | re.DOTALL,
        )
        if wave_match:
            result["confirmed_wave"] = wave_match.group(1).strip()

    # Extract corrections
    corr_match = re.search(
        r"\*\*Corrections\*\*[:\s]*(.+?)(?:\n\n|\n\*\*|$)",
        raw_text,
        re.IGNORECASE | re.DOTALL,
    )
    if corr_match:
        corr_text = corr_match.group(1).strip()
        # Split by bullet points or newlines
        corrections = [
            line.strip("- *• ").strip()
            for line in corr_text.split("\n")
            if line.strip("- *• ").strip()
        ]
        result["corrections"] = corrections
    else:
        corr_match = re.search(
            r"Corrections[:\s]*(.+?)(?:\n\n|\n[A-Z]|$)",
            raw_text,
            re.IGNORECASE | re.DOTALL,
        )
        if corr_match:
            corr_text = corr_match.group(1).strip()
            corrections = [
                line.strip("- *• ").strip()
                for line in corr_text.split("\n")
                if line.strip("- *• ").strip()
            ]
            result["corrections"] = corrections

    # Extract scenarios
    scenarios = []
    scenario_keywords = [
        ("bullish", r"(?:Scenario\s*1|Bullish)"),
        ("bearish", r"(?:Scenario\s*2|Bearish)"),
        ("neutral", r"(?:Scenario\s*3|Neutral)"),
    ]

    for scenario_type, pattern in scenario_keywords:
        # Try **Scenario N (Type)** format first
        scen_match = re.search(
            rf"\*\*\s*{pattern}\s*\([^)]*\)\s*\*\*[:\s]*(.+?)(?=\n\*\*|\n\n|$)",
            raw_text,
            re.IGNORECASE | re.DOTALL,
        )
        if not scen_match:
            # Fallback without parentheses
            scen_match = re.search(
                rf"\*\*\s*{pattern}\s*\*\*[:\s]*(.+?)(?=\n\*\*|\n\n|$)",
                raw_text,
                re.IGNORECASE | re.DOTALL,
            )
        if not scen_match:
            # Fallback without bold markers — stop at known section headers
            section_headers = r"Scenario\s*\d|Key\s+Fibonacci|Overall\s+Confidence|Confirmed\s+Wave|Corrections"
            scen_match = re.search(
                rf"{pattern}\s*\([^)]*\)[:\s]*(.+?)(?={section_headers}|$)",
                raw_text,
                re.IGNORECASE | re.DOTALL,
            )

        if scen_match:
            scen_text = scen_match.group(1).strip()
            target = _extract_target_price(scen_text)
            confidence = _extract_confidence(scen_text)
            scenarios.append({
                "scenario": scenario_type,
                "description": scen_text[:300],
                "target_price": target,
                "confidence": confidence,
            })

    result["projections"] = scenarios

    # Extract key fibonacci levels
    fib_match = re.search(
        r"\*\*Key Fibonacci Levels\*\*[:\s]*(.+?)(?:\n\n|\n\*\*|$)",
        raw_text,
        re.IGNORECASE | re.DOTALL,
    )
    if fib_match:
        result["key_fib_levels"] = _extract_fib_levels(fib_match.group(1))
    else:
        fib_match = re.search(
            r"Key Fibonacci Levels[:\s]*(.+?)(?:\n\n|\n[A-Z]|$)",
            raw_text,
            re.IGNORECASE | re.DOTALL,
        )
        if fib_match:
            result["key_fib_levels"] = _extract_fib_levels(fib_match.group(1))

    # Extract overall confidence
    conf_match = re.search(
        r"\*\*Overall Confidence\*\*[:\s]*(.+?)(?:\n\n|$)",
        raw_text,
        re.IGNORECASE | re.DOTALL,
    )
    if conf_match:
        result["overall_confidence"] = _extract_confidence(conf_match.group(1))
    else:
        conf_match = re.search(
            r"Overall Confidence[:\s]*(.+?)(?:\n\n|$)",
            raw_text,
            re.IGNORECASE | re.DOTALL,
        )
        if conf_match:
            result["overall_confidence"] = _extract_confidence(conf_match.group(1))

    return result


def _extract_confidence(text: str) -> float:
    """从文本中提取置信度百分比 (如 '85%' -> 0.85)。"""
    if not text:
        return 0.0
    # Match patterns like 85%, 85.5%, 0.85, 85 percent
    match = re.search(r"(\d+(?:\.\d+)?)\s*%", text)
    if match:
        return min(float(match.group(1)) / 100.0, 1.0)
    # Match decimal patterns like 0.85 or 0.72
    match = re.search(r"\b(0\.\d+)\b", text)
    if match:
        return min(float(match.group(1)), 1.0)
    # Match plain number 0-100
    match = re.search(r"\b(\d{1,3})\b", text)
    if match:
        val = float(match.group(1))
        if val > 1.0:
            return min(val / 100.0, 1.0)
        return min(val, 1.0)
    return 0.0


def _normalize_confidences(projections: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """对scenario置信度做softmax归一化，确保和=1.0。"""
    if not projections:
        return projections

    confidences = [p.get("confidence", 0.0) for p in projections]
    # Softmax
    exp_vals = [math.exp(c) for c in confidences]
    sum_exp = sum(exp_vals)
    if sum_exp == 0:
        # 平均分配
        normalized = [1.0 / len(projections)] * len(projections)
    else:
        normalized = [e / sum_exp for e in exp_vals]

    for p, norm in zip(projections, normalized):
        p["confidence"] = round(norm, 4)

    return projections


def _parse_kimi_wave_structure(raw_text: str) -> Optional[Dict[str, Any]]:
    """从Kimi返回的文本中提取JSON浪型结构。"""
    if not raw_text:
        return None

    # Try to extract JSON from markdown code block
    json_match = re.search(r'```(?:json)?\s*\n(.*?)\n```', raw_text, re.DOTALL)
    if json_match:
        json_text = json_match.group(1)
    else:
        # Try to find JSON between braces
        brace_match = re.search(r'\{.*\}', raw_text, re.DOTALL)
        if brace_match:
            json_text = brace_match.group(0)
        else:
            return None

    try:
        structure = json.loads(json_text)
        # Validate required fields
        if "waves" in structure and isinstance(structure["waves"], list):
            return structure
        return None
    except (json.JSONDecodeError, Exception):
        return None


def _extract_target_price(text: str) -> Optional[float]:
    """从文本中提取目标价位 (如 '$75,000' -> 75000.0)。"""
    if not text:
        return None
    # First try 'Target: $X' pattern for precision
    match = re.search(r"Target[:\s]*[$]\s*([\d,]+(?:\.\d+)?)", text, re.IGNORECASE)
    if match:
        return float(match.group(1).replace(",", ""))
    # Then try any dollar amount
    match = re.search(r"[$]\s*([\d,]+(?:\.\d+)?)", text)
    if match:
        return float(match.group(1).replace(",", ""))
    # Then try number followed by USD
    match = re.search(r"([\d,]+(?:\.\d+)?)\s*USD", text, re.IGNORECASE)
    if match:
        return float(match.group(1).replace(",", ""))
    return None


def _extract_fib_levels(text: str) -> List[float]:
    """从文本中提取斐波那契水平 (如 '0.382, 0.5, 0.618' -> [0.382, 0.5, 0.618])。"""
    if not text:
        return []
    levels: List[float] = []
    # Match patterns like 0.382, 0.5, 0.618, 1.0, 1.618, 2.618
    found = re.findall(r"\b(\d+(?:\.\d+)?)\b", text)
    for num_str in found:
        try:
            val = float(num_str)
            # Filter to reasonable fib levels
            if 0.0 < val <= 5.0:
                levels.append(val)
        except ValueError:
            continue
    return levels


def _extract_current_wave_probabilities(raw_text: str) -> Dict[str, float]:
    """从 Kimi 返回文本中提取当前浪概率分布。"""
    probabilities = {}

    # 匹配格式："Current Wave (Most Likely): Wave 5 — 65%"
    patterns = [
        r"Current Wave \(Most Likely\):?\s*([\w\s_\-()]+)[—\-:]\s*(\d+(?:\.\d+)?)\s*%?",
        r"Alternative \d+:?\s*([\w\s_\-()]+)[—\-:]\s*(\d+(?:\.\d+)?)\s*%?",
        r"([\w\s_\-()]+):?\s*(\d+(?:\.\d+)?)\s*%\s*\(?(?:probability|likely)\)?",
    ]

    for pattern in patterns:
        for match in re.finditer(pattern, raw_text, re.IGNORECASE):
            wave_name = match.group(1).strip().lower().replace(" ", "_")
            prob_value = float(match.group(2))
            if prob_value > 1:  # 如果是 0-100 的百分数
                prob_value /= 100.0
            probabilities[wave_name] = prob_value

    return probabilities
