"""
Elliott Wave Chart Generator

Renders candlestick charts with Elliott Wave annotations,
Fibonacci retracement levels, and multi-scenario projections.
"""

import os
from typing import List, Dict, Tuple, Optional, Any
from datetime import datetime

import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import matplotlib.gridspec as gridspec
import matplotlib.ticker as ticker
from matplotlib.patches import Rectangle, Circle
from loguru import logger


def _ensure_dir(path: str) -> None:
    """Ensure the parent directory for a file path exists."""
    dir_name = os.path.dirname(path)
    if dir_name:
        os.makedirs(dir_name, exist_ok=True)


def _format_price_label(price: Optional[float]) -> str:
    """Format a price for chart labels; preserve precision for low-priced tokens."""
    if price is None:
        return ""
    p = float(price)
    if p >= 1:
        return f"{p:,.0f}"
    elif p >= 0.01:
        return f"{p:,.4f}"
    else:
        return f"{p:,.6f}"


def _ms_to_date_num(ms_ts: float) -> float:
    """Convert millisecond timestamp to matplotlib date number."""
    return mdates.date2num(datetime.fromtimestamp(ms_ts / 1000.0))


def _draw_candlestick(
    ax,
    x: float,
    open_price: float,
    high: float,
    low: float,
    close: float,
    width: float = 0.6,
    alpha: float = 0.9,
) -> None:
    """Draw a single candlestick on the given Axes."""
    color = "#26a69a" if close >= open_price else "#ef5350"
    edge_color = color

    body_bottom = min(open_price, close)
    body_height = abs(close - open_price)
    if body_height == 0:
        body_height = 0.0001  # avoid zero-height rectangles

    # Wick
    ax.plot([x, x], [low, high], color=edge_color, linewidth=0.8, alpha=alpha, zorder=2)

    # Body
    rect = Rectangle(
        (x - width / 2, body_bottom),
        width,
        body_height,
        facecolor=color,
        edgecolor=edge_color,
        linewidth=0.8,
        alpha=alpha,
        zorder=3,
    )
    ax.add_patch(rect)


def _kline_to_prices(klines: List[Dict]) -> Tuple[List[float], List[float], List[float], List[float], List[float]]:
    """Extract open/high/low/close/times from klines."""
    opens, highs, lows, closes, times = [], [], [], [], []
    for k in klines:
        opens.append(float(k.get("open", 0)))
        highs.append(float(k.get("high", 0)))
        lows.append(float(k.get("low", 0)))
        closes.append(float(k.get("close", 0)))
        times.append(float(k.get("open_time", 0)))
    return opens, highs, lows, closes, times


