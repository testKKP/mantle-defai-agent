import axios, { type AxiosInstance } from 'axios';
import type { SentimentData, OnChainOverview, BlockData, GasData, NetworkData, ProtocolData, SwapQuote, AppSettings, TrendsData, TVLHistory, WizardSessionData, ChainInfo, TokenInfo, RouteOption, AnalysisProgress, WalletCheckResult, TrendTransaction, HourlyAnalysis, HalfDaySummary, BigSummary, TrendAggregates, TrendTarget, ChainDistributionItem, LargeTransaction, MonitorSummaryItem, ElliottWaveResult, OnChainSignal } from '../types';

const DEFAULT_SETTINGS: AppSettings = {
  apiBase: import.meta.env.VITE_API_BASE || '',
  refreshInterval: 900000,
};

function loadSettings(): AppSettings {
  try {
    const saved = localStorage.getItem('mantle_settings');
    if (saved) {
      const parsed = JSON.parse(saved);
      return { ...DEFAULT_SETTINGS, ...parsed };
    }
  } catch { /* ignore */ }
  return DEFAULT_SETTINGS;
}

let currentSettings = loadSettings();

export function getSettings(): AppSettings {
  return { ...currentSettings };
}

export function saveSettings(settings: Partial<AppSettings>): void {
  currentSettings = { ...currentSettings, ...settings };
  localStorage.setItem('mantle_settings', JSON.stringify(currentSettings));
}

function createClient(): AxiosInstance {
  return axios.create({
    baseURL: currentSettings.apiBase,
    timeout: 15000,
    headers: {
      'Content-Type': 'application/json',
    },
  });
}

let apiClient = createClient();

export function refreshApiClient(): void {
  apiClient = createClient();
}

// Health check
export async function checkHealth(): Promise<{ online: boolean; services?: Record<string, boolean> }> {
  try {
    const res = await apiClient.get('/health', { timeout: 5000 });
    return { online: res.status === 200, services: res.data?.services };
  } catch {
    return { online: false };
  }
}

// Sentiment
export async function getLatestSentiment(walletAddress?: string): Promise<SentimentData> {
  const params = walletAddress ? { wallet_address: walletAddress } : undefined;
  const res = await apiClient.get('/api/sentiment/latest', { params });
  if (res.data?.success) return res.data.data;
  throw new Error(res.data?.message || 'Failed to load sentiment');
}

export async function analyzeSentiment(timeframe: string, walletAddress?: string): Promise<SentimentData> {
  const body: Record<string, any> = { timeframe };
  if (walletAddress) body.wallet_address = walletAddress;
  const res = await apiClient.post('/api/sentiment/analyze', body);
  if (res.data?.success) return res.data.data;
  throw new Error(res.data?.message || 'Failed to analyze sentiment');
}

// OnChain
export async function getOnChainOverview(): Promise<OnChainOverview> {
  const res = await apiClient.get('/api/onchain/overview');
  if (res.data?.success) return res.data.data;
  throw new Error(res.data?.message || 'Failed to load overview');
}

export async function getProtocols(): Promise<ProtocolData[]> {
  const res = await apiClient.get('/api/onchain/protocols');
  if (res.data?.success) {
    const data = res.data.data;
    return Array.isArray(data) ? data : (data.protocols || []);
  }
  throw new Error(res.data?.message || 'Failed to load protocols');
}

export async function getBlockData(): Promise<BlockData> {
  const res = await apiClient.get('/api/onchain/block');
  if (res.data?.success) return res.data.data;
  throw new Error(res.data?.message || 'Failed to load block data');
}

export async function getGasData(): Promise<GasData> {
  const res = await apiClient.get('/api/onchain/gas');
  if (res.data?.success) return res.data.data;
  throw new Error(res.data?.message || 'Failed to load gas data');
}

export async function getNetworkData(): Promise<NetworkData> {
  const res = await apiClient.get('/api/onchain/network');
  if (res.data?.success) return res.data.data;
  throw new Error(res.data?.message || 'Failed to load network data');
}

export async function getAllOnChainData(): Promise<{
  overview: OnChainOverview;
  protocols: ProtocolData[];
  block: BlockData;
  gas: GasData;
  network: NetworkData;
}> {
  const res = await apiClient.get('/api/onchain/all');
  if (res.data?.success) return res.data.data;
  throw new Error(res.data?.message || 'Failed to load onchain data');
}

