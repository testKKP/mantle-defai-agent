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
    调用 Kimi CLI 分两轮分析艾略特波浪图表。

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
            "kimi_structure": {...},
        }
    """
    try:
        return await _analyze_elliott_wave_with_kimi_impl(chart_path, symbol, timeframe, wave_candidate)
    except Exception as e:
        logger.warning(f"[KimiVision] Unexpected error in analyze_elliott_wave_with_kimi: {e}")
        return {"error": f"analysis_failed: {e}"}


async def _analyze_elliott_wave_with_kimi_impl(
    chart_path: str,
    symbol: str,
    timeframe: str,
    wave_candidate: Dict[str, Any],
) -> Dict[str, Any]:
    """Internal implementation of two-phase Elliott Wave analysis with text fallback."""
    # Phase 1: identify corrective patterns first
    prompt1 = _build_elliott_wave_phase1_prompt(symbol, timeframe, wave_candidate)
    raw_text1 = await _call_kimi_vision(chart_path, prompt1, timeout=220)

    phase1_structure = None

    if not raw_text1:
        logger.warning("[KimiVision] Phase 1 empty/timeout, trying text fallback")
        fallback = await _fallback_text_verification(symbol, timeframe, wave_candidate)
        if fallback:
            return fallback
        return {"error": "phase1_failed"}

    phase1_structure = _parse_kimi_wave_structure(raw_text1)
    if not phase1_structure:
        logger.warning("[KimiVision] Phase 1 failed to parse valid structure, trying text fallback")
        fallback = await _fallback_text_verification(symbol, timeframe, wave_candidate)
        if fallback:
            return fallback
        return {"error": "phase1_failed"}

    adjustments = phase1_structure.get("adjustments")
    if not isinstance(adjustments, list) or len(adjustments) == 0:
        logger.warning("[KimiVision] Phase 1 missing adjustments array, trying text fallback")
        fallback = await _fallback_text_verification(symbol, timeframe, wave_candidate)
        if fallback:
            return fallback
        return {"error": "phase1_failed"}

    # Phase 2: detailed structure based on Phase 1
    prompt2 = _build_elliott_wave_phase2_prompt(symbol, timeframe, wave_candidate, phase1_structure)
    raw_text2 = await _call_kimi_vision(chart_path, prompt2, timeout=120)

    if not raw_text2:
        logger.warning("[KimiVision] Phase 2 empty/timeout, trying text fallback")
        fallback = await _fallback_text_verification(symbol, timeframe, wave_candidate)
        if fallback:
            return fallback
        return {"error": "phase2_failed"}

    phase2_structure = _parse_kimi_wave_structure(raw_text2)
    if not phase2_structure or not phase2_structure.get("waves"):
        logger.warning("[KimiVision] Phase 2 failed to parse valid structure, trying text fallback")
        fallback = await _fallback_text_verification(symbol, timeframe, wave_candidate)
        if fallback:
            return fallback
        return {"error": "phase2_failed"}

    # Merge phase1 + phase2
    merged = dict(phase1_structure)
    if phase2_structure:
        if phase2_structure.get("waves"):
            merged["waves"] = phase2_structure["waves"]
        if phase2_structure.get("sub_waves"):
            merged["sub_waves"] = phase2_structure["sub_waves"]
        if phase2_structure.get("projections"):
            merged["projections"] = phase2_structure["projections"]
        # If phase2 provides annotations, override phase1's
        if phase2_structure.get("annotations"):
            merged["annotations"] = phase2_structure["annotations"]

    # Continue with existing logic to build parsed result
    parsed = _parse_kimi_response(raw_text1)
    parsed["kimi_structure"] = merged

    # Populate projections from merged structure if available
    if merged.get("projections"):
        parsed["projections"] = merged["projections"]

    # Set confirmed wave from merged structure
    if merged.get("waves"):
        parsed["confirmed_wave"] = f"{merged.get('wave_pattern', '')} - Currently in {merged.get('current_wave', '')}"

    # Extract current wave probabilities from Kimi's response
    parsed["current_wave_probabilities"] = _extract_current_wave_probabilities(raw_text1)

    # Normalize confidences
    if parsed.get("projections"):
        parsed["projections"] = _normalize_confidences(parsed["projections"])

    logger.info(f"[KimiVision] Parsed analysis for {symbol} {timeframe}: "
                f"confidence={parsed.get('overall_confidence', 0):.2f}, "
                f"projections={len(parsed.get('projections', []))}")
    return parsed


def _build_parsed_from_fallback(structure: Dict[str, Any], symbol: str, timeframe: str) -> Dict[str, Any]:
    """Build the final parsed result dict from a fallback wave structure."""
    parsed = {
        "confirmed_wave": f"{structure.get('wave_pattern', '')} - Currently in {structure.get('current_wave', '')}",
        "corrections": [],
        "projections": structure.get("projections", []),
        "key_fib_levels": [],
        "overall_confidence": structure.get("overall_confidence", 0.0),
        "raw_analysis": "[fallback] Text-only review of algorithm wave candidate",
        "kimi_structure": structure,
        "fallback": True,
    }

    if parsed.get("projections"):
        parsed["projections"] = _normalize_confidences(parsed["projections"])

    logger.info(f"[KimiVision] Fallback analysis for {symbol} {timeframe}: "
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
            stdout_preview = result.stdout[:500].replace('\n', ' ') if result.stdout else "(empty)"
            stderr_preview = result.stderr[:500].replace('\n', ' ') if result.stderr else "(empty)"
            logger.warning(
                f"[KimiVision] Kimi CLI error (rc={result.returncode}): "
                f"stderr={stderr_preview}, stdout_preview={stdout_preview}"
            )
            # If stdout contains a JSON block despite non-zero exit, try to use it.
            if result.stdout and "```json" in result.stdout:
                return result.stdout
            return ""
        return result.stdout
    except asyncio.TimeoutError:
        logger.warning("[KimiVision] Kimi CLI analysis timed out")
        return ""
    except Exception as e:
        logger.warning(f"[KimiVision] Kimi CLI analysis failed: {e}")
        return ""


def _serialize_candidate_waves(waves: List[Any]) -> str:
    """Serialize waves for text prompt; tolerate both dict and tuple/list entries."""
    serialized: List[Any] = []
    for w in waves:
        if isinstance(w, dict):
            serialized.append(w)
        elif isinstance(w, (tuple, list)) and len(w) >= 6:
            # Best-effort mapping of tuple/list to labelled wave object.
            serialized.append({
                "label": w[0],
                "start_idx": w[1],
                "end_idx": w[2],
                "start_price": w[3],
                "end_price": w[4],
                "type": w[5],
            })
        elif isinstance(w, (tuple, list)):
            serialized.append(list(w))
        else:
            serialized.append(w)
    return json.dumps(serialized, ensure_ascii=False)


def _build_fallback_verification_prompt(symbol: str, timeframe: str, wave_candidate: Dict[str, Any]) -> str:
    """Build a text-only prompt asking Kimi to verify/fix the algorithm wave candidate."""
    waves = wave_candidate.get("waves", [])
    projections = wave_candidate.get("projections", [])
    # Keep prompt compact so the 15s text fallback can reliably return.
    max_waves = 6
    if len(waves) > max_waves:
        displayed_waves = waves[-max_waves:]
        waves_note = f" (showing last {max_waves} of {len(waves)} waves for brevity)"
    else:
        displayed_waves = waves
        waves_note = ""
    return f"""You are an Elliott Wave expert. The algorithm generated the following candidate for {symbol} {timeframe}:

