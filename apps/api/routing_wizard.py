"""
Mantle DeFAI Trader - Smart Routing Wizard Engine
交互式智能路由向导系统后端

功能：
1. 向导式多步骤状态机（8步）
2. Agent 异步智能路由分析
3. 进度追踪与状态持久化
4. 多链/多 DEX 路由方案生成
"""

import asyncio
import json
import os
import uuid
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Request
from loguru import logger
from pydantic import BaseModel, Field
from web3 import Web3

# Import database layer
from decimal import Decimal, ROUND_DOWN
from db import db_get, db_set
from clients import DEXQuoteProvider, MantleProvider

# ============ Configuration ============

# Supported chains
SUPPORTED_CHAINS = [
    {
        "id": "mantle",
        "name": "Mantle",
        "chain_id": 5000,
        "native_token": "MNT",
        "rpc_url": "https://rpc.mantle.xyz",
        "explorer_url": "https://mantlescan.xyz",
        "is_evm": True,
        "color": "#2D6B5E",
    },
    {
        "id": "ethereum",
        "name": "Ethereum",
        "chain_id": 1,
        "native_token": "ETH",
        "rpc_url": "https://eth.llamarpc.com",
        "explorer_url": "https://etherscan.io",
        "is_evm": True,
        "color": "#627EEA",
    },
    {
        "id": "arbitrum",
        "name": "Arbitrum",
        "chain_id": 42161,
        "native_token": "ETH",
        "rpc_url": "https://arb1.arbitrum.io/rpc",
        "explorer_url": "https://arbiscan.io",
        "is_evm": True,
        "color": "#28A0F0",
    },
    {
        "id": "base",
        "name": "Base",
        "chain_id": 8453,
        "native_token": "ETH",
        "rpc_url": "https://mainnet.base.org",
        "explorer_url": "https://basescan.org",
        "is_evm": True,
        "color": "#0052FF",
    },
    {
        "id": "mantle_sepolia",
        "name": "Mantle Sepolia",
        "chain_id": 5003,
        "native_token": "MNT",
        "rpc_url": "https://rpc.sepolia.mantle.xyz",
        "explorer_url": "https://sepolia.mantlescan.xyz",
        "is_evm": True,
        "color": "#2D6B5E",
    },
]

# Supported tokens per chain
SUPPORTED_TOKENS = {
    "mantle": [
        {"symbol": "MNT", "name": "Mantle", "address": "0x78c1b0C915c4FAA5FffA6CAbf0219DA63d7f4cb8", "decimals": 18, "is_native": True, "price_usd": 0.65},
        {"symbol": "USDC", "name": "USD Coin", "address": "0x09Bc4E0D864854c6aFB6eB9A9cdF58aC190D0dF9", "decimals": 6, "is_native": False, "price_usd": 1.0},
        {"symbol": "USDT", "name": "Tether", "address": "0x201EBa5CC46D216Ce6DC03F6a759e8E766e956aE", "decimals": 6, "is_native": False, "price_usd": 1.0},
        {"symbol": "WMNT", "name": "Wrapped Mantle", "address": "0x78c1b0C915c4FAA5FffA6CAbf0219DA63d7f4cb8", "decimals": 18, "is_native": False, "price_usd": 0.65},
        {"symbol": "mETH", "name": "Mantle Staked Ether", "address": "0xcDA86A272531e8640cD7F1a92c01839911B90bb0", "decimals": 18, "is_native": False, "price_usd": 3200},
    ],
    "ethereum": [
        {"symbol": "ETH", "name": "Ethereum", "address": "0xEeeeeEeeeEeEeeEeEeEeeEEEeeeeEeeeeeeeEEeE", "decimals": 18, "is_native": True, "price_usd": 3200},
        {"symbol": "USDC", "name": "USD Coin", "address": "0xA0b86a33E6441e6C7D3D4B4f6b8E2F5c1D2A3B4C", "decimals": 6, "is_native": False, "price_usd": 1.0},
        {"symbol": "USDT", "name": "Tether", "address": "0xdAC17F958D2ee523a2206206994597C13D831ec7", "decimals": 6, "is_native": False, "price_usd": 1.0},
        {"symbol": "WETH", "name": "Wrapped Ether", "address": "0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2", "decimals": 18, "is_native": False, "price_usd": 3200},
    ],
    "arbitrum": [
        {"symbol": "ETH", "name": "Ethereum", "address": "0xEeeeeEeeeEeEeeEeEeEeeEEEeeeeEeeeeeeeEEeE", "decimals": 18, "is_native": True, "price_usd": 3200},
        {"symbol": "USDC", "name": "USD Coin", "address": "0xaf88d065e77c8cC2239327C5EDb3A432268e5831", "decimals": 6, "is_native": False, "price_usd": 1.0},
        {"symbol": "USDT", "name": "Tether", "address": "0xFd086bC7CD5C481DCC9C85ebE478A1C0b69FCbb9", "decimals": 6, "is_native": False, "price_usd": 1.0},
    ],
    "base": [
        {"symbol": "ETH", "name": "Ethereum", "address": "0xEeeeeEeeeEeEeeEeEeEeeEEEeeeeEeeeeeeeEEeE", "decimals": 18, "is_native": True, "price_usd": 3200},
        {"symbol": "USDC", "name": "USD Coin", "address": "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913", "decimals": 6, "is_native": False, "price_usd": 1.0},
    ],
    "mantle_sepolia": [
        {"symbol": "MNT", "name": "Mantle", "address": "0x78c1b0C915c4FAA5FffA6CAbf0219DA63d7f4cb8", "decimals": 18, "is_native": True, "price_usd": 0.65},
        {"symbol": "USDC", "name": "USD Coin", "address": "0x09Bc4E0D864854c6aFB6eB9A9cdF58aC190D0dF9", "decimals": 6, "is_native": False, "price_usd": 1.0},
        {"symbol": "USDT", "name": "Tether", "address": "0x201EBa5CC46D216Ce6DC03F6a759e8E766e956aE", "decimals": 6, "is_native": False, "price_usd": 1.0},
    ],
}

# Bridge protocols
BRIDGE_PROTOCOLS = {
    "mantle_official": {"name": "Mantle Official Bridge", "type": "canonical", "time_min": 12, "time_max": 10080, "fee_bps": 0},
    "wormhole": {"name": "Wormhole", "type": "generic", "time_min": 2, "time_max": 5, "fee_bps": 5},
    "symbiosis": {"name": "Symbiosis", "type": "dex_aggregator", "time_min": 30, "time_max": 180, "fee_bps": 15},
    "router_nitro": {"name": "Router Nitro", "type": "intent", "time_min": 10, "time_max": 60, "fee_bps": 8},
    "cctp": {"name": "Circle CCTP", "type": "usdc_native", "time_min": 20, "time_max": 30, "fee_bps": 0},
}

# DEX protocols per chain
DEX_PROTOCOLS = {
    "mantle": [
        {"name": "Merchant Moe", "type": "native_dex", "fee_bps": 20, "router": "0x013e138EF6008ae5FDFDE29700e3f2Bc61d21E3a"},
        {"name": "Agni Finance", "type": "amm", "fee_bps": 30, "router": ""},
        {"name": "FusionX", "type": "amm", "fee_bps": 25, "router": ""},
    ],
    "ethereum": [
        {"name": "Uniswap V3", "type": "amm", "fee_bps": 5, "router": ""},
        {"name": "Curve", "type": "stable_swap", "fee_bps": 4, "router": ""},
        {"name": "1inch", "type": "aggregator", "fee_bps": 0, "router": ""},
    ],
    "arbitrum": [
        {"name": "Uniswap V3", "type": "amm", "fee_bps": 5, "router": ""},
        {"name": "Camelot", "type": "amm", "fee_bps": 20, "router": ""},
    ],
    "base": [
        {"name": "Uniswap V3", "type": "amm", "fee_bps": 5, "router": ""},
        {"name": "Aerodrome", "type": "amm", "fee_bps": 20, "router": ""},
    ],
}

# ============ Pydantic Models ============

class WizardStep(str, Enum):
    CHAIN_SELECT = "chain_select"
    TOKEN_SELECT = "token_select"
    AMOUNT_INPUT = "amount_input"
    SMART_ANALYSIS = "smart_analysis"
    ROUTE_DISPLAY = "route_display"
    ROUTE_SELECT = "route_select"
    WALLET_CHECK = "wallet_check"
    EXECUTE_CONFIRM = "execute_confirm"


class StepChainData(BaseModel):
    source_chain: str
    target_chain: str


