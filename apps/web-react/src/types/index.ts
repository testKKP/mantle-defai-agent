export interface CalculationStep {
  step: string;
  value: number;
  description?: string;
}

export interface SentimentData {
  sentiment_index: number;
  bullish_count: number;
  neutral_count: number;
  bearish_count: number;
  total_analyzed: number;
  top_bullish?: TokenData[];
  top_bearish?: TokenData[];
  mantle_data?: MantleSentimentData;
  timeframe: string;
  data_freshness: string;
  timestamp?: string;
  calculation_steps?: CalculationStep[];
  analysis_params?: AnalysisParams;
  login_required?: boolean;
  // Extended fields (wallet-authenticated only)
  market_bias?: 'bullish' | 'bearish' | 'neutral';
  bias_strength?: 'strong' | 'moderate' | 'weak';
  fng?: { value: number; classification: string; timestamp: string };
  market_breadth?: string;
  btc_change_24h?: number;
  position_report?: {
    '1d': { long: any[]; short: any[]; watch: string };
    '4h': { long: any[]; short: any[]; watch: string };
    '1w': { long: any[]; short: any[]; watch: string };
  };
  risk_warning?: string;
  signals?: any[];
  backtest_results?: Record<string, any>;
}

export interface MantleSentimentData {
  block_number: number;
  tx_count: number;
  gas_ratio: number;
  gas_price_gwei: number;
  on_chain_score: number;
  network_activity: string;
  weight?: number;
}

export interface AnalysisParams {
  symbols_count: number;
  timeframe: string;
  indicators: string[];
  binance_weight: number;
  mantle_weight: number;
}

export interface CalculationDetail {
  binance_bullish: number;
  binance_total: number;
  binance_score: number;
  binance_weight: number;
  binance_contribution: number;
  mantle_tx_count: number;
  mantle_tx_score: number;
  mantle_gas_ratio: number;
  mantle_gas_score: number;
  mantle_score: number;
  mantle_weight: number;
  mantle_contribution: number;
  final_index: number;
}

export interface TokenData {
  symbol: string;
  price: number;
  price_change_24h: number;
  alignment: 'bullish' | 'bearish' | 'neutral' | 'unknown' | 'error';
  strength: string;
  score: number;
  price_above_all?: boolean;
  price_below_all?: boolean;
  mas?: Record<string, number>;
  spreads?: Record<string, number>;
  volume_trend: string;
  volume_24h?: number;
  price_range?: {
    high_24h: number;
    low_24h: number;
    range: number;
  };
  error?: string;
}

export interface ProtocolData {
  protocol_id: string;
  protocol_name: string;
  name?: string; // alias for protocol_name
  chain: string;
  category: string;
  tvl: number;
  tvl_change_24h: number;
  tvl_change_7d?: number;
  volume_24h: number;
  volume_change_24h: number;
  fees_24h: number;
  timestamp: string;
}

export interface OnChainOverview {
  chain: string;
  total_tvl: number;
  total_volume_24h: number;
  total_fees_24h: number;
  protocol_count: number;
  timestamp: string;
}

export interface BlockData {
  number: number;
  hash: string;
  timestamp: number;
  timestamp_iso: string;
  gas_used: number;
  gas_limit: number;
  gas_utilization: number;
  tx_count: number;
  size: number;
}

export interface GasData {
  wei: number;
  gwei: number;
  mnt: number;
  timestamp: string;
}

export interface NetworkData {
  latest_block: number;
  avg_block_time_sec: number;
  tx_count_latest: number;
  gas_utilization: number;
  timestamp: string;
}

export interface SwapQuote {
  expected_output: string;
  minimum_output: string;
  price_impact: number;
  fee_amount: string;
  gas_estimate: string;
  route: string[];
}

export interface Transaction {
  id: string;
  tx_hash: string;
  status: 'pending' | 'success' | 'failed';
  sender: string;
  token_in: string;
  token_out: string;
  amount_in: string;
  expected_output: string;
  timestamp: string;
  explorer_url: string;
}

export interface WalletState {
  connected: boolean;
  address: string | null;
  chainId: number | null;
  balances: Record<string, string>;
}

export interface ApiStatus {
  online: boolean;
  services?: Record<string, boolean>;
  checking: boolean;
}

export interface AppSettings {
  apiBase: string;
  refreshInterval: number;
}

export type TimeFrame = '1h' | '4h' | '1d';

export interface SentimentHistoryPoint {
  timestamp: string;
  index: number;
  bullish: number;
  bearish: number;
  neutral: number;
}

export interface TrendPoint {
  timestamp: string;
  activity_index?: number;
  gas_price?: number;
  tx_count?: number;
  tvl?: number;
}

export interface TrendsData {
  activity: TrendPoint[];
  gas: TrendPoint[];
  tvl: TrendPoint[];
  protocols: ProtocolData[];
}

export interface TVLHistoryPoint {
  timestamp: string;
  tvl: number;
  change_24h?: number;
}