Algorithm candidate:
- Pattern: {wave_candidate.get('wave_pattern', 'N/A')}
- Direction: {wave_candidate.get('direction', 'N/A')}
- Current wave: {wave_candidate.get('current_wave', 'N/A')}
- Score: {wave_candidate.get('score', 0):.0%}
- Waves{waves_note}: {_serialize_candidate_waves(displayed_waves)}
- Projections: {json.dumps(projections, ensure_ascii=False)}

Please review and fix any obvious errors. Return ONLY a JSON object in a markdown code block:

```json
{{
  "wave_pattern": "...",
  "direction": "up|down",
  "current_wave": "...",
  "waves": [
    {{"label": "1", "start_idx": ..., "end_idx": ..., "start_price": ..., "end_price": ..., "type": "impulse|corrective"}}
  ],
  "projections": [
    {{"scenario": "bullish", "target_price": ..., "confidence": 0.4, "support_levels": [...], "resistance_levels": [...]}},
    {{"scenario": "bearish", "target_price": ..., "confidence": 0.35, "support_levels": [...], "resistance_levels": [...]}},
    {{"scenario": "neutral", "target_price": ..., "confidence": 0.25, "support_levels": [...], "resistance_levels": [...]}}
  ],
  "annotations": "brief expert comment",
  "likely_next_move": "...",
  "overall_confidence": 0.65
}}
```

