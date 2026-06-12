import { useState, useMemo, useEffect, useCallback } from 'react';
import { useTranslation } from 'react-i18next';
import {
  Blocks, Fuel, Activity, Zap, BarChart3,
  TrendingUp, TrendingDown, Minus, Clock,
  ChevronDown, ChevronUp, Loader2, Sparkles
} from 'lucide-react';
import { useApp } from '../context/AppContext';
import {
  AreaChart, Area, LineChart, Line,
  XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer,
  PieChart, Pie, Cell,
} from 'recharts';
import {
  getHourlyAnalysis,
  getHalfDaySummaries,
  getBigSummaries,
  getTrendAggregates,
  analyzeTargetsWithAI,
  getLargeTransactions,
  getMonitorSummary,
} from '../services/api';
import type { HourlyAnalysis, HalfDaySummary, BigSummary, TrendAggregates, LargeTransaction, MonitorSummaryItem } from '../types';

/* ───────────────────────────────
   工具函数
   ─────────────────────────────── */
function formatNumber(n: number | undefined | null, digits = 2): string {
  if (n === undefined || n === null || isNaN(n)) return '--';
  if (n >= 1e9) return `${(n / 1e9).toFixed(digits)}B`;
  if (n >= 1e6) return `${(n / 1e6).toFixed(digits)}M`;
  if (n >= 1e3) return `${(n / 1e3).toFixed(digits)}K`;
  return n.toFixed(digits);
}

const CHAIN_COLORS = ['#7ED7C4', '#F4D06F', '#E07A5F', '#98C1D9', '#E0FBFC'];
const CATEGORY_COLORS = ['#7ED7C4', '#F4D06F', '#E07A5F', '#98C1D9', '#E0FBFC', '#3D5A80', '#EE6C4D', '#A8DADC', '#457B9D'];

/* ───────────────────────────────
   骨架屏
   ─────────────────────────────── */
function ShimmerBox({ className = '' }: { className?: string }) {
  return <div className={`shimmer rounded-lg ${className}`} />;
}

/* ───────────────────────────────
   指标卡片
   ─────────────────────────────── */
function MetricCard({
  title, value, subValue, icon: Icon, trend, loading = false,
}: {
  title: string;
  value: string;
  subValue?: string;
  icon: React.ElementType;
  trend?: 'up' | 'down' | 'neutral';
  loading?: boolean;
}) {
  if (loading) {
    return (
      <div className="card p-4">
        <div className="flex items-center justify-between mb-3">
          <ShimmerBox className="w-20 h-4" />
          <ShimmerBox className="w-8 h-8 rounded-lg" />
        </div>
        <ShimmerBox className="w-24 h-7 mb-2" />
        <ShimmerBox className="w-32 h-3" />
      </div>
    );
  }
  return (
    <div className="card p-4 hover:border-white/10 transition-all duration-200">
      <div className="flex items-center justify-between mb-2">
        <span className="text-gray-400 text-sm">{title}</span>
        <div className={`w-8 h-8 rounded-lg flex items-center justify-center ${
          trend === 'up' ? 'bg-emerald-500/10 text-emerald-400' :
          trend === 'down' ? 'bg-red-500/10 text-red-400' :
          'bg-gray-800 text-gray-400'
        }`}>
          <Icon className="w-4 h-4" />
        </div>
      </div>
      <div className="text-xl font-bold text-white">{value}</div>
      {subValue && <div className="text-xs text-gray-500 mt-1">{subValue}</div>}
    </div>
  );
}

/* ───────────────────────────────
   趋势方向标签
   ─────────────────────────────── */
function TrendBadge({ direction }: { direction: 'bullish' | 'bearish' | 'neutral' }) {
  const config = {
    bullish: { text: '看涨', class: 'bg-emerald-500/10 text-emerald-400', icon: TrendingUp },
    bearish: { text: '看跌', class: 'bg-red-500/10 text-red-400', icon: TrendingDown },
    neutral: { text: '中性', class: 'bg-amber-500/10 text-amber-400', icon: Minus },
  };
  const c = config[direction] || config.neutral;
  const Icon = c.icon;
  return (
    <span className={`inline-flex items-center gap-1 px-2.5 py-1 rounded-full text-xs font-medium ${c.class}`}>
      <Icon className="w-3 h-3" />
      {c.text}
    </span>
  );
}

/* ───────────────────────────────
   小型趋势概览卡片
   ─────────────────────────────── */
function SmallCard({ title, value, subValue, loading = false }: {
  title: string;
  value: React.ReactNode;
  subValue?: string;
  loading?: boolean;
}) {
  if (loading) {
    return (
      <div className="card p-3">
        <ShimmerBox className="w-16 h-3 mb-2" />
        <ShimmerBox className="w-20 h-5 mb-1" />
        <ShimmerBox className="w-24 h-3" />
      </div>
    );
  }
  return (
    <div className="card p-3 hover:border-white/10 transition-all duration-200">
      <div className="text-gray-400 text-xs mb-1">{title}</div>
      <div className="text-base font-bold text-white">{value}</div>
      {subValue && <div className="text-[10px] text-gray-500 mt-0.5">{subValue}</div>}
    </div>
  );
}

/* ───────────────────────────────
   大额交易监控 Tab 内容
   ─────────────────────────────── */