// Mantle Trends & TVL
export async function getMantleTrends(): Promise<TrendsData> {
  const res = await apiClient.get('/api/mantle/trends');
  if (res.data?.success) {
    const data = res.data.data;
    // Backend returns { block_activity: number[], gas_trend: number[], timestamps: string[] }
    // Convert to frontend TrendsData format { activity: TrendPoint[], gas: TrendPoint[], ... }
    const timestamps: string[] = data.timestamps || [];
    const activity = timestamps.map((ts: string, i: number) => ({
      timestamp: ts,
      activity_index: data.block_activity?.[i] ?? undefined,
    }));
    const gas = timestamps.map((ts: string, i: number) => ({
      timestamp: ts,
      gas_price: data.gas_trend?.[i] ?? undefined,
    }));
    return { activity, gas, tvl: [], protocols: [] };
  }
  throw new Error(res.data?.message || 'Failed to load trends');
}

export async function getMantleTVLHistory(): Promise<TVLHistory> {
  const res = await apiClient.get('/api/mantle/tvl/history');
  if (res.data?.success) {
    const data = res.data.data;
    // Backend returns {chain, days, history: [{date, tvl}]}
    const history = Array.isArray(data) ? data : (data.history || []);
    return history.map((d: any) => ({
      timestamp: d.date || d.timestamp,
      tvl: d.tvl,
    }));
  }
  throw new Error(res.data?.message || 'Failed to load TVL history');
}

// Swap
export async function getSwapQuote(
  tokenIn: string,
  tokenOut: string,
  amountIn: string,
  slippage: number = 0.005
): Promise<SwapQuote> {
  const res = await apiClient.post('/api/swap/quote', {
    token_in: tokenIn,
    token_out: tokenOut,
    amount_in: amountIn,
    slippage,
  });
  if (res.data?.success) return res.data.data;
  throw new Error(res.data?.message || 'Failed to get quote');
}

// Wallet
export async function getWalletBalance(address: string): Promise<Record<string, string>> {
  const res = await apiClient.get(`/api/wallet/balance/${address}`);
  if (res.data?.success) return res.data.data.balances;
  throw new Error(res.data?.message || 'Failed to load balance');
}

// Transaction History
const TX_STORAGE_KEY = 'mantle_transactions';

export function saveTransaction(tx: any): void {
  try {
    const existing = getTransactions();
    const newTx = {
      id: `${Date.now()}_${Math.random().toString(36).substr(2, 9)}`,
      tx_hash: tx.tx_hash || tx.hash,
      status: tx.status === 1 || tx.status === 'success' ? 'success' : 'pending',
      sender: tx.sender,
      token_in: tx.token_in,
      token_out: tx.token_out,
      amount_in: tx.amount_in,
      expected_output: tx.expected_output || tx.min_amount_out,
      timestamp: new Date().toISOString(),
      explorer_url: tx.explorer_url || `https://mantlescan.xyz/tx/${tx.tx_hash || tx.hash}`,
    };
    const updated = [newTx, ...existing].slice(0, 100);
    localStorage.setItem(TX_STORAGE_KEY, JSON.stringify(updated));
  } catch (e) {
    console.error('Failed to save transaction:', e);
  }
}

export function getTransactions(): any[] {
  try {
    const saved = localStorage.getItem(TX_STORAGE_KEY);
    return saved ? JSON.parse(saved) : [];
  } catch {
    return [];
  }
}

export function clearTransactions(): void {
  localStorage.removeItem(TX_STORAGE_KEY);
}

// ============ Smart Routing Wizard API ============

export async function startWizard(): Promise<WizardSessionData> {
  const res = await apiClient.post('/api/routing/wizard/start');
  if (res.data?.success) return res.data.data;
  throw new Error(res.data?.message || 'Failed to start wizard');
}

export async function getWizardSession(sessionId: string): Promise<WizardSessionData> {
  const res = await apiClient.get(`/api/routing/wizard/${sessionId}`);
  if (res.data?.success) return res.data.data;
  throw new Error(res.data?.message || 'Failed to get session');
}

export async function submitWizardStep(
  sessionId: string,
  stepId: string,
  data: Record<string, any>
): Promise<WizardSessionData> {
  const res = await apiClient.post(`/api/routing/wizard/${sessionId}/step/${stepId}`, data);
  if (res.data?.success) return res.data.data;
  throw new Error(res.data?.message || 'Failed to submit step');
}

