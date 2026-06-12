import asyncio
import aiohttp

API_BASE = "http://43.134.37.174:8000"

async def test_single_backtest():
    async with aiohttp.ClientSession() as session:
        async with session.get(f"{API_BASE}/api/sentiment/backtest/BTCUSDT/1d") as resp:
            data = await resp.json()
            print(f"Status: {resp.status}")
            print(f"Has stats: {'stats' in data.get('data', {})}")
            print(f"Has current_signal: {'current_signal' in data.get('data', {})}")
            return data

async def test_batch_backtest():
    async with aiohttp.ClientSession() as session:
        async with session.get(f"{API_BASE}/api/sentiment/backtest/batch/1d") as resp:
            data = await resp.json()
            print(f"Status: {resp.status}")
            print(f"Has recommendations: {'recommendations' in data.get('data', {})}")
            if data.get('data', {}).get('recommendations'):
                print(f"Top recommendation: {data['data']['recommendations'][0]['symbol']}")
            return data

if __name__ == "__main__":
    print("=== Testing Single Backtest ===")
    asyncio.run(test_single_backtest())
    print("\n=== Testing Batch Backtest ===")
    asyncio.run(test_batch_backtest())