Rules:
- Keep the same wave labels and indices if they are reasonable
- Fix only obvious violations of Elliott Wave rules
- Projections confidence must sum to 1.0
- Keep annotations under 50 words
"""


async def _fallback_text_verification(
    symbol: str,
    timeframe: str,
    wave_candidate: Dict[str, Any],
    timeout: int = 15,
) -> Optional[Dict[str, Any]]:
    """When vision analysis fails, quickly verify/fix algorithm candidate via text-only Kimi prompt."""
    prompt = _build_fallback_verification_prompt(symbol, timeframe, wave_candidate)
    try:
        proc = await asyncio.create_subprocess_exec(
            "kimi", "--print", "--quiet", "--no-thinking", "-p", prompt,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
        raw_text = stdout.decode("utf-8", errors="replace")

        if proc.returncode != 0:
            stderr_preview = stderr.decode("utf-8", errors="replace")[:500].replace('\n', ' ')
            stdout_preview = raw_text[:500].replace('\n', ' ')
            logger.warning(
                f"[KimiVision] Text fallback CLI error (rc={proc.returncode}): "
                f"stderr={stderr_preview}, stdout_preview={stdout_preview}"
            )
            return None

        structure = _parse_kimi_wave_structure(raw_text)
        if not structure or len(structure.get("waves", [])) < 2:
            logger.warning("[KimiVision] Text fallback failed to return valid structure")
            return None

        parsed = {
            "confirmed_wave": f"{structure.get('wave_pattern', '')} - Currently in {structure.get('current_wave', '')}",
            "corrections": [],
            "projections": structure.get("projections", []),
            "key_fib_levels": [],
            "overall_confidence": structure.get("overall_confidence", 0.0),
            "raw_analysis": "[fallback] Text-only review of algorithm wave candidate",
            "kimi_structure": structure,
            "fallback": True,
        }

        if parsed.get("projections"):
            parsed["projections"] = _normalize_confidences(parsed["projections"])

        logger.info(f"[KimiVision] Fallback analysis for {symbol} {timeframe}: "
                    f"confidence={parsed.get('overall_confidence', 0):.2f}, "
                    f"projections={len(parsed.get('projections', []))}")
        return parsed
    except asyncio.TimeoutError:
        logger.warning(f"[KimiVision] Text fallback timed out after {timeout}s")
        return None
    except Exception as e:
        logger.warning(f"[KimiVision] Text fallback failed: {e}")
        return None


def _build_text_fallback_prompt(symbol: str, timeframe: str, wave_candidate: Dict[str, Any]) -> str:
    """Build a text-only prompt for Kimi to review and refine algorithm wave candidate."""
    waves = wave_candidate.get("waves", [])
    wave_summary = _serialize_candidate_waves(waves[:12])

    pivots = wave_candidate.get("zigzag_pivots", [])
    pivot_summary = "\n".join(
        f"  {(p[2] if isinstance(p, tuple) else p.get('type', '?'))} @ idx "
        f"{(p[0] if isinstance(p, tuple) else p.get('idx', '?'))}: "
        f"{(p[1] if isinstance(p, tuple) else p.get('price', '?'))}"
        for p in pivots[:12]
    ) or "  (none)"

    return f"""You are an Elliott Wave analyst. The vision analysis timed out for {symbol} {timeframe}. Review the algorithm candidate below and return a corrected JSON wave structure.

Candidate:
- symbol: {symbol}
- timeframe: {timeframe}
- wave_pattern: {wave_candidate.get('wave_pattern', 'N/A')}
- direction: {wave_candidate.get('direction', 'N/A')}
- current_wave: {wave_candidate.get('current_wave', 'N/A')}
- score: {wave_candidate.get('score', 0):.0%}

Waves ({len(waves)}):
{wave_summary}

ZigZag Pivots ({len(pivots)}):
{pivot_summary}

Return ONLY a JSON markdown block with this structure:

```json
{{
  "wave_pattern": "Impulse 1-2-3-4-5 + Corrective A-B-C",
  "direction": "up",
  "current_wave": "Wave 5 extending",
  "waves": [
    {{"label": "1", "start_idx": 10, "end_idx": 35, "start_price": 45000, "end_price": 52000, "type": "impulse"}}
  ],
  "projections": [
    {{"scenario": "bullish", "description": "...", "target_price": 80000, "confidence": 0.4}},
    {{"scenario": "bearish", "description": "...", "target_price": 65000, "confidence": 0.35}},
    {{"scenario": "neutral", "description": "...", "target_price": 74000, "confidence": 0.25}}
  ],
  "annotations": "Reviewed via text fallback.",
  "likely_next_move": "...",
  "overall_confidence": 0.55
}}
```