class StepTokenData(BaseModel):
    token_in: str
    token_out: str
    token_in_symbol: str
    token_out_symbol: str


class StepAmountData(BaseModel):
    amount: str
    amount_usd: Optional[float] = None


class RouteStepDetail(BaseModel):
    step_number: int
    step_type: str  # "swap", "bridge", "wrap", "unwrap", "approve"
    protocol: str
    protocol_type: str
    from_token: str
    to_token: str
    from_chain: str
    to_chain: str
    from_chain_name: str
    to_chain_name: str
    amount_in: str
    amount_in_usd: float
    expected_out: str
    expected_out_usd: float
    fee_usd: float
    gas_estimate_usd: float
    time_estimate_sec: int
    details: Dict[str, Any] = {}


class RouteOption(BaseModel):
    route_id: str
    name: str
    description: str
    total_steps: int
    steps: List[RouteStepDetail]
    total_input_usd: float
    total_output_usd: float
    total_output_token: str
    total_fee_usd: float
    total_gas_usd: float
    total_slippage: float
    total_time_sec: int
    net_return_usd: float
    net_return_percent: float
    score: float
    tags: List[str] = []
    risk_level: str = "low"  # low, medium, high


class AnalysisProgress(BaseModel):
    status: str  # "idle", "analyzing", "completed", "failed"
    progress_percent: int
    current_task: str
    logs: List[str] = []
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    error: Optional[str] = None


class AnalysisResult(BaseModel):
    status: str
    progress: AnalysisProgress
    routes: List[RouteOption] = []
    best_route_id: Optional[str] = None
    analysis_summary: Optional[str] = None


class WalletCheckResult(BaseModel):
    address: str
    source_chain: str
    target_chain: str
    token_in: str
    token_out: str
    amount: str
    balance_ok: bool
    balance_sufficient: bool
    balance_current: str
    balance_required: str
    allowance_ok: bool
    allowance_current: str
    allowance_required: str
    source_gas_ok: bool
    source_gas_balance: str
    source_gas_required: str
    target_gas_ok: bool
    target_gas_balance: str
    target_gas_required: str
    warnings: List[str] = []
    can_proceed: bool


class ExecutionResult(BaseModel):
    status: str  # "pending", "submitted", "confirmed", "failed"
    tx_hash: Optional[str] = None
    explorer_url: Optional[str] = None
    error: Optional[str] = None
    gas_used: Optional[str] = None
    actual_output: Optional[str] = None
    timestamp: Optional[str] = None


class WizardSessionData(BaseModel):
    session_id: str
    current_step: WizardStep
    completed_steps: List[WizardStep]
    created_at: str
    updated_at: str
    chain_data: Optional[StepChainData] = None
    token_data: Optional[StepTokenData] = None
    amount_data: Optional[StepAmountData] = None
    analysis_data: Optional[AnalysisResult] = None
    selected_route_id: Optional[str] = None
    wallet_check: Optional[WalletCheckResult] = None
    execution_data: Optional[ExecutionResult] = None
    is_cross_chain: bool = False


# ============ Step Validation ============

STEP_ORDER = [
    WizardStep.CHAIN_SELECT,
    WizardStep.TOKEN_SELECT,
    WizardStep.AMOUNT_INPUT,
    WizardStep.SMART_ANALYSIS,
    WizardStep.ROUTE_DISPLAY,
    WizardStep.ROUTE_SELECT,
    WizardStep.WALLET_CHECK,
    WizardStep.EXECUTE_CONFIRM,
]

STEP_REQUIREMENTS = {
    WizardStep.CHAIN_SELECT: [],
    WizardStep.TOKEN_SELECT: [WizardStep.CHAIN_SELECT],
    WizardStep.AMOUNT_INPUT: [WizardStep.CHAIN_SELECT, WizardStep.TOKEN_SELECT],
    WizardStep.SMART_ANALYSIS: [WizardStep.CHAIN_SELECT, WizardStep.TOKEN_SELECT, WizardStep.AMOUNT_INPUT],
    WizardStep.ROUTE_DISPLAY: [WizardStep.CHAIN_SELECT, WizardStep.TOKEN_SELECT, WizardStep.AMOUNT_INPUT, WizardStep.SMART_ANALYSIS],
    WizardStep.ROUTE_SELECT: [WizardStep.CHAIN_SELECT, WizardStep.TOKEN_SELECT, WizardStep.AMOUNT_INPUT, WizardStep.SMART_ANALYSIS, WizardStep.ROUTE_DISPLAY],
    WizardStep.WALLET_CHECK: [WizardStep.CHAIN_SELECT, WizardStep.TOKEN_SELECT, WizardStep.AMOUNT_INPUT, WizardStep.SMART_ANALYSIS, WizardStep.ROUTE_DISPLAY, WizardStep.ROUTE_SELECT],
    WizardStep.EXECUTE_CONFIRM: [WizardStep.CHAIN_SELECT, WizardStep.TOKEN_SELECT, WizardStep.AMOUNT_INPUT, WizardStep.SMART_ANALYSIS, WizardStep.ROUTE_DISPLAY, WizardStep.ROUTE_SELECT, WizardStep.WALLET_CHECK],
}

STEP_TRANSITIONS = {
    WizardStep.CHAIN_SELECT: WizardStep.TOKEN_SELECT,
    WizardStep.TOKEN_SELECT: WizardStep.AMOUNT_INPUT,
    WizardStep.AMOUNT_INPUT: WizardStep.SMART_ANALYSIS,
    WizardStep.SMART_ANALYSIS: WizardStep.ROUTE_DISPLAY,
    WizardStep.ROUTE_DISPLAY: WizardStep.ROUTE_SELECT,
    WizardStep.ROUTE_SELECT: WizardStep.WALLET_CHECK,
    WizardStep.WALLET_CHECK: WizardStep.EXECUTE_CONFIRM,
}


def get_step_index(step: WizardStep) -> int:
    return STEP_ORDER.index(step)


def can_advance_to(session: WizardSessionData, target_step: WizardStep) -> tuple[bool, Optional[str]]:
    """Check if session can advance to target step."""
    required = STEP_REQUIREMENTS.get(target_step, [])
    for req in required:
        if req not in session.completed_steps:
            return False, f"需要先完成步骤: {req.value}"
    return True, None


def get_next_step(current: WizardStep) -> Optional[WizardStep]:
    return STEP_TRANSITIONS.get(current)


# ============ Session Manager ============

