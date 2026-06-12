#!/usr/bin/env python3
"""
Standalone batch backtest runner.
Called via subprocess from FastAPI to isolate the event loop.
Usage: python3 batch_backtest_runner.py <timeframe> [symbol1,symbol2,...]
Output: JSON to stdout
"""

import asyncio
import json
import sys
import os

# Add parent dir to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from backtest import run_batch_backtest


async def main():
    timeframe = sys.argv[1] if len(sys.argv) > 1 else "1d"
    result = await run_batch_backtest(timeframe)
    print(json.dumps({"success": True, "data": result}, default=str))


if __name__ == "__main__":
    asyncio.run(main())