Rules:
- Include every major wave in `waves`, ordered by start_idx.
- Each wave needs: label, start_idx, end_idx, start_price, end_price, type.
- Projections must include bullish, bearish, neutral with confidences summing to 1.0.
- Return only the JSON markdown block.
"""


async def _call_kimi_text_fallback(symbol: str, timeframe: str, wave_candidate: Dict[str, Any], timeout: int = 15) -> Optional[Dict[str, Any]]:
    """Call Kimi CLI without image, asking it to review algorithm wave candidate."""
    prompt = _build_text_fallback_prompt(symbol, timeframe, wave_candidate)
    try:
        proc = await asyncio.create_subprocess_exec(
            "kimi", "--print", "--quiet", "--no-thinking", "-p", prompt,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
        raw_text = stdout.decode("utf-8", errors="replace")

        if proc.returncode != 0:
            stderr_preview = stderr.decode("utf-8", errors="replace")[:500].replace('\n', ' ')
            stdout_preview = raw_text[:500].replace('\n', ' ')
            logger.warning(
                f"[KimiVision] Text fallback CLI error (rc={proc.returncode}): "
                f"stderr={stderr_preview}, stdout_preview={stdout_preview}"
            )
            return None

        structure = _parse_kimi_wave_structure(raw_text)
        if not structure:
            logger.warning("[KimiVision] Text fallback failed to return valid structure")
            return None
        return structure
    except asyncio.TimeoutError:
        logger.warning(f"[KimiVision] Text fallback timed out after {timeout}s")
        return None
    except Exception as e:
        logger.warning(f"[KimiVision] Text fallback failed: {e}")
        return None


async def analyze_elliott_wave_text_fallback(
    symbol: str,
    timeframe: str,
    wave_candidate: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Fast text-based fallback when Kimi vision Phase 1 times out.
    Sends the algorithm candidate as JSON and asks Kimi to review/fix/annotate.
    Returns a structure compatible with plot_kimi_annotated_wave.
    """
    phase1_structure = await _call_kimi_text_fallback(symbol, timeframe, wave_candidate, timeout=15)
    if not phase1_structure or len(phase1_structure.get("waves", [])) < 2:
        return {"error": "text_fallback_failed"}

    parsed = {
        "confirmed_wave": f"{phase1_structure.get('wave_pattern', '')} - Currently in {phase1_structure.get('current_wave', '')}",
        "corrections": [],
        "projections": phase1_structure.get("projections", []),
        "key_fib_levels": [],
        "overall_confidence": phase1_structure.get("overall_confidence", 0.0),
        "raw_analysis": "[fallback] Text-only review of algorithm wave candidate",
        "kimi_structure": phase1_structure,
        "fallback": True,
    }

    if parsed.get("projections"):
        parsed["projections"] = _normalize_confidences(parsed["projections"])

    logger.info(f"[KimiVision] Public text fallback for {symbol} {timeframe}: "
                f"confidence={parsed.get('overall_confidence', 0):.2f}, "
                f"projections={len(parsed.get('projections', []))}")
    return parsed


async def analyze_elliott_wave_text_only(
    candidate: Dict[str, Any],
    symbol: str,
    timeframe: str,
    timeout: int = 60,
) -> Dict[str, Any]:
    """
    Fast text-only Elliott Wave analysis for altcoins.

    Sends the algorithm-generated wave candidate as structured JSON to Kimi
    without any chart image. Kimi validates the structure, corrects rule
    violations, and returns a refined wave structure that can be plotted
    with `plot_kimi_annotated_wave`.

    Args:
        candidate: Highest-score algorithm candidate dict.
        symbol: Token symbol, e.g. "SOL".
        timeframe: Timeframe, e.g. "1d".
        timeout: Kimi CLI timeout in seconds (default 60).

    Returns:
        Dict with the same format as `analyze_elliott_wave_with_kimi()`.
    """
    try:
        return await _analyze_elliott_wave_text_only_impl(candidate, symbol, timeframe, timeout)
    except Exception as e:
        logger.warning(f"[KimiVision] Unexpected error in analyze_elliott_wave_text_only: {e}")
        return {"error": f"analysis_failed: {e}"}


async def _analyze_elliott_wave_text_only_impl(
    candidate: Dict[str, Any],
    symbol: str,
    timeframe: str,
    timeout: int,
) -> Dict[str, Any]:
    """Internal implementation of the fast text-only Elliott Wave analysis."""
    prompt = _build_elliott_wave_text_only_prompt(symbol, timeframe, candidate)
    raw_text = await _call_kimi_text(prompt, timeout=timeout)

    if not raw_text:
        logger.warning("[KimiVision] Text-only analysis returned empty/timeout")
        return {"error": "text_analysis_empty"}

    structure = _parse_kimi_wave_structure(raw_text)
    if not structure or len(structure.get("waves", [])) < 2:
        logger.warning("[KimiVision] Text-only analysis failed to parse valid structure")
        return {"error": "text_analysis_parse_failed"}

    parsed = _parse_kimi_response(raw_text)
    parsed["kimi_structure"] = structure

    if structure.get("projections"):
        parsed["projections"] = structure["projections"]

    if structure.get("waves"):
        parsed["confirmed_wave"] = (
            f"{structure.get('wave_pattern', '')} - Currently in {structure.get('current_wave', '')}"
        )

    parsed["current_wave_probabilities"] = _extract_current_wave_probabilities(raw_text)

    if parsed.get("projections"):
        parsed["projections"] = _normalize_confidences(parsed["projections"])

    overall_confidence = structure.get("overall_confidence", parsed.get("overall_confidence", 0.0))
    parsed["overall_confidence"] = overall_confidence
    parsed["kimi_structure"]["overall_confidence"] = overall_confidence

    logger.info(f"[KimiVision] Text-only analysis for {symbol} {timeframe}: "
                f"confidence={parsed.get('overall_confidence', 0):.2f}, "
                f"waves={len(structure.get('waves', []))}, "
                f"projections={len(parsed.get('projections', []))}")
    return parsed