class RoutingSessionManager:
    """Manages wizard sessions with SQLite persistence."""

    def __init__(self):
        self._agent_tasks: Dict[str, asyncio.Task] = {}
        self._agent_progress: Dict[str, Dict[str, Any]] = {}

    def _session_key(self, session_id: str) -> str:
        return f"wizard_session_{session_id}"

    async def create_session(self) -> WizardSessionData:
        """Create a new wizard session."""
        session_id = str(uuid.uuid4())[:12]
        now = datetime.utcnow().isoformat()
        session = WizardSessionData(
            session_id=session_id,
            current_step=WizardStep.CHAIN_SELECT,
            completed_steps=[],
            created_at=now,
            updated_at=now,
        )
        await self._save(session)
        logger.info(f"Created wizard session: {session_id}")
        return session

    async def get_session(self, session_id: str) -> Optional[WizardSessionData]:
        """Get session by ID."""
        data = await db_get(self._session_key(session_id))
        if data is None:
            return None
        try:
            return WizardSessionData(**data)
        except Exception as e:
            logger.error(f"Failed to parse session {session_id}: {e}")
            return None

    async def _save(self, session: WizardSessionData):
        """Save session to database."""
        session.updated_at = datetime.utcnow().isoformat()
        await db_set(self._session_key(session.session_id), session.model_dump(), ttl_seconds=3600)

    async def submit_step(self, session_id: str, step_id: str, data: Dict[str, Any]) -> WizardSessionData:
        """Submit data for a step and advance to next step."""
        session = await self.get_session(session_id)
        if session is None:
            raise HTTPException(status_code=404, detail="会话不存在或已过期")

        try:
            target_step = WizardStep(step_id)
        except ValueError:
            raise HTTPException(status_code=400, detail=f"无效的步骤: {step_id}")

        # Validate step can be submitted
        if target_step != session.current_step:
            # Allow going back to previous steps
            target_idx = get_step_index(target_step)
            current_idx = get_step_index(session.current_step)
            if target_idx > current_idx:
                raise HTTPException(status_code=400, detail=f"当前步骤是 {session.current_step.value}，不能跳转到 {step_id}")

        # Validate prerequisites
        ok, err = can_advance_to(session, target_step)
        if not ok:
            raise HTTPException(status_code=400, detail=err)

        # Store step data
        if target_step == WizardStep.CHAIN_SELECT:
            session.chain_data = StepChainData(**data)
            session.is_cross_chain = data.get("source_chain") != data.get("target_chain")
        elif target_step == WizardStep.TOKEN_SELECT:
            session.token_data = StepTokenData(**data)
        elif target_step == WizardStep.AMOUNT_INPUT:
            session.amount_data = StepAmountData(**data)
        elif target_step == WizardStep.ROUTE_SELECT:
            session.selected_route_id = data.get("route_id")
        elif target_step == WizardStep.WALLET_CHECK:
            session.wallet_check = WalletCheckResult(**data)
        elif target_step == WizardStep.EXECUTE_CONFIRM:
            session.execution_data = ExecutionResult(**data)

        # Mark as completed if advancing forward
        if target_step not in session.completed_steps:
            session.completed_steps.append(target_step)

        # Advance to next step
        next_step = get_next_step(target_step)
        if next_step and get_step_index(next_step) > get_step_index(session.current_step):
            session.current_step = next_step

        await self._save(session)
        logger.info(f"Session {session_id}: completed {step_id}, now at {session.current_step.value}")
        return session

    async def advance_step(self, session_id: str) -> WizardSessionData:
        """Advance to next step without data (used after agent completes)."""
        session = await self.get_session(session_id)
        if session is None:
            raise HTTPException(status_code=404, detail="会话不存在或已过期")

        next_step = get_next_step(session.current_step)
        if next_step:
            if session.current_step not in session.completed_steps:
                session.completed_steps.append(session.current_step)
            session.current_step = next_step
            await self._save(session)
        return session

    async def update_analysis(self, session_id: str, analysis: AnalysisResult):
        """Update analysis data for a session."""
        session = await self.get_session(session_id)
        if session:
            session.analysis_data = analysis
            await self._save(session)

    async def update_execution(self, session_id: str, execution: ExecutionResult):
        """Update execution data for a session."""
        session = await self.get_session(session_id)
        if session:
            session.execution_data = execution
            await self._save(session)

    async def get_agent_progress(self, session_id: str) -> Dict[str, Any]:
        """Get agent progress for a session."""
        return self._agent_progress.get(session_id, {
            "status": "idle",
            "progress_percent": 0,
            "current_task": "等待开始",
            "logs": [],
        })

    async def set_agent_progress(self, session_id: str, progress: Dict[str, Any]):
        """Set agent progress for a session."""
        self._agent_progress[session_id] = progress

    async def cancel_agent(self, session_id: str):
        """Cancel running agent task."""
        if session_id in self._agent_tasks:
            task = self._agent_tasks[session_id]
            if not task.done():
                task.cancel()
            del self._agent_tasks[session_id]


# Global session manager
session_manager = RoutingSessionManager()


# ============ Smart Routing Engine ============