export async function analyzeRoutes(sessionId: string): Promise<{ status: string; message: string }> {
  const res = await apiClient.post(`/api/routing/wizard/${sessionId}/analyze`);
  if (res.data?.success) return res.data.data;
  throw new Error(res.data?.message || 'Failed to start analysis');
}

export async function getAnalysisStatus(sessionId: string): Promise<{
  current_step: string;
  analysis_status: string;
  progress: AnalysisProgress;
  routes_count: number;
  best_route_id?: string;
}> {
  const res = await apiClient.get(`/api/routing/wizard/${sessionId}/status`);
  if (res.data?.success) return res.data.data;
  throw new Error(res.data?.message || 'Failed to get status');
}

export async function selectRoute(sessionId: string, routeId: string): Promise<{
  selected_route: RouteOption;
  current_step: string;
}> {
  const res = await apiClient.post(`/api/routing/wizard/${sessionId}/select-route`, { route_id: routeId });
  if (res.data?.success) return res.data.data;
  throw new Error(res.data?.message || 'Failed to select route');
}

export async function checkWallet(sessionId: string, walletAddress: string): Promise<WalletCheckResult> {
  const res = await apiClient.post(`/api/routing/wizard/${sessionId}/wallet-check`, { wallet_address: walletAddress });
  if (res.data?.success) return res.data.data;
  throw new Error(res.data?.message || 'Failed to check wallet');
}

export async function executeRoute(sessionId: string, senderAddress: string): Promise<any> {
  const res = await apiClient.post(`/api/routing/wizard/${sessionId}/execute`, { sender_address: senderAddress });
  if (res.data?.success) return res.data.data;
  throw new Error(res.data?.message || 'Failed to execute route');
}

export async function getSupportedChains(): Promise<ChainInfo[]> {
  const res = await apiClient.get('/api/routing/chains');
  if (res.data?.success) return res.data.data;
  throw new Error(res.data?.message || 'Failed to get chains');
}

export async function getSupportedTokens(chainId: string): Promise<TokenInfo[]> {
  const res = await apiClient.get(`/api/routing/tokens/${chainId}`);
  if (res.data?.success) return res.data.data;
  throw new Error(res.data?.message || 'Failed to get tokens');
}

// ============ Backtest API ============

export async function runBacktest(): Promise<{ closed: number; evaluated: number; errors: string[]; timestamp: string }> {
  const res = await apiClient.post('/api/sentiment/backtest/run');
  if (res.data?.success) return res.data.data;
  throw new Error(res.data?.message || 'Failed to run backtest');
}

export async function getBacktestResult(symbol: string, timeframe: string): Promise<{
  symbol: string;
  timeframe: string;
  stats: Record<string, {
    total_signals: number;
    insufficient_data: boolean;
    win_rate: number;
    avg_pnl: number;
    avg_net_pnl: number;
    max_pnl: number;
    min_pnl: number;
    profit_factor: number;
    avg_win: number;
    avg_loss: number;
  }>;
  recent_signals: any[];
}> {
  const res = await apiClient.get(`/api/sentiment/backtest/${encodeURIComponent(symbol)}/${encodeURIComponent(timeframe)}`);
  if (res.data?.success) return res.data.data;
  throw new Error(res.data?.message || 'Failed to load backtest result');
}

export async function getBacktestSummary(): Promise<{
  symbols: { symbol: string; overall_win_rate: number; best_strength: string | null; total_signals: number }[];
  total_symbols: number;
}> {
  const res = await apiClient.get('/api/sentiment/backtest/summary');
  if (res.data?.success) return res.data.data;
  throw new Error(res.data?.message || 'Failed to load backtest summary');
}

export async function getBatchBacktest(timeframe: string): Promise<{
  timeframe: string;
  total_symbols_tested: number;
  symbols_with_signals: number;
  recommendations: any[];
  all_signals: any[];
  timestamp: string;
}> {
  const res = await apiClient.get(`/api/sentiment/backtest-batch/${encodeURIComponent(timeframe)}`, { timeout: 120000 });
  if (res.data?.success) return res.data.data;
  throw new Error(res.data?.message || 'Batch backtest failed');
}

// ============ On-Chain Trends API ============

export async function getTrendTransactions(hours = 1, chain?: string): Promise<{ success: boolean; count: number; data: TrendTransaction[] }> {
  const params = new URLSearchParams();
  params.append('hours', String(hours));
  if (chain) params.append('chain', chain);
  const res = await apiClient.get(`/api/onchain/trend-transactions?${params.toString()}`);
  if (!res.data?.success) throw new Error(res.data?.message || 'Failed to load trend transactions');
  return res.data;
}

