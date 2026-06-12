export interface DecryptedSignal {
  version?: string
  timestamp?: string
  agent_id?: string
  decision: {
    symbol: string
    timeframe: string
    direction: string
    confidence: string
    reason: string
  }
  elliott_wave?: {
    wave_pattern?: string
    current_wave?: string
    direction?: string
    projections?: Array<{
      scenario?: string
      target_price?: number
      confidence?: number
      stop_loss?: number
    }>
    score?: number
    chart_hash?: string
    chart_path?: string
  }
  backtest?: {
    win_rate?: number
    avg_pnl?: number
    profit_factor?: number
    total_signals?: number
    duration_bucket?: string
    current_signal?: {
      pattern?: string
      duration?: number
      strength?: string
      recommendation?: {
        action?: string
        score?: number
      }
    }
  }
  sentiment?: {
    sentiment_index?: number
    market_bias?: string
    bias_strength?: string
    fng_value?: number
    fng_label?: string
    bullish_count?: number
    bearish_count?: number
    neutral_count?: number
  }
  position_report?: {
    [timeframe: string]: {
      long: Array<{ symbol: string; confidence: string; reason: string }>
      short: Array<{ symbol: string; confidence: string; reason: string }>
      watch: string
    }
  }
  onchain_context?: {
    mantle_tvl?: number
    tvl_change_24h?: number
    gas_gwei?: number
    block_number?: number
    protocol_count?: number
  }
  dashboard?: {
    top_bullish: Array<{ symbol: string; score: number; price_change_24h: number }>
    top_bearish: Array<{ symbol: string; score: number; price_change_24h: number }>
  }

  // 趋势图表数据
  trends?: {
    activity?: Array<{ t: string; v: number }>
    gas?: Array<{ t: string; v: number }>
    tvl?: Array<{ t: string; v: number }>
  }

  // 完整币种评分（前 10）
  symbol_scores?: Array<{
    symbol: string
    score?: number
    price?: number
    change_24h?: number
  }>

  // 协议列表（前 5）
  protocols?: Array<{
    slug: string
    name?: string
    tvl?: number
    tvl_change_1d?: number
    category?: string
  }>

  // 概览完整字段
  overview?: {
    total_volume_24h?: number
    total_fees_24h?: number
    active_addresses?: number
  }

  // 区块详情
  block?: {
    number?: number
    tx_count?: number
    gas_used?: string
    timestamp?: number
  }

  // Gas 详情
  gas?: {
    wei?: number
    gwei?: number
  }

  // 网络详情
  network?: {
    latest_block?: number
    avg_block_time?: number
    tx_count?: number
  }

  // 风险警告
  risk_warning?: string

  // 完整数据哈希（用于验证 API 数据完整性）
  full_data_hash?: string

  raw: string
}

export function parseSignalData(data: string): DecryptedSignal {
  try {
    const parsed = JSON.parse(data)
    return {
      version: parsed.version,
      timestamp: parsed.timestamp,
      agent_id: parsed.agent_id,
      decision: parsed.decision || {
        symbol: '',
        timeframe: '',
        direction: '',
        confidence: '',
        reason: '',
      },
      elliott_wave: parsed.elliott_wave || undefined,
      backtest: parsed.backtest,
      sentiment: parsed.sentiment,
      position_report: parsed.position_report,
      onchain_context: parsed.onchain_context,
      dashboard: parsed.dashboard,
      trends: parsed.trends,
      symbol_scores: parsed.symbol_scores,
      protocols: parsed.protocols,
      overview: parsed.overview,
      block: parsed.block,
      gas: parsed.gas,
      network: parsed.network,
      risk_warning: parsed.risk_warning,
      raw: data,
    }
  } catch (err: unknown) {
    const message = err instanceof Error ? err.message : String(err)
    return {
      decision: {
        symbol: '',
        timeframe: '',
        direction: '',
        confidence: '',
        reason: `Parse error: ${message}`,
      },
      raw: `Parse error: ${message}`,
    }
  }
}