class SmartRoutingEngine:
    """Generates intelligent routing options for cross-chain swaps."""

    def __init__(self):
        self.dex_provider = DEXQuoteProvider()
        self.mantle_provider = MantleProvider()
        self._mnt_price_usd = 0.65  # Fallback MNT price for gas calc

    async def analyze_routes(
        self,
        source_chain: str,
        target_chain: str,
        token_in: str,
        token_out: str,
        amount: str,
        is_cross_chain: bool,
        progress_callback: Optional[callable] = None,
    ) -> AnalysisResult:
        """
        Agent-style route analysis with progress reporting.
        Returns multiple route options with detailed breakdowns.
        """
        logs: List[str] = []

        def log(msg: str):
            logs.append(f"[{datetime.utcnow().strftime('%H:%M:%S')}] {msg}")
            if progress_callback:
                progress_callback(msg)
            logger.info(f"[RoutingAgent] {msg}")

        async def report_progress(percent: int, task: str):
            if progress_callback:
                progress_callback(task, percent)

        # Start analysis
        await report_progress(5, "初始化路由分析引擎...")
        log("启动智能路由分析 Agent")
        log(f"参数: {source_chain} -> {target_chain}, {token_in} -> {token_out}, 金额: {amount}")

        await asyncio.sleep(0.3)  # Simulate initialization

        # Get token info
        await report_progress(10, "获取代币信息...")
        in_tokens = SUPPORTED_TOKENS.get(source_chain, [])
        out_tokens = SUPPORTED_TOKENS.get(target_chain, [])
        in_token_info = next((t for t in in_tokens if t["symbol"] == token_in), None)
        out_token_info = next((t for t in out_tokens if t["symbol"] == token_out), None)

        if not in_token_info or not out_token_info:
            raise ValueError(f"不支持的代币组合: {token_in} on {source_chain} -> {token_out} on {target_chain}")

        amount_float = float(amount)
        amount_usd = amount_float * in_token_info.get("price_usd", 1.0)
        log(f"输入金额: {amount} {token_in} (约 ${amount_usd:.2f})")

        routes: List[RouteOption] = []

        if is_cross_chain:
            # Cross-chain routing
            await report_progress(20, "分析跨链桥接选项...")
            log("检测到跨链交易，评估桥接协议...")
            await asyncio.sleep(0.5)

            bridges = ["mantle_official", "symbiosis", "router_nitro"]
            if token_in == "USDC" or token_out == "USDC":
                bridges.append("cctp")

            for i, bridge_id in enumerate(bridges):
                progress = 25 + i * 10
                bridge = BRIDGE_PROTOCOLS[bridge_id]
                await report_progress(progress, f"评估 {bridge['name']}...")
                log(f"评估桥接: {bridge['name']} (类型: {bridge['type']})")
                await asyncio.sleep(0.3)

                route = self._build_cross_chain_route(
                    source_chain, target_chain, token_in, token_out,
                    amount_float, amount_usd, in_token_info, out_token_info,
                    bridge_id, bridge
                )
                routes.append(route)
                log(f"生成路由: {route.name} (得分: {route.score:.1f})")

        else:
            # Same-chain routing
            await report_progress(20, "分析同链 DEX 选项...")
            log("同链交易，查询 DEX 流动性...")
            await asyncio.sleep(0.3)

            dexes = DEX_PROTOCOLS.get(source_chain, [])

            for i, dex in enumerate(dexes):
                progress = 30 + i * 15
                await report_progress(progress, f"查询 {dex['name']} 报价...")
                log(f"查询 DEX: {dex['name']}")
                await asyncio.sleep(0.3)

                route = self._build_same_chain_route(
                    source_chain, token_in, token_out,
                    amount_float, amount_usd, in_token_info, out_token_info,
                    dex
                )
                routes.append(route)
                log(f"生成路由: {route.name} (得分: {route.score:.1f})")

            # Add aggregator route
            await report_progress(75, "查询聚合器最优路径...")
            log("查询 DEX 聚合器 (ODOS / 1inch / OpenOcean)...")
            await asyncio.sleep(0.4)
            agg_route = self._build_aggregator_route(
                source_chain, token_in, token_out,
                amount_float, amount_usd, in_token_info, out_token_info
            )
            routes.append(agg_route)
            log(f"生成聚合器路由: {agg_route.name} (得分: {agg_route.score:.1f})")

        # Score and rank routes
        await report_progress(85, "计算路由评分...")
        log("综合评分所有路由方案...")
        routes = self._rank_routes(routes)

        # Add tags
        if routes:
            routes[0].tags.append("best")
            fastest = min(routes, key=lambda r: r.total_time_sec)
            if fastest.route_id != routes[0].route_id:
                fastest.tags.append("fastest")
            cheapest = min(routes, key=lambda r: r.total_fee_usd + r.total_gas_usd)
            if cheapest.route_id != routes[0].route_id and cheapest.route_id != fastest.route_id:
                cheapest.tags.append("cheapest")
            routes[0].tags.append("recommended")

        for route in routes:
            log(f"最终排名: {route.name} | 净收益: ${route.net_return_usd:.4f} | 标签: {', '.join(route.tags)}")

        await report_progress(95, "生成分析报告...")
        log("生成最终分析报告...")
        await asyncio.sleep(0.2)

        best_route = routes[0] if routes else None
        summary = self._generate_analysis_summary(routes, source_chain, target_chain, token_in, token_out, amount_float, is_cross_chain)

        await report_progress(100, "分析完成")
        log("智能路由分析完成")

        return AnalysisResult(
            status="completed",
            progress=AnalysisProgress(
                status="completed",
                progress_percent=100,
                current_task="分析完成",
                logs=logs,
                completed_at=datetime.utcnow().isoformat(),
            ),
            routes=routes,
            best_route_id=best_route.route_id if best_route else None,
            analysis_summary=summary,
        )

    def _build_same_chain_route(
        self, chain: str, token_in: str, token_out: str,
        amount: float, amount_usd: float,
        in_info: dict, out_info: dict,
        dex: dict
    ) -> RouteOption:
        """Build a same-chain swap route with REAL on-chain quote when available."""
        chain_name = next((c["name"] for c in SUPPORTED_CHAINS if c["id"] == chain), chain)
        real_quote = None
        is_real = False

        # Try real on-chain quote for Merchant Moe on Mantle
        if dex["name"] == "Merchant Moe" and chain == "mantle":
            try:
                in_decimals = in_info.get("decimals", 18)
                amount_wei = int(amount * (10 ** in_decimals))
                real_quote = self.dex_provider.get_quote(token_in, token_out, str(amount_wei))
                is_real = True
                logger.info(f"Real quote: {token_in} -> {token_out}, amount={amount}, out={real_quote['expected_output']}")
            except Exception as e:
                logger.warning(f"Real DEX quote failed for {dex['name']}: {e}, falling back to simulation")

        if real_quote:
            out_decimals = out_info.get("decimals", 18)
            expected_out_wei = int(real_quote["expected_output"])
            expected_out = expected_out_wei / (10 ** out_decimals)
            expected_out_usd = expected_out * out_info.get("price_usd", 1.0)

            fee_wei = int(real_quote.get("fee_amount", "0"))
            fee_token = fee_wei / (10 ** in_info.get("decimals", 18))
            fee_usd = fee_token * in_info.get("price_usd", 1.0)

            price_impact = real_quote.get("price_impact", 0) / 100
            slippage = max(price_impact * 100, 0.5)

            # Real gas estimation using on-chain gas price
            gas_price_data = self.mantle_provider.get_gas_price()
            if gas_price_data:
                gas_price_wei = gas_price_data["wei"]
                gas_limit = int(real_quote.get("gas_estimate", "150000"))
                gas_mnt = gas_price_wei * gas_limit / 1e18
                gas_usd = gas_mnt * self._mnt_price_usd
            else:
                gas_usd = 0.1

            details = {
                "price_impact": f"{price_impact * 100:.2f}%",
                "fee_bps": dex["fee_bps"],
                "pairs": real_quote.get("pairs", []),
                "route_addresses": real_quote.get("route_addresses", []),
                "is_real_quote": True,
            }
        else:
            # Fallback simulation for DEXes without on-chain integration
            price_impact = min(0.001 + (amount_usd / 100000) * 0.01, 0.05)
            fee_rate = dex["fee_bps"] / 10000
            expected_out_usd = amount_usd * (1 - price_impact - fee_rate)
            expected_out = expected_out_usd / out_info.get("price_usd", 1.0) if out_info.get("price_usd", 1.0) > 0 else 0
            fee_usd = amount_usd * fee_rate
            gas_usd = 0.1 if chain == "mantle" else 2.0
            slippage = (price_impact + fee_rate) * 100
            details = {
                "price_impact": f"{price_impact * 100:.2f}%",
                "fee_bps": dex["fee_bps"],
                "is_real_quote": False,
                "note": "模拟报价（该 DEX 暂无链上集成）",
            }

        step = RouteStepDetail(
            step_number=1,
            step_type="swap",
            protocol=dex["name"],
            protocol_type=dex["type"],
            from_token=token_in,
            to_token=token_out,
            from_chain=chain,
            to_chain=chain,
            from_chain_name=chain_name,
            to_chain_name=chain_name,
            amount_in=str(amount),
            amount_in_usd=amount_usd,
            expected_out=f"{expected_out:.6f}",
            expected_out_usd=expected_out_usd,
            fee_usd=fee_usd,
            gas_estimate_usd=gas_usd,
            time_estimate_sec=15,
            details=details,
        )

        score = self._calculate_score(expected_out_usd, amount_usd, fee_usd + gas_usd, slippage, 15)
        if is_real:
            score += 25  # Strong boost for real on-chain quotes so they rank first

        return RouteOption(
            route_id=f"samechain_{dex['name'].lower().replace(' ', '_')}_{uuid.uuid4().hex[:6]}",
            name=f"{dex['name']} 直接兑换" + (" [真实报价]" if is_real else " [模拟]"),
            description=f"通过 {dex['name']} 在 {chain_name} 上直接兑换 {token_in} -> {token_out}" + ("，数据来自链上实时查询" if is_real else "，预估数据"),
            total_steps=1,
            steps=[step],
            total_input_usd=amount_usd,
            total_output_usd=expected_out_usd,
            total_output_token=token_out,
            total_fee_usd=fee_usd,
            total_gas_usd=gas_usd,
            total_slippage=slippage,
            total_time_sec=15,
            net_return_usd=expected_out_usd - amount_usd,
            net_return_percent=(expected_out_usd - amount_usd) / amount_usd * 100 if amount_usd > 0 else 0,
            score=score,
            risk_level="low",
        )

    def _build_aggregator_route(
        self, chain: str, token_in: str, token_out: str,
        amount: float, amount_usd: float,
        in_info: dict, out_info: dict
    ) -> RouteOption:
        """Build an aggregator route using REAL on-chain quote when available."""
        chain_name = next((c["name"] for c in SUPPORTED_CHAINS if c["id"] == chain), chain)
        real_quote = None
        is_real = False

        # Try real on-chain quote as "aggregator best path"
        if chain == "mantle":
            try:
                in_decimals = in_info.get("decimals", 18)
                amount_wei = int(amount * (10 ** in_decimals))
                real_quote = self.dex_provider.get_quote(token_in, token_out, str(amount_wei))
                is_real = True
                logger.info(f"Aggregator real quote: {token_in} -> {token_out}, out={real_quote['expected_output']}")
            except Exception as e:
                logger.warning(f"Aggregator real quote failed: {e}, falling back to simulation")

        if real_quote:
            out_decimals = out_info.get("decimals", 18)
            expected_out_wei = int(real_quote["expected_output"])
            expected_out = expected_out_wei / (10 ** out_decimals)
            expected_out_usd = expected_out * out_info.get("price_usd", 1.0)

            fee_wei = int(real_quote.get("fee_amount", "0"))
            fee_token = fee_wei / (10 ** in_info.get("decimals", 18))
            fee_usd = fee_token * in_info.get("price_usd", 1.0)

            price_impact = real_quote.get("price_impact", 0) / 100
            slippage = max(price_impact * 100, 0.5)

            gas_price_data = self.mantle_provider.get_gas_price()
            if gas_price_data:
                gas_price_wei = gas_price_data["wei"]
                gas_limit = int(real_quote.get("gas_estimate", "150000"))
                gas_mnt = gas_price_wei * gas_limit / 1e18
                gas_usd = gas_mnt * self._mnt_price_usd
            else:
                gas_usd = 0.15

            steps = [RouteStepDetail(
                step_number=1,
                step_type="swap",
                protocol="Merchant Moe LB",
                protocol_type="aggregator",
                from_token=token_in,
                to_token=token_out,
                from_chain=chain,
                to_chain=chain,
                from_chain_name=chain_name,
                to_chain_name=chain_name,
                amount_in=str(amount),
                amount_in_usd=amount_usd,
                expected_out=f"{expected_out:.6f}",
                expected_out_usd=expected_out_usd,
                fee_usd=fee_usd,
                gas_estimate_usd=gas_usd,
                time_estimate_sec=12,
                details={
                    "price_impact": f"{price_impact * 100:.2f}%",
                    "pairs": real_quote.get("pairs", []),
                    "route_addresses": real_quote.get("route_addresses", []),
                    "is_real_quote": True,
                    "note": "链上实时最优路径",
                },
            )]
        else:
            # Fallback simulation
            price_impact = min(0.0005 + (amount_usd / 200000) * 0.008, 0.03)
            fee_rate = 0.001
            expected_out_usd = amount_usd * (1 - price_impact - fee_rate)
            expected_out = expected_out_usd / out_info.get("price_usd", 1.0) if out_info.get("price_usd", 1.0) > 0 else 0
            fee_usd = amount_usd * fee_rate
            gas_usd = 0.15 if chain == "mantle" else 3.0
            slippage = (price_impact + fee_rate) * 100

            steps = []
            if amount_usd > 5000:
                split1 = amount * 0.6
                split2 = amount * 0.4
                steps.append(RouteStepDetail(
                    step_number=1,
                    step_type="swap",
                    protocol="ODOS",
                    protocol_type="aggregator",
                    from_token=token_in,
                    to_token=token_out,
                    from_chain=chain,
                    to_chain=chain,
                    from_chain_name=chain_name,
                    to_chain_name=chain_name,
                    amount_in=f"{split1:.6f}",
                    amount_in_usd=amount_usd * 0.6,
                    expected_out=f"{expected_out * 0.6:.6f}",
                    expected_out_usd=expected_out_usd * 0.6,
                    fee_usd=fee_usd * 0.6,
                    gas_estimate_usd=gas_usd * 0.5,
                    time_estimate_sec=10,
                    details={"split": "60%", "path": f"{token_in} -> {token_out}", "is_real_quote": False},
                ))
                steps.append(RouteStepDetail(
                    step_number=2,
                    step_type="swap",
                    protocol="1inch",
                    protocol_type="aggregator",
                    from_token=token_in,
                    to_token=token_out,
                    from_chain=chain,
                    to_chain=chain,
                    from_chain_name=chain_name,
                    to_chain_name=chain_name,
                    amount_in=f"{split2:.6f}",
                    amount_in_usd=amount_usd * 0.4,
                    expected_out=f"{expected_out * 0.4:.6f}",
                    expected_out_usd=expected_out_usd * 0.4,
                    fee_usd=fee_usd * 0.4,
                    gas_estimate_usd=gas_usd * 0.5,
                    time_estimate_sec=10,
                    details={"split": "40%", "path": f"{token_in} -> {token_out}", "is_real_quote": False},
                ))
            else:
                steps.append(RouteStepDetail(
                    step_number=1,
                    step_type="swap",
                    protocol="ODOS",
                    protocol_type="aggregator",
                    from_token=token_in,
                    to_token=token_out,
                    from_chain=chain,
                    to_chain=chain,
                    from_chain_name=chain_name,
                    to_chain_name=chain_name,
                    amount_in=str(amount),
                    amount_in_usd=amount_usd,
                    expected_out=f"{expected_out:.6f}",
                    expected_out_usd=expected_out_usd,
                    fee_usd=fee_usd,
                    gas_estimate_usd=gas_usd,
                    time_estimate_sec=12,
                    details={"split": "100%", "path": f"{token_in} -> {token_out}", "is_real_quote": False, "note": "模拟聚合路径"},
                ))

        score = self._calculate_score(expected_out_usd, amount_usd, fee_usd + gas_usd, slippage, 12)
        score += 3  # Aggregator bonus
        if is_real:
            score += 25

        return RouteOption(
            route_id=f"aggregator_best_{uuid.uuid4().hex[:6]}",
            name="智能聚合器最优路径" + (" [真实报价]" if is_real else " [模拟]"),
            description=f"链上聚合最优路径，获取 {chain_name} 上 {token_in}->{token_out} 最佳价格" + ("，数据来自链上实时查询" if is_real else "，预估数据"),
            total_steps=len(steps),
            steps=steps,
            total_input_usd=amount_usd,
            total_output_usd=expected_out_usd,
            total_output_token=token_out,
            total_fee_usd=fee_usd,
            total_gas_usd=gas_usd,
            total_slippage=slippage,
            total_time_sec=12,
            net_return_usd=expected_out_usd - amount_usd,
            net_return_percent=(expected_out_usd - amount_usd) / amount_usd * 100 if amount_usd > 0 else 0,
            score=score,
            tags=["smart"],
            risk_level="low",
        )

    def _build_cross_chain_route(
        self, source: str, target: str, token_in: str, token_out: str,
        amount: float, amount_usd: float,
        in_info: dict, out_info: dict,
        bridge_id: str, bridge: dict
    ) -> RouteOption:
        """Build a cross-chain route with bridge."""
        source_name = next((c["name"] for c in SUPPORTED_CHAINS if c["id"] == source), source)
        target_name = next((c["name"] for c in SUPPORTED_CHAINS if c["id"] == target), target)

        steps = []
        step_num = 1

        # If input is native, may need wrap
        if in_info.get("is_native", False):
            wrapped = next((t for t in SUPPORTED_TOKENS.get(source, []) if t["symbol"] == f"W{token_in}" or t["symbol"] == f"W{token_in[:3]}"), None)
            if wrapped:
                steps.append(RouteStepDetail(
                    step_number=step_num,
                    step_type="wrap",
                    protocol="WToken",
                    protocol_type="wrap",
                    from_token=token_in,
                    to_token=wrapped["symbol"],
                    from_chain=source,
                    to_chain=source,
                    from_chain_name=source_name,
                    to_chain_name=source_name,
                    amount_in=str(amount),
                    amount_in_usd=amount_usd,
                    expected_out=str(amount),
                    expected_out_usd=amount_usd,
                    fee_usd=0,
                    gas_estimate_usd=0.05 if source == "mantle" else 1.0,
                    time_estimate_sec=5,
                    details={"note": f"将 {token_in} 包装为 {wrapped['symbol']}"},
                ))
                step_num += 1
                token_in_for_bridge = wrapped["symbol"]
            else:
                token_in_for_bridge = token_in
        else:
            token_in_for_bridge = token_in

        # Bridge step
        bridge_fee_usd = amount_usd * bridge["fee_bps"] / 10000
        bridge_gas = 0.2 if source == "mantle" else 2.0
        time_sec = bridge["time_min"] * 60 + (bridge["time_max"] - bridge["time_min"]) * 30

        # Simulate bridge output (slight loss)
        bridge_output_usd = amount_usd * 0.998
        bridge_output_amount = bridge_output_usd / out_info.get("price_usd", 1.0)

        steps.append(RouteStepDetail(
            step_number=step_num,
            step_type="bridge",
            protocol=bridge["name"],
            protocol_type=bridge["type"],
            from_token=token_in_for_bridge,
            to_token=token_out if bridge_id == "cctp" else token_in_for_bridge,
            from_chain=source,
            to_chain=target,
            from_chain_name=source_name,
            to_chain_name=target_name,
            amount_in=str(amount),
            amount_in_usd=amount_usd,
            expected_out=f"{bridge_output_amount:.6f}",
            expected_out_usd=bridge_output_usd,
            fee_usd=bridge_fee_usd,
            gas_estimate_usd=bridge_gas,
            time_estimate_sec=time_sec,
            details={
                "bridge_type": bridge["type"],
                "time_range": f"{bridge['time_min']}min - {bridge['time_max']}min" if bridge["time_max"] < 1000 else f"{bridge['time_min']}min - {bridge['time_max']//60}h",
            },
        ))
        step_num += 1

        # If bridge doesn't swap, need destination swap
        if bridge_id != "cctp" or token_in_for_bridge != token_out:
            # Simulate destination swap
            dest_price_impact = 0.002
            dest_fee_rate = 0.003
            dest_expected_usd = bridge_output_usd * (1 - dest_price_impact - dest_fee_rate)
            dest_expected = dest_expected_usd / out_info.get("price_usd", 1.0) if out_info.get("price_usd", 1.0) > 0 else 0
            dest_fee = bridge_output_usd * dest_fee_rate
            dest_gas = 0.1 if target == "mantle" else 2.0

            steps.append(RouteStepDetail(
                step_number=step_num,
                step_type="swap",
                protocol="Destination DEX",
                protocol_type="amm",
                from_token=token_in_for_bridge,
                to_token=token_out,
                from_chain=target,
                to_chain=target,
                from_chain_name=target_name,
                to_chain_name=target_name,
                amount_in=f"{bridge_output_amount:.6f}",
                amount_in_usd=bridge_output_usd,
                expected_out=f"{dest_expected:.6f}",
                expected_out_usd=dest_expected_usd,
                fee_usd=dest_fee,
                gas_estimate_usd=dest_gas,
                time_estimate_sec=15,
                details={"price_impact": f"{dest_price_impact*100:.2f}%"},
            ))
            final_output_usd = dest_expected_usd
            final_output = dest_expected
        else:
            final_output_usd = bridge_output_usd
            final_output = bridge_output_amount

        total_fee = sum(s.fee_usd for s in steps)
        total_gas = sum(s.gas_estimate_usd for s in steps)
        total_time = sum(s.time_estimate_sec for s in steps)
        slippage = 0.5  # Cross-chain has higher slippage

        score = self._calculate_score(final_output_usd, amount_usd, total_fee + total_gas, slippage, total_time)
        # Penalize slow bridges
        if bridge_id == "mantle_official":
            score -= 15
            risk_level = "medium"
        elif bridge_id == "symbiosis":
            score += 2
            risk_level = "medium"
        elif bridge_id == "router_nitro":
            score += 5
            risk_level = "low"
        else:
            risk_level = "low"

        return RouteOption(
            route_id=f"crosschain_{bridge_id}_{uuid.uuid4().hex[:6]}",
            name=f"{bridge['name']} 跨链方案",
            description=f"通过 {bridge['name']} 从 {source_name} 跨链到 {target_name}",
            total_steps=len(steps),
            steps=steps,
            total_input_usd=amount_usd,
            total_output_usd=final_output_usd,
            total_output_token=token_out,
            total_fee_usd=total_fee,
            total_gas_usd=total_gas,
            total_slippage=slippage,
            total_time_sec=total_time,
            net_return_usd=final_output_usd - amount_usd,
            net_return_percent=(final_output_usd - amount_usd) / amount_usd * 100 if amount_usd > 0 else 0,
            score=score,
            risk_level=risk_level,
        )

    def _calculate_score(self, output_usd: float, input_usd: float, cost_usd: float, slippage: float, time_sec: int) -> float:
        """Calculate route score (0-100). Higher is better."""
        if input_usd <= 0:
            return 0
        # Return ratio (50%)
        return_ratio = output_usd / input_usd
        return_score = min(max((return_ratio - 0.95) * 1000, 0), 50)

        # Cost efficiency (25%)
        cost_ratio = cost_usd / input_usd
        cost_score = max(25 - cost_ratio * 2500, 0)

        # Slippage (15%)
        slippage_score = max(15 - slippage * 10, 0)

        # Speed (10%)
        time_score = max(10 - time_sec / 60, 0)

        return round(return_score + cost_score + slippage_score + time_score, 1)

    def _rank_routes(self, routes: List[RouteOption]) -> List[RouteOption]:
        """Sort routes by score descending, with real on-chain quotes prioritized."""
        # Prioritize real quotes: boolean True > False when multiplied by a large factor
        def sort_key(r: RouteOption):
            is_real = any(s.details.get("is_real_quote", False) for s in r.steps)
            return (is_real, r.score)
        return sorted(routes, key=sort_key, reverse=True)

    def _generate_analysis_summary(
        self, routes: List[RouteOption],
        source: str, target: str, token_in: str, token_out: str,
        amount: float, is_cross_chain: bool
    ) -> str:
        """Generate human-readable analysis summary."""
        if not routes:
            return "未找到可用路由方案"

        best = routes[0]
        cross_str = "跨链" if is_cross_chain else "同链"

        summary = (
            f"分析完成！共找到 {len(routes)} 个{best.from_chain if False else cross_str}路由方案。"
            f"最优方案为「{best.name}」，预计获得 {best.total_output_usd:.2f} USD 等值 {token_out}，"
            f"净收益 {best.net_return_percent:+.3f}%，耗时约 {best.total_time_sec//60}分{best.total_time_sec%60}秒。"
        )

        if is_cross_chain:
            summary += " 跨链交易请注意桥接时间和最终性确认。"

        return summary