export type TVLHistory = TVLHistoryPoint[];

// ============ Smart Routing Wizard Types ============

export type WizardStepType =
  | 'chain_select'
  | 'token_select'
  | 'amount_input'
  | 'smart_analysis'
  | 'route_display'
  | 'route_select'
  | 'wallet_check'
  | 'execute_confirm';

export interface ChainInfo {
  id: string;
  name: string;
  chain_id: number;
  native_token: string;
  rpc_url: string;
  explorer_url: string;
  is_evm: boolean;
  color: string;
}

export interface TokenInfo {
  symbol: string;
  name: string;
  address: string;
  decimals: number;
  is_native: boolean;
  price_usd: number;
}

export interface RouteStepDetail {
  step_number: number;
  step_type: string;
  protocol: string;
  protocol_type: string;
  from_token: string;
  to_token: string;
  from_chain: string;
  to_chain: string;
  from_chain_name: string;
  to_chain_name: string;
  amount_in: string;
  amount_in_usd: number;
  expected_out: string;
  expected_out_usd: number;
  fee_usd: number;
  gas_estimate_usd: number;
  time_estimate_sec: number;
  details: Record<string, any>;
}

export interface RouteOption {
  route_id: string;
  name: string;
  description: string;
  total_steps: number;
  steps: RouteStepDetail[];
  total_input_usd: number;
  total_output_usd: number;
  total_output_token: string;
  total_fee_usd: number;
  total_gas_usd: number;
  total_slippage: number;
  total_time_sec: number;
  net_return_usd: number;
  net_return_percent: number;
  score: number;
  tags: string[];
  risk_level: string;
}

export interface AnalysisProgress {
  status: string;
  progress_percent: number;
  current_task: string;
  logs: string[];
  started_at?: string;
  completed_at?: string;
  error?: string;
}

export interface AnalysisResult {
  status: string;
  progress: AnalysisProgress;
  routes: RouteOption[];
  best_route_id?: string;
  analysis_summary?: string;
}

export interface WalletCheckResult {
  address: string;
  source_chain: string;
  target_chain: string;
  token_in: string;
  token_out: string;
  amount: string;
  balance_ok: boolean;
  balance_sufficient: boolean;
  balance_current: string;
  balance_required: string;
  allowance_ok: boolean;
  allowance_current: string;
  allowance_required: string;
  source_gas_ok: boolean;
  source_gas_balance: string;
  source_gas_required: string;
  target_gas_ok: boolean;
  target_gas_balance: string;
  target_gas_required: string;
  warnings: string[];
  can_proceed: boolean;
}

export interface ExecutionResult {
  status: string;
  tx_hash?: string;
  explorer_url?: string;
  error?: string;
  gas_used?: string;
  actual_output?: string;
  timestamp?: string;
}

export interface WizardSessionData {
  session_id: string;
  current_step: WizardStepType;
  completed_steps: WizardStepType[];
  created_at: string;
  updated_at: string;
  chain_data?: {
    source_chain: string;
    target_chain: string;
  };
  token_data?: {
    token_in: string;
    token_out: string;
    token_in_symbol: string;
    token_out_symbol: string;
  };
  amount_data?: {
    amount: string;
    amount_usd?: number;
  };
  analysis_data?: AnalysisResult;
  selected_route_id?: string;
  wallet_check?: WalletCheckResult;
  execution_data?: ExecutionResult;
  is_cross_chain: boolean;
}

export interface WizardStepConfig {
  id: WizardStepType;
  label: string;
  description: string;
  icon: string;
}

// ============ Backtest Types ============

export interface BacktestStrengthStats {
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
}

export interface BacktestSignal {
  id: number;
  symbol: string;
  timeframe: string;
  direction: 'long' | 'short';
  confidence: string;
  strength: string;
  entry_price: number;
  timestamp: string;
  primary_pattern: string | null;
  secondary_patterns: string[];
  exit_price: number | null;
  exit_timestamp: string | null;
  pnl_pct: number | null;
  net_pnl_pct?: number | null;
  duration?: number;
  duration_bucket?: string;
  created_at: string;
}

export interface BacktestResult {
  symbol: string;
  timeframe: string;
  total_signals?: number;
  stats: Record<string, BacktestStrengthStats>;
  current_signal?: CurrentSignal | null;
  recent_signals: BacktestSignal[];
}

export interface BacktestSummaryItem {
  symbol: string;
  overall_win_rate: number;
  best_strength: string | null;
  total_signals: number;
}

export interface BacktestSummary {
  symbols: BacktestSummaryItem[];
  total_symbols: number;
}

// ============ Similar-State Backtest Types (New) ============

export interface SimilarStateStats {
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
}

export interface CurrentSignal {
  symbol: string;
  timeframe: string;
  direction: 'long' | 'short';
  pattern: string;
  duration: number;
  duration_bucket: string;
  strength: string;
  current_price: number;
  similar_state_stats: SimilarStateStats;
  recommendation: {
    action: string;
    confidence: 'high' | 'medium' | 'low';
    score: number;
    reason: string;
  };
}