function LargeTransactionsTab({
  largeTxs,
  monitorSummary,
  loading,
  filter,
  setFilter,
}: {
  largeTxs: LargeTransaction[];
  monitorSummary: MonitorSummaryItem[];
  loading: boolean;
  filter: 'all' | 'long' | 'short';
  setFilter: (f: 'all' | 'long' | 'short') => void;
}) {
  if (loading) {
    return (
      <div className="space-y-4">
        <ShimmerBox className="h-32" />
        <ShimmerBox className="h-64" />
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* 推荐币种卡片 */}
      <div>
        <h4 className="text-sm font-semibold text-gray-300 mb-3">当前关注币种</h4>
        {monitorSummary.length === 0 ? (
          <div className="text-sm text-gray-500">暂无情绪分析推荐币种</div>
        ) : (
          <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-3">
            {monitorSummary.map((item) => (
              <div
                key={item.symbol}
                className={`p-3 rounded-lg border ${
                  item.direction === 'long'
                    ? 'border-emerald-500/30 bg-emerald-500/5'
                    : item.direction === 'short'
                    ? 'border-red-500/30 bg-red-500/5'
                    : 'border-gray-700 bg-gray-800/50'
                }`}
              >
                <div className="flex items-center gap-2 mb-1">
                  <span className="text-base font-bold text-white">{item.symbol}</span>
                  {item.direction === 'long' && <TrendingUp className="w-4 h-4 text-emerald-400" />}
                  {item.direction === 'short' && <TrendingDown className="w-4 h-4 text-red-400" />}
                </div>
                <div className="text-xs text-gray-400 mb-1">
                  {item.direction === 'long' ? '做多' : item.direction === 'short' ? '做空' : '观望'}
                  {item.confidence && ` · ${item.confidence === 'high' ? '高' : item.confidence === 'medium' ? '中' : '低'}置信`}
                </div>
                <div className="text-xs text-emerald-400 font-medium">
                  {item.total_tx_count} 笔 · ${formatNumber(item.total_volume_usd)}
                </div>
                <div className="text-xs text-gray-500 mt-0.5">
                  {item.chains.join(', ')}
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* 筛选器 */}
      <div className="flex items-center gap-2">
        <span className="text-sm text-gray-400">筛选:</span>
        {(['all', 'long', 'short'] as const).map((f) => (
          <button
            key={f}
            onClick={() => setFilter(f)}
            className={`px-3 py-1 rounded-md text-xs font-medium transition ${
              filter === f
                ? 'bg-[#2D6B5E] text-white'
                : 'bg-gray-800 text-gray-400 hover:text-gray-200'
            }`}
          >
            {f === 'all' ? '全部' : f === 'long' ? '做多' : '做空'}
          </button>
        ))}
      </div>

      {/* 大额交易列表 */}
      <div>
        <h4 className="text-sm font-semibold text-gray-300 mb-3">
          大额交易 (≥$10,000) · {largeTxs.length} 笔
        </h4>
        {largeTxs.length === 0 ? (
          <div className="text-sm text-gray-500 py-8 text-center">暂无符合条件的大额交易</div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-xs">
              <thead>
                <tr className="text-gray-500 border-b border-gray-800">
                  <th className="text-left py-2 px-2">链</th>
                  <th className="text-left py-2 px-2">时间</th>
                  <th className="text-left py-2 px-2">Token</th>
                  <th className="text-right py-2 px-2">Amount</th>
                  <th className="text-right py-2 px-2">USD</th>
                  <th className="text-left py-2 px-2">From</th>
                  <th className="text-left py-2 px-2">To</th>
                  <th className="text-left py-2 px-2">Type</th>
                  <th className="text-left py-2 px-2">协议</th>
                </tr>
              </thead>
              <tbody>
                {largeTxs.slice(0, 50).map((tx, i) => (
                  <tr key={i} className="border-b border-gray-800/50 hover:bg-gray-800/30">
                    <td className="py-2 px-2 text-gray-300">{tx.chain}</td>
                    <td className="py-2 px-2 text-gray-400">
                      {tx.block_time ? new Date(tx.block_time).toLocaleString('zh-CN', { month: 'numeric', day: 'numeric', hour: '2-digit', minute: '2-digit' }) : '--'}
                    </td>
                    <td className="py-2 px-2">
                      <span className="text-white font-medium">{tx.token_symbol}</span>
                      {tx.source_symbol && tx.source_symbol !== tx.token_symbol && (
                        <span className="text-gray-500 ml-1">({tx.source_symbol})</span>
                      )}
                    </td>
                    <td className="py-2 px-2 text-right text-gray-300">{formatNumber(tx.token_amount, 4)}</td>
                    <td className="py-2 px-2 text-right text-emerald-400 font-medium">${formatNumber(tx.token_amount_usd)}</td>
                    <td className="py-2 px-2 text-gray-500 font-mono">{tx.from_address ? `${tx.from_address.slice(0, 6)}...${tx.from_address.slice(-4)}` : '--'}</td>
                    <td className="py-2 px-2 text-gray-500 font-mono">{tx.to_address ? `${tx.to_address.slice(0, 6)}...${tx.to_address.slice(-4)}` : '--'}</td>
                    <td className="py-2 px-2">
                      <span className={`px-1.5 py-0.5 rounded text-[10px] ${
                        tx.tx_type === 'swap' ? 'bg-purple-500/20 text-purple-300' : 'bg-gray-700 text-gray-400'
                      }`}>
                        {tx.tx_type || 'transfer'}
                      </span>
                    </td>
                    <td className="py-2 px-2">
                      {tx.protocol ? (
                        <span className="px-1.5 py-0.5 rounded text-[10px] bg-blue-500/20 text-blue-300">
                          {tx.protocol}
                        </span>
                      ) : (
                        <span className="text-gray-600">--</span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}

/* ───────────────────────────────
   链上趋势 Tab 内容
   ─────────────────────────────── */
function OnChainTrendsTab({
  hourlyData,
  trendLoading,
  trendError,
  bigExpanded,
  setBigExpanded,
  latestHourly,
  latestHalfDay,
  latestBig,
  aggregates,
  aggregatesLoading,
  targetAnalysis,
  targetAnalysisLoading,
}: {
  hourlyData: HourlyAnalysis[];
  trendLoading: boolean;
  trendError: string | null;
  bigExpanded: boolean;
  setBigExpanded: (v: boolean) => void;
  latestHourly?: HourlyAnalysis;
  latestHalfDay?: HalfDaySummary;
  latestBig?: BigSummary;
  aggregates?: TrendAggregates | null;
  aggregatesLoading?: boolean;
  targetAnalysis?: string;
  targetAnalysisLoading?: boolean;
}) {
  const hourlyChartData = hourlyData.map(h => ({
    timestamp: h.hour,
    volume: h.total_volume,
    tx_count: h.tx_count,
  })).reverse();

  const formatTime = (ts: string) => {
    try {
      const d = new Date(ts);
      return `${d.getMonth() + 1}/${d.getDate()} ${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`;
    } catch { return ts; }
  };

  const formatAmount = (n: number | undefined | null) => {
    if (n === undefined || n === null || isNaN(n)) return '--';
    if (n >= 1e9) return `${(n / 1e9).toFixed(2)}B`;
    if (n >= 1e6) return `${(n / 1e6).toFixed(2)}M`;
    if (n >= 1e3) return `${(n / 1e3).toFixed(2)}K`;
    return n.toFixed(2);
  };

  return (
    <div className="space-y-5">
      {/* Moralis 状态指示器 */}
      <div className="flex items-center gap-2 text-xs text-gray-500">
        <span className="flex items-center gap-1">
          <div className="w-1.5 h-1.5 rounded-full bg-emerald-400" />
          Moralis 数据增强已启用
        </span>
        <span>|</span>
        <span>实时价格填充中</span>
      </div>

      {/* A. 趋势概览卡片 */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
        <SmallCard
          title="趋势方向"
          value={latestHourly ? <TrendBadge direction={latestHourly.trend_direction} /> : '--'}
          subValue={latestHourly ? `更新于 ${formatTime(latestHourly.created_at)}` : undefined}
          loading={trendLoading}
        />
        <SmallCard
          title="热点叙事"
          value={latestHourly?.top_narrative || '暂无'}
          subValue={latestHourly ? `最近1小时` : undefined}
          loading={trendLoading}
        />
        <SmallCard
          title="总交易量"
          value={latestHourly ? `$${formatAmount(latestHourly.total_volume)}` : '--'}
          subValue={latestHourly ? `${latestHourly.tx_count} 笔交易` : undefined}
          loading={trendLoading}
        />
        <SmallCard
          title="交易笔数"
          value={latestHourly ? `${latestHourly.tx_count}` : '--'}
          subValue={latestHourly ? `最近1小时` : undefined}
          loading={trendLoading}
        />
      </div>

      {/* 多链分析 + 饼状图 */}
      <div className="card p-4">
        <h3 className="text-sm font-semibold text-white mb-4 flex items-center gap-2">
          <BarChart3 className="w-4 h-4 text-emerald-400" />
          多链交易分布
        </h3>
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
          {/* 左：链分布饼图 */}
          <div>
            <div className="text-xs text-gray-500 mb-2 text-center">链分布</div>
            <ResponsiveContainer width="100%" height={220}>
              <PieChart>
                <Pie
                  data={aggregates?.chain_distribution || []}
                  cx="50%" cy="50%"
                  innerRadius={60} outerRadius={80}
                  paddingAngle={3}
                  dataKey="value"
                  nameKey="name"
                >
                  {(aggregates?.chain_distribution || []).map((_, i) => (
                    <Cell key={`cell-chain-${i}`} fill={CHAIN_COLORS[i % CHAIN_COLORS.length]} />
                  ))}
                </Pie>
                <Tooltip
                  contentStyle={{ backgroundColor: '#1f2937', border: '1px solid #374151', borderRadius: '8px' }}
                  formatter={(value: any, name: any, props: any) => [
                    `${value} 笔 ($${formatAmount(props?.payload?.volume)})`,
                    name
                  ]}
                />
              </PieChart>
            </ResponsiveContainer>
            <div className="flex flex-wrap gap-2 justify-center mt-2">
              {(aggregates?.chain_distribution || []).map((item, i) => (
                <div key={item.name} className="flex items-center gap-1 text-xs text-gray-400">
                  <div className="w-2 h-2 rounded-full" style={{ backgroundColor: CHAIN_COLORS[i % CHAIN_COLORS.length] }} />
                  {item.name} ({item.value})
                </div>
              ))}
            </div>
          </div>
          {/* 右：赛道分布饼图 */}
          <div>
            <div className="text-xs text-gray-500 mb-2 text-center">赛道分布</div>
            <ResponsiveContainer width="100%" height={220}>
              <PieChart>
                <Pie
                  data={aggregates?.category_distribution || []}
                  cx="50%" cy="50%"
                  innerRadius={60} outerRadius={80}
                  paddingAngle={3}
                  dataKey="value"
                  nameKey="name"
                >
                  {(aggregates?.category_distribution || []).map((_, i) => (
                    <Cell key={`cell-cat-${i}`} fill={CATEGORY_COLORS[i % CATEGORY_COLORS.length]} />
                  ))}
                </Pie>
                <Tooltip
                  contentStyle={{ backgroundColor: '#1f2937', border: '1px solid #374151', borderRadius: '8px' }}
                  formatter={(value: any, name: any, props: any) => [
                    `${value} 笔 ($${formatAmount(props?.payload?.volume)})`,
                    name
                  ]}
                />
              </PieChart>
            </ResponsiveContainer>
            <div className="flex flex-wrap gap-2 justify-center mt-2">
              {(aggregates?.category_distribution || []).map((item, i) => (
                <div key={item.name} className="flex items-center gap-1 text-xs text-gray-400">
                  <div className="w-2 h-2 rounded-full" style={{ backgroundColor: CATEGORY_COLORS[i % CATEGORY_COLORS.length] }} />
                  {item.name} ({item.value})
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>

      {/* 趋势标的 Top 10 */}
      <div className="card p-4">
        <h3 className="text-sm font-semibold text-white mb-3 flex items-center gap-2">
          <TrendingUp className="w-4 h-4 text-emerald-400" />
          趋势标的 Top {aggregates?.top_targets.length || 0}
        </h3>
        {aggregatesLoading ? (
          <div className="space-y-2">
            {[1,2,3].map(i => <ShimmerBox key={i} className="w-full h-10" />)}
          </div>
        ) : aggregates && aggregates.top_targets.length > 0 ? (
          <div className="overflow-x-auto">
            <table className="w-full text-xs">
              <thead>
                <tr className="text-gray-500 border-b border-gray-800">
                  <th className="text-left py-2 px-2">排名</th>
                  <th className="text-left py-2 px-2">代币</th>
                  <th className="text-left py-2 px-2">链</th>
                  <th className="text-right py-2 px-2">交易数</th>
                  <th className="text-right py-2 px-2">总量</th>
                  <th className="text-right py-2 px-2">USD 价值</th>
                  <th className="text-right py-2 px-2">Swap</th>
                  <th className="text-right py-2 px-2">活跃地址</th>
                  <th className="text-right py-2 px-2">评分</th>
                  <th className="text-left py-2 px-2">赛道</th>
                </tr>
              </thead>
              <tbody>
                {aggregates.top_targets.map((target) => (
                  <tr key={`${target.chain}-${target.token_symbol}`} className="border-b border-gray-800/50 hover:bg-white/5">
                    <td className="py-2 px-2 font-mono text-emerald-400">#{target.rank}</td>
                    <td className="py-2 px-2 font-semibold text-white">{target.token_symbol}</td>
                    <td className="py-2 px-2 text-gray-400">{target.chain}</td>
                    <td className="py-2 px-2 text-right text-gray-300">{target.tx_count}</td>
                    <td className="py-2 px-2 text-right text-gray-300">{formatAmount(target.total_amount)}</td>
                    <td className="py-2 px-2 text-right">
                      {target.total_amount_usd ? (
                        <span className="text-emerald-400">${formatAmount(target.total_amount_usd)}</span>
                      ) : (
                        <span className="text-gray-600">--</span>
                      )}
                    </td>
                    <td className="py-2 px-2 text-right text-gray-300">{target.swap_count}</td>
                    <td className="py-2 px-2 text-right text-gray-300">{target.unique_addresses}</td>
                    <td className="py-2 px-2 text-right">
                      <span className={`font-mono font-bold ${
                        target.trend_score >= 80 ? 'text-emerald-400' :
                        target.trend_score >= 60 ? 'text-amber-400' :
                        'text-gray-400'
                      }`}>{target.trend_score.toFixed(1)}</span>
                    </td>
                    <td className="py-2 px-2">
                      <span className="px-1.5 py-0.5 rounded text-[10px] bg-gray-800 text-gray-300">{target.category}</span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <div className="text-xs text-gray-500 text-center py-4">暂无趋势标的数据</div>
        )}
      </div>

      {/* AI 标的分析 */}
      {(targetAnalysis || targetAnalysisLoading) && (
        <div className="card p-4">
          <h3 className="text-sm font-semibold text-white mb-3 flex items-center gap-2">
            <Sparkles className="w-4 h-4 text-purple-400" />
            AI 趋势标的分析
          </h3>
          {targetAnalysisLoading ? (
            <div className="flex items-center gap-2 text-xs text-gray-500">
              <Loader2 className="w-3 h-3 animate-spin" />
              Kimi 正在分析趋势标的...
            </div>
          ) : (
            <div className="text-sm text-gray-300 whitespace-pre-wrap leading-relaxed bg-gray-900/50 rounded-lg p-3">
              {targetAnalysis}
            </div>
          )}
        </div>
      )}

      {/* 大额交易 */}
      {aggregates && aggregates.large_transactions.length > 0 && (
        <div className="card p-4">
          <h3 className="text-sm font-semibold text-white mb-3 flex items-center gap-2">
            <Zap className="w-4 h-4 text-amber-400" />
            大额交易（&gt;${formatAmount(1000)}）
          </h3>
          <div className="overflow-x-auto">
            <table className="w-full text-xs">
              <thead>
                <tr className="text-gray-500 border-b border-gray-800">
                  <th className="text-left py-2 px-2">时间</th>
                  <th className="text-left py-2 px-2">链</th>
                  <th className="text-left py-2 px-2">代币</th>
                  <th className="text-right py-2 px-2">数量</th>
                  <th className="text-right py-2 px-2">USD</th>
                  <th className="text-left py-2 px-2">类型</th>
                </tr>
              </thead>
              <tbody>
                {aggregates.large_transactions.slice(0, 10).map((tx, i) => (
                  <tr key={`large-${tx.tx_hash}-${i}`} className="border-b border-gray-800/50 hover:bg-white/5">
                    <td className="py-2 px-2 text-gray-400">{formatTime(tx.block_time)}</td>
                    <td className="py-2 px-2 text-gray-400">{tx.chain}</td>
                    <td className="py-2 px-2 font-semibold text-white">{tx.token_symbol}</td>
                    <td className="py-2 px-2 text-right text-gray-300">{formatAmount(tx.token_amount)}</td>
                    <td className="py-2 px-2 text-right">
                      {tx.token_amount_usd ? (
                        <span className="text-emerald-400">${formatAmount(tx.token_amount_usd)}</span>
                      ) : '--'}
                    </td>
                    <td className="py-2 px-2">
                      <span className={`px-1.5 py-0.5 rounded text-[10px] ${tx.tx_type === 'swap' ? 'bg-purple-500/20 text-purple-400' : 'bg-gray-800 text-gray-300'}`}>
                        {tx.tx_type}
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* C. 每小时分析历史 - 图表 */}
      {hourlyChartData.length > 0 && (
        <div className="card p-4">
          <div className="flex items-center gap-2 mb-3">
            <Clock className="w-4 h-4 text-[#7ED7C4]" />
            <h4 className="text-sm font-semibold text-white">24小时趋势</h4>
          </div>
          <div className="h-60">
            <ResponsiveContainer width="100%" height="100%" minWidth={0} minHeight={0}>
              <AreaChart data={hourlyChartData}>
                <defs>
                  <linearGradient id="trendVolGrad" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="5%" stopColor="#7ED7C4" stopOpacity={0.3} />
                    <stop offset="95%" stopColor="#7ED7C4" stopOpacity={0} />
                  </linearGradient>
                </defs>
                <CartesianGrid strokeDasharray="3 3" stroke="#374151" />
                <XAxis
                  dataKey="timestamp"
                  tick={{ fill: '#9ca3af', fontSize: 10 }}
                  tickFormatter={(v: string) => {
                    const d = new Date(v);
                    return `${String(d.getHours()).padStart(2, '0')}:00`;
                  }}
                />
                <YAxis tick={{ fill: '#9ca3af', fontSize: 10 }} />
                <Tooltip
                  contentStyle={{ backgroundColor: '#1f2937', border: '1px solid #374151', borderRadius: '8px' }}
                  labelStyle={{ color: '#9ca3af' }}
                />
                <Area
                  type="monotone"
                  dataKey="volume"
                  stroke="#7ED7C4"
                  fill="url(#trendVolGrad)"
                  strokeWidth={2}
                  name="交易量"
                />
              </AreaChart>
            </ResponsiveContainer>
          </div>
        </div>
      )}

      {/* D. 12小时汇总 */}
      {latestHalfDay && (
        <div className="card p-4">
          <div className="flex items-center gap-2 mb-3">
            <TrendingUp className="w-4 h-4 text-[#7ED7C4]" />
            <h4 className="text-sm font-semibold text-white">12小时汇总</h4>
            <TrendBadge direction={latestHalfDay.trend_direction} />
          </div>
          <div className="grid grid-cols-2 md:grid-cols-3 gap-3 mb-3">
            <div>
              <div className="text-gray-500 text-xs">时间段</div>
              <div className="text-gray-300 text-sm">{formatTime(latestHalfDay.period_start)} - {formatTime(latestHalfDay.period_end)}</div>
            </div>
            <div>
              <div className="text-gray-500 text-xs">总交易量</div>
              <div className="text-white text-sm font-bold">${formatAmount(latestHalfDay.total_volume)}</div>
            </div>
            <div>
              <div className="text-gray-500 text-xs">交易笔数</div>
              <div className="text-white text-sm font-bold">{latestHalfDay.tx_count}</div>
            </div>
          </div>
          {latestHalfDay.category_distribution && Object.keys(latestHalfDay.category_distribution).length > 0 && (
            <div className="mb-3">
              <div className="text-gray-500 text-xs mb-1">赛道分布</div>
              <div className="flex flex-wrap gap-1.5">
                {Object.entries(latestHalfDay.category_distribution).map(([cat, count]) => (
                  <span key={cat} className="px-2 py-0.5 rounded bg-gray-800 text-gray-300 text-[10px]">
                    {cat}: {count}
                  </span>
                ))}
              </div>
            </div>
          )}
          {latestHalfDay.kimi_summary && (
            <div className="bg-gray-900/50 rounded-lg p-3 border border-gray-800">
              <div className="flex items-center gap-1 mb-1">
                <Sparkles className="w-3 h-3 text-[#7ED7C4]" />
                <span className="text-[#7ED7C4] text-xs font-medium">Kimi 总结</span>
              </div>
              <p className="text-gray-300 text-xs leading-relaxed">{latestHalfDay.kimi_summary}</p>
            </div>
          )}
        </div>
      )}

      {/* E. 3天大汇总 */}
      {latestBig && (
        <div className="card p-4">
          <div className="flex items-center justify-between mb-3">
            <div className="flex items-center gap-2">
              <Sparkles className="w-4 h-4 text-[#7ED7C4]" />
              <h4 className="text-sm font-semibold text-white">3天深度分析</h4>
            </div>
            <button
              onClick={() => setBigExpanded(!bigExpanded)}
              className="flex items-center gap-1 text-gray-400 hover:text-white text-xs transition"
            >
              {bigExpanded ? '收起' : '展开'}
              {bigExpanded ? <ChevronUp className="w-3 h-3" /> : <ChevronDown className="w-3 h-3" />}
            </button>
          </div>
          <div className="grid grid-cols-2 md:grid-cols-3 gap-3 mb-3">
            <div>
              <div className="text-gray-500 text-xs">时间段</div>
              <div className="text-gray-300 text-sm">{formatTime(latestBig.period_start)} - {formatTime(latestBig.period_end)}</div>
            </div>
            <div>
              <div className="text-gray-500 text-xs">总交易量</div>
              <div className="text-white text-sm font-bold">${formatAmount(latestBig.total_volume)}</div>
            </div>
            <div>
              <div className="text-gray-500 text-xs">交易笔数</div>
              <div className="text-white text-sm font-bold">{latestBig.tx_count}</div>
            </div>
          </div>
          {latestBig.narrative_evolution && (
            <div className="mb-3">
              <div className="text-gray-500 text-xs mb-1">叙事演变</div>
              <p className="text-gray-300 text-xs leading-relaxed">{latestBig.narrative_evolution}</p>
            </div>
          )}
          {bigExpanded && latestBig.kimi_deep_analysis && (
            <div className="bg-gray-900/50 rounded-lg p-3 border border-gray-800 mt-2">
              <div className="flex items-center gap-1 mb-2">
                <Sparkles className="w-3 h-3 text-[#7ED7C4]" />
                <span className="text-[#7ED7C4] text-xs font-medium">Kimi 深度分析</span>
              </div>
              <p className="text-gray-300 text-xs leading-relaxed whitespace-pre-wrap">{latestBig.kimi_deep_analysis}</p>
            </div>
          )}
        </div>
      )}

      {/* 错误状态 */}
      {trendError && (
        <div className="card p-4 border-red-500/20">
          <div className="text-red-400 text-sm">{trendError}</div>
        </div>
      )}
    </div>
  );
}

/* ───────────────────────────────
   主组件
   ─────────────────────────────── */
type ChartTab = 'activity' | 'gas' | 'tvl' | 'trends' | 'large';

export default function OnChain() {
  const { t } = useTranslation();
  const { overview, block, gas, network, trends, tvlHistory, loading } = useApp();
  const [activeChartTab, setActiveChartTab] = useState<ChartTab>('activity');

  // 链上趋势状态
  const [hourlyData, setHourlyData] = useState<HourlyAnalysis[]>([]);
  const [halfDayData, setHalfDayData] = useState<HalfDaySummary[]>([]);
  const [bigData, setBigData] = useState<BigSummary[]>([]);
  const [trendLoading, setTrendLoading] = useState(false);
  const [trendError, setTrendError] = useState<string | null>(null);
  const [bigExpanded, setBigExpanded] = useState(false);
  const [aggregates, setAggregates] = useState<TrendAggregates | null>(null);
  const [aggregatesLoading, setAggregatesLoading] = useState(false);
  const [targetAnalysis, setTargetAnalysis] = useState<string>('');
  const [targetAnalysisLoading, setTargetAnalysisLoading] = useState(false);

  // 大额交易监控状态
  const [largeTxs, setLargeTxs] = useState<LargeTransaction[]>([]);
  const [monitorSummary, setMonitorSummary] = useState<MonitorSummaryItem[]>([]);
  const [largeLoading, setLargeLoading] = useState(false);
  const [largeFilter, setLargeFilter] = useState<'all' | 'long' | 'short'>('all');

  const latestHourly = hourlyData[0];
  const latestHalfDay = halfDayData[0];
  const latestBig = bigData[0];

  // AI 趋势标的分析（独立触发，不阻塞 aggregatesLoading）
  const fetchTargetAnalysis = useCallback(async (data: TrendAggregates) => {
    setTargetAnalysisLoading(true);
    try {
      const aiRes = await analyzeTargetsWithAI({
        top_targets: data.top_targets.slice(0, 5),
        chain_distribution: data.chain_distribution,
        category_distribution: data.category_distribution,
        summary: data.summary,
      });
      setTargetAnalysis(aiRes.analysis);
    } catch (e) {
      console.error('AI analysis failed:', e);
    } finally {
      setTargetAnalysisLoading(false);
    }
  }, []);

  // 获取聚合数据（饼图 + 趋势标的）
  const fetchAggregates = useCallback(async () => {
    try {
      setAggregatesLoading(true);
      const data = await getTrendAggregates(24);
      setAggregates(data);
      // AI 分析单独触发，不阻塞 aggregatesLoading
      if (data.top_targets.length > 0) {
        fetchTargetAnalysis(data);
      }
    } catch (e) {
      console.error('Aggregates fetch failed:', e);
    } finally {
      setAggregatesLoading(false);
    }
  }, [fetchTargetAnalysis]);

  // 获取所有趋势数据（页面加载时）
  const fetchAllTrendData = useCallback(async () => {
    setTrendLoading(true);
    setTrendError(null);
    try {
      const [hourly, halfDay, big] = await Promise.all([
        getHourlyAnalysis(24),
        getHalfDaySummaries(5),
        getBigSummaries(3),
      ]);
      setHourlyData(Array.isArray(hourly) ? hourly : []);
      setHalfDayData(Array.isArray(halfDay) ? halfDay : []);
      setBigData(Array.isArray(big) ? big : []);
    } catch (e: any) {
      setTrendError(e.message || '加载链上趋势数据失败');
      console.error('Failed to load trend data:', e);
    } finally {
      setTrendLoading(false);
    }
  }, []);

  const fetchLargeTransactions = useCallback(async () => {
    setLargeLoading(true);
    try {
      const [txRes, summaryRes] = await Promise.all([
        getLargeTransactions(24, undefined, largeFilter === 'all' ? undefined : largeFilter),
        getMonitorSummary(24),
      ]);
      setLargeTxs(txRes?.data || []);
      setMonitorSummary(summaryRes?.data || []);
    } catch (e: any) {
      console.error('Failed to load large transactions:', e);
    } finally {
      setLargeLoading(false);
    }
  }, [largeFilter]);

  // 切换到 trends tab 时加载数据
  useEffect(() => {
    if (activeChartTab === 'trends') {
      fetchAllTrendData();
      fetchAggregates();
    } else if (activeChartTab === 'large') {
      fetchLargeTransactions();
    }
  }, [activeChartTab, fetchAllTrendData, fetchAggregates, fetchLargeTransactions]);

  const chartData = useMemo(() => {
    if (activeChartTab === 'activity' && trends?.activity) return trends.activity;
    if (activeChartTab === 'gas' && trends?.gas) return trends.gas;
    if (activeChartTab === 'tvl') return tvlHistory.map(d => ({ timestamp: d.timestamp, tvl: d.tvl }));
    return [];
  }, [activeChartTab, trends, tvlHistory]);

  const chartDataKey = activeChartTab === 'tvl' ? 'tvl' : activeChartTab === 'gas' ? 'gas_price' : 'activity_index';
  const chartColor = activeChartTab === 'activity' ? '#7ED7C4' : activeChartTab === 'gas' ? '#f59e0b' : '#4A9B8C';

  const chartTabs: { key: ChartTab; label: string }[] = [
    { key: 'activity', label: t('onchain.activityTrend') },
    { key: 'gas', label: t('onchain.gasTrend') },
    { key: 'tvl', label: t('onchain.tvlChange') },
    { key: 'trends', label: '链上趋势' },
    { key: 'large', label: '大额监控' },
  ];

  return (
    <div className="space-y-6 p-4 md:p-6 max-w-7xl mx-auto">
      {/* Header */}
      <div className="flex items-center gap-2">
        <Blocks className="w-5 h-5 text-[#7ED7C4]" />
        <div>
          <h2 className="text-lg font-semibold text-white">{t('onchain.pageTitle')}</h2>
          <p className="text-xs text-gray-500">{t('onchain.agentDesc')}</p>
        </div>
      </div>

      {/* 4 个关键指标卡片 */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
        <MetricCard
          title={t('onchain.blockHeight')}
          value={block ? block.number.toLocaleString() : '--'}
          subValue={block ? t('onchain.txCountWithUnit', { count: block.tx_count }) : ''}
          icon={Blocks}
          trend="up"
          loading={loading}
        />
        <MetricCard
          title={t('onchain.txCount')}
          value={network ? `${network.tx_count_latest?.toLocaleString() || '--'}` : '--'}
          subValue={network ? t('onchain.avgBlockTime', { time: network.avg_block_time_sec }) : ''}
          icon={Zap}
          loading={loading}
        />
        <MetricCard
          title={t('onchain.gasPrice')}
          value={gas ? `${gas.gwei} Gwei` : '--'}
          subValue={t('onchain.networkFees')}
          icon={Fuel}
          loading={loading}
        />
        <MetricCard
          title={t('onchain.networkActivity')}
          value={overview ? t('onchain.protocolCount', { count: overview.protocol_count }) : '--'}
          subValue={overview ? `TVL $${formatNumber(overview.total_tvl)}` : ''}
          icon={Activity}
          trend="up"
          loading={loading}
        />
      </div>

      {/* Tab 图表区 */}
      <div className="card p-5">
        <div className="flex items-center gap-2 mb-4">
          <BarChart3 className="w-5 h-5 text-[#7ED7C4]" />
          <h3 className="text-lg font-semibold text-white">{t('onchain.trendChart')}</h3>
        </div>
        <div className="flex gap-1 mb-4 bg-gray-800/50 p-1 rounded-lg w-fit">
          {chartTabs.map(tab => (
            <button
              key={tab.key}
              onClick={() => setActiveChartTab(tab.key)}
              className={`px-4 py-1.5 rounded-md text-sm font-medium transition ${
                activeChartTab === tab.key
                  ? 'bg-[#2D6B5E] text-white'
                  : 'text-gray-400 hover:text-gray-200'
              }`}
            >
              {tab.label}
            </button>
          ))}
        </div>
        {activeChartTab === 'large' ? (
          <LargeTransactionsTab
            largeTxs={largeTxs}
            monitorSummary={monitorSummary}
            loading={largeLoading}
            filter={largeFilter}
            setFilter={setLargeFilter}
          />
        ) : activeChartTab === 'trends' ? (
          <OnChainTrendsTab
            hourlyData={hourlyData}
            trendLoading={trendLoading}
            trendError={trendError}
            bigExpanded={bigExpanded}
            setBigExpanded={setBigExpanded}
            latestHourly={latestHourly}
            aggregates={aggregates}
            aggregatesLoading={aggregatesLoading}
            targetAnalysis={targetAnalysis}
            targetAnalysisLoading={targetAnalysisLoading}
            latestHalfDay={latestHalfDay}
            latestBig={latestBig}
          />
        ) : (
          <div className="h-72">
            {loading ? (
              <ShimmerBox className="h-full" />
            ) : chartData.length > 0 ? (
              <ResponsiveContainer width="100%" height="100%" minWidth={0} minHeight={0}>
                {activeChartTab === 'gas' ? (
                  <LineChart data={chartData}>
                    <defs>
                      <linearGradient id="lineGrad" x1="0" y1="0" x2="0" y2="1">
                        <stop offset="5%" stopColor={chartColor} stopOpacity={0.3} />
                        <stop offset="95%" stopColor={chartColor} stopOpacity={0} />
                      </linearGradient>
                    </defs>
                    <CartesianGrid strokeDasharray="3 3" stroke="#374151" />
                    <XAxis
                      dataKey="timestamp"
                      tick={{ fill: '#9ca3af', fontSize: 12 }}
                      tickFormatter={(v: string) => {
                        const d = new Date(v);
                        return `${d.getMonth() + 1}/${d.getDate()}`;
                      }}
                    />
                    <YAxis tick={{ fill: '#9ca3af', fontSize: 12 }} />
                    <Tooltip
                      contentStyle={{ backgroundColor: '#1f2937', border: '1px solid #374151', borderRadius: '8px' }}
                      labelStyle={{ color: '#9ca3af' }}
                    />
                    <Line
                      type="monotone"
                      dataKey={chartDataKey}
                      stroke={chartColor}
                      strokeWidth={2}
                      dot={false}
                    />
                  </LineChart>
                ) : (
                  <AreaChart data={chartData}>
                    <defs>
                      <linearGradient id="areaGrad" x1="0" y1="0" x2="0" y2="1">
                        <stop offset="5%" stopColor={chartColor} stopOpacity={0.3} />
                        <stop offset="95%" stopColor={chartColor} stopOpacity={0} />
                      </linearGradient>
                    </defs>
                    <CartesianGrid strokeDasharray="3 3" stroke="#374151" />
                    <XAxis
                      dataKey="timestamp"
                      tick={{ fill: '#9ca3af', fontSize: 12 }}
                      tickFormatter={(v: string) => {
                        const d = new Date(v);
                        return `${d.getMonth() + 1}/${d.getDate()}`;
                      }}
                    />
                    <YAxis tick={{ fill: '#9ca3af', fontSize: 12 }} />
                    <Tooltip
                      contentStyle={{ backgroundColor: '#1f2937', border: '1px solid #374151', borderRadius: '8px' }}
                      labelStyle={{ color: '#9ca3af' }}
                    />
                    <Area
                      type="monotone"
                      dataKey={chartDataKey}
                      stroke={chartColor}
                      fill="url(#areaGrad)"
                      strokeWidth={2}
                    />
                  </AreaChart>
                )}
              </ResponsiveContainer>
            ) : (
              <div className="flex items-center justify-center h-full text-gray-500">
                {t('onchain.noData')}
              </div>
            )}
          </div>
        )}
      </div>

      {/* 区块详情 & Gas 详情 */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <div className="card p-5">
          <div className="flex items-center gap-2 mb-4">
            <Blocks className="w-4 h-4 text-[#7ED7C4]" />
            <h3 className="font-semibold text-white">{t('onchain.blockDetails')}</h3>
          </div>
          {loading ? (
            <div className="space-y-3">
              <ShimmerBox className="h-6" />
              <ShimmerBox className="h-6" />
              <ShimmerBox className="h-6" />
              <ShimmerBox className="h-6" />
            </div>
          ) : block ? (
            <div className="space-y-3 text-sm">
              <div className="flex justify-between">
                <span className="text-gray-500">{t('onchain.blockNumber')}</span>
                <span className="text-gray-200 font-mono">{block.number.toLocaleString()}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-gray-500">{t('onchain.hash')}</span>
                <span className="text-gray-200 font-mono truncate max-w-[200px]">{block.hash}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-gray-500">{t('onchain.timestamp')}</span>
                <span className="text-gray-200">{block.timestamp_iso || new Date(block.timestamp * 1000).toLocaleString()}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-gray-500">{t('onchain.txCountLabel')}</span>
                <span className="text-gray-200">{block.tx_count}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-gray-500">{t('onchain.gasUsed')}</span>
                <span className="text-gray-200">{block.gas_used?.toLocaleString()}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-gray-500">{t('onchain.gasLimit')}</span>
                <span className="text-gray-200">{block.gas_limit?.toLocaleString()}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-gray-500">{t('onchain.utilization')}</span>
                <span className={`font-medium ${(block.gas_utilization ?? 0) > 80 ? 'text-red-400' : (block.gas_utilization ?? 0) > 50 ? 'text-amber-400' : 'text-emerald-400'}`}>
                  {block.gas_utilization ?? '--'}%
                </span>
              </div>
            </div>
          ) : (
            <div className="text-gray-500 text-sm py-4 text-center">{t('onchain.noData')}</div>
          )}
        </div>

        <div className="card p-5">
          <div className="flex items-center gap-2 mb-4">
            <Fuel className="w-4 h-4 text-[#7ED7C4]" />
            <h3 className="font-semibold text-white">{t('onchain.gasDetails')}</h3>
          </div>
          {loading ? (
            <div className="space-y-3">
              <ShimmerBox className="h-6" />
              <ShimmerBox className="h-6" />
              <ShimmerBox className="h-6" />
              <ShimmerBox className="h-6" />
            </div>
          ) : gas ? (
            <div className="space-y-3 text-sm">
              <div className="flex justify-between">
                <span className="text-gray-500">Wei</span>
                <span className="text-gray-200 font-mono">{gas.wei?.toLocaleString()}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-gray-500">Gwei</span>
                <span className="text-gray-200 font-mono">{gas.gwei}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-gray-500">MNT</span>
                <span className="text-gray-200 font-mono">{gas.mnt}</span>
              </div>
              {overview && (
                <div className="flex justify-between">
                  <span className="text-gray-500">24h Fees</span>
                  <span className="text-gray-200">${(overview.total_fees_24h || 0).toLocaleString()}</span>
                </div>
              )}
              {network && (
                <div className="flex justify-between">
                  <span className="text-gray-500">{t('onchain.avgBlockTimeLabel')}</span>
                  <span className="text-gray-200">{network.avg_block_time_sec}s</span>
                </div>
              )}
            </div>
          ) : (
            <div className="text-gray-500 text-sm py-4 text-center">{t('onchain.noData')}</div>
          )}
        </div>
      </div>
    </div>
  );
}