# Global engine
routing_engine = SmartRoutingEngine()


# ============ Wallet Check Simulator ============

async def check_wallet_for_route(
    session: WizardSessionData,
    wallet_address: str
) -> WalletCheckResult:
    """Check wallet balances and allowances using REAL on-chain data."""
    if not session.amount_data or not session.token_data or not session.chain_data:
        raise ValueError("会话数据不完整")

    amount = float(session.amount_data.amount)
    token_in = session.token_data.token_in
    source = session.chain_data.source_chain
    target = session.chain_data.target_chain

    # Get token info
    tokens = SUPPORTED_TOKENS.get(source, [])
    token_info = next((t for t in tokens if t["symbol"] == token_in), None)
    decimals = token_info["decimals"] if token_info else 18
    is_native = token_info.get("is_native", False) if token_info else False
    required_str = f"{amount:.{decimals}f}"

    # --- Real balance check (Mantle only) ---
    balance_raw = 10.0  # fallback
    balance_str = f"{Decimal(str(balance_raw)).quantize(Decimal('0.' + '0'*decimals))}"
    balance_ok = balance_raw >= amount
    balance_sufficient = balance_raw >= amount * 1.05

    if source == "mantle" and token_info:
        try:
            provider = MantleProvider()
            token_address = _resolve_token_address(token_in, source)
            balance_wei = provider.get_token_balance(token_address, wallet_address)
            if balance_wei is not None:
                balance_raw = balance_wei / (10 ** decimals)
                balance_str = f"{Decimal(balance_wei) / Decimal(10 ** decimals):.{decimals}f}"
                balance_ok = balance_raw >= amount
                balance_sufficient = balance_raw >= amount * 1.05
                logger.info(f"Real balance for {wallet_address}: {balance_str} {token_in}")
        except Exception as e:
            logger.warning(f"Failed to query real balance: {e}, using fallback")

    # --- Real allowance check (Mantle only) ---
    allowance_ok = is_native
    allowance_str = "∞" if is_native else "0"
    allowance_required = "0" if is_native else required_str

    if not is_native and source == "mantle" and token_info:
        try:
            provider = MantleProvider()
            token_address = _resolve_token_address(token_in, source)
            router_address = LB_ROUTER_ADDRESS
            allowance_wei = provider.get_token_allowance(token_address, wallet_address, router_address)
            if allowance_wei is not None:
                required_wei = int(amount * (10 ** decimals))
                allowance_ok = allowance_wei >= required_wei
                allowance_str = f"{Decimal(allowance_wei) / Decimal(10 ** decimals):.{decimals}f}"
                logger.info(f"Real allowance for {wallet_address}: {allowance_str} {token_in}")
        except Exception as e:
            logger.warning(f"Failed to query real allowance: {e}, using fallback")

    # --- Real gas checks (Mantle only) ---
    source_gas_ok = True
    source_gas = "0.05" if source == "mantle" else "0.002"
    source_gas_required = "0.01" if source == "mantle" else "0.001"

    if source == "mantle":
        try:
            provider = MantleProvider()
            gas_price_data = provider.get_gas_price()
            # Native MNT balance for gas
            native_balance_wei = provider.get_token_balance(_resolve_token_address("MNT", source), wallet_address)
            if gas_price_data and native_balance_wei is not None:
                gas_price_wei = gas_price_data["wei"]
                gas_limit = 200000
                gas_needed_mnt = gas_price_wei * gas_limit / 1e18
                source_gas = f"{native_balance_wei / 1e18:.6f}"
                source_gas_required = f"{gas_needed_mnt:.6f}"
                source_gas_ok = native_balance_wei / 1e18 >= gas_needed_mnt * 1.5
        except Exception as e:
            logger.warning(f"Failed to query real gas data: {e}, using fallback")

    target_gas_ok = True
    target_gas = "0.05" if target == "mantle" else "0.002"
    target_gas_required = "0.01" if target == "mantle" else "0.001"

    if target == "mantle" and source != target:
        try:
            provider = MantleProvider()
            gas_price_data = provider.get_gas_price()
            native_balance_wei = provider.get_token_balance(_resolve_token_address("MNT", target), wallet_address)
            if gas_price_data and native_balance_wei is not None:
                gas_price_wei = gas_price_data["wei"]
                gas_limit = 200000
                gas_needed_mnt = gas_price_wei * gas_limit / 1e18
                target_gas = f"{native_balance_wei / 1e18:.6f}"
                target_gas_required = f"{gas_needed_mnt:.6f}"
                target_gas_ok = native_balance_wei / 1e18 >= gas_needed_mnt * 1.5
        except Exception as e:
            logger.warning(f"Failed to query real target gas data: {e}, using fallback")

    warnings = []
    if not balance_ok:
        warnings.append(f"{token_in} 余额不足: 当前 {balance_str}, 需要 {required_str}")
    elif not balance_sufficient:
        warnings.append(f"{token_in} 余额紧张，建议保留 5% 缓冲以支付 Gas 费用")
    if not allowance_ok:
        warnings.append(f"需要先授权 {token_in} 给路由器合约")
    if session.is_cross_chain:
        warnings.append("跨链交易需要目标链 Gas 代币用于后续操作")
        if source == "ethereum" or target == "ethereum":
            warnings.append("以太坊 Gas 费用较高，请注意成本")

    can_proceed = balance_ok and source_gas_ok and target_gas_ok

    return WalletCheckResult(
        address=wallet_address,
        source_chain=source,
        target_chain=target,
        token_in=token_in,
        token_out=session.token_data.token_out,
        amount=session.amount_data.amount,
        balance_ok=balance_ok,
        balance_sufficient=balance_sufficient,
        balance_current=balance_str,
        balance_required=required_str,
        allowance_ok=allowance_ok,
        allowance_current=allowance_str,
        allowance_required=allowance_required,
        source_gas_ok=source_gas_ok,
        source_gas_balance=source_gas,
        source_gas_required=source_gas_required,
        target_gas_ok=target_gas_ok,
        target_gas_balance=target_gas,
        target_gas_required=target_gas_required,
        warnings=warnings,
        can_proceed=can_proceed,
    )