export async function triggerHourlyAnalysis(): Promise<{ success: boolean; message: string }> {
  const res = await apiClient.post('/api/onchain/analyze-now');
  if (res.data?.success) return res.data.data;
  throw new Error(res.data?.message || 'Failed to trigger analysis');
}

export async function getHourlyAnalysis(limit = 24): Promise<HourlyAnalysis[]> {
  const res = await apiClient.get(`/api/onchain/analysis/hourly?limit=${limit}`);
  if (res.data?.success) return res.data.data;
  throw new Error(res.data?.message || 'Failed to load hourly analysis');
}

export async function getHalfDaySummaries(limit = 10): Promise<HalfDaySummary[]> {
  const res = await apiClient.get(`/api/onchain/analysis/half-day?limit=${limit}`);
  if (res.data?.success) return res.data.data;
  throw new Error(res.data?.message || 'Failed to load half-day summaries');
}

export async function getBigSummaries(limit = 5): Promise<BigSummary[]> {
  const res = await apiClient.get(`/api/onchain/analysis/big?limit=${limit}`);
  if (res.data?.success) return res.data.data;
  throw new Error(res.data?.message || 'Failed to load big summaries');
}

export async function getTrendAggregates(hours = 24): Promise<TrendAggregates> {
  const res = await apiClient.get(`/api/onchain/trend-aggregates?hours=${hours}`);
  if (!res.data?.success) throw new Error(res.data?.message || 'Failed to load trend aggregates');
  return res.data.data;
}

export async function analyzeTargetsWithAI(data: {
  top_targets: TrendTarget[];
  chain_distribution: ChainDistributionItem[];
  category_distribution: ChainDistributionItem[];
  summary: TrendAggregates['summary'];
}): Promise<{ success: boolean; analysis: string }> {
  const res = await apiClient.post('/api/onchain/analyze-targets', data);
  if (!res.data?.success) throw new Error(res.data?.message || 'AI analysis failed');
  return res.data;
}

// 大额交易监控
export async function getLargeTransactions(
  hours?: number,
  symbol?: string,
  direction?: string,
  chain?: string,
  min_usd?: number,
): Promise<{ success: boolean; count: number; data: LargeTransaction[] }> {
  const params = new URLSearchParams();
  if (hours) params.set('hours', hours.toString());
  if (symbol) params.set('symbol', symbol);
  if (direction) params.set('direction', direction);
  if (chain) params.set('chain', chain);
  if (min_usd) params.set('min_usd', min_usd.toString());
  const res = await apiClient.get(`/api/onchain/large-transactions?${params}`);
  return res.data;
}

export async function getMonitorSummary(hours?: number): Promise<{ success: boolean; data: MonitorSummaryItem[] }> {
  const params = new URLSearchParams();
  if (hours) params.set('hours', hours.toString());
  const res = await apiClient.get(`/api/onchain/monitor/summary?${params}`);
  return res.data;
}

// ============ On-Chain Signals API ============

export async function getRecentOnChainSignals(limit?: number): Promise<OnChainSignal[]> {
  const res = await apiClient.get('/api/onchain/signals/recent', {
    params: { limit: limit ?? 50 },
  });
  if (res.data?.success) return res.data.data || [];
  throw new Error(res.data?.message || 'Failed to load on-chain signals');
}

// ============ Elliott Wave API ============

export async function getElliottWave(symbol: string, timeframe: string = '1d'): Promise<ElliottWaveResult | null> {
  const res = await apiClient.get('/api/sentiment/elliott-wave', {
    params: { symbol, timeframe },
    timeout: 10000,
  });
  if (res.data?.success) return res.data.data;
  return null;
}

export interface ElliottWaveListItem {
  symbol: string;
  timeframe: string;
  chart_paths: string[];
  computed_at: string;
  wave_pattern?: string;
  direction?: string;
  current_wave?: string;
}

export async function getElliottWaveList(timeframe: string = '1d'): Promise<ElliottWaveListItem[]> {
  const res = await apiClient.get('/api/sentiment/elliott-wave/list', {
    params: { timeframe },
    timeout: 10000,
  });
  if (res.data?.success) return res.data.data || [];
  throw new Error(res.data?.message || 'Failed to load Elliott Wave list');
}