def _build_elliott_wave_text_only_prompt(
    symbol: str, timeframe: str, candidate: Dict[str, Any]
) -> str:
    """Build a compact text-only prompt for fast Elliott Wave review."""
    waves = candidate.get("waves", [])
    projections = candidate.get("projections", [])
    probabilities = candidate.get("current_wave_probabilities", {})

    # Keep prompt compact for fast response (30-60s).
    max_waves = 8
    if len(waves) > max_waves:
        displayed_waves = waves[-max_waves:]
        waves_note = f" (showing last {max_waves} of {len(waves)} waves)"
    else:
        displayed_waves = waves
        waves_note = ""

    return f"""You are an expert Elliott Wave analyst. Analyze the following {symbol}/{timeframe} wave structure generated by an algorithm.

Algorithm candidate:
- Pattern: {candidate.get('wave_pattern', 'N/A')}
- Direction: {candidate.get('direction', 'N/A')}
- Current Wave: {candidate.get('current_wave', 'N/A')}
- Score: {candidate.get('score', 0):.0%}
- Waves{waves_note}: {_serialize_candidate_waves(displayed_waves)}
- Projections: {json.dumps(projections, ensure_ascii=False)}
- Probabilities: {json.dumps(probabilities, ensure_ascii=False)}

Task:
1. Validate against Elliott Wave rules (Wave 3 not shortest among 1/3/5; Wave 4 price zone must not overlap Wave 1; Wave 2 typically 38.2%-61.8% of Wave 1; A-B-C corrections consistent).
2. Correct any invalid labels or indices if needed, but preserve the algorithm's structure when reasonable.
3. Provide a refined `waves` array covering the major waves, ordered by `start_idx`.
4. Provide `bullish`, `bearish`, and `neutral` projections with `confidence` values summing to exactly 1.0.
5. Explain the current situation in `annotations` and the likely next move in `likely_next_move`.

Return ONLY a JSON object in a markdown code block:

```json
{{
  "wave_pattern": "Impulse 1-2-3-4-5 + Corrective A-B-C",
  "direction": "up",
  "current_wave": "Wave 5 extending",
  "waves": [
    {{"label": "1", "start_idx": 10, "end_idx": 35, "start_price": 45000, "end_price": 52000, "type": "impulse"}},
    {{"label": "2", "start_idx": 35, "end_idx": 48, "start_price": 52000, "end_price": 48000, "type": "corrective"}},
    {{"label": "3", "start_idx": 48, "end_idx": 92, "start_price": 48000, "end_price": 68000, "type": "impulse"}},
    {{"label": "4", "start_idx": 92, "end_idx": 110, "start_price": 68000, "end_price": 62000, "type": "corrective"}},
    {{"label": "5", "start_idx": 110, "end_idx": 145, "start_price": 62000, "end_price": 75000, "type": "impulse"}}
  ],
  "sub_waves": [],
  "projections": [
    {{"scenario": "bullish", "description": "Wave 5 extension", "target_price": 80000, "confidence": 0.40, "support_levels": [72000, 70000], "resistance_levels": [80000, 83000]}},
    {{"scenario": "bearish", "description": "Start A-B-C correction", "target_price": 65000, "confidence": 0.35, "support_levels": [65000, 62000], "resistance_levels": [72000, 75000]}},
    {{"scenario": "neutral", "description": "Sideways consolidation", "target_price": 74000, "confidence": 0.25, "support_levels": [70000, 68000], "resistance_levels": [76000, 78000]}}
  ],
  "support_resistance_analysis": {{
    "key_support": 70000,
    "key_resistance": 76000,
    "support_tested": true,
    "support_held": true,
    "resistance_tested": false,
    "resistance_held": false,
    "breakout_direction": "up",
    "breakout_confirmed": false,
    "analysis": "Price tested 70000 support and held; now approaching 76000 resistance."
  }},
  "directional_bias": {{
    "primary_direction": "bullish",
    "primary_probability": 0.55,
    "secondary_direction": "bearish",
    "secondary_probability": 0.30,
    "neutral_probability": 0.15,
    "rationale": "Wave 5 extension suggests momentum, but approaching resistance."
  }},
  "annotations": "Brief expert comment on current wave structure.",
  "likely_next_move": "Likely continuation or correction based on current wave.",
  "overall_confidence": 0.72
}}
```

Rules:
- Each wave MUST include: label, start_idx, end_idx, start_price, end_price, type (impulse or corrective).
- `start_idx` and `end_idx` are 0-based candle indices from left to right.
- Keep only major waves in `waves`; tiny sub-waves go to `sub_waves` (optional).
- Projections MUST include bullish, bearish, neutral with confidences summing to 1.0.
- Each projection MUST include `support_levels` and `resistance_levels`.
- You MUST identify the nearest key support and resistance levels in `support_resistance_analysis`.
- You MUST analyze whether price has tested support/resistance and whether support held or resistance held.
- You MUST state whether a breakout/breakdown occurred or is forming, and the breakout direction.
- You MUST provide `directional_bias` with primary/secondary/neutral probabilities summing to 1.0.
- Do not output any text outside the JSON markdown code block.
"""