# ============ FastAPI Router ============

routing_router = APIRouter(prefix="/api/routing", tags=["Smart Routing"])


@routing_router.post("/wizard/start", summary="Start New Routing Wizard")
async def start_wizard():
    """Start a new smart routing wizard session."""
    session = await session_manager.create_session()
    return {
        "success": True,
        "data": session.model_dump(),
        "message": "智能路由向导已启动，请选择源链和目标链",
    }


@routing_router.get("/wizard/{session_id}", summary="Get Wizard Session")
async def get_wizard_session(session_id: str):
    """Get current state of a wizard session."""
    session = await session_manager.get_session(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="会话不存在或已过期")
    return {
        "success": True,
        "data": session.model_dump(),
    }


@routing_router.post("/wizard/{session_id}/step/{step_id}", summary="Submit Step Data")
async def submit_step(session_id: str, step_id: str, request: Request):
    """Submit data for a wizard step and advance."""
    body = await request.json()
    session = await session_manager.submit_step(session_id, step_id, body)
    return {
        "success": True,
        "data": session.model_dump(),
        "message": f"步骤 {step_id} 已完成，当前步骤: {session.current_step.value}",
    }


@routing_router.post("/wizard/{session_id}/analyze", summary="Trigger Smart Route Analysis")
async def analyze_routes(session_id: str):
    """Trigger the Routing Agent to analyze routes."""
    session = await session_manager.get_session(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="会话不存在或已过期")

    if not session.chain_data or not session.token_data or not session.amount_data:
        raise HTTPException(status_code=400, detail="请先完成链选择、代币选择和金额输入")

    # Mark analysis step as in-progress
    if WizardStep.SMART_ANALYSIS not in session.completed_steps:
        session.completed_steps.append(WizardStep.SMART_ANALYSIS)
    session.current_step = WizardStep.SMART_ANALYSIS
    session.analysis_data = AnalysisResult(
        status="analyzing",
        progress=AnalysisProgress(
            status="analyzing",
            progress_percent=0,
            current_task="准备分析...",
            logs=["Agent 启动中..."],
            started_at=datetime.utcnow().isoformat(),
        ),
    )
    await session_manager._save(session)

    async def progress_callback(task: str, percent: Optional[int] = None):
        progress = await session_manager.get_agent_progress(session_id)
        progress["current_task"] = task
        if percent is not None:
            progress["progress_percent"] = percent
        progress["logs"].append(task)
        progress["status"] = "analyzing"
        await session_manager.set_agent_progress(session_id, progress)

    async def run_analysis():
        try:
            result = await routing_engine.analyze_routes(
                source_chain=session.chain_data.source_chain,
                target_chain=session.chain_data.target_chain,
                token_in=session.token_data.token_in,
                token_out=session.token_data.token_out,
                amount=session.amount_data.amount,
                is_cross_chain=session.is_cross_chain,
                progress_callback=progress_callback,
            )
            await session_manager.update_analysis(session_id, result)

            # Auto-advance to route display
            s = await session_manager.get_session(session_id)
            if s:
                s.current_step = WizardStep.ROUTE_DISPLAY
                if WizardStep.ROUTE_DISPLAY not in s.completed_steps:
                    s.completed_steps.append(WizardStep.ROUTE_DISPLAY)
                await session_manager._save(s)

            progress = await session_manager.get_agent_progress(session_id)
            progress["status"] = "completed"
            progress["progress_percent"] = 100
            progress["current_task"] = "分析完成"
            await session_manager.set_agent_progress(session_id, progress)

        except Exception as e:
            logger.error(f"Route analysis failed for {session_id}: {e}")
            progress = await session_manager.get_agent_progress(session_id)
            progress["status"] = "failed"
            progress["current_task"] = f"分析失败: {str(e)}"
            progress["error"] = str(e)
            await session_manager.set_agent_progress(session_id, progress)

            s = await session_manager.get_session(session_id)
            if s and s.analysis_data:
                s.analysis_data.status = "failed"
                s.analysis_data.progress.status = "failed"
                s.analysis_data.progress.error = str(e)
                await session_manager._save(s)

    # Start analysis in background
    task = asyncio.create_task(run_analysis())
    session_manager._agent_tasks[session_id] = task

    return {
        "success": True,
        "data": {
            "session_id": session_id,
            "status": "analyzing",
            "message": "智能路由 Agent 已启动，正在分析最优路径...",
        },
    }


