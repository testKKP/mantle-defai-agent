"""
Elliott Wave Theory - Automatic Pattern Recognition

Implements automatic Elliott Wave pattern detection from Binance K-line data.
Outputs top-N candidate wave structures with scoring and rule validation.
"""

import os
import itertools
from typing import List, Dict, Tuple, Optional
from dataclasses import dataclass
from loguru import logger


# --- Trend segmentation parameters ---
MAX_PER_SEGMENT = 3
MAX_TOTAL = 50
MIN_PIVOTS_PER_SEGMENT = 2
PRICE_TOLERANCE = 0.002
MIN_KLINES_PER_SEGMENT = 15
SEGMENT_GAP_TOLERANCE = 5


@dataclass
class TrendSegment:
    idx: int
    start_pivot_idx: int
    end_pivot_idx: int
    start_kline_idx: int
    end_kline_idx: int
    direction: str  # "up", "down", "sideways"
    pattern_hint: str  # "impulse", "corrective"


def zigzag(prices: List[float], deviation: float = 0.10) -> List[Tuple[int, float, str]]:
    """
    Pivot point extraction using percentage-based reversal threshold.

    When price reverses by more than `deviation` proportion,
    marks the prior extreme as a pivot (peak or trough).

    Returns:
        List of (index, price, 'peak'|'trough') tuples.
    """
    if not prices or len(prices) < 2:
        logger.warning("zigzag: prices list is too short")
        return []

    pivots: List[Tuple[int, float, str]] = []
    direction: Optional[str] = None
    last_pivot_idx = 0
    last_pivot_price = prices[0]
    # Track running high/low during initial uncertain phase
    running_high_idx, running_high_price = 0, prices[0]
    running_low_idx, running_low_price = 0, prices[0]

    for i, price in enumerate(prices[1:], start=1):
        if direction is None:
            if price > running_high_price:
                running_high_idx, running_high_price = i, price
            if price < running_low_price:
                running_low_idx, running_low_price = i, price
            # Determine direction when price deviates enough from either extreme
            if price >= running_low_price * (1 + deviation):
                direction = "up"
                last_pivot_idx = running_low_idx
                last_pivot_price = running_low_price
            elif price <= running_high_price * (1 - deviation):
                direction = "down"
                last_pivot_idx = running_high_idx
                last_pivot_price = running_high_price
        elif direction == "up":
            if price > last_pivot_price:
                last_pivot_idx = i
                last_pivot_price = price
            elif price <= last_pivot_price * (1 - deviation):
                pivots.append((last_pivot_idx, last_pivot_price, "peak"))
                direction = "down"
                last_pivot_idx = i
                last_pivot_price = price
        elif direction == "down":
            if price < last_pivot_price:
                last_pivot_idx = i
                last_pivot_price = price
            elif price >= last_pivot_price * (1 + deviation):
                pivots.append((last_pivot_idx, last_pivot_price, "trough"))
                direction = "up"
                last_pivot_idx = i
                last_pivot_price = price

    # Add the final unfinished pivot if it exists and is an extreme
    if direction is not None and len(prices) > 1:
        final_type = "peak" if direction == "up" else "trough"
        # Avoid duplicating the last recorded pivot
        if not pivots or last_pivot_idx != pivots[-1][0]:
            pivots.append((last_pivot_idx, last_pivot_price, final_type))

    logger.debug(f"zigzag: found {len(pivots)} pivots with deviation={deviation}")
    return pivots


def generate_impulse_candidates(
    pivots: List[Tuple[int, float, str]],
    prices: List[float],
) -> List[Dict]:
    """
    Generate impulse wave (1-2-3-4-5) candidates from pivot points.

    Selects 5 consecutive alternating pivots:
      - Case A (up):   peak -> trough -> peak -> trough -> peak
      - Case B (down): trough -> peak -> trough -> peak -> trough

    Returns:
        List of wave dicts, each describing a 1-2-3-4-5 structure.
    """
    candidates: List[Dict] = []
    if len(pivots) < 5:
        logger.debug("generate_impulse_candidates: not enough pivots")
        return candidates

    for i in range(len(pivots) - 4):
        p1, p2, p3, p4, p5 = pivots[i], pivots[i + 1], pivots[i + 2], pivots[i + 3], pivots[i + 4]

        # Case A: up impulse  peak->trough->peak->trough->peak
        if p1[2] == "peak" and p2[2] == "trough" and p3[2] == "peak" and p4[2] == "trough" and p5[2] == "peak":
            wave = {
                "wave_type": "impulse",
                "wave_pattern": "1-2-3-4-5",
                "direction": "up",
                "waves": [
                    {"wave": 1, "start_idx": max(0, p1[0] - 1), "end_idx": p1[0], "start_price": prices[max(0, p1[0] - 1)], "end_price": p1[1]},
                    {"wave": 2, "start_idx": p1[0], "end_idx": p2[0], "start_price": p1[1], "end_price": p2[1]},
                    {"wave": 3, "start_idx": p2[0], "end_idx": p3[0], "start_price": p2[1], "end_price": p3[1]},
                    {"wave": 4, "start_idx": p3[0], "end_idx": p4[0], "start_price": p3[1], "end_price": p4[1]},
                    {"wave": 5, "start_idx": p4[0], "end_idx": p5[0], "start_price": p4[1], "end_price": p5[1]},
                ],
            }
            candidates.append(wave)

        # Case B: down impulse  trough->peak->trough->peak->trough
        elif p1[2] == "trough" and p2[2] == "peak" and p3[2] == "trough" and p4[2] == "peak" and p5[2] == "trough":
            wave = {
                "wave_type": "impulse",
                "wave_pattern": "1-2-3-4-5",
                "direction": "down",
                "waves": [
                    {"wave": 1, "start_idx": max(0, p1[0] - 1), "end_idx": p1[0], "start_price": prices[max(0, p1[0] - 1)], "end_price": p1[1]},
                    {"wave": 2, "start_idx": p1[0], "end_idx": p2[0], "start_price": p1[1], "end_price": p2[1]},
                    {"wave": 3, "start_idx": p2[0], "end_idx": p3[0], "start_price": p2[1], "end_price": p3[1]},
                    {"wave": 4, "start_idx": p3[0], "end_idx": p4[0], "start_price": p3[1], "end_price": p4[1]},
                    {"wave": 5, "start_idx": p4[0], "end_idx": p5[0], "start_price": p4[1], "end_price": p5[1]},
                ],
            }
            candidates.append(wave)

    logger.debug(f"generate_impulse_candidates: generated {len(candidates)} candidates")
    return candidates