def plot_raw_candlestick(
    klines: List[Dict],
    symbol: str,
    timeframe: str,
    output_path: str,
    pivots: Optional[List[Tuple[int, float, str]]] = None,
    show_zigzag: bool = True,
) -> str:
    """Generate a raw candlestick chart with optional ZigZag pivot annotations."""
    _ensure_dir(output_path)
    if not klines:
        logger.warning("plot_raw_candlestick: empty klines")
        return ""
    
    opens, highs, lows, closes, times = _kline_to_prices(klines)
    dates = [_ms_to_date_num(t) for t in times]
    
    fig, ax = plt.subplots(figsize=(14, 8), dpi=150)
    n_bars = len(klines)
    bar_width = 0.6 * (dates[1] - dates[0]) if n_bars > 1 else 0.0005
    for i in range(n_bars):
        _draw_candlestick(ax, dates[i], opens[i], highs[i], lows[i], closes[i], width=bar_width)

    # --- ZigZag pivot annotations ---
    if show_zigzag and pivots:
        valid_pivots: List[Tuple[int, float, str]] = []
        for p in pivots:
            if not isinstance(p, (list, tuple)) or len(p) < 3:
                continue
            idx = int(p[0])
            price = float(p[1])
            ptype = str(p[2]).lower()
            if 0 <= idx < n_bars:
                valid_pivots.append((idx, price, ptype))

        if valid_pivots:
            conn_x = [dates[idx] for idx, _, _ in valid_pivots]
            conn_y = [price for _, price, _ in valid_pivots]
            ax.plot(conn_x, conn_y, color="#2962ff", linestyle="--", linewidth=1.2, alpha=0.8, zorder=4)

            for idx, price, ptype in valid_pivots:
                color = "#2962ff" if ptype == "peak" else "#ff6f00"
                ax.plot(dates[idx], price, marker="o", color=color, markersize=6, zorder=5)

    ax.set_title(f"{symbol}/{timeframe} - Raw Chart + ZigZag Pivots for Analysis", fontsize=14, fontweight="bold", pad=10)
    ax.set_xlabel("Date", fontsize=10)
    ax.set_ylabel("Price", fontsize=10)
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%m-%d %H:%M"))
    ax.xaxis.set_major_locator(mdates.AutoDateLocator())
    fig.autofmt_xdate(rotation=30)
    ax.grid(True, linestyle="--", alpha=0.3, zorder=0)
    ax.set_xlim(dates[0] - (dates[1] - dates[0]) * 0.5 if len(dates) > 1 else dates[0] - 0.01,
                dates[-1] + (dates[-1] - dates[0]) * 0.05)
    
    # Logarithmic price scale
    # 确保价格数据全部为正，对数坐标要求 y > 0
    min_price = min(lows)
    if min_price <= 0:
        # 将所有价格平移，使最小值变为正值
        shift = abs(min_price) + 0.0001
        lows = [l + shift for l in lows]
        highs = [h + shift for h in highs]
        opens = [o + shift for o in opens]
        closes = [c + shift for c in closes]
    ax.set_yscale('log')
    ax.yaxis.set_major_formatter(ticker.FuncFormatter(lambda x, pos: f'{x:,.0f}' if x >= 1 else f'{x:.4f}'))
    ax.set_ylim(min(lows) * 0.92, max(highs) * 1.08)
    
    plt.tight_layout()
    fig.savefig(output_path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    logger.info(f"plot_raw_candlestick: saved raw chart to {output_path}")
    return output_path


def plot_elliott_wave(
    klines: List[Dict],
    wave_candidate: Dict,
    symbol: str,
    timeframe: str,
    output_path: str,
) -> str:
    """
    Draw a candlestick chart with Elliott Wave annotations.

    Chart contents:
        1. Candlesticks (green bullish, red bearish)
        2. Wave labels (1, 2, 3, 4, 5, A, B, C) with background boxes
        3. Dashed connecting lines between wave segments
        4. Fibonacci retracement levels for Wave 2 and Wave 4
        5. Title / subtitle with pattern, score, and current wave info
        6. Formatted time axis labels

    Args:
        klines:        Binance K-line data list.
        wave_candidate: Wave dict from ElliottWaveAnalyzer.
        symbol:        Trading pair symbol (e.g. "BTCUSDT").
        timeframe:     Timeframe string (e.g. "1h", "4h", "1d").
        output_path:   Path where the PNG image will be saved.

    Returns:
        The saved file path.
    """
    _ensure_dir(output_path)

    if not klines:
        logger.warning("plot_elliott_wave: empty klines")
        return ""

    opens, highs, lows, closes, times = _kline_to_prices(klines)
    dates = [_ms_to_date_num(t) for t in times]

    fig, ax = plt.subplots(figsize=(14, 8), dpi=150)

    # --- 1. Candlesticks ---
    n_bars = len(klines)
    bar_width = 0.6 * (dates[1] - dates[0]) if n_bars > 1 else 0.0005
    for i in range(n_bars):
        _draw_candlestick(ax, dates[i], opens[i], highs[i], lows[i], closes[i], width=bar_width)

    # --- 2. Wave annotations ---
    waves = wave_candidate.get("waves", [])
    direction = wave_candidate.get("direction", "up")
    wave_type = wave_candidate.get("wave_type", "impulse")

    wave_labels = []
    for w in waves:
        wave_label = w.get("wave", "")
        if wave_label:
            wave_labels.append(str(wave_label))
    if not wave_labels:
        if wave_type == "impulse":
            wave_labels = ["1", "2", "3", "4", "5"]
        else:
            wave_labels = ["A", "B", "C"]

    label_x: List[float] = []
    label_y: List[float] = []
    label_texts: List[str] = []

    for idx, w in enumerate(waves):
        if idx >= len(wave_labels):
            break
        end_idx = int(w["end_idx"])
        if 0 <= end_idx < n_bars:
            x = dates[end_idx]
            # Place label above peak, below trough
            label = wave_labels[idx]
            is_peak_label = str(label) in ("1", "3", "5", "A", "C", "W", "Y") or (str(label).startswith("(") and str(label) in ("(i)", "(iii)", "(v)"))
            if direction == "up":
                if is_peak_label:
                    y = highs[end_idx] + (max(highs) - min(lows)) * 0.015
                else:
                    y = lows[end_idx] - (max(highs) - min(lows)) * 0.025
            else:
                if is_peak_label:
                    y = lows[end_idx] - (max(highs) - min(lows)) * 0.025
                else:
                    y = highs[end_idx] + (max(highs) - min(lows)) * 0.015
            label_x.append(x)
            label_y.append(y)
            label_texts.append(wave_labels[idx])

    # Draw dashed connecting line between wave start/end points
    conn_x: List[float] = []
    conn_y: List[float] = []
    for w in waves:
        s_idx = int(w["start_idx"])
        e_idx = int(w["end_idx"])
        if 0 <= s_idx < n_bars and 0 <= e_idx < n_bars:
            conn_x.extend([dates[s_idx], dates[e_idx], None])
            conn_y.extend([w["start_price"], w["end_price"], None])
    if conn_x:
        ax.plot(conn_x, conn_y, color="#2962ff", linestyle="--", linewidth=1.2, alpha=0.8, zorder=4)

    # Draw labels with background
    for x, y, txt in zip(label_x, label_y, label_texts):
        ax.text(
            x, y, txt,
            fontsize=14,
            fontweight="bold",
            color="#1a237e",
            ha="center",
            va="center",
            bbox=dict(boxstyle="round,pad=0.2", facecolor="#fff9c4", edgecolor="#1a237e", alpha=0.95),
            zorder=5,
        )

    # --- 3. Fibonacci retracement lines (Wave 2 and Wave 4) ---
    if wave_type in ("impulse", "composite") and len(waves) >= 4:
        fib_colors = ["#9e9e9e", "#757575", "#616161"]
        fib_labels = ["38.2%", "50.0%", "61.8%"]
        fib_ratios = [0.382, 0.500, 0.618]

        for wave_idx in (1, 3):  # Wave 2 and Wave 4
            prev_wave = waves[wave_idx - 1]
            curr_wave = waves[wave_idx]
            prev_start = prev_wave["start_price"]
            prev_end = prev_wave["end_price"]
            fib_range = abs(prev_end - prev_start)
            if fib_range == 0:
                continue

            for ratio, color, label in zip(fib_ratios, fib_colors, fib_labels):
                if direction == "up":
                    level = max(prev_start, prev_end) - fib_range * ratio
                else:
                    level = min(prev_start, prev_end) + fib_range * ratio

                # Draw horizontal line across the chart
                ax.axhline(
                    y=level,
                    color=color,
                    linestyle=":",
                    linewidth=0.8,
                    alpha=0.7,
                    xmin=0.02,
                    xmax=0.98,
                    zorder=1,
                )
                # Right-side label
                ax.text(
                    dates[-1] + (dates[-1] - dates[0]) * 0.005,
                    level,
                    f"W{wave_idx + 1} {label}",
                    fontsize=7,
                    color=color,
                    va="center",
                    ha="left",
                    zorder=5,
                )

    # --- 4. Title & Subtitle ---
    pattern = wave_candidate.get("wave_pattern", "Unknown")
    score = wave_candidate.get("score", 0.0)
    current_wave = wave_labels[-1] if wave_labels else "?"
    title = f"{symbol}/{timeframe} - Elliott Wave Analysis"
    subtitle = f"Wave Pattern: {pattern} | Score: {int(score * 100)}% | Current: Wave {current_wave}"

    ax.set_title(title, fontsize=14, fontweight="bold", pad=10)
    ax.text(0.5, 1.02, subtitle, transform=ax.transAxes, fontsize=10, ha="center", color="#424242")

    # --- 5. Current wave probability annotation ---
    current_wave_probs = wave_candidate.get("current_wave_probabilities", {})
    if current_wave_probs:
        prob_text = "Current Wave Probabilities:\n"
        for wave_name, prob in sorted(current_wave_probs.items(), key=lambda x: x[1], reverse=True)[:3]:
            prob_text += f"  {wave_name}: {prob*100:.0f}%\n"

        ax.text(
            0.02, 0.98, prob_text,
            transform=ax.transAxes,
            fontsize=9,
            verticalalignment='top',
            bbox=dict(boxstyle='round', facecolor='wheat', alpha=0.8),
            family='monospace',
        )

    # --- 6. Highlight current forming wave ---
    if waves and len(klines) > 0:
        last_wave = waves[-1]
        last_end_idx = int(last_wave["end_idx"])
        last_end_price = last_wave["end_price"]
        if 0 <= last_end_idx < n_bars:
            # 红色虚线：最后一个 completed wave 终点 → 当前最新K线
            ax.plot(
                [dates[last_end_idx], dates[-1]],
                [last_end_price, closes[-1]],
                color="#d32f2f",
                linestyle="--",
                linewidth=2.0,
                alpha=0.8,
                zorder=5,
                label="Current Wave (forming)" if waves else None,
            )

    # --- 7. Axis formatting ---
    ax.set_xlabel("Date", fontsize=10)
    ax.set_ylabel("Price", fontsize=10)

    # Time axis
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%m-%d %H:%M"))
    ax.xaxis.set_major_locator(mdates.AutoDateLocator())
    fig.autofmt_xdate(rotation=30)

    # Grid and margins
    ax.grid(True, linestyle="--", alpha=0.3, zorder=0)
    ax.set_xlim(dates[0] - (dates[1] - dates[0]) * 0.5 if len(dates) > 1 else dates[0] - 0.01,
                dates[-1] + (dates[-1] - dates[0]) * 0.05 if len(dates) > 1 else dates[-1] + 0.01)
    ax.set_ylim(min(lows) - (max(highs) - min(lows)) * 0.08,
                max(highs) + (max(highs) - min(lows)) * 0.08)

    plt.tight_layout()
    fig.savefig(output_path, dpi=150, bbox_inches="tight")
    plt.close(fig)

    logger.info(f"plot_elliott_wave: saved chart to {output_path}")
    return output_path


def plot_kimi_annotated_wave(
    klines: List[Dict],
    kimi_structure: Dict[str, Any],
    symbol: str,
    timeframe: str,
    output_path: str,
) -> str:
    """
    Draw a candlestick chart annotated with Kimi's wave structure.
    
    Supports multiple wave types:
    - Impulse waves: 1,2,3,4,5 (blue dashed + yellow labels)
    - Corrective waves: A,B,C (orange dashed + light orange labels)
    - Double zigzag: W,X,Y (green dashed + light green labels)
    - Sub-waves: (i),(ii),(iii),(iv),(v) (purple small font)
    """
    _ensure_dir(output_path)
    if not klines:
        logger.warning("plot_kimi_annotated_wave: empty klines")
        return ""
    
    opens, highs, lows, closes, times = _kline_to_prices(klines)
    dates = [_ms_to_date_num(t) for t in times]
    n_bars = len(klines)
    
    fig, ax = plt.subplots(figsize=(14, 8), dpi=150)
    
    # Draw candlesticks
    bar_width = 0.6 * (dates[1] - dates[0]) if n_bars > 1 else 0.0005
    for i in range(n_bars):
        _draw_candlestick(ax, dates[i], opens[i], highs[i], lows[i], closes[i], width=bar_width)
    
    # Wave type styles
    wave_styles = {
        "impulse": {"color": "#2962ff", "facecolor": "#fff9c4", "edgecolor": "#1a237e"},
        "corrective": {"color": "#ff6f00", "facecolor": "#ffe0b2", "edgecolor": "#e65100"},
        "zigzag": {"color": "#0288d1", "facecolor": "#e1f5fe", "edgecolor": "#01579b"},
        "flat": {"color": "#f57c00", "facecolor": "#ffe0b2", "edgecolor": "#e65100"},
        "triangle": {"color": "#7b1fa2", "facecolor": "#e1bee7", "edgecolor": "#4a148c"},
        "double_zigzag": {"color": "#2e7d32", "facecolor": "#c8e6c9", "edgecolor": "#1b5e20"},
        "sub": {"color": "#7b1fa2", "facecolor": "#e1bee7", "edgecolor": "#4a148c"},
    }
    
    def _get_wave_style(label: str, wave_type_hint: str = "") -> Dict[str, str]:
        if label.startswith("(") and label.endswith(")"):
            return wave_styles["sub"]
        if wave_type_hint and wave_type_hint in wave_styles:
            return wave_styles[wave_type_hint]
        if label in ("W", "X", "Y"):
            return wave_styles["double_zigzag"]
        if label in ("A", "B", "C", "D", "E"):
            return wave_styles["corrective"]
        return wave_styles["impulse"]
    
    # Draw waves from kimi_structure
    waves = kimi_structure.get("waves", [])
    # Only show the most recent 5 waves to focus on near-term price action
    waves = waves[-5:] if len(waves) > 5 else waves
    direction = kimi_structure.get("direction", "up")
    
    def _get_wave_price(w: Dict[str, Any], idx: int) -> float:
        """Return high/low/close price at idx based on wave label parity."""
        label = str(w.get("label", ""))
        is_peak = label in ("1", "3", "5", "A", "C", "W", "Y") or label in ("(i)", "(iii)", "(v)")
        is_trough = label in ("2", "4", "B", "D", "E", "X") or label in ("(ii)", "(iv)")
        if is_peak:
            return highs[idx] if 0 <= idx < n_bars else closes[idx]
        elif is_trough:
            return lows[idx] if 0 <= idx < n_bars else closes[idx]
        else:
            return closes[idx]
    
    # Draw dashed connecting lines
    conn_x: List[float] = []
    conn_y: List[float] = []
    for w in waves:
        s_idx = int(w.get("start_idx", 0))
        e_idx = int(w.get("end_idx", 0))
        if 0 <= s_idx < n_bars and 0 <= e_idx < n_bars:
            conn_x.extend([dates[s_idx], dates[e_idx], None])
            # Use actual price at indices if available, else approximate
            sp = _get_wave_price(w, s_idx)
            ep = _get_wave_price(w, e_idx)
            conn_y.extend([sp, ep, None])
    if conn_x:
        ax.plot(conn_x, conn_y, color="#2962ff", linestyle="--", linewidth=1.2, alpha=0.8, zorder=4)
    
    # Draw labels
    wave_type_hint = kimi_structure.get("wave_type", "")
    for w in waves:
        label = str(w.get("label", ""))
        if not label:
            continue
        end_idx = int(w.get("end_idx", 0))
        if 0 <= end_idx < n_bars:
            x = dates[end_idx]
            style = _get_wave_style(label, wave_type_hint)
            is_sub = label.startswith("(") and label.endswith(")")
            
            if direction == "up":
                if label in ("1", "3", "5", "A", "C", "W", "Y") or (label.startswith("(") and label in ("(i)", "(iii)", "(v)")):
                    y = highs[end_idx] + (max(highs) - min(lows)) * (0.01 if is_sub else 0.015)
                else:
                    y = lows[end_idx] - (max(highs) - min(lows)) * (0.02 if is_sub else 0.025)
            else:
                if label in ("1", "3", "5", "A", "C", "W", "Y") or (label.startswith("(") and label in ("(i)", "(iii)", "(v)")):
                    y = lows[end_idx] - (max(highs) - min(lows)) * (0.02 if is_sub else 0.025)
                else:
                    y = highs[end_idx] + (max(highs) - min(lows)) * (0.01 if is_sub else 0.015)
            
            fontsize = 10 if is_sub else 14
            ax.text(
                x, y, label,
                fontsize=fontsize,
                fontweight="bold",
                color=style["edgecolor"],
                ha="center",
                va="center",
                bbox=dict(boxstyle="round,pad=0.2", facecolor=style["facecolor"], edgecolor=style["edgecolor"], alpha=0.95),
                zorder=5,
            )
    
    # Draw sub_waves if present
    sub_waves = kimi_structure.get("sub_waves", [])
    # Only show the most recent 5 sub-waves to focus on near-term price action
    sub_waves = sub_waves[-5:] if len(sub_waves) > 5 else sub_waves
    for sw in sub_waves:
        label = str(sw.get("label", ""))
        if not label:
            continue
        end_idx = int(sw.get("end_idx", 0))
        if 0 <= end_idx < n_bars:
            x = dates[end_idx]
            style = wave_styles["sub"]
            if direction == "up":
                if label in ("(i)", "(iii)", "(v)"):
                    y = highs[end_idx] + (max(highs) - min(lows)) * 0.01
                else:
                    y = lows[end_idx] - (max(highs) - min(lows)) * 0.02
            else:
                if label in ("(i)", "(iii)", "(v)"):
                    y = lows[end_idx] - (max(highs) - min(lows)) * 0.02
                else:
                    y = highs[end_idx] + (max(highs) - min(lows)) * 0.01
            ax.text(
                x, y, label,
                fontsize=10,
                fontweight="bold",
                color=style["edgecolor"],
                ha="center",
                va="center",
                bbox=dict(boxstyle="round,pad=0.2", facecolor=style["facecolor"], edgecolor=style["edgecolor"], alpha=0.95),
                zorder=5,
            )
    
    # Title
    wave_pattern = kimi_structure.get("wave_pattern", "Unknown")
    current_wave = kimi_structure.get("current_wave", "")
    overall_confidence = kimi_structure.get("overall_confidence", 0.0)
    ax.set_title(
        f"{symbol}/{timeframe} - Kimi AI Annotated | {wave_pattern}",
        fontsize=14, fontweight="bold", pad=10,
    )
    if current_wave:
        ax.text(0.5, 1.02, f"Current: {current_wave} | Confidence: {int(overall_confidence * 100)}%", 
                transform=ax.transAxes, fontsize=10, ha="center", color="#424242")
    
    # Support and Resistance levels from projections
    projections = kimi_structure.get("projections", [])
    support_levels: List[float] = []
    resistance_levels: List[float] = []
    for proj in projections:
        support_levels.extend(proj.get("support_levels", []))
        resistance_levels.extend(proj.get("resistance_levels", []))
    # Deduplicate and sort
    support_levels = sorted(list(set([float(s) for s in support_levels if s])))
    resistance_levels = sorted(list(set([float(r) for r in resistance_levels if r])))

    for level in support_levels:
        if level > 0 and min(lows) * 0.5 <= level <= max(highs) * 1.5:
            ax.axhline(y=level, color='#22c55e', linestyle='--', alpha=0.5, linewidth=1, zorder=1)
            ax.text(
                dates[-1] + (dates[-1] - dates[0]) * 0.005,
                level,
                f"Support {_format_price_label(level)}",
                fontsize=7,
                color='#22c55e',
                va='center',
                ha='left',
                zorder=5,
            )
    for level in resistance_levels:
        if level > 0 and min(lows) * 0.5 <= level <= max(highs) * 1.5:
            ax.axhline(y=level, color='#ef4444', linestyle='--', alpha=0.5, linewidth=1, zorder=1)
            ax.text(
                dates[-1] + (dates[-1] - dates[0]) * 0.005,
                level,
                f"Resistance {_format_price_label(level)}",
                fontsize=7,
                color='#ef4444',
                va='center',
                ha='left',
                zorder=5,
            )

    # Key Support / Resistance from support_resistance_analysis
    sr_analysis = kimi_structure.get("support_resistance_analysis", {})
    key_support = sr_analysis.get("key_support")
    key_resistance = sr_analysis.get("key_resistance")

    if key_support:
        ax.axhline(y=key_support, color='#22c55e', linestyle='-', alpha=0.7, linewidth=1.5, zorder=3)
        ax.text(
            dates[-1] + (dates[-1] - dates[0]) * 0.005,
            key_support,
            f"Key Support {_format_price_label(key_support)}",
            fontsize=8,
            color='#22c55e',
            va='center',
            ha='left',
            zorder=5,
        )
    if key_resistance:
        ax.axhline(y=key_resistance, color='#ef4444', linestyle='-', alpha=0.7, linewidth=1.5, zorder=3)
        ax.text(
            dates[-1] + (dates[-1] - dates[0]) * 0.005,
            key_resistance,
            f"Key Resistance {_format_price_label(key_resistance)}",
            fontsize=8,
            color='#ef4444',
            va='center',
            ha='left',
            zorder=5,
        )

    # Breakout / directional bias annotation box
    directional_bias = kimi_structure.get("directional_bias", {})
    primary_direction = directional_bias.get("primary_direction", "")
    primary_probability = directional_bias.get("primary_probability", 0.0)
    breakout_direction = sr_analysis.get("breakout_direction", "")
    breakout_confirmed = sr_analysis.get("breakout_confirmed", False)
    sr_text = sr_analysis.get("analysis", "")

    info_lines = []
    if primary_direction:
        info_lines.append(f"Bias: {primary_direction.upper()} {primary_probability*100:.0f}%")
    if breakout_direction:
        info_lines.append(f"Breakout: {breakout_direction.upper()} {'confirmed' if breakout_confirmed else 'forming'}")
    if sr_text:
        info_lines.append(sr_text[:120])
    if info_lines:
        ax.text(
            0.02, 0.98, "\n".join(info_lines),
            transform=ax.transAxes,
            fontsize=9,
            verticalalignment='top',
            color='black',
            bbox=dict(boxstyle='round', facecolor='wheat', alpha=0.85),
            zorder=6,
        )

    # Axis formatting
    ax.set_xlabel("Date", fontsize=10)
    ax.set_ylabel("Price", fontsize=10)
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%m-%d %H:%M"))
    ax.xaxis.set_major_locator(mdates.AutoDateLocator())
    fig.autofmt_xdate(rotation=30)
    ax.grid(True, linestyle="--", alpha=0.3, zorder=0)
    ax.set_xlim(dates[0] - (dates[1] - dates[0]) * 0.5 if len(dates) > 1 else dates[0] - 0.01,
                dates[-1] + (dates[-1] - dates[0]) * 0.05)
    # Logarithmic price scale
    min_price = min(lows)
    if min_price <= 0:
        shift = abs(min_price) + 0.0001
        lows = [l + shift for l in lows]
        highs = [h + shift for h in highs]
        opens = [o + shift for o in opens]
        closes = [c + shift for c in closes]
    ax.set_yscale('log')
    ax.yaxis.set_major_formatter(ticker.FuncFormatter(lambda x, pos: f'{x:,.0f}' if x >= 1 else f'{x:.4f}'))
    ax.set_ylim(min(lows) * 0.92, max(highs) * 1.08)
    
    plt.tight_layout()
    fig.savefig(output_path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    logger.info(f"plot_kimi_annotated_wave: saved chart to {output_path}")
    return output_path


def plot_wave_projections(
    klines: List[Dict],
    wave_candidate: Dict,
    projections: List[Dict],
    output_path: str,
) -> str:
    """
    Draw a chart showing the current wave plus multiple future projections.

    Chart contents:
        1. Confirmed historical candlesticks (solid candles)
        2. Current wave annotation (labels + dashed line)
        3. Three projection scenarios (dashed lines, different colors)
           - bullish: green dashed
           - bearish: red dashed
           - neutral: gray dashed
        4. Target price horizontal lines + labels

    Args:
        klines:        Binance K-line data list.
        wave_candidate: Current wave dict from ElliottWaveAnalyzer.
        projections:   List of projection dicts:
            [
              {"scenario": "bullish", "description": "Wave 5 Extension", "target_price": 75000},
              {"scenario": "bearish", "description": "ABC Correction", "target_price": 58000},
              {"scenario": "neutral", "description": "Sideways", "target_price": 65000},
            ]
        output_path:   Path where the PNG image will be saved.

    Returns:
        The saved file path.
    """
    _ensure_dir(output_path)

    if not klines:
        logger.warning("plot_wave_projections: empty klines")
        return ""

    opens, highs, lows, closes, times = _kline_to_prices(klines)
    dates = [_ms_to_date_num(t) for t in times]

    fig, ax = plt.subplots(figsize=(14, 8), dpi=150)

    # --- 1. Candlesticks ---
    n_bars = len(klines)
    bar_width = 0.6 * (dates[1] - dates[0]) if n_bars > 1 else 0.0005
    for i in range(n_bars):
        _draw_candlestick(ax, dates[i], opens[i], highs[i], lows[i], closes[i], width=bar_width)

    # --- 2. Current wave annotation ---
    waves = wave_candidate.get("waves", [])
    direction = wave_candidate.get("direction", "up")
    wave_type = wave_candidate.get("wave_type", "impulse")

    wave_labels = []
    for w in waves:
        wave_label = w.get("wave", "")
        if wave_label:
            wave_labels.append(str(wave_label))
    if not wave_labels:
        if wave_type == "impulse":
            wave_labels = ["1", "2", "3", "4", "5"]
        else:
            wave_labels = ["A", "B", "C"]

    # Draw dashed connecting line for current wave
    conn_x: List[float] = []
    conn_y: List[float] = []
    for w in waves:
        s_idx = int(w["start_idx"])
        e_idx = int(w["end_idx"])
        if 0 <= s_idx < n_bars and 0 <= e_idx < n_bars:
            conn_x.extend([dates[s_idx], dates[e_idx], None])
            conn_y.extend([w["start_price"], w["end_price"], None])
    if conn_x:
        ax.plot(conn_x, conn_y, color="#2962ff", linestyle="--", linewidth=1.2, alpha=0.8, zorder=4)

    # Draw labels
    for idx, w in enumerate(waves):
        if idx >= len(wave_labels):
            break
        end_idx = int(w["end_idx"])
        if 0 <= end_idx < n_bars:
            x = dates[end_idx]
            label = wave_labels[idx]
            is_peak_label = str(label) in ("1", "3", "5", "A", "C", "W", "Y") or (str(label).startswith("(") and str(label) in ("(i)", "(iii)", "(v)"))
            if direction == "up":
                if is_peak_label:
                    y = highs[end_idx] + (max(highs) - min(lows)) * 0.015
                else:
                    y = lows[end_idx] - (max(highs) - min(lows)) * 0.025
            else:
                if is_peak_label:
                    y = lows[end_idx] - (max(highs) - min(lows)) * 0.025
                else:
                    y = highs[end_idx] + (max(highs) - min(lows)) * 0.015
            ax.text(
                x, y, wave_labels[idx],
                fontsize=14,
                fontweight="bold",
                color="#1a237e",
                ha="center",
                va="center",
                bbox=dict(boxstyle="round,pad=0.2", facecolor="#fff9c4", edgecolor="#1a237e", alpha=0.95),
                zorder=5,
            )

    # --- 3. Projection scenarios ---
    scenario_colors = {
        "bullish": "#2e7d32",
        "bearish": "#c62828",
        "neutral": "#757575",
    }
    scenario_styles = {
        "bullish": (0, (5, 2)),
        "bearish": (0, (5, 2)),
        "neutral": (0, (3, 1, 1, 1)),
    }

    last_date = dates[-1]
    last_price = closes[-1]
    date_span = (dates[-1] - dates[0]) if len(dates) > 1 else 1.0
    projection_horizon = date_span * 0.25  # extend 25% of chart width

    for proj in projections:
        scenario = proj.get("scenario", "neutral")
        target_price = float(proj.get("target_price", last_price))
        description = proj.get("description", scenario)
        color = scenario_colors.get(scenario, "#757575")
        linestyle = scenario_styles.get(scenario, (0, (3, 1, 1, 1)))

        proj_dates = [last_date, last_date + projection_horizon]
        proj_prices = [last_price, target_price]

        ax.plot(
            proj_dates, proj_prices,
            color=color,
            linestyle=linestyle,
            linewidth=1.8,
            alpha=0.9,
            zorder=4,
            label=f"{scenario.upper()}: {description}",
        )

        # Target horizontal line + label
        ax.axhline(
            y=target_price,
            color=color,
            linestyle=":",
            linewidth=0.8,
            alpha=0.6,
            xmin=0.70,
            xmax=0.98,
            zorder=1,
        )
        ax.text(
            last_date + projection_horizon * 1.02,
            target_price,
            f"{target_price:,.2f}",
            fontsize=8,
            color=color,
            va="center",
            ha="left",
            zorder=5,
        )

    # --- 4. Legend ---
    if projections:
        ax.legend(loc="upper left", fontsize=9, framealpha=0.9)

    # --- 5. Title ---
    pattern = wave_candidate.get("wave_pattern", "Unknown")
    score = wave_candidate.get("score", 0.0)
    ax.set_title(
        f"Wave Projection Analysis | Pattern: {pattern} | Score: {int(score * 100)}%",
        fontsize=14,
        fontweight="bold",
        pad=10,
    )

    # --- 6. Axis formatting ---
    ax.set_xlabel("Date", fontsize=10)
    ax.set_ylabel("Price", fontsize=10)

    ax.xaxis.set_major_formatter(mdates.DateFormatter("%m-%d %H:%M"))
    ax.xaxis.set_major_locator(mdates.AutoDateLocator())
    fig.autofmt_xdate(rotation=30)

    ax.grid(True, linestyle="--", alpha=0.3, zorder=0)
    ax.set_xlim(
        dates[0] - (dates[1] - dates[0]) * 0.5 if len(dates) > 1 else dates[0] - 0.01,
        dates[-1] + projection_horizon * 1.15,
    )

    all_prices = highs + lows + [p.get("target_price", last_price) for p in projections]
    ax.set_ylim(
        min(all_prices) - (max(all_prices) - min(all_prices)) * 0.10,
        max(all_prices) + (max(all_prices) - min(all_prices)) * 0.10,
    )

    plt.tight_layout()
    fig.savefig(output_path, dpi=150, bbox_inches="tight")
    plt.close(fig)

    logger.info(f"plot_wave_projections: saved chart to {output_path}")
    return output_path


def plot_elliott_wave_unified(
    klines: List[Dict],
    wave_candidate: Dict,
    projections: List[Dict],
    symbol: str,
    timeframe: str,
    output_path: str,
) -> str:
    """
    Draw a unified Elliott Wave chart with left panel (candlestick + annotations + projections)
    and right panel (probabilities + projections + status info).
    """
    _ensure_dir(output_path)

    if not klines:
        logger.warning("plot_elliott_wave_unified: empty klines")
        return ""

    opens, highs, lows, closes, times = _kline_to_prices(klines)
    dates = [_ms_to_date_num(t) for t in times]
    n_bars = len(klines)
    bar_width = 0.6 * (dates[1] - dates[0]) if n_bars > 1 else 0.0005
    date_span = (dates[-1] - dates[0]) if len(dates) > 1 else 1.0

    fig = plt.figure(figsize=(16, 9), dpi=150, facecolor='#1a1a1a')
    gs = gridspec.GridSpec(1, 2, width_ratios=[4, 1], wspace=0.02)

    # --- Left panel: Main chart ---
    ax_main = fig.add_subplot(gs[0, 0])
    ax_main.set_facecolor('#1a1a1a')
    ax_main.tick_params(colors='white')
    ax_main.xaxis.label.set_color('white')
    ax_main.yaxis.label.set_color('white')
    ax_main.title.set_color('white')

    # 1. Candlesticks
    for i in range(n_bars):
        _draw_candlestick(ax_main, dates[i], opens[i], highs[i], lows[i], closes[i], width=bar_width)

    # 2. Wave annotations
    waves = wave_candidate.get("waves", [])
    # Only show the most recent 5 waves to focus on near-term price action
    waves = waves[-5:] if len(waves) > 5 else waves
    direction = wave_candidate.get("direction", "up")
    wave_type = wave_candidate.get("wave_type", "impulse")

    wave_labels = []
    for w in waves:
        wave_label = w.get("wave", "")
        if wave_label:
            wave_labels.append(str(wave_label))
    if not wave_labels:
        if wave_type == "impulse":
            wave_labels = ["1", "2", "3", "4", "5"]
        else:
            wave_labels = ["A", "B", "C"]

    label_x: List[float] = []
    label_y: List[float] = []
    label_texts: List[str] = []

    for idx, w in enumerate(waves):
        if idx >= len(wave_labels):
            break
        end_idx = int(w["end_idx"])
        if 0 <= end_idx < n_bars:
            x = dates[end_idx]
            label = wave_labels[idx]
            is_peak_label = str(label) in ("1", "3", "5", "A", "C", "W", "Y") or (str(label).startswith("(") and str(label) in ("(i)", "(iii)", "(v)"))
            if direction == "up":
                if is_peak_label:
                    y = highs[end_idx] + (max(highs) - min(lows)) * 0.015
                else:
                    y = lows[end_idx] - (max(highs) - min(lows)) * 0.025
            else:
                if is_peak_label:
                    y = lows[end_idx] - (max(highs) - min(lows)) * 0.025
                else:
                    y = highs[end_idx] + (max(highs) - min(lows)) * 0.015
            label_x.append(x)
            label_y.append(y)
            label_texts.append(wave_labels[idx])

    # Dashed connecting line between completed waves
    conn_x: List[float] = []
    conn_y: List[float] = []
    for w in waves:
        s_idx = int(w["start_idx"])
        e_idx = int(w["end_idx"])
        if 0 <= s_idx < n_bars and 0 <= e_idx < n_bars:
            conn_x.extend([dates[s_idx], dates[e_idx], None])
            conn_y.extend([w["start_price"], w["end_price"], None])
    if conn_x:
        ax_main.plot(conn_x, conn_y, color="#2962ff", linestyle="--", linewidth=1.2, alpha=0.8, zorder=4)

    # Wave labels with background
    for x, y, txt in zip(label_x, label_y, label_texts):
        ax_main.text(
            x, y, txt,
            fontsize=14,
            fontweight="bold",
            color="#1a237e",
            ha="center",
            va="center",
            bbox=dict(boxstyle="round,pad=0.2", facecolor="#fff9c4", edgecolor="#1a237e", alpha=0.95),
            zorder=5,
        )

    # 3. Fibonacci retracement lines
    if wave_type in ("impulse", "composite") and len(waves) >= 4:
        fib_colors = ["#9e9e9e", "#757575", "#616161"]
        fib_labels = ["38.2%", "50.0%", "61.8%"]
        fib_ratios = [0.382, 0.500, 0.618]

        for wave_idx in (1, 3):
            prev_wave = waves[wave_idx - 1]
            curr_wave = waves[wave_idx]
            prev_start = prev_wave["start_price"]
            prev_end = prev_wave["end_price"]
            fib_range = abs(prev_end - prev_start)
            if fib_range == 0:
                continue

            for ratio, color, label in zip(fib_ratios, fib_colors, fib_labels):
                if direction == "up":
                    level = max(prev_start, prev_end) - fib_range * ratio
                else:
                    level = min(prev_start, prev_end) + fib_range * ratio

                ax_main.axhline(
                    y=level,
                    color=color,
                    linestyle=":",
                    linewidth=0.8,
                    alpha=0.7,
                    xmin=0.02,
                    xmax=0.98,
                    zorder=1,
                )
                ax_main.text(
                    dates[-1] + date_span * 0.005,
                    level,
                    f"W{wave_idx + 1} {label}",
                    fontsize=7,
                    color=color,
                    va="center",
                    ha="left",
                    zorder=5,
                )

    # 3.5 Key Support / Resistance from Kimi analysis
    kimi_analysis = wave_candidate.get("kimi_analysis", {})
    sr_analysis = {}
    directional_bias = {}
    if isinstance(kimi_analysis, dict):
        # Parsed Kimi result may have SR/directional_bias at top level, or nested under kimi_structure.
        sr_analysis = kimi_analysis.get("support_resistance_analysis") or {}
        if not sr_analysis:
            sr_analysis = kimi_analysis.get("kimi_structure", {}).get("support_resistance_analysis", {}) or {}
        directional_bias = kimi_analysis.get("directional_bias") or {}
        if not directional_bias:
            directional_bias = kimi_analysis.get("kimi_structure", {}).get("directional_bias", {}) or {}
    key_support = sr_analysis.get("key_support")
    key_resistance = sr_analysis.get("key_resistance")

    if key_support and min(lows) * 0.5 <= key_support <= max(highs) * 1.5:
        ax_main.axhline(
            y=key_support,
            color='#22c55e',
            linestyle='-',
            linewidth=1.5,
            alpha=0.7,
            xmin=0.02,
            xmax=0.98,
            zorder=3,
        )
        ax_main.text(
            dates[-1] + date_span * 0.005,
            key_support,
            f"Key Support {_format_price_label(key_support)}",
            fontsize=8,
            color='#22c55e',
            va='center',
            ha='left',
            zorder=5,
        )
    if key_resistance and min(lows) * 0.5 <= key_resistance <= max(highs) * 1.5:
        ax_main.axhline(
            y=key_resistance,
            color='#ef4444',
            linestyle='-',
            linewidth=1.5,
            alpha=0.7,
            xmin=0.02,
            xmax=0.98,
            zorder=3,
        )
        ax_main.text(
            dates[-1] + date_span * 0.005,
            key_resistance,
            f"Key Resistance {_format_price_label(key_resistance)}",
            fontsize=8,
            color='#ef4444',
            va='center',
            ha='left',
            zorder=5,
        )

    # 4. Highlight current forming wave (red dashed line)
    if waves and len(klines) > 0:
        last_wave = waves[-1]
        last_end_idx = int(last_wave["end_idx"])
        last_end_price = last_wave["end_price"]
        if 0 <= last_end_idx < n_bars:
            ax_main.plot(
                [dates[last_end_idx], dates[-1]],
                [last_end_price, closes[-1]],
                color="#d32f2f",
                linestyle="--",
                linewidth=2.0,
                alpha=0.8,
                zorder=5,
                label="Current Wave (forming)",
            )

    # 5. Projection lines (extend 20% to the right)
    scenario_colors = {
        "bullish": "#2e7d32",
        "bearish": "#c62828",
        "neutral": "#757575",
    }
    scenario_styles = {
        "bullish": (0, (5, 2)),
        "bearish": (0, (5, 2)),
        "neutral": (0, (3, 1, 1, 1)),
    }

    last_date = dates[-1]
    last_price = closes[-1]
    projection_horizon = date_span * 0.20

    for proj in projections:
        scenario = proj.get("scenario", "neutral")
        target_price = float(proj.get("target_price", last_price))
        color = scenario_colors.get(scenario, "#757575")
        linestyle = scenario_styles.get(scenario, (0, (3, 1, 1, 1)))

        proj_dates = [last_date, last_date + projection_horizon]
        proj_prices = [last_price, target_price]

        ax_main.plot(
            proj_dates, proj_prices,
            color=color,
            linestyle=linestyle,
            linewidth=1.8,
            alpha=0.9,
            zorder=4,
        )

    # 6. Title
    pattern = wave_candidate.get("wave_pattern", "Unknown")
    score = wave_candidate.get("score", 0.0)
    current_wave = wave_labels[-1] if wave_labels else "?"
    ax_main.set_title(
        f"{symbol}/{timeframe} - Elliott Wave Analysis | {pattern} | Score: {int(score * 100)}%",
        fontsize=13,
        fontweight="bold",
        pad=10,
        color='white',
    )

    # 7. Axis formatting
    ax_main.set_xlabel("Date", fontsize=10)
    ax_main.set_ylabel("Price", fontsize=10)
    ax_main.xaxis.set_major_formatter(mdates.DateFormatter("%m-%d %H:%M"))
    ax_main.xaxis.set_major_locator(mdates.AutoDateLocator())
    fig.autofmt_xdate(rotation=30)
    ax_main.grid(True, linestyle='--', alpha=0.2, color='white', zorder=0)

    # Extended xlim to fit projection lines (+20% more)
    x_margin_left = (dates[1] - dates[0]) * 0.5 if len(dates) > 1 else 0.01
    x_margin_right = date_span * 0.25  # 5% original + 20% extra
    ax_main.set_xlim(dates[0] - x_margin_left, dates[-1] + x_margin_right)

    all_prices = highs + lows + [p.get("target_price", last_price) for p in projections]
    ax_main.set_ylim(
        min(all_prices) - (max(all_prices) - min(all_prices)) * 0.10,
        max(all_prices) + (max(all_prices) - min(all_prices)) * 0.10,
    )

    # --- Right panel: Info panel ---
    ax_panel = fig.add_subplot(gs[0, 1])
    ax_panel.set_facecolor('#222222')
    ax_panel.set_xlim(0, 1)
    ax_panel.set_ylim(0, 1)
    ax_panel.axis('off')

    # 1. CURRENT WAVE title
    ax_panel.text(0.5, 0.95, "CURRENT WAVE",
                  transform=ax_panel.transAxes,
                  fontsize=11, fontweight='bold', color='#7ED7C4',
                  ha='center', va='top')
    ax_panel.axhline(y=0.93, xmin=0.05, xmax=0.95, color='#555555', linewidth=0.5)

    # 2. Probability horizontal bars (top3)
    current_wave_probs = wave_candidate.get("current_wave_probabilities", {})
    if current_wave_probs:
        sorted_probs = sorted(current_wave_probs.items(), key=lambda x: x[1], reverse=True)[:3]
        bar_start_y = 0.88
        bar_height = 0.025
        bar_gap = 0.015
        bar_left = 0.1
        bar_right = 0.9
        bar_width_total = bar_right - bar_left

        for rank, (wave_name, prob) in enumerate(sorted_probs):
            y_bottom = bar_start_y - rank * (bar_height + bar_gap)
            # Background bar
            bg_rect = Rectangle((bar_left, y_bottom), bar_width_total, bar_height,
                                facecolor='#333333', edgecolor='none',
                                transform=ax_panel.transAxes, zorder=1)
            ax_panel.add_patch(bg_rect)
            # Filled bar
            fill_width = bar_width_total * prob
            fill_rect = Rectangle((bar_left, y_bottom), fill_width, bar_height,
                                  facecolor='#7ED7C4', edgecolor='none',
                                  transform=ax_panel.transAxes, zorder=2)
            ax_panel.add_patch(fill_rect)
            # Wave name label (left side)
            ax_panel.text(bar_left - 0.02, y_bottom + bar_height / 2,
                          str(wave_name),
                          transform=ax_panel.transAxes,
                          fontsize=9, color='white',
                          ha='right', va='center')
            # Percentage (right side)
            ax_panel.text(bar_right + 0.02, y_bottom + bar_height / 2,
                          f"{prob * 100:.0f}%",
                          transform=ax_panel.transAxes,
                          fontsize=10, color='white',
                          ha='left', va='center')

    # 3. PROJECTIONS title
    ax_panel.text(0.5, 0.72, "PROJECTIONS",
                  transform=ax_panel.transAxes,
                  fontsize=11, fontweight='bold', color='#7ED7C4',
                  ha='center', va='top')
    ax_panel.axhline(y=0.70, xmin=0.05, xmax=0.95, color='#555555', linewidth=0.5)

    # 4. Projection items
    if projections:
        proj_start_y = 0.68
        proj_gap = 0.06
        for rank, proj in enumerate(projections):
            y_center = proj_start_y - rank * proj_gap
            scenario = proj.get("scenario", "neutral")
            color = scenario_colors.get(scenario, "#757575")
            target_price = proj.get("target_price", 0)
            description = proj.get("description", scenario)
            desc_short = (description[:20] + '...') if len(str(description)) > 20 else str(description)

            # Color dot
            circle = Circle((0.12, y_center), 0.008,
                            facecolor=color, edgecolor='none',
                            transform=ax_panel.transAxes, zorder=3)
            ax_panel.add_patch(circle)

            # Scenario name (uppercase, bold)
            ax_panel.text(0.18, y_center + 0.01,
                          scenario.upper(),
                          transform=ax_panel.transAxes,
                          fontsize=9, fontweight='bold', color='white',
                          ha='left', va='center')
            # Target price
            ax_panel.text(0.18, y_center - 0.012,
                          f"{float(target_price):,.2f}",
                          transform=ax_panel.transAxes,
                          fontsize=9, color='white',
                          ha='left', va='center')
            # Description (truncated)
            ax_panel.text(0.18, y_center - 0.028,
                          desc_short,
                          transform=ax_panel.transAxes,
                          fontsize=8, color='#999999',
                          ha='left', va='center')

    # 5. STATUS title
    ax_panel.text(0.5, 0.48, "STATUS",
                  transform=ax_panel.transAxes,
                  fontsize=11, fontweight='bold', color='#7ED7C4',
                  ha='center', va='top')
    ax_panel.axhline(y=0.46, xmin=0.05, xmax=0.95, color='#555555', linewidth=0.5)

    status = wave_candidate.get("current_wave_status", "forming")
    if status.lower() == "completed":
        status_text = "✓ COMPLETED"
        status_color = '#7ED7C4'
    else:
        status_text = "⚡ FORMING"
        status_color = '#FFD93D'

    ax_panel.text(0.5, 0.42, status_text,
                  transform=ax_panel.transAxes,
                  fontsize=12, fontweight='bold', color=status_color,
                  ha='center', va='top')
    ax_panel.text(0.5, 0.38, f"Confidence: {int(score * 100)}%",
                  transform=ax_panel.transAxes,
                  fontsize=10, color='white',
                  ha='center', va='top')

    # 5.5 Support / Resistance & Directional Bias
    if sr_analysis:
        ax_panel.text(0.5, 0.35, "S/R & BIAS",
                      transform=ax_panel.transAxes,
                      fontsize=11, fontweight='bold', color='#7ED7C4',
                      ha='center', va='top')
        ax_panel.axhline(y=0.33, xmin=0.05, xmax=0.95, color='#555555', linewidth=0.5)

        sr_y = 0.29
        if key_support:
            ax_panel.text(0.1, sr_y, f"Key Support: {key_support:,.2f}",
                          transform=ax_panel.transAxes,
                          fontsize=9, color='#22c55e',
                          ha='left', va='top')
            sr_y -= 0.04
        if key_resistance:
            ax_panel.text(0.1, sr_y, f"Key Resistance: {key_resistance:,.2f}",
                          transform=ax_panel.transAxes,
                          fontsize=9, color='#ef4444',
                          ha='left', va='top')
            sr_y -= 0.04

        # directional_bias already extracted from kimi_analysis/kimi_structure above
        if directional_bias:
            primary_direction = directional_bias.get("primary_direction", "")
            primary_probability = directional_bias.get("primary_probability", 0.0)
            secondary_direction = directional_bias.get("secondary_direction", "")
            secondary_probability = directional_bias.get("secondary_probability", 0.0)
            if primary_direction:
                ax_panel.text(0.1, sr_y, f"Bias: {primary_direction.upper()} {primary_probability*100:.0f}%",
                              transform=ax_panel.transAxes,
                              fontsize=9, color='white',
                              ha='left', va='top')
                sr_y -= 0.04
            if secondary_direction:
                ax_panel.text(0.1, sr_y, f"Alt: {secondary_direction.upper()} {secondary_probability*100:.0f}%",
                              transform=ax_panel.transAxes,
                              fontsize=9, color='#999999',
                              ha='left', va='top')
                sr_y -= 0.04

        breakout_direction = sr_analysis.get("breakout_direction", "")
        breakout_confirmed = sr_analysis.get("breakout_confirmed", False)
        if breakout_direction:
            status = "confirmed" if breakout_confirmed else "forming"
            ax_panel.text(0.1, sr_y, f"Breakout: {breakout_direction.upper()} ({status})",
                          transform=ax_panel.transAxes,
                          fontsize=9, color='#FFD93D',
                          ha='left', va='top')
            sr_y -= 0.04

        analysis_text = sr_analysis.get("analysis", "")
        if analysis_text:
            ax_panel.text(0.1, sr_y, analysis_text[:80],
                          transform=ax_panel.transAxes,
                          fontsize=8, color='#aaaaaa',
                          ha='left', va='top')

    # 6. Bottom info
    ax_panel.text(0.5, 0.12,
                  f"Pattern: {pattern}\\nScore: {int(score * 100)}%\\nCurrent Wave: {current_wave}",
                  transform=ax_panel.transAxes,
                  fontsize=8, color='#888888',
                  ha='center', va='bottom')

    fig.savefig(output_path, dpi=150, bbox_inches='tight', facecolor='#1a1a1a')
    plt.close(fig)
    logger.info(f"plot_elliott_wave_unified: saved chart to {output_path}")
    return output_path