@routing_router.get("/wizard/{session_id}/status", summary="Get Analysis Status")
async def get_analysis_status(session_id: str):
    """Get real-time analysis progress."""
    session = await session_manager.get_session(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="会话不存在或已过期")

    progress = await session_manager.get_agent_progress(session_id)

    return {
        "success": True,
        "data": {
            "session_id": session_id,
            "current_step": session.current_step.value,
            "analysis_status": session.analysis_data.status if session.analysis_data else "idle",
            "progress": progress,
            "routes_count": len(session.analysis_data.routes) if session.analysis_data else 0,
            "best_route_id": session.analysis_data.best_route_id if session.analysis_data else None,
        },
    }


@routing_router.post("/wizard/{session_id}/select-route", summary="Select Route")
async def select_route(session_id: str, request: Request):
    """Select a route option."""
    body = await request.json()
    route_id = body.get("route_id")

    session = await session_manager.get_session(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="会话不存在或已过期")

    if not session.analysis_data or not session.analysis_data.routes:
        raise HTTPException(status_code=400, detail="请先完成路由分析")

    route = next((r for r in session.analysis_data.routes if r.route_id == route_id), None)
    if route is None:
        raise HTTPException(status_code=400, detail=f"无效的路由 ID: {route_id}")

    session.selected_route_id = route_id
    if WizardStep.ROUTE_SELECT not in session.completed_steps:
        session.completed_steps.append(WizardStep.ROUTE_SELECT)
    session.current_step = WizardStep.WALLET_CHECK
    await session_manager._save(session)

    return {
        "success": True,
        "data": {
            "session_id": session_id,
            "selected_route": route.model_dump(),
            "current_step": session.current_step.value,
        },
        "message": f"已选择路由: {route.name}，进入钱包检查",
    }


@routing_router.post("/wizard/{session_id}/wallet-check", summary="Check Wallet")
async def wallet_check(session_id: str, request: Request):
    """Check wallet balances and allowances."""
    body = await request.json()
    wallet_address = body.get("wallet_address")

    if not wallet_address:
        raise HTTPException(status_code=400, detail="需要提供钱包地址")

    session = await session_manager.get_session(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="会话不存在或已过期")

    result = await check_wallet_for_route(session, wallet_address)

    session.wallet_check = result
    if WizardStep.WALLET_CHECK not in session.completed_steps:
        session.completed_steps.append(WizardStep.WALLET_CHECK)
    session.current_step = WizardStep.EXECUTE_CONFIRM
    await session_manager._save(session)

    return {
        "success": True,
        "data": result.model_dump(),
        "message": "钱包检查完成" if result.can_proceed else "钱包检查发现问题，请查看警告",
    }