def generate_corrective_candidates(
    pivots: List[Tuple[int, float, str]],
    prices: List[float],
) -> List[Dict]:
    """
    Generate corrective wave (A-B-C) candidates from pivot points.

    Selects 3 consecutive alternating pivots:
      - Case A: peak -> trough -> peak
      - Case B: trough -> peak -> trough

    Returns:
        List of wave dicts, each describing an A-B-C structure.
    """
    candidates: List[Dict] = []
    if len(pivots) < 3:
        logger.debug("generate_corrective_candidates: not enough pivots")
        return candidates

    for i in range(len(pivots) - 2):
        p1, p2, p3 = pivots[i], pivots[i + 1], pivots[i + 2]

        # Case A: peak -> trough -> peak
        if p1[2] == "peak" and p2[2] == "trough" and p3[2] == "peak":
            wave = {
                "wave_type": "corrective",
                "wave_pattern": "A-B-C",
                "direction": "down",
                "waves": [
                    {"wave": "A", "start_idx": max(0, p1[0] - 1), "end_idx": p1[0], "start_price": prices[max(0, p1[0] - 1)], "end_price": p1[1]},
                    {"wave": "B", "start_idx": p1[0], "end_idx": p2[0], "start_price": p1[1], "end_price": p2[1]},
                    {"wave": "C", "start_idx": p2[0], "end_idx": p3[0], "start_price": p2[1], "end_price": p3[1]},
                ],
            }
            candidates.append(wave)

        # Case B: trough -> peak -> trough
        elif p1[2] == "trough" and p2[2] == "peak" and p3[2] == "trough":
            wave = {
                "wave_type": "corrective",
                "wave_pattern": "A-B-C",
                "direction": "up",
                "waves": [
                    {"wave": "A", "start_idx": max(0, p1[0] - 1), "end_idx": p1[0], "start_price": prices[max(0, p1[0] - 1)], "end_price": p1[1]},
                    {"wave": "B", "start_idx": p1[0], "end_idx": p2[0], "start_price": p1[1], "end_price": p2[1]},
                    {"wave": "C", "start_idx": p2[0], "end_idx": p3[0], "start_price": p2[1], "end_price": p3[1]},
                ],
            }
            candidates.append(wave)

    logger.debug(f"generate_corrective_candidates: generated {len(candidates)} candidates")
    return candidates


def generate_zigzag_candidates(
    pivots: List[Tuple[int, float, str]],
    prices: List[float],
) -> List[Dict]:
    """
    Generate ZigZag (5-3-5) A-B-C corrective candidates.

    From pivots, identifies A-B-C structures where:
    - Wave A is a strong 5-wave impulse move
    - Wave B is a shallow 3-wave correction (38.2%-78.6% of A)
    - Wave C is a strong 5-wave impulse (0.618-1.618 of A)

    Uses the same pivot selection as corrective candidates but applies
    ZigZag-specific proportion rules.
    """
    candidates: List[Dict] = []
    if len(pivots) < 3:
        return candidates

    for i in range(len(pivots) - 2):
        p1, p2, p3 = pivots[i], pivots[i + 1], pivots[i + 2]

        if p1[2] == "peak" and p2[2] == "trough" and p3[2] == "peak":
            direction = "down"
        elif p1[2] == "trough" and p2[2] == "peak" and p3[2] == "trough":
            direction = "up"
        else:
            continue

        wave = {
            "wave_type": "zigzag",
            "wave_pattern": "ZigZag A-B-C (5-3-5)",
            "direction": direction,
            "waves": [
                {"wave": "A", "start_idx": max(0, p1[0] - 1), "end_idx": p1[0], "start_price": prices[max(0, p1[0] - 1)], "end_price": p1[1]},
                {"wave": "B", "start_idx": p1[0], "end_idx": p2[0], "start_price": p1[1], "end_price": p2[1]},
                {"wave": "C", "start_idx": p2[0], "end_idx": p3[0], "start_price": p2[1], "end_price": p3[1]},
            ],
        }
        candidates.append(wave)

    logger.debug(f"generate_zigzag_candidates: generated {len(candidates)} candidates")
    return candidates


def generate_flat_candidates(
    pivots: List[Tuple[int, float, str]],
    prices: List[float],
) -> List[Dict]:
    """
    Generate Flat (3-3-5) A-B-C corrective candidates.

    From pivots, identifies A-B-C structures where:
    - Wave A is a 3-wave structure (shorter, less impulsive)
    - Wave B retraces 80%-105% of Wave A (often near or beyond A's start)
    - Wave C is a 5-wave impulse
    """
    candidates: List[Dict] = []
    if len(pivots) < 3:
        return candidates

    for i in range(len(pivots) - 2):
        p1, p2, p3 = pivots[i], pivots[i + 1], pivots[i + 2]

        if p1[2] == "peak" and p2[2] == "trough" and p3[2] == "peak":
            direction = "down"
        elif p1[2] == "trough" and p2[2] == "peak" and p3[2] == "trough":
            direction = "up"
        else:
            continue

        wave = {
            "wave_type": "flat",
            "wave_pattern": "Flat A-B-C (3-3-5)",
            "direction": direction,
            "waves": [
                {"wave": "A", "start_idx": max(0, p1[0] - 1), "end_idx": p1[0], "start_price": prices[max(0, p1[0] - 1)], "end_price": p1[1]},
                {"wave": "B", "start_idx": p1[0], "end_idx": p2[0], "start_price": p1[1], "end_price": p2[1]},
                {"wave": "C", "start_idx": p2[0], "end_idx": p3[0], "start_price": p2[1], "end_price": p3[1]},
            ],
        }
        candidates.append(wave)

    logger.debug(f"generate_flat_candidates: generated {len(candidates)} candidates")
    return candidates


def generate_triangle_candidates(
    pivots: List[Tuple[int, float, str]],
    prices: List[float],
) -> List[Dict]:
    """
    Generate Triangle (3-3-3-3-3) A-B-C-D-E corrective candidates.

    From pivots, identifies A-B-C-D-E structures where:
    - Each sub-wave is a 3-wave structure
    - Contracting Triangle: each successive wave is shorter
    - Expanding Triangle: each successive wave is longer
    """
    candidates: List[Dict] = []
    if len(pivots) < 5:
        return candidates

    for i in range(len(pivots) - 4):
        p1, p2, p3, p4, p5 = pivots[i], pivots[i + 1], pivots[i + 2], pivots[i + 3], pivots[i + 4]

        # Need 5 alternating pivots
        types = [p1[2], p2[2], p3[2], p4[2], p5[2]]
        expected_a = ["peak", "trough", "peak", "trough", "peak"]
        expected_b = ["trough", "peak", "trough", "peak", "trough"]
        if types not in (expected_a, expected_b):
            continue

        direction = "sideways"
        wave = {
            "wave_type": "triangle",
            "wave_pattern": "Triangle A-B-C-D-E (3-3-3-3-3)",
            "direction": direction,
            "waves": [
                {"wave": "A", "start_idx": max(0, p1[0] - 1), "end_idx": p1[0], "start_price": prices[max(0, p1[0] - 1)], "end_price": p1[1]},
                {"wave": "B", "start_idx": p1[0], "end_idx": p2[0], "start_price": p1[1], "end_price": p2[1]},
                {"wave": "C", "start_idx": p2[0], "end_idx": p3[0], "start_price": p2[1], "end_price": p3[1]},
                {"wave": "D", "start_idx": p3[0], "end_idx": p4[0], "start_price": p3[1], "end_price": p4[1]},
                {"wave": "E", "start_idx": p4[0], "end_idx": p5[0], "start_price": p4[1], "end_price": p5[1]},
            ],
        }
        candidates.append(wave)

    logger.debug(f"generate_triangle_candidates: generated {len(candidates)} candidates")
    return candidates


