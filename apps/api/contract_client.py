"""
Web3.py client to interact with MantleDeFAIRegistry on Mantle Sepolia.
"""

import os
import json
from typing import List, Dict, Optional
from loguru import logger
from web3 import Web3

# Connect to Mantle Sepolia
MANTLE_SEPOLIA_RPC = "https://rpc.sepolia.mantle.xyz"
MANTLE_SEPOLIA_CHAIN_ID = 5003

w3 = Web3(Web3.HTTPProvider(MANTLE_SEPOLIA_RPC))

# Load contract ABI
_ABI_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "abi", "MantleDeFAIRegistry.json")
with open(_ABI_PATH) as f:
    _ABI = json.load(f)

REGISTRY_ADDRESS = os.getenv("REGISTRY_ADDRESS", "")
REGISTRY_PRIVATE_KEY = os.getenv("REGISTRY_PRIVATE_KEY", "")


def _get_contract():
    """Return contract instance if address is configured."""
    if not REGISTRY_ADDRESS:
        return None
    try:
        address = Web3.to_checksum_address(REGISTRY_ADDRESS)
        return w3.eth.contract(address=address, abi=_ABI)
    except Exception as e:
        logger.warning(f"[RegistryClient] Failed to instantiate contract: {e}")
        return None


def _get_account():
    """Return account if private key is configured."""
    if not REGISTRY_PRIVATE_KEY:
        return None
    try:
        return w3.eth.account.from_key(REGISTRY_PRIVATE_KEY)
    except Exception as e:
        logger.warning(f"[RegistryClient] Failed to load account from private key: {e}")
        return None


def _is_configured() -> bool:
    """Check if both contract address and private key are available."""
    return bool(REGISTRY_ADDRESS and REGISTRY_PRIVATE_KEY)


class RegistryClient:
    """Client for interacting with MantleDeFAIRegistry smart contract."""

    def __init__(self):
        self._contract = _get_contract()
        self._account = _get_account()
        self._configured = _is_configured()
        if self._configured and self._contract and self._account:
            logger.info(f"[RegistryClient] Initialized for contract {REGISTRY_ADDRESS}")
            logger.info(f"[RegistryClient] Submitter address: {self._account.address}")
        elif not self._configured:
            logger.info("[RegistryClient] On-chain registry not configured (missing REGISTRY_ADDRESS or REGISTRY_PRIVATE_KEY). Skipping on-chain submissions.")

    @property
    def configured(self) -> bool:
        return self._configured

    @property
    def submitter_address(self) -> Optional[str]:
        return self._account.address if self._account else None

    def submit_signal(self, symbol: str, timeframe: str, encrypted_data: bytes, data_hash: str) -> Optional[str]:
        """Submit a single encrypted signal to the on-chain registry. Returns tx hash or None."""
        if not self._configured or not self._contract or not self._account:
            logger.debug("[RegistryClient] Skipping submit_signal: not configured")
            return None

        try:
            tx_hash = self._send_transaction(
                self._contract.functions.submitSignal(
                    symbol,
                    timeframe,
                    encrypted_data,
                    Web3.to_bytes(hexstr=data_hash),
                )
            )
            logger.info(f"[RegistryClient] submit_signal tx: {tx_hash}")
            return tx_hash
        except Exception as e:
            logger.warning(f"[RegistryClient] submit_signal failed: {e}")
            return None

    def submit_signals_batch(self, signals: List[Dict]) -> Optional[str]:
        """
        Submit multiple encrypted signals in a batch.
        
        signals: list of dicts with keys:
            - symbol (str)
            - timeframe (str)
            - encrypted_data (bytes)
            - data_hash (str) — hex string of keccak256 hash
        
        Returns tx hash or None.
        """
        if not self._configured or not self._contract or not self._account:
            logger.debug("[RegistryClient] Skipping submit_signals_batch: not configured")
            return None

        if not signals:
            return None

        try:
            symbols = [s["symbol"] for s in signals]
            timeframes = [s["timeframe"] for s in signals]
            encrypted_data_array = [s["encrypted_data"] for s in signals]
            data_hashes = [Web3.to_bytes(hexstr=s["data_hash"]) for s in signals]

            tx_hash = self._send_transaction(
                self._contract.functions.submitSignalsBatch(
                    symbols,
                    timeframes,
                    encrypted_data_array,
                    data_hashes,
                )
            )
            logger.info(f"[RegistryClient] submit_signals_batch tx: {tx_hash} ({len(signals)} signals)")
            return tx_hash
        except Exception as e:
            logger.warning(f"[RegistryClient] submit_signals_batch failed: {e}")
            return None

    def is_subscribed(self, user_address: str) -> bool:
        """Check if a user has an active on-chain subscription."""
        if not self._contract:
            return False
        try:
            checksum_addr = Web3.to_checksum_address(user_address)
            result = self._contract.functions.isSubscribed(checksum_addr).call()
            return bool(result)
        except Exception as e:
            logger.warning(f"[RegistryClient] is_subscribed check failed for {user_address}: {e}")
            return False

    def _send_transaction(self, func) -> str:
        """Build, sign, and send a transaction. Returns tx hash hex."""
        nonce = w3.eth.get_transaction_count(self._account.address)
        gas_price = w3.eth.gas_price

        tx = func.build_transaction({
            "from": self._account.address,
            "nonce": nonce,
            "gasPrice": gas_price,
            "chainId": MANTLE_SEPOLIA_CHAIN_ID,
        })

        # Estimate gas
        try:
            estimated = w3.eth.estimate_gas(tx)
            tx["gas"] = int(estimated * 1.2)
        except Exception as e:
            logger.warning(f"[RegistryClient] Gas estimation failed, using default: {e}")
            tx["gas"] = 500000

        signed = self._account.sign_transaction(tx)
        tx_hash = w3.eth.send_raw_transaction(signed.rawTransaction)
        return tx_hash.hex()


# Global instance
registry = RegistryClient()