async def _call_kimi_text(prompt: str, timeout: int = 60) -> str:
    """Call Kimi CLI in text-only mode (no image)."""
    try:
        result = await asyncio.wait_for(
            asyncio.to_thread(
                subprocess.run,
                ["kimi", "--print", "--quiet", "--no-thinking", "-p", prompt],
                capture_output=True,
                text=True,
                timeout=timeout,
            ),
            timeout=timeout + 5,
        )
        if result.returncode != 0:
            stdout_preview = result.stdout[:500].replace('\n', ' ') if result.stdout else "(empty)"
            stderr_preview = result.stderr[:500].replace('\n', ' ') if result.stderr else "(empty)"
            logger.warning(
                f"[KimiVision] Kimi CLI text error (rc={result.returncode}): "
                f"stderr={stderr_preview}, stdout_preview={stdout_preview}"
            )
            if result.stdout and "```json" in result.stdout:
                return result.stdout
            return ""
        return result.stdout
    except asyncio.TimeoutError:
        logger.warning("[KimiVision] Kimi CLI text analysis timed out")
        return ""
    except Exception as e:
        logger.warning(f"[KimiVision] Kimi CLI text analysis failed: {e}")
        return ""


def _build_elliott_wave_prompt(
    symbol: str, timeframe: str, wave_candidate: Dict[str, Any]
) -> str:
    """构建用于 Elliott Wave 图表分析的英文 Kimi prompt。"""
    return f"""You are a professional Elliott Wave Theory analyst. Please analyze the {symbol} {timeframe} chart.

## CRITICAL: Adjustment-First Wave Counting
Analyze in this order:

1. **Identify corrective / consolidation patterns first**: box ranges, flats (A-B-C, 3-3-5), zigzags (A-B-C, 5-3-5), triangles (A-B-C-D-E), double zigzags (W-X-Y).
2. **For each corrective pattern, determine what it corrects** and use `adjustment_for` to describe the prior segment.
3. **Then identify impulse waves** (1-2-3-4-5) that connect these corrections. Labels 1-5 are impulse phases; A-C (or W-Y) are corrective phases.
4. **Classify the latest correction as Wave 2 or Wave B**: Wave 2 is a shallow retracement (38.2%-61.8%) of Wave 1 followed by Wave 3 in the same direction; Wave B is part of a larger A-B-C correction, often deeper/complex, followed by Wave C opposite to Wave A. Explain in `annotations` and `likely_next_move`.
5. **Infer the next major move** and reflect it in `direction`, `current_wave`, `projections`, and `annotations`.

The `waves` array must include ALL waves from ALL phases, ordered chronologically by `start_idx`. Do not label tiny sub-waves as primary waves — those belong in `sub_waves` only. Analyze from MACRO to MICRO: determine overall direction, identify major support/resistance, and establish trend channels across the full chart. The chart uses logarithmic price scale.

Please return your analysis in the following JSON format inside a markdown code block:

```json
{{
  "wave_pattern": "Impulse 1-2-3-4-5 + Corrective A-B-C",
  "direction": "mixed",
  "current_wave": "Wave C extending",
  "adjustment_context": "Latest correction (Wave C) is part of a larger A-B-C correction following the completion of Wave 5.",
  "likely_next_move": "If Wave C completes near 60000, expect a new impulse wave in the opposite direction of the prior A-B-C correction.",
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
      "support_levels": [68000, 65000, 62000],
      "resistance_levels": [75000, 78000, 82000]
    }},
    {{
      "scenario": "bearish",
      "description": "Wave C extends to 1.618 of Wave A",
      "target_price": 58000,
      "confidence": 0.35,
      "support_levels": [62000, 58000, 55000],
      "resistance_levels": [70000, 75000, 78000]
    }},
    {{
      "scenario": "neutral",
      "description": "Sideways consolidation in a triangle",
      "target_price": 68000,
      "confidence": 0.25,
      "support_levels": [65000, 62000],
      "resistance_levels": [72000, 75000]
    }}
  ],
  "support_resistance_analysis": {{
    "key_support": 65000,
    "key_resistance": 75000,
    "support_tested": true,
    "support_held": true,
    "resistance_tested": false,
    "resistance_held": false,
    "breakout_direction": "up",
    "breakout_confirmed": false,
    "analysis": "Price tested 65000 support twice and held, now approaching 75000 resistance."
  }},
  "directional_bias": {{
    "primary_direction": "bullish",
    "primary_probability": 0.55,
    "secondary_direction": "bearish",
    "secondary_probability": 0.30,
    "neutral_probability": 0.15,
    "rationale": "Wave 5 extension suggests momentum, but approaching resistance."
  }},
  "annotations": "Left phase: Wave 3 is the longest and strongest, typical of a healthy impulse. Wave 4 correction is shallow and does not overlap Wave 1. Right phase: A-B-C corrective pattern following the completion of Wave 5.",
  "overall_confidence": 0.68
}}
```

You MUST also provide:
1. **Key support and resistance levels**: Identify the nearest key support and resistance from the visible price action.
2. **Support/resistance test analysis**: State whether price has tested support or resistance, whether support held or resistance held, and whether a breakout/breakdown is occurring or forming.
3. **Directional bias with probabilities**: Provide primary (bullish/bearish) direction with probability, plus secondary and neutral probabilities that sum to 1.0.
4. **Target prices** in projections should respect support/resistance levels.

Important notes:
- The `waves` array must include ALL waves you identify, with exact start_idx and end_idx from the chart
- Each wave MUST include: label, start_idx, end_idx, start_price, end_price, type
- Optional wave fields: wave_role, adjustment_for, parent_segment, retracement_ratio, description
- start_idx and end_idx are 0-based candle indices from left to right
- start_price and end_price are the actual prices at the start and end candle of each wave
- Labels can be: 1,2,3,4,5 (impulse), A,B,C (corrective), W,X,Y (double zigzag), (i),(ii),(iii),(iv),(v) (sub-waves)
- Projections MUST include bullish, bearish, neutral scenarios with confidences summing to 1.0
- Optional top-level fields: adjustment_context, likely_next_move
- Be precise with indices and prices - I will use your wave structure to re-annotate the chart

Algorithm preliminary result (for reference only):
- Wave Pattern: {wave_candidate.get('wave_pattern', 'N/A')}
- Current Wave: {wave_candidate.get('current_wave', 'N/A')}
- Direction: {wave_candidate.get('direction', 'N/A')}
- Algorithm Score: {wave_candidate.get('score', 0):.0%}

## Common Patterns
- **Impulse (1-2-3-4-5)**: Wave 3 not shortest; Wave 4 not overlap Wave 1
- **ZigZag (A-B-C)**: Sharp 5-3-5 correction
- **Flat (A-B-C)**: Sideways 3-3-5 correction
- **Triangle (A-B-C-D-E)**: Consolidation, each sub-wave 3-wave
- **Double ZigZag (W-X-Y)**: Two ZigZags connected by X

### Distinguishing Wave 2 vs Wave B
- **Wave 2**: Within 1-2-3-4-5 impulse; retraces 38.2%-61.8% of Wave 1; not >100% of Wave 1; followed by Wave 3 in same direction as Wave 1; simpler structure.
- **Wave B**: Within A-B-C correction; can retrace 38.2%-138.2% of Wave A; often complex/time-consuming; followed by Wave C opposite to Wave A.
- Use `wave_role` field to capture this classification.

## Strict Elliott Wave Rules (you MUST follow):
1. In an Impulse wave (1-2-3-4-5), Wave 3 can NEVER be the shortest among waves 1, 3, 5
2. Wave 4's price zone must NOT overlap Wave 1's price zone (except slight overlap in leverage/futures markets)
3. Wave 2 typically retraces 38.2%-61.8% of Wave 1
4. In a Corrective wave (A-B-C), Wave B should not exceed the start of Wave A; Wave C is typically 0.618-1.618× Wave A
5. In a Triangle, each sub-wave (A,B,C,D,E) must be a 3-wave structure
6. Every corrective wave MUST be explicitly classified as either Wave 2 or Wave B in its `wave_role` or `description` field.

Set `overall_confidence` to reflect how certain the current wave label is. Ensure the `projections` confidence values sum to 1.0.

## ZigZag Reference (Auxiliary Only):
The chart shows algorithm-generated ZigZag pivots (blue dashed line, blue peaks, orange troughs) for reference only. Make independent judgments; if pivots contradict Elliott Wave rules, rules take precedence.
"""