def generate_double_zigzag_candidates(
    pivots: List[Tuple[int, float, str]],
    prices: List[float],
) -> List[Dict]:
    """
    Generate Double ZigZag (W-X-Y) corrective candidates.

    From pivots, identifies W-X-Y structures where:
    - W is a ZigZag (5-3-5)
    - X is a 3-wave corrective connector
    - Y is a ZigZag (5-3-5)
    - X should NOT retrace more than 50%-61.8% of W
    """
    candidates: List[Dict] = []
    if len(pivots) < 7:
        return candidates

    for i in range(len(pivots) - 6):
        p1, p2, p3, p4, p5, p6, p7 = (
            pivots[i], pivots[i + 1], pivots[i + 2],
            pivots[i + 3], pivots[i + 4], pivots[i + 5], pivots[i + 6]
        )

        types = [p1[2], p2[2], p3[2], p4[2], p5[2], p6[2], p7[2]]
        expected_a = ["peak", "trough", "peak", "trough", "peak", "trough", "peak"]
        expected_b = ["trough", "peak", "trough", "peak", "trough", "peak", "trough"]
        if types not in (expected_a, expected_b):
            continue

        # W direction: p1->p3, X: p3->p5, Y: p5->p7
        if types == expected_a:
            w_direction = "down"  # peak->trough->peak means W ends at peak, started before p1
            x_direction = "down"
            y_direction = "down"
        else:
            w_direction = "up"
            x_direction = "up"
            y_direction = "up"

        wave = {
            "wave_type": "double_zigzag",
            "wave_pattern": "Double ZigZag W-X-Y (5-3-5-X-5-3-5)",
            "direction": w_direction,
            "waves": [
                {"wave": "W", "start_idx": max(0, p1[0] - 1), "end_idx": p3[0], "start_price": prices[max(0, p1[0] - 1)], "end_price": p3[1]},
                {"wave": "X", "start_idx": p3[0], "end_idx": p5[0], "start_price": p3[1], "end_price": p5[1]},
                {"wave": "Y", "start_idx": p5[0], "end_idx": p7[0], "start_price": p5[1], "end_price": p7[1]},
            ],
            "sub_waves": [
                {"wave": "(a)", "start_idx": max(0, p1[0] - 1), "end_idx": p1[0], "start_price": prices[max(0, p1[0] - 1)], "end_price": p1[1]},
                {"wave": "(b)", "start_idx": p1[0], "end_idx": p2[0], "start_price": p1[1], "end_price": p2[1]},
                {"wave": "(c)", "start_idx": p2[0], "end_idx": p3[0], "start_price": p2[1], "end_price": p3[1]},
                {"wave": "(x)", "start_idx": p3[0], "end_idx": p5[0], "start_price": p3[1], "end_price": p5[1]},
                {"wave": "(a)", "start_idx": p5[0], "end_idx": p5[0], "start_price": p5[1], "end_price": p5[1]},
                {"wave": "(b)", "start_idx": p5[0], "end_idx": p6[0], "start_price": p5[1], "end_price": p6[1]},
                {"wave": "(c)", "start_idx": p6[0], "end_idx": p7[0], "start_price": p6[1], "end_price": p7[1]},
            ],
        }
        candidates.append(wave)

    logger.debug(f"generate_double_zigzag_candidates: generated {len(candidates)} candidates")
    return candidates


def validate_zigzag_rules(wave: Dict) -> Dict[str, bool]:
    """
    Validate ZigZag (5-3-5) rules.

    Rules:
        1. wave_a_exist: Wave A has a reasonable magnitude.
        2. wave_b_retrace: Wave B retraces 38.2%-78.6% of Wave A.
        3. wave_c_ratio: Wave C is 0.618-1.618 of Wave A.
    """
    waves = wave.get("waves", [])
    if len(waves) < 3:
        return {
            "wave_a_exist": False,
            "wave_b_retrace": False,
            "wave_c_ratio": False,
        }

    wa = waves[0]
    wb = waves[1]
    wc = waves[2]

    wave_a_height = abs(wa["end_price"] - wa["start_price"])
    wave_b_height = abs(wb["end_price"] - wb["start_price"])
    wave_c_height = abs(wc["end_price"] - wc["start_price"])

    wave_a_exist = wave_a_height > 0

    wave_b_retrace = wave_b_height / wave_a_height if wave_a_height > 0 else 0.0
    wave_b_retrace_ok = 0.382 <= wave_b_retrace <= 0.786

    wave_c_ratio = wave_c_height / wave_a_height if wave_a_height > 0 else 0.0
    wave_c_ratio_ok = 0.618 <= wave_c_ratio <= 1.618

    return {
        "wave_a_exist": wave_a_exist,
        "wave_b_retrace": wave_b_retrace_ok,
        "wave_c_ratio": wave_c_ratio_ok,
    }


def validate_flat_rules(wave: Dict) -> Dict[str, bool]:
    """
    Validate Flat (3-3-5) rules.

    Rules:
        1. wave_a_exist: Wave A has a reasonable magnitude.
        2. wave_b_retrace: Wave B retraces 80%-105% of Wave A (deep retrace).
        3. wave_c_is_5wave: Wave C is larger than Wave A (5-wave impulse characteristic).
    """
    waves = wave.get("waves", [])
    if len(waves) < 3:
        return {
            "wave_a_exist": False,
            "wave_b_retrace": False,
            "wave_c_is_5wave": False,
        }

    wa = waves[0]
    wb = waves[1]
    wc = waves[2]

    wave_a_height = abs(wa["end_price"] - wa["start_price"])
    wave_b_height = abs(wb["end_price"] - wb["start_price"])
    wave_c_height = abs(wc["end_price"] - wc["start_price"])

    wave_a_exist = wave_a_height > 0

    wave_b_retrace = wave_b_height / wave_a_height if wave_a_height > 0 else 0.0
    wave_b_retrace_ok = 0.80 <= wave_b_retrace <= 1.05

    wave_c_is_5wave = wave_c_height >= wave_a_height * 0.5

    return {
        "wave_a_exist": wave_a_exist,
        "wave_b_retrace": wave_b_retrace_ok,
        "wave_c_is_5wave": wave_c_is_5wave,
    }


def validate_triangle_rules(wave: Dict) -> Dict[str, bool]:
    """
    Validate Triangle (3-3-3-3-3) rules.

    Rules:
        1. five_waves: Has exactly 5 waves (A-B-C-D-E).
        2. contracting: Each successive wave is shorter (Contracting Triangle).
        3. expanding: Each successive wave is longer (Expanding Triangle).
        4. valid_structure: Either contracting OR expanding, not neither.
    """
    waves = wave.get("waves", [])
    if len(waves) < 5:
        return {
            "five_waves": False,
            "contracting": False,
            "expanding": False,
            "valid_structure": False,
        }

    wave_lengths = []
    for w in waves:
        h = abs(w["end_price"] - w["start_price"])
        wave_lengths.append(h)

    five_waves = len(waves) == 5

    # Contracting: each wave shorter than previous
    contracting = all(wave_lengths[i] > wave_lengths[i + 1] for i in range(len(wave_lengths) - 1))

    # Expanding: each wave longer than previous
    expanding = all(wave_lengths[i] < wave_lengths[i + 1] for i in range(len(wave_lengths) - 1))

    valid_structure = contracting or expanding

    return {
        "five_waves": five_waves,
        "contracting": contracting,
        "expanding": expanding,
        "valid_structure": valid_structure,
    }