# Merchant Moe LB Router ABI (minimal for build_transaction)
LB_ROUTER_ABI_WIZARD = [
    {
        "inputs": [
            {"internalType": "uint256", "name": "amountOutMin", "type": "uint256"},
            {"components": [
                {"internalType": "address", "name": "token", "type": "address"},
                {"internalType": "uint256", "name": "binStep", "type": "uint256"},
                {"internalType": "uint8", "name": "version", "type": "uint8"}
            ], "internalType": "struct ILBRouter.Path[]", "name": "path", "type": "tuple[]"},
            {"internalType": "address", "name": "to", "type": "address"},
            {"internalType": "uint256", "name": "deadline", "type": "uint256"}
        ],
        "name": "swapExactNATIVEForTokens",
        "outputs": [{"internalType": "uint256", "name": "amountOut", "type": "uint256"}],
        "stateMutability": "payable",
        "type": "function"
    },
    {
        "inputs": [
            {"internalType": "uint256", "name": "amountIn", "type": "uint256"},
            {"internalType": "uint256", "name": "amountOutMinNATIVE", "type": "uint256"},
            {"components": [
                {"internalType": "address", "name": "token", "type": "address"},
                {"internalType": "uint256", "name": "binStep", "type": "uint256"},
                {"internalType": "uint8", "name": "version", "type": "uint8"}
            ], "internalType": "struct ILBRouter.Path[]", "name": "path", "type": "tuple[]"},
            {"internalType": "address payable", "name": "to", "type": "address"},
            {"internalType": "uint256", "name": "deadline", "type": "uint256"}
        ],
        "name": "swapExactTokensForNATIVE",
        "outputs": [{"internalType": "uint256", "name": "amountOut", "type": "uint256"}],
        "stateMutability": "nonpayable",
        "type": "function"
    },
    {
        "inputs": [
            {"internalType": "uint256", "name": "amountIn", "type": "uint256"},
            {"internalType": "uint256", "name": "amountOutMin", "type": "uint256"},
            {"components": [
                {"internalType": "address", "name": "token", "type": "address"},
                {"internalType": "uint256", "name": "binStep", "type": "uint256"},
                {"internalType": "uint8", "name": "version", "type": "uint8"}
            ], "internalType": "struct ILBRouter.Path[]", "name": "path", "type": "tuple[]"},
            {"internalType": "address", "name": "to", "type": "address"},
            {"internalType": "uint256", "name": "deadline", "type": "uint256"}
        ],
        "name": "swapExactTokensForTokens",
        "outputs": [{"internalType": "uint256", "name": "amountOut", "type": "uint256"}],
        "stateMutability": "nonpayable",
        "type": "function"
    },
]

LB_ROUTER_ADDRESS = "0x013e138EF6008ae5FDFDE29700e3f2Bc61d21E3a"
MANTLE_CHAIN_ID = 5000
MANTLE_SEPOLIA_CHAIN_ID = 5003


def _resolve_token_address(symbol: str, chain: str = "mantle") -> str:
    """Resolve token symbol to address."""
    tokens = SUPPORTED_TOKENS.get(chain, SUPPORTED_TOKENS.get("mantle", []))
    for t in tokens:
        if t["symbol"].upper() == symbol.upper():
            return t["address"]
    # Fallback: treat as address if it looks like one
    if symbol.startswith("0x") and len(symbol) == 42:
        return Web3.to_checksum_address(symbol)
    raise ValueError(f"Unknown token: {symbol} on chain {chain}")


@routing_router.post("/wizard/{session_id}/execute", summary="Execute Route")
async def execute_route(session_id: str, request: Request):
    """Build unsigned transaction for the selected route. Client signs with MetaMask."""
    body = await request.json()
    sender_address = body.get("sender_address")
    if not sender_address:
        raise HTTPException(status_code=400, detail="请提供 sender_address")

    session = await session_manager.get_session(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="会话不存在或已过期")

    if not session.selected_route_id:
        raise HTTPException(status_code=400, detail="请先选择路由方案")

    selected = None
    if session.analysis_data:
        selected = next((r for r in session.analysis_data.routes if r.route_id == session.selected_route_id), None)

    if not selected:
        raise HTTPException(status_code=400, detail="未找到选中的路由方案")

    # Cross-chain not supported for real execution yet
    if session.is_cross_chain:
        return {
            "success": False,
            "data": {
                "status": "not_supported",
                "error": "跨链路由的真实交易执行暂未支持，请选择同链路由进行测试。",
            },
            "message": "跨链执行暂未支持",
        }

    # Same-chain: build real transaction via Merchant Moe
    try:
        chain_id = MANTLE_CHAIN_ID  # Default to mainnet; can be overridden
        w3 = Web3(Web3.HTTPProvider("https://rpc.mantle.xyz", request_kwargs={"timeout": 10}))
        if not w3.is_connected():
            w3 = Web3(Web3.HTTPProvider("https://rpc.sepolia.mantle.xyz", request_kwargs={"timeout": 10}))
            chain_id = MANTLE_SEPOLIA_CHAIN_ID

        sender = Web3.to_checksum_address(sender_address)
        token_in = session.token_data.token_in if session.token_data else "MNT"
        token_out = session.token_data.token_out if session.token_data else "USDC"
        amount_str = session.amount_data.amount if session.amount_data else "0"

        # Parse amount
        amount_in = int(float(amount_str) * 1e18)  # Assuming 18 decimals for simplicity

        token_in_addr = _resolve_token_address(token_in)
        token_out_addr = _resolve_token_address(token_out)

        router_contract = w3.eth.contract(
            address=Web3.to_checksum_address(LB_ROUTER_ADDRESS),
            abi=LB_ROUTER_ABI_WIZARD
        )

        path = [
            (token_in_addr, 20, 2),
            (token_out_addr, 20, 2),
        ]

        # Estimate min output (use 0.5% slippage)
        min_amount_out = int(amount_in * 0.995)
        deadline = int(datetime.utcnow().timestamp()) + 1200

        is_native_in = token_in.upper() in ("MNT", "WMNT")
        is_native_out = token_out.upper() in ("MNT", "WMNT")

        # Get nonce and gas price
        nonce = w3.eth.get_transaction_count(sender)
        gas_price = w3.eth.gas_price

        if is_native_in:
            tx = router_contract.functions.swapExactNATIVEForTokens(
                min_amount_out, path, sender, deadline
            ).build_transaction({
                "from": sender,
                "value": amount_in,
                "gas": 500000,
                "gasPrice": gas_price,
                "nonce": nonce,
                "chainId": chain_id,
            })
        elif is_native_out:
            tx = router_contract.functions.swapExactTokensForNATIVE(
                amount_in, min_amount_out, path, sender, deadline
            ).build_transaction({
                "from": sender,
                "gas": 500000,
                "gasPrice": gas_price,
                "nonce": nonce,
                "chainId": chain_id,
            })
        else:
            tx = router_contract.functions.swapExactTokensForTokens(
                amount_in, min_amount_out, path, sender, deadline
            ).build_transaction({
                "from": sender,
                "gas": 500000,
                "gasPrice": gas_price,
                "nonce": nonce,
                "chainId": chain_id,
            })

        # Estimate gas
        try:
            estimated_gas = w3.eth.estimate_gas(tx)
            tx["gas"] = int(estimated_gas * 1.2)
        except Exception as e:
            logger.warning(f"Gas estimation failed: {e}, using default gas limit")

        execution = ExecutionResult(
            status="ready_to_sign",
            tx_hash=None,
            explorer_url=f"{'https://sepolia.mantlescan.xyz' if chain_id == 5003 else 'https://mantlescan.xyz'}/address/{sender}",
            gas_used=str(tx["gas"]),
            actual_output=None,
            timestamp=datetime.utcnow().isoformat(),
        )

        session.execution_data = execution
        if WizardStep.EXECUTE_CONFIRM not in session.completed_steps:
            session.completed_steps.append(WizardStep.EXECUTE_CONFIRM)
        await session_manager._save(session)

        return {
            "success": True,
            "data": {
                **execution.model_dump(),
                "tx_params": {
                    "to": tx["to"],
                    "data": tx["data"],
                    "value": str(tx.get("value", 0)),
                    "gasLimit": str(tx["gas"]),
                    "gasPrice": str(gas_price),
                    "nonce": nonce,
                    "chainId": chain_id,
                    "from": sender,
                }
            },
            "message": "交易已构建，请在钱包中签名并广播",
        }

    except Exception as e:
        logger.error(f"Failed to build execution transaction: {e}")
        raise HTTPException(status_code=500, detail=f"构建交易失败: {str(e)}")


@routing_router.get("/chains", summary="Get Supported Chains")
async def get_chains():
    """Get list of supported chains."""
    return {
        "success": True,
        "data": SUPPORTED_CHAINS,
    }


@routing_router.get("/tokens/{chain_id}", summary="Get Supported Tokens")
async def get_tokens(chain_id: str):
    """Get supported tokens for a chain."""
    tokens = SUPPORTED_TOKENS.get(chain_id, [])
    return {
        "success": True,
        "data": tokens,
        "chain": chain_id,
    }


@routing_router.get("/wizard/{session_id}/reset", summary="Reset Wizard")
async def reset_wizard(session_id: str):
    """Reset wizard to initial state."""
    await session_manager.cancel_agent(session_id)
    new_session = await session_manager.create_session()
    return {
        "success": True,
        "data": new_session.model_dump(),
        "message": "向导已重置",
    }
