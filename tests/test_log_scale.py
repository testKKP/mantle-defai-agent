import sys
sys.path.insert(0, 'apps/api')
from chart_generator import plot_kimi_annotated_wave

# 用模拟数据测试（包含接近0的价格）
klines = [
    {"open": 1.5, "high": 1.6, "low": 1.4, "close": 1.55, "open_time": 1700000000000},
    {"open": 1.55, "high": 1.58, "low": 1.48, "close": 1.5, "open_time": 1700086400000},
    {"open": 1.5, "high": 1.52, "low": 1.15, "close": 1.2, "open_time": 1700172800000},
    {"open": 1.2, "high": 1.35, "low": 1.18, "close": 1.3, "open_time": 1700259200000},
    {"open": 1.3, "high": 1.32, "low": 1.25, "close": 1.28, "open_time": 1700345600000},
    {"open": 1.28, "high": 1.3, "low": 0.75, "close": 0.8, "open_time": 1700432000000},
    {"open": 0.8, "high": 0.95, "low": 0.78, "close": 0.9, "open_time": 1700518400000},
    {"open": 0.9, "high": 0.92, "low": 0.85, "close": 0.88, "open_time": 1700604800000},
    {"open": 0.88, "high": 0.9, "low": 0.25, "close": 0.3, "open_time": 1700691200000},
]

kimi_structure = {
    "wave_pattern": "Impulse",
    "direction": "down",
    "current_wave": "Wave 5",
    "score": 0.62,
    "waves": [
        {"label": "1", "start_idx": 0, "end_idx": 2, "start_price": 1.5, "end_price": 1.2, "type": "impulse"},
        {"label": "2", "start_idx": 2, "end_idx": 3, "start_price": 1.2, "end_price": 1.3, "type": "corrective"},
        {"label": "3", "start_idx": 3, "end_idx": 5, "start_price": 1.3, "end_price": 0.8, "type": "impulse"},
        {"label": "4", "start_idx": 5, "end_idx": 6, "start_price": 0.8, "end_price": 0.9, "type": "corrective"},
        {"label": "5", "start_idx": 6, "end_idx": 8, "start_price": 0.9, "end_price": 0.3, "type": "impulse"},
    ],
    "sub_waves": [],
    "projections": [
        {"scenario": "bearish", "description": "Extension", "target_price": 0.17, "confidence": 0.4, "trigger_condition": "", "time_horizon": {}, "support_levels": [0.1, 0.05], "resistance_levels": [0.5, 0.8], "stop_loss": 0.9}
    ],
    "annotations": "Test",
    "overall_confidence": 0.62
}

output = plot_kimi_annotated_wave(klines, kimi_structure, "WLD", "1d", "tests/screenshots/test_log_scale.png")
print(f"Generated: {output}")