def validate_impulse_rules(wave: Dict) -> Dict[str, bool]:
    """
    Validate impulse wave rules.

    Rules (lenient for real-world K-line data):
        1. wave2_fib: Wave 2 retraces 30%-80% of Wave 1.
        2. wave3_not_shortest: Wave 3 > 80% of min(Wave1, Wave5).
        3. wave3_extend: Wave 3 is 100%-300% of Wave 1.
        4. wave4_fib: Wave 4 retraces 20%-60% of Wave 3.
        5. wave4_no_overlap: Wave 4 does not overlap Wave 1 price zone.
        6. wave5_exist: Wave 5 has a positive magnitude.

    Returns:
        Dict mapping rule name -> bool result.
    """
    waves = wave.get("waves", [])
    if len(waves) < 5:
        return {
            "wave2_fib": False,
            "wave3_not_shortest": False,
            "wave3_extend": False,
            "wave4_fib": False,
            "wave4_no_overlap": False,
            "wave5_exist": False,
        }

    w1 = waves[0]
    w2 = waves[1]
    w3 = waves[2]
    w4 = waves[3]
    w5 = waves[4]

    wave1_height = w1["end_price"] - w1["start_price"]
    wave2_height = w2["end_price"] - w2["start_price"]
    wave3_height = w3["end_price"] - w3["start_price"]
    wave4_height = w4["end_price"] - w4["start_price"]
    wave5_height = w5["end_price"] - w5["start_price"]

    # 1. wave2 retracement 30%-80%
    wave2_retrace = abs(wave2_height) / abs(wave1_height) if wave1_height != 0 else 0.0
    wave2_fib = 0.30 <= wave2_retrace <= 0.80

    # 2. wave3 not shortest
    wave3_not_shortest = abs(wave3_height) > min(abs(wave1_height), abs(wave5_height)) * 0.8 if min(abs(wave1_height), abs(wave5_height)) > 0 else False

    # 3. wave3 extension 100%-300%
    wave3_ratio = abs(wave3_height) / abs(wave1_height) if wave1_height != 0 else 0.0
    wave3_extend = 1.0 <= wave3_ratio <= 3.0

    # 4. wave4 retracement 20%-60%
    wave4_retrace = abs(wave4_height) / abs(wave3_height) if wave3_height != 0 else 0.0
    wave4_fib = 0.20 <= wave4_retrace <= 0.60

    # 5. wave4 no overlap with wave1
    direction = wave.get("direction", "up")
    wave1_high = max(w1["start_price"], w1["end_price"])
    wave1_low = min(w1["start_price"], w1["end_price"])
    wave4_high = max(w4["start_price"], w4["end_price"])
    wave4_low = min(w4["start_price"], w4["end_price"])
    if direction == "up":
        wave4_no_overlap = wave4_low > wave1_high
    else:
        wave4_no_overlap = wave4_high < wave1_low

    # 6. wave5 existence
    wave5_exist = abs(wave5_height) > 0

    return {
        "wave2_fib": wave2_fib,
        "wave3_not_shortest": wave3_not_shortest,
        "wave3_extend": wave3_extend,
        "wave4_fib": wave4_fib,
        "wave4_no_overlap": wave4_no_overlap,
        "wave5_exist": wave5_exist,
    }


def validate_corrective_rules(wave: Dict) -> Dict[str, bool]:
    """
    Validate corrective wave (A-B-C) rules.

    Rules:
        1. wave_a_exist: Wave A has a reasonable magnitude (>0).
        2. wave_b_retrace: Wave B retraces 30%-80% of Wave A.
        3. wave_c_extend: Wave C extends 80%-200% of Wave A.

    Returns:
        Dict mapping rule name -> bool result.
    """
    waves = wave.get("waves", [])
    if len(waves) < 3:
        return {
            "wave_a_exist": False,
            "wave_b_retrace": False,
            "wave_c_extend": False,
        }

    wa = waves[0]
    wb = waves[1]
    wc = waves[2]

    wave_a_height = wa["end_price"] - wa["start_price"]
    wave_b_height = wb["end_price"] - wb["start_price"]
    wave_c_height = wc["end_price"] - wc["start_price"]

    wave_a_exist = abs(wave_a_height) > 0

    wave_b_retrace = abs(wave_b_height) / abs(wave_a_height) if wave_a_height != 0 else 0.0
    wave_b_retrace_ok = 0.30 <= wave_b_retrace <= 0.80

    wave_c_ratio = abs(wave_c_height) / abs(wave_a_height) if wave_a_height != 0 else 0.0
    wave_c_extend = 0.80 <= wave_c_ratio <= 2.0

    return {
        "wave_a_exist": wave_a_exist,
        "wave_b_retrace": wave_b_retrace_ok,
        "wave_c_extend": wave_c_extend,
    }


def score_candidate(wave: Dict, validations: Dict) -> float:
    """
    Score a wave candidate on a 0.0-1.0 scale.

    Weights:
        - Wave 3 not shortest : 0.25
        - Wave 4 no overlap   : 0.25
        - Fibonacci ratios / structure rules : 0.50

    Returns:
        Float score between 0.0 and 1.0.
    """
    score = 0.0

    if validations.get("wave3_not_shortest", False):
        score += 0.25
    if validations.get("wave4_no_overlap", False):
        score += 0.25

    # Fibonacci / structure composite
    fib_score = 0.0
    fib_count = 0
    if "wave2_fib" in validations:
        fib_score += 1.0 if validations["wave2_fib"] else 0.0
        fib_count += 1
    if "wave3_extend" in validations:
        fib_score += 1.0 if validations["wave3_extend"] else 0.0
        fib_count += 1
    if "wave4_fib" in validations:
        fib_score += 1.0 if validations["wave4_fib"] else 0.0
        fib_count += 1
    if "wave_b_retrace" in validations:
        fib_score += 1.0 if validations["wave_b_retrace"] else 0.0
        fib_count += 1
    if "wave_c_ratio" in validations:
        fib_score += 1.0 if validations["wave_c_ratio"] else 0.0
        fib_count += 1
    if "wave_c_is_5wave" in validations:
        fib_score += 1.0 if validations["wave_c_is_5wave"] else 0.0
        fib_count += 1
    if "valid_structure" in validations:
        fib_score += 1.0 if validations["valid_structure"] else 0.0
        fib_count += 1

    if fib_count > 0:
        score += (fib_score / fib_count) * 0.50

    return round(score, 4)


# ---------------------------------------------------------------------------
# Trend segmentation helpers
# ---------------------------------------------------------------------------