def _build_elliott_wave_phase1_prompt(symbol: str, timeframe: str, wave_candidate: Dict[str, Any]) -> str:
    return f"""You are an Elliott Wave analyst. Analyze the {symbol} {timeframe} chart.

Identify corrective / consolidation patterns first. Return ONLY a JSON object in a markdown code block:

```json
{{
  "wave_pattern": "Impulse 1-2-3-4-5 + Corrective A-B-C",
  "direction": "down",
  "current_wave": "Wave B forming",
  "adjustments": [
    {{
      "label": "2",
      "type": "wave_2",
      "location": "idx 35-48",
      "adjustment_for": "Wave 1",
      "wave_role": "wave_2_correction",
      "description": "Shallow retracement"
    }}
  ],
  "waves": [
    {{"label": "1", "start_idx": 10, "end_idx": 35, "start_price": 45000, "end_price": 52000, "type": "impulse"}},
    {{"label": "2", "start_idx": 35, "end_idx": 48, "start_price": 52000, "end_price": 48000, "type": "corrective", "wave_role": "wave_2_correction", "adjustment_for": "Wave 1"}}
  ],
  "projections": [
    {{"scenario": "bullish", "description": "...", "target_price": 60000, "confidence": 0.45, "support_levels": [52000, 50000], "resistance_levels": [60000, 63000]}},
    {{"scenario": "bearish", "description": "...", "target_price": 40000, "confidence": 0.35, "support_levels": [42000, 40000], "resistance_levels": [50000, 52000]}},
    {{"scenario": "neutral", "description": "...", "target_price": 50000, "confidence": 0.20, "support_levels": [48000, 46000], "resistance_levels": [52000, 54000]}}
  ],
  "support_resistance_analysis": {{
    "key_support": 50000,
    "key_resistance": 55000,
    "support_tested": true,
    "support_held": true,
    "resistance_tested": false,
    "resistance_held": false,
    "breakout_direction": "up",
    "breakout_confirmed": false,
    "analysis": "Price tested 50000 support and held; now watching 55000 resistance."
  }},
  "directional_bias": {{
    "primary_direction": "bullish",
    "primary_probability": 0.55,
    "secondary_direction": "bearish",
    "secondary_probability": 0.30,
    "neutral_probability": 0.15,
    "rationale": "Wave structure implies upward continuation after support held."
  }},
  "annotations": "...",
  "likely_next_move": "...",
  "overall_confidence": 0.65
}}
```

Rules:
- Each wave needs: label, start_idx, end_idx, start_price, end_price, type
- start_idx/end_idx are 0-based candle indices from left to right
- Keep descriptions under 10 words
- You MUST identify the nearest key support and resistance levels
- You MUST analyze whether price tested support/resistance and whether support held or resistance held
- You MUST state whether a breakout/breakdown occurred or is forming
- You MUST provide directional bias with probabilities (primary + secondary + neutral = 1.0)

Hint: {wave_candidate.get('wave_pattern', 'N/A')}, {wave_candidate.get('current_wave', 'N/A')}, {wave_candidate.get('direction', 'N/A')}, score {wave_candidate.get('score', 0):.0%}
"""