export interface SimilarStateBacktestResult {
  symbol: string;
  timeframe: string;
  total_signals: number;
  stats: Record<string, SimilarStateStats>;
  current_signal: CurrentSignal | null;
  recent_signals: BacktestSignal[];
}

export interface BatchBacktestResult {
  timeframe: string;
  total_symbols_tested: number;
  symbols_with_signals: number;
  recommendations: CurrentSignal[];
  all_signals: CurrentSignal[];
  timestamp: string;
}

// ============ On-Chain Trends Types ============

export interface TrendTransaction {
  chain: string;
  tx_hash: string;
  block_time: string;
  from_address?: string;
  to_address?: string;
  token_address?: string;
  token_symbol: string;
  token_amount: number;
  token_amount_usd?: number;
  tx_type: string;
  category?: string;
  protocol?: string;
}

export interface HourlyAnalysis {
  id: string;
  hour: string;
  total_volume: number;
  tx_count: number;
  category_distribution: Record<string, number>;
  trend_direction: 'bullish' | 'bearish' | 'neutral';
  top_narrative: string;
  kimi_summary: string;
  created_at: string;
}

export interface HalfDaySummary {
  id: string;
  period_start: string;
  period_end: string;
  total_volume: number;
  tx_count: number;
  category_distribution: Record<string, number>;
  trend_direction: 'bullish' | 'bearish' | 'neutral';
  top_narrative: string;
  kimi_summary: string;
  created_at: string;
}

export interface BigSummary {
  id: string;
  period_start: string;
  period_end: string;
  total_volume: number;
  tx_count: number;
  narrative_evolution: string;
  kimi_deep_analysis: string;
  created_at: string;
}

export interface ChainDistributionItem {
  name: string;
  value: number;
  tx_count: number;
  volume: number;
}

export interface TrendTarget {
  rank: number;
  chain: string;
  token_symbol: string;
  tx_count: number;
  total_amount: number;
  total_amount_usd?: number;
  swap_count: number;
  unique_addresses: number;
  trend_score: number;
  category: string;
}

export interface TrendAggregates {
  chain_distribution: ChainDistributionItem[];
  category_distribution: ChainDistributionItem[];
  top_targets: TrendTarget[];
  large_transactions: TrendTransaction[];
  summary: {
    total_tx: number;
    total_volume: number;
    unique_tokens: number;
    unique_chains: number;
    time_range_hours: number;
  };
}

// ============ Large Transaction Monitor Types ============

export interface LargeTransaction {
  id?: number;
  chain: string;
  tx_hash: string;
  block_number?: number;
  block_time: string;
  from_address: string;
  to_address: string;
  token_address?: string;
  token_symbol: string;
  source_symbol?: string;
  token_amount: number;
  token_amount_usd: number;
  tx_type: string;
  category?: string;
  protocol?: string;
  direction?: string;
  confidence?: string;
}

export interface MonitorSummaryItem {
  symbol: string;
  direction: string | null;
  confidence: string | null;
  reason: string | null;
  chains: string[];
  total_tx_count: number;
  total_volume_usd: number;
  latest_tx_time: string | null;
}

// ============ Elliott Wave Types ============

export interface ElliottWaveItem {
  wave: string;
  start_idx: number;
  end_idx: number;
  start_price: number;
  end_price: number;
}

export interface ElliottWaveCandidate {
  wave_type: string;
  wave_pattern: string;
  direction: string;
  current_wave: string | number;
  score: number;
  waves: ElliottWaveItem[];
  fib_ratios: Record<string, number>;
  validations: Record<string, boolean>;
  chart_path: string;
  projection_chart_path?: string;
  kimi_annotated?: boolean;
  projections?: Array<{
    scenario: string;
    description: string;
    target_price: number;
    confidence?: number;
  }>;
  kimi_analysis?: {
    confirmed_wave: string;
    corrections: string[];
    projections: Array<{
      scenario: string;
      description: string;
      target_price: number;
      confidence: number;
    }>;
    key_fib_levels: number[];
    overall_confidence: number;
    raw_analysis: string;
    current_wave_probabilities?: Record<string, number>;
    kimi_structure?: {
      wave_pattern?: string;
      direction?: string;
      current_wave?: string;
      waves?: ElliottWaveItem[];
    };
  };
  // 新增字段：当前浪概率
  current_wave_probabilities?: Record<string, number>;
  current_wave_status?: string;
  completed_waves?: number;
}

export interface ElliottWaveResult {
  symbol: string;
  timeframe: string;
  klines_count: number;
  candidates: ElliottWaveCandidate[];
  analysis_time_ms: number;
  message?: string;
  // 新增字段
  cached_at?: string;
  is_cached?: boolean;
  computed_at?: string;
}