def detect_trend_segments(
    pivots: List[Tuple[int, float, str]],
    prices: List[float],
    min_pivots: int = 3,
    price_tolerance: float = 0.002,
) -> List[TrendSegment]:
    """
    基于 HH/HL 和 LH/LL 识别趋势方向，将 pivots 划分为连续同向的 TrendSegment。

    Returns:
        List[TrendSegment]
    """
    if len(pivots) < min_pivots:
        logger.debug(f"detect_trend_segments: not enough pivots ({len(pivots)} < {min_pivots})")
        return []

    # 1. 对每个 pivot 位置做局部方向判断（取前最多 5 个 pivot 做窗口）
    directions: List[str] = []
    for i in range(len(pivots)):
        start = max(0, i - 5)
        window = pivots[start : i + 1]
        if len(window) < 3:
            directions.append(directions[-1] if directions else "sideways")
        else:
            directions.append(_classify_local_direction(window, price_tolerance))

    # 2. 合并连续同向
    segments: List[TrendSegment] = []
    current_dir = directions[0]
    seg_start_pivot = 0
    seg_start_kline = pivots[0][0]

    for i in range(1, len(pivots)):
        if directions[i] != current_dir:
            segments.append(
                TrendSegment(
                    idx=len(segments),
                    start_pivot_idx=seg_start_pivot,
                    end_pivot_idx=i - 1,
                    start_kline_idx=seg_start_kline,
                    end_kline_idx=pivots[i - 1][0],
                    direction=current_dir,
                    pattern_hint="impulse" if current_dir in ("up", "down") else "corrective",
                )
            )
            current_dir = directions[i]
            seg_start_pivot = i
            seg_start_kline = pivots[i][0]

    # 闭合最后一段
    segments.append(
        TrendSegment(
            idx=len(segments),
            start_pivot_idx=seg_start_pivot,
            end_pivot_idx=len(pivots) - 1,
            start_kline_idx=seg_start_kline,
            end_kline_idx=pivots[-1][0],
            direction=current_dir,
            pattern_hint="impulse" if current_dir in ("up", "down") else "corrective",
        )
    )

    # 3. 合并过短段
    segments = _merge_short_segments(segments, min_pivots)

    # 4. 按 kline 范围过滤极小段，但不过度过滤短数据
    min_klines = min(MIN_KLINES_PER_SEGMENT, max(5, len(prices) // 8))
    segments = [
        s
        for s in segments
        if (s.end_kline_idx - s.start_kline_idx) >= min_klines
    ]

    # 重新编号
    for i, seg in enumerate(segments):
        seg.idx = i

    logger.debug(f"detect_trend_segments: generated {len(segments)} segments")
    return segments


def _classify_local_direction(
    window_pivots: List[Tuple[int, float, str]], price_tolerance: float
) -> str:
    """
    给定 pivot 窗口，判断局部趋势方向。
    HH + HL => "up", LH + LL => "down"。
    都不满足时看首尾价格变化幅度：
        < 30% 波动范围 => "sideways"，否则按价格变化方向决定。
    """
    if len(window_pivots) < 3:
        return "sideways"

    peaks = [p[1] for p in window_pivots if p[2] == "peak"]
    troughs = [p[1] for p in window_pivots if p[2] == "trough"]

    tol = price_tolerance

    hh = (
        all(peaks[i] >= peaks[i - 1] * (1 - tol) for i in range(1, len(peaks)))
        if len(peaks) >= 2
        else False
    )
    hl = (
        all(troughs[i] >= troughs[i - 1] * (1 - tol) for i in range(1, len(troughs)))
        if len(troughs) >= 2
        else False
    )

    lh = (
        all(peaks[i] <= peaks[i - 1] * (1 + tol) for i in range(1, len(peaks)))
        if len(peaks) >= 2
        else False
    )
    ll = (
        all(troughs[i] <= troughs[i - 1] * (1 + tol) for i in range(1, len(troughs)))
        if len(troughs) >= 2
        else False
    )

    if hh and hl:
        return "up"
    if lh and ll:
        return "down"

    # 都不满足：先看同类型 pivot 的趋势，再看另一种类型的趋势
    curr_type = window_pivots[-1][2]
    other_type = "trough" if curr_type == "peak" else "peak"

    same_type_prices = [p[1] for p in window_pivots if p[2] == curr_type]
    other_type_prices = [p[1] for p in window_pivots if p[2] == other_type]

    if len(same_type_prices) >= 2:
        if same_type_prices[-1] > same_type_prices[0] * (1 + tol):
            return "up"
        if same_type_prices[-1] < same_type_prices[0] * (1 - tol):
            return "down"
        # 首尾相等时，看最近同类型 pivot 的趋势
        if len(same_type_prices) >= 3:
            if same_type_prices[-1] > same_type_prices[-2] * (1 + tol):
                return "up"
            if same_type_prices[-1] < same_type_prices[-2] * (1 - tol):
                return "down"

    if len(other_type_prices) >= 2:
        if other_type_prices[-1] > other_type_prices[0] * (1 + tol):
            return "up"
        if other_type_prices[-1] < other_type_prices[0] * (1 - tol):
            return "down"
        # 首尾相等时，看最近异类型 pivot 的趋势
        if len(other_type_prices) >= 3:
            if other_type_prices[-1] > other_type_prices[-2] * (1 + tol):
                return "up"
            if other_type_prices[-1] < other_type_prices[-2] * (1 - tol):
                return "down"

    # 最后 fallback：看首尾变化幅度
    start_price = window_pivots[0][1]
    end_price = window_pivots[-1][1]
    min_price = min(p[1] for p in window_pivots)
    max_price = max(p[1] for p in window_pivots)
    price_range = max_price - min_price

    if price_range == 0:
        return "sideways"

    change_ratio = abs(end_price - start_price) / price_range
    if change_ratio < 0.20:
        return "sideways"
    elif end_price > start_price:
        return "up"
    else:
        return "down"


def _merge_short_segments(
    segments: List[TrendSegment], min_pivots: int
) -> List[TrendSegment]:
    """
    将 pivot 数少于 min_pivots 的段进行智能合并。
    - 同方向短段合并到上一段
    - 反向短段保留为独立段（趋势反转很重要）
    - 横盘段合并到相邻段
    - 首段过短合并到下一段
    """
    if not segments:
        return segments

    merged = [segments[0]]
    for seg in segments[1:]:
        seg_len = seg.end_pivot_idx - seg.start_pivot_idx + 1
        if seg_len < min_pivots and merged:
            last = merged[-1]
            if seg.direction == last.direction:
                # 同方向合并
                last.end_pivot_idx = seg.end_pivot_idx
                last.end_kline_idx = seg.end_kline_idx
            elif seg.direction == "sideways":
                # 横盘段合并到相邻段（无论方向）
                last.end_pivot_idx = seg.end_pivot_idx
                last.end_kline_idx = seg.end_kline_idx
            else:
                # 反向段保留为独立段（趋势反转很重要）
                merged.append(seg)
        else:
            merged.append(seg)

    # 处理首段过短的情况
    if len(merged) > 1:
        first_len = merged[0].end_pivot_idx - merged[0].start_pivot_idx + 1
        if first_len < min_pivots:
            # 首段过短，合并到下一段
            merged[1].start_pivot_idx = merged[0].start_pivot_idx
            merged[1].start_kline_idx = merged[0].start_kline_idx
            merged.pop(0)

    return merged


def _generate_segment_candidates(
    segment: TrendSegment,
    seg_pivots: List[Tuple[int, float, str]],
    prices: List[float],
) -> List[Dict]:
    """
    在单段 pivot 子集上调用现有函数生成候选，并做段内 validate + score。
    对每个 candidate 标记 _segment_idx。
    同时生成新的调整浪类型候选（zigzag、flat、triangle、double_zigzag）。
    """
    candidates: List[Dict] = []
    if segment.direction in ("up", "down"):
        candidates.extend(generate_impulse_candidates(seg_pivots, prices))
        candidates.extend(generate_double_zigzag_candidates(seg_pivots, prices))
    candidates.extend(generate_corrective_candidates(seg_pivots, prices))
    candidates.extend(generate_zigzag_candidates(seg_pivots, prices))
    candidates.extend(generate_flat_candidates(seg_pivots, prices))
    candidates.extend(generate_triangle_candidates(seg_pivots, prices))

    scored: List[Dict] = []
    for cand in candidates:
        wave_type = cand.get("wave_type", "")
        if wave_type == "impulse":
            validations = validate_impulse_rules(cand)
        elif wave_type == "zigzag":
            validations = validate_zigzag_rules(cand)
        elif wave_type == "flat":
            validations = validate_flat_rules(cand)
        elif wave_type == "triangle":
            validations = validate_triangle_rules(cand)
        elif wave_type == "double_zigzag":
            validations = validate_zigzag_rules(cand)
        else:
            validations = validate_corrective_rules(cand)

        rule_score = score_candidate(cand, validations)
        cand["rule_score"] = rule_score
        cand["validations"] = validations
        cand["_segment_idx"] = segment.idx
        scored.append(cand)

    scored.sort(key=lambda x: x["rule_score"], reverse=True)
    return scored


def combine_segments(
    segment_candidates: List[List[Dict]],
    segments: List[TrendSegment],
    prices: List[float],
) -> List[Dict]:
    """
    每段保留 top 3 候选，笛卡尔积组合所有段，组合数上限 MAX_TOTAL。
    """
    if not segment_candidates or not segments:
        return []

    # 过滤空段
    filtered: List[List[Dict]] = []
    for seg_cands in segment_candidates:
        top = seg_cands[:MAX_PER_SEGMENT]
        if top:
            filtered.append(top)

    if not filtered:
        return []
    if len(filtered) == 1:
        return filtered[0]

    # 笛卡尔积
    combinations = list(itertools.product(*filtered))
    if len(combinations) > MAX_TOTAL:
        combinations = combinations[:MAX_TOTAL]

    composites: List[Dict] = []
    for combo in combinations:
        composite = _build_composite(combo, segments, prices)
        composites.append(composite)

    return composites


def _build_composite(
    seg_cands: Tuple[Dict, ...],
    segments: List[TrendSegment],
    prices: List[float],
) -> Dict:
    """
    将多个段候选拼接为组合候选。
    所有 waves 按时间顺序拼接，编号连续。
    """
    all_waves: List[Dict] = []
    segment_meta: List[Dict] = []

    for cand, seg in zip(seg_cands, segments):
        start_wave_idx = len(all_waves)
        for w in cand.get("waves", []):
            wave_copy = dict(w)
            all_waves.append(wave_copy)

        segment_meta.append(
            {
                "segment_idx": seg.idx,
                "direction": seg.direction,
                "pattern_hint": seg.pattern_hint,
                "wave_type": cand.get("wave_type"),
                "direction_in_segment": cand.get("direction"),
                "start_wave_idx": start_wave_idx,
                "end_wave_idx": len(all_waves) - 1,
            }
        )

    last_seg = segments[-1]
    last_cand = seg_cands[-1]

    composite: Dict = {
        "wave_type": "composite",
        "wave_pattern": "composite",
        "direction": last_cand.get("direction", last_seg.direction),
        "waves": all_waves,
        "segments": segment_meta,
        "segment_count": len(segments),
        "_segment_candidates": [c.get("rule_score", 0.0) for c in seg_cands],
    }
    return composite


def score_composite_candidate(candidate: Dict, total_bars: int) -> float:
    """
    组合候选打分：
      - 段内规则分数加权平均（40%）
      - 段间连续性（15%）：gap > SEGMENT_GAP_TOLERANCE 则扣分
      - 新鲜度（20%）：最后一段越接近最新 K 线越好
      - 跨度（25%）：覆盖 K 线比例
    """
    seg_scores = candidate.get("_segment_candidates", [])
    if not seg_scores:
        return 0.0

    # 规则分（40%）
    avg_rule_score = sum(seg_scores) / len(seg_scores)
    rule_component = avg_rule_score * 0.40

    waves = candidate.get("waves", [])
    segments_meta = candidate.get("segments", [])

    # 连续性（15%）
    continuity_score = 1.0
    for i in range(1, len(segments_meta)):
        prev_end_wave_idx = segments_meta[i - 1]["end_wave_idx"]
        curr_start_wave_idx = segments_meta[i]["start_wave_idx"]
        if (
            0 <= prev_end_wave_idx < len(waves)
            and 0 <= curr_start_wave_idx < len(waves)
        ):
            prev_end_kline = waves[prev_end_wave_idx]["end_idx"]
            curr_start_kline = waves[curr_start_wave_idx]["start_idx"]
            gap = curr_start_kline - prev_end_kline
            if gap > SEGMENT_GAP_TOLERANCE:
                continuity_score -= min(1.0, (gap - SEGMENT_GAP_TOLERANCE) / 20.0)
    continuity_score = max(0.0, continuity_score)
    continuity_component = continuity_score * 0.15

    # 新鲜度（20%）
    last_end_idx = waves[-1]["end_idx"] if waves else 0
    recency_score = last_end_idx / max(total_bars - 1, 1)
    recency_component = recency_score * 0.20

    # 跨度（25%）
    start_idx = waves[0]["start_idx"] if waves else 0
    end_idx = waves[-1]["end_idx"] if waves else 0
    span_ratio = (end_idx - start_idx) / max(total_bars - 1, 1)
    span_component = span_ratio * 0.25

    total_score = rule_component + continuity_component + recency_component + span_component
    return round(total_score, 4)


def calculate_composite_wave_probability(
    candidate: Dict, prices: List[float]
) -> Dict:
    """
    交易决策只关心最后一段。
    构建 proxy candidate 只含最后一段，调用现有 calculate_current_wave_probability()。
    返回结果附加 total_segments 和 current_segment_idx。
    """
    segments_meta = candidate.get("segments", [])
    if not segments_meta:
        result = calculate_current_wave_probability(candidate, prices)
        result["total_segments"] = 0
        result["current_segment_idx"] = 0
        return result

    last_seg = segments_meta[-1]
    start_idx = last_seg["start_wave_idx"]
    end_idx = last_seg["end_wave_idx"]

    waves = candidate.get("waves", [])
    proxy_waves = waves[start_idx : end_idx + 1] if waves else []

    proxy_candidate = {
        "wave_type": last_seg.get("wave_type", "impulse"),
        "direction": last_seg.get("direction_in_segment", "up"),
        "waves": proxy_waves,
    }

    result = calculate_current_wave_probability(proxy_candidate, prices)
    result["total_segments"] = len(segments_meta)
    result["current_segment_idx"] = len(segments_meta) - 1
    return result


# ---------------------------------------------------------------------------
# Main analyzer
# ---------------------------------------------------------------------------

class ElliottWaveAnalyzer:
    """
    Main Elliott Wave analysis engine.

    Provides:
        - ZigZag pivot extraction
        - Impulse (1-2-3-4-5) candidate generation
        - Corrective (A-B-C) candidate generation
        - Rule validation and scoring
        - Top-N ranked output
    """

    def __init__(self, deviation: float = 0.10, min_span_ratio: float = 0.15):
        """
        Args:
            deviation: Minimum price reversal proportion to register a pivot.
                       Default 0.10 (10%). Adjust for higher/lower volatility.
            min_span_ratio: Minimum span ratio (wave1.start_idx to wave5.end_idx) / total_bars
                            for a candidate to be considered. Default 0.30 (30%).
        """
        self.deviation = deviation
        self.min_span_ratio = min_span_ratio
        logger.info(f"ElliottWaveAnalyzer initialized (deviation={deviation}, min_span_ratio={min_span_ratio})")

    def _calculate_recency_score(self, candidate: Dict, total_bars: int) -> float:
        """计算候选波浪的新鲜度分数。

        最后一个浪的 end_idx 越接近最新的K线，分数越高。
        返回 0.0 ~ 1.0 的分数。
        """
        waves = candidate.get("waves", [])
        if not waves:
            return 0.0
        last_end_idx = waves[-1].get("end_idx", 0)
        # end_idx 越接近 total_bars-1，分数越高
        return last_end_idx / max(total_bars - 1, 1)

    def _calculate_span_score(self, candidate: Dict, total_bars: int) -> float:
        """计算候选波浪的跨度分数（覆盖数据范围的比例）。

        wave1.start_idx 到 wave5.end_idx（或 A.end_idx 到 C.end_idx）
        覆盖的数据范围越广，分数越高。
        返回 0.0 ~ 1.0 的分数。
        """
        waves = candidate.get("waves", [])
        if not waves:
            return 0.0
        start_idx = waves[0].get("start_idx", 0)
        end_idx = waves[-1].get("end_idx", 0)
        span = end_idx - start_idx
        return span / max(total_bars - 1, 1)

    def analyze(self, klines: List[Dict], top_n: int = 3) -> List[Dict]:
        """
        Main analysis entry point.

        Args:
            klines: Binance K-line data. Each dict must contain at least 'close'.
                    Expected keys: open_time, open, high, low, close, volume, close_time.
            top_n:  Maximum number of top-scored candidates to return.

        Returns:
            List of top-N wave candidate dicts, sorted by score descending.
            Each candidate includes:
                - wave_type, wave_pattern, direction
                - waves: list of wave segments with start/end index and price
                - validations: rule validation results
                - score: 0.0-1.0 float
        """
        if not klines:
            logger.warning("analyze: empty klines input")
            return []

        # 1. Extract close prices
        prices: List[float] = []
        for idx, k in enumerate(klines):
            close = k.get("close")
            if close is None:
                logger.warning(f"analyze: kline at index {idx} missing 'close', skipping")
                continue
            prices.append(float(close))

        if len(prices) < 5:
            logger.warning(f"analyze: only {len(prices)} valid close prices, need at least 5")
            return []

        # 2. ZigZag pivot extraction
        pivots = zigzag(prices, deviation=self.deviation)
        if len(pivots) < 3:
            logger.info(f"analyze: only {len(pivots)} pivots found, not enough for wave detection")
            return []

        # 3. NEW: Trend segmentation
        segments = detect_trend_segments(
            pivots, prices, min_pivots=MIN_PIVOTS_PER_SEGMENT, price_tolerance=PRICE_TOLERANCE
        )

        composite_candidates: List[Dict] = []
        if segments:
            segment_candidates: List[List[Dict]] = []
            for seg in segments:
                seg_pivots = pivots[seg.start_pivot_idx : seg.end_pivot_idx + 1]
                if len(seg_pivots) < 3:
                    continue
                cands = _generate_segment_candidates(seg, seg_pivots, prices)
                if cands:
                    segment_candidates.append(cands)

            if len(segment_candidates) == len(segments) and segment_candidates:
                composite_candidates = combine_segments(segment_candidates, segments, prices)

        # 6. Fallback to legacy global analysis if no composites
        if not composite_candidates:
            logger.info("analyze: no composite candidates, falling back to legacy analysis")
            return self._legacy_analyze(pivots, prices, top_n)

        # 7. Score composites
        total_bars = len(prices)
        scored_candidates: List[Dict] = []
        best_span_ratio = 0.0
        for candidate in composite_candidates:
            score = score_composite_candidate(candidate, total_bars)
            candidate["score"] = score

            waves = candidate.get("waves", [])
            if waves:
                span_start = waves[0].get("start_idx", 0)
                span_end = waves[-1].get("end_idx", 0)
                span_ratio = (span_end - span_start) / max(total_bars - 1, 1)
            else:
                span_ratio = 0.0

            best_span_ratio = max(best_span_ratio, span_ratio)
            if span_ratio < self.min_span_ratio:
                continue

            candidate["span_ratio"] = span_ratio
            scored_candidates.append(candidate)

        if not scored_candidates:
            logger.warning(
                f"analyze: all {len(composite_candidates)} composite candidates filtered by span_ratio "
                f"(min_span={self.min_span_ratio}, best_span={best_span_ratio:.3f})"
            )
            logger.info("analyze: no scored composite candidates after span filter, falling back to legacy")
            return self._legacy_analyze(pivots, prices, top_n)

        scored_candidates.sort(key=lambda x: x["score"], reverse=True)

        # 8. Calculate current wave probability for each candidate
        for candidate in scored_candidates:
            prob_data = calculate_composite_wave_probability(candidate, prices)
            candidate["current_wave"] = prob_data["current_wave"]
            candidate["current_wave_probabilities"] = prob_data["probabilities"]
            candidate["current_wave_status"] = prob_data["status"]
            candidate["completed_waves"] = prob_data["completed_waves"]
            candidate["total_segments"] = prob_data.get("total_segments", 0)
            candidate["current_segment_idx"] = prob_data.get("current_segment_idx", 0)
            candidate["zigzag_pivots"] = [(p[0], p[1], p[2]) for p in pivots]

        # 9. Return top N
        top_candidates = scored_candidates[:top_n]
        logger.info(
            f"analyze: {len(segments)} segments, {len(composite_candidates)} composite candidates, "
            f"returning top {len(top_candidates)} (max score={top_candidates[0]['score'] if top_candidates else 0})"
        )
        return top_candidates

    def _legacy_analyze(
        self, pivots: List[Tuple[int, float, str]], prices: List[float], top_n: int
    ) -> List[Dict]:
        """旧版全局分析（回退用）。同时生成新的调整浪类型候选。"""
        impulse_candidates = generate_impulse_candidates(pivots, prices)
        corrective_candidates = generate_corrective_candidates(pivots, prices)
        zigzag_candidates = generate_zigzag_candidates(pivots, prices)
        flat_candidates = generate_flat_candidates(pivots, prices)
        triangle_candidates = generate_triangle_candidates(pivots, prices)
        double_zigzag_candidates = generate_double_zigzag_candidates(pivots, prices)
        all_candidates = (
            impulse_candidates
            + corrective_candidates
            + zigzag_candidates
            + flat_candidates
            + triangle_candidates
            + double_zigzag_candidates
        )

        if not all_candidates:
            logger.info("analyze: no wave candidates generated")
            return []

        total_bars = len(prices)
        scored_candidates: List[Dict] = []
        for candidate in all_candidates:
            wave_type = candidate.get("wave_type", "")
            if wave_type == "impulse":
                validations = validate_impulse_rules(candidate)
            elif wave_type == "zigzag" or wave_type == "double_zigzag":
                validations = validate_zigzag_rules(candidate)
            elif wave_type == "flat":
                validations = validate_flat_rules(candidate)
            elif wave_type == "triangle":
                validations = validate_triangle_rules(candidate)
            else:
                validations = validate_corrective_rules(candidate)

            waves = candidate.get("waves", [])
            if waves:
                span_start = waves[0].get("start_idx", 0)
                span_end = waves[-1].get("end_idx", 0)
                span_ratio = (span_end - span_start) / max(total_bars - 1, 1)
            else:
                span_ratio = 0.0

            if span_ratio < self.min_span_ratio:
                continue

            rule_score = score_candidate(candidate, validations)
            recency_score = self._calculate_recency_score(candidate, total_bars)
            span_score = self._calculate_span_score(candidate, total_bars)
            candidate["score"] = rule_score * 0.5 + recency_score * 0.2 + span_score * 0.3
            candidate["rule_score"] = rule_score
            candidate["recency_score"] = recency_score
            candidate["span_score"] = span_score
            candidate["span_ratio"] = span_ratio
            candidate["validations"] = validations
            scored_candidates.append(candidate)

        scored_candidates.sort(key=lambda x: x["score"], reverse=True)

        for candidate in scored_candidates:
            prob_data = calculate_current_wave_probability(candidate, prices)
            candidate["current_wave"] = prob_data["current_wave"]
            candidate["current_wave_probabilities"] = prob_data["probabilities"]
            candidate["current_wave_status"] = prob_data["status"]
            candidate["completed_waves"] = prob_data["completed_waves"]
            candidate["zigzag_pivots"] = [(p[0], p[1], p[2]) for p in pivots]

        top_candidates = scored_candidates[:top_n]
        logger.info(
            f"analyze (legacy): {len(impulse_candidates)} impulse + {len(corrective_candidates)} corrective + "
            f"{len(zigzag_candidates)} zigzag + {len(flat_candidates)} flat + {len(triangle_candidates)} triangle + "
            f"{len(double_zigzag_candidates)} double_zigzag "
            f"candidates, returning top {len(top_candidates)} (max score={top_candidates[0]['score'] if top_candidates else 0})"
        )
        return top_candidates


def calculate_current_wave_probability(wave_candidate: Dict, prices: List[float]) -> Dict:
    """基于波浪结构和当前价格位置，计算当前可能处于哪个浪的概率分布。

    Returns:
        {
            "current_wave": "wave_5",  # 最高概率的浪
            "probabilities": {
                "wave_5": 0.65,
                "wave_4": 0.25,
                "wave_3": 0.10,
            },
            "status": "forming",  # "forming" | "completed"
        }
    """
    wave_type = wave_candidate.get("wave_type", "impulse")
    direction = wave_candidate.get("direction", "up")
    waves = wave_candidate.get("waves", [])
    current_price = float(prices[-1]) if prices else 0.0

    if not waves:
        return {"current_wave": "unknown", "probabilities": {}, "status": "unknown", "completed_waves": 0}

    # 统计已完成的浪
    completed_count = len(waves)
    last_wave = waves[-1]
    last_end_price = last_wave.get("end_price", current_price)

    probabilities = {}

    if wave_type == "impulse":
        # 推动浪 1-2-3-4-5
        if completed_count >= 5:
            # 所有浪已完成，可能在延伸或开始修正
            probabilities = {"wave_5_extended": 0.5, "corrective_a": 0.3, "wave_5_completed": 0.2}
        elif completed_count == 4:
            # 已完成4浪，当前最可能是 Wave 5 形成中
            # 根据当前价格与 Wave 4 终点的距离调整概率
            wave4_end = last_end_price
            wave3 = waves[2] if len(waves) > 2 else None
            wave3_length = abs(wave3["end_price"] - wave3["start_price"]) if wave3 else 0

            distance_from_wave4 = abs(current_price - wave4_end)
            progress = min(distance_from_wave4 / max(wave3_length * 0.3, 1), 1.0)

            wave5_prob = 0.60 + progress * 0.25  # 0.60 ~ 0.85
            wave4_prob = 0.30 - progress * 0.20  # 0.30 ~ 0.10
            wave3_prob = max(0.10 - progress * 0.05, 0.02)

            probabilities = {"wave_5": wave5_prob, "wave_4": wave4_prob, "wave_3": wave3_prob}
        elif completed_count == 3:
            probabilities = {"wave_4": 0.55, "wave_3": 0.30, "wave_5": 0.15}
        elif completed_count == 2:
            probabilities = {"wave_3": 0.60, "wave_2": 0.25, "wave_4": 0.15}
        elif completed_count == 1:
            probabilities = {"wave_2": 0.55, "wave_1": 0.30, "wave_3": 0.15}
        else:
            probabilities = {"wave_1": 0.70, "wave_2": 0.30}
    elif wave_type == "triangle":
        # 三角形 A-B-C-D-E
        if completed_count >= 5:
            probabilities = {"triangle_completed": 0.6, "breakout_bullish": 0.2, "breakout_bearish": 0.2}
        elif completed_count == 4:
            probabilities = {"wave_e": 0.60, "triangle_completed": 0.25, "wave_d": 0.15}
        elif completed_count == 3:
            probabilities = {"wave_d": 0.55, "wave_c": 0.30, "wave_e": 0.15}
        elif completed_count == 2:
            probabilities = {"wave_c": 0.60, "wave_b": 0.25, "wave_d": 0.15}
        elif completed_count == 1:
            probabilities = {"wave_b": 0.55, "wave_a": 0.30, "wave_c": 0.15}
        else:
            probabilities = {"wave_a": 0.70, "wave_b": 0.30}
    elif wave_type == "double_zigzag":
        # W-X-Y
        if completed_count >= 3:
            probabilities = {"double_zigzag_completed": 0.6, "new_impulse_1": 0.4}
        elif completed_count == 2:
            probabilities = {"wave_y": 0.65, "wave_x": 0.25, "wave_w": 0.10}
        elif completed_count == 1:
            probabilities = {"wave_x": 0.55, "wave_w": 0.30, "wave_y": 0.15}
        else:
            probabilities = {"wave_w": 0.70, "wave_x": 0.30}
    else:
        # 修正浪 A-B-C (corrective, zigzag, flat)
        if completed_count >= 3:
            probabilities = {"corrective_completed": 0.6, "new_impulse_1": 0.4}
        elif completed_count == 2:
            probabilities = {"wave_c": 0.65, "wave_b": 0.25, "wave_a": 0.10}
        elif completed_count == 1:
            probabilities = {"wave_b": 0.55, "wave_a": 0.30, "wave_c": 0.15}
        else:
            probabilities = {"wave_a": 0.70, "wave_b": 0.30}

    # 排序取最高概率
    sorted_probs = sorted(probabilities.items(), key=lambda x: x[1], reverse=True)
    current_wave = sorted_probs[0][0] if sorted_probs else "unknown"

    is_completed = (
        completed_count >= 5 and wave_type == "impulse"
    ) or (
        completed_count >= 3 and wave_type in ("corrective", "zigzag", "flat", "double_zigzag")
    ) or (
        completed_count >= 5 and wave_type == "triangle"
    )

    return {
        "current_wave": current_wave,
        "probabilities": probabilities,
        "status": "completed" if is_completed else "forming",
        "completed_waves": completed_count,
    }