def _build_elliott_wave_phase2_prompt(symbol: str, timeframe: str, wave_candidate: Dict[str, Any], phase1_result: Dict[str, Any]) -> str:
    # Summarize phase1 to keep prompt short and avoid token bloat.
    adjustments = phase1_result.get("adjustments", [])
    adj_summary = ""
    if adjustments:
        lines = []
        for a in adjustments[:6]:  # cap to avoid overly long prompts
            label = a.get("label", "?")
            wave_role = a.get("wave_role", a.get("type", ""))
            location = a.get("location", "")
            description = a.get("description", "")[:80]
            lines.append(f"- {label} ({wave_role}): {location} — {description}")
        adj_summary = "\n".join(lines)
    else:
        adj_summary = "No prior adjustments identified."

    return f"""You are an Elliott Wave analyst. Analyze the {symbol} {timeframe} chart.

## Prior Assessment
- Pattern: {phase1_result.get('wave_pattern', 'N/A')}
- Direction: {phase1_result.get('direction', 'N/A')}
- Current wave: {phase1_result.get('current_wave', 'N/A')}
- Adjustments:
{adj_summary}

## Task
Provide ONLY the `waves` array that matches the prior assessment. Skip projections and sub-waves.

## Output Format
Return ONLY a JSON object in a markdown code block:

```json
{{
  "waves": [
    {{"label": "1", "start_idx": 10, "end_idx": 35, "start_price": 45000, "end_price": 52000, "type": "impulse"}},
    {{"label": "2", "start_idx": 35, "end_idx": 48, "start_price": 52000, "end_price": 48000, "type": "corrective", "wave_role": "wave_2_correction", "adjustment_for": "Wave 1"}}
  ]
}}
```

Important:
- Each wave MUST include: label, start_idx, end_idx, start_price, end_price, type
- Use 0-based candle indices from left to right
- Set type to either "impulse" or "corrective"
- Keep the array concise: only major waves, no tiny sub-waves
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
        # Validate required fields: either full wave structure (phase 2)
        # or core phase 1 fields without waves.
        has_waves = "waves" in structure and isinstance(structure["waves"], list)
        has_phase1_fields = (
            "wave_pattern" in structure
            and "direction" in structure
            and "current_wave" in structure
        )
        if has_waves or has_phase1_fields:
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
