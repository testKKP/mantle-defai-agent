#!/usr/bin/env python3
"""One-shot script to sync all historical on-chain signals into local SQLite DB."""

import asyncio
import json
import sys
import os

# Add apps/api to path for imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from web3 import Web3
from db import db_save_onchain_signal, db_manager

RPC_URL = "https://rpc.sepolia.mantle.xyz"
CONTRACT_ADDRESS = "0x684802d365d1bbc0b74f7b57f823acdf965d1ba3"

# Load ABI from web-react
ABI_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "../web-react/src/abi/MantleDeFAIRegistry.json",
)
with open(ABI_PATH) as f:
    ABI = json.load(f)

SYMBOLS = ["BTC", "ETH", "MNT", "SOL", "ARB"]
TIMEFRAMES = ["4h", "1d", "1w"]


async def sync_all():
    # Initialize db manager
    await db_manager.initialize()

    if not db_manager._initialized:
        print("ERROR: Database manager not initialized", file=sys.stderr)
        sys.exit(1)

    w3 = Web3(Web3.HTTPProvider(RPC_URL))
    if not w3.is_connected():
        print(f"ERROR: Cannot connect to RPC {RPC_URL}", file=sys.stderr)
        sys.exit(1)

    contract = w3.eth.contract(
        address=Web3.to_checksum_address(CONTRACT_ADDRESS), abi=ABI
    )

    total_onchain = 0
    total_synced = 0

    for symbol in SYMBOLS:
        for tf in TIMEFRAMES:
            count = contract.functions.getSignalCount(symbol, tf).call()
            total_onchain += count
            print(f"{symbol}/{tf}: {count} signals")
            if count == 0:
                continue

            # Read in batches of 100
            batch_size = 100
            for offset in range(0, count, batch_size):
                limit = min(batch_size, count - offset)
                signals = contract.functions.getSignals(symbol, tf, offset, limit).call()
                for s in signals:
                    # s is a tuple / AttributeDict:
                    #   data (str), dataHash (bytes32), timestamp (int), submitter (address)
                    data = s[0] if isinstance(s, (tuple, list)) else s.data
                    data_hash_raw = s[1] if isinstance(s, (tuple, list)) else s.dataHash
                    timestamp = s[2] if isinstance(s, (tuple, list)) else s.timestamp

                    # Convert bytes32 to hex string for tx_hash placeholder
                    if isinstance(data_hash_raw, bytes):
                        data_hash_hex = "0x" + data_hash_raw.hex()
                    else:
                        data_hash_hex = str(data_hash_raw)

                    # block_number is not in Signal struct; use 0 as placeholder
                    block_number = 0

                    await db_save_onchain_signal(
                        tx_hash=data_hash_hex,
                        block_number=block_number,
                        symbol=symbol,
                        timeframe=tf,
                        data=data,
                        data_hash=data_hash_hex,
                        timestamp=int(timestamp),
                    )
                    total_synced += 1

            print(f"  -> synced signals for {symbol}/{tf}")

    print(f"\nTotal on-chain signals: {total_onchain}")
    print(f"Total synced to DB:     {total_synced}")


if __name__ == "__main__":
    asyncio.run(sync_all())
