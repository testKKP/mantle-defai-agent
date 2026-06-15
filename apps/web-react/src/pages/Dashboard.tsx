import { useState, useEffect, useMemo } from 'react';
import {
  TrendingUp, TrendingDown, Minus, Blocks, Fuel,
  BarChart3, PieChart, Zap, ArrowRight, Clock, ChevronUp,
  ChevronDown, Layers, Gauge, HelpCircle
} from 'lucide-react';
import {
  AreaChart, Area,
  XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer
} from 'recharts';
import type { SentimentData, TokenData, ProtocolData, CalculationStep, OnChainOverview } from '../types';
import { useApp } from '../context/AppContext';
import { useTranslation } from 'react-i18next';
import { translateCalcStep, translateCalcDescription } from '../utils/translateBackend';

/* ───────────────────────────────
   工具函数
   ─────────────────────────────── */
function getSentimentColor(value: number): string {
  if (value >= 70) return '#10b981';
  if (value >= 40) return '#f59e0b';
  return '#ef4444';
}

function getSentimentLabel(value: number, t: (key: string) => string): string {
  if (value >= 70) return t('dashboard.bullish');
  if (value >= 40) return t('dashboard.neutral');
  return t('dashboard.bearish');
}

function getSentimentBg(value: number): string {
  if (value >= 70) return 'bg-emerald-500/10 text-emerald-400 border-emerald-500/20';
  if (value >= 40) return 'bg-amber-500/10 text-amber-400 border-amber-500/20';
  return 'bg-red-500/10 text-red-400 border-red-500/20';
}

function formatNumber(n: number, digits = 2): string {
  if (n >= 1e9) return `${(n / 1e9).toFixed(digits)}B`;
  if (n >= 1e6) return `${(n / 1e6).toFixed(digits)}M`;
  if (n >= 1e3) return `${(n / 1e3).toFixed(digits)}K`;
  return n.toFixed(digits);
}

function formatTimeAgo(dateStr?: string, t?: (key: string) => string): string {
  if (!dateStr) return '--';
  const d = new Date(dateStr);
  const now = new Date();
  const diff = Math.floor((now.getTime() - d.getTime()) / 1000);
  if (diff < 60) return `${diff}${t ? t('time.secondsAgo') : 's ago'}`;
  if (diff < 3600) return `${Math.floor(diff / 60)}${t ? t('time.minutesAgo') : 'm ago'}`;
  if (diff < 86400) return `${Math.floor(diff / 3600)}${t ? t('time.hoursAgo') : 'h ago'}`;
  return `${Math.floor(diff / 86400)}${t ? t('time.daysAgo') : 'd ago'}`;
}

/* ───────────────────────────────
   骨架屏组件
   ─────────────────────────────── */
function ShimmerBox({ className = '' }: { className?: string }) {
  return <div className={`shimmer rounded-lg ${className}`} />;
}

function ShimmerCard({ children, className = '' }: { children?: React.ReactNode; className?: string }) {
  return (
    <div className={`card p-5 ${className}`}>
      {children}
    </div>
  );
}

/* ───────────────────────────────
   情绪指数 Gauge（270° 弧形）
   ─────────────────────────────── */
function SentimentGauge({ value, size = 220, label }: { value: number; size?: number; label: string }) {
  const radius = (size - 40) / 2;
  const strokeWidth = 14;
  const center = size / 2;
  const circumference = 2 * Math.PI * radius;
  const arcLength = circumference * 0.75; // 270°
  const progress = Math.min(Math.max(value, 0), 100) / 100;
  const dashOffset = arcLength * (1 - progress);
  const color = getSentimentColor(value);

  // 计算指针角度 (270° arc starts at 135°, ends at 45°)
  const startAngle = 135;
  const angle = startAngle + progress * 270;
  const rad = (angle * Math.PI) / 180;
  const needleLen = radius - strokeWidth - 4;
  const needleX = center + needleLen * Math.cos(rad);
  const needleY = center + needleLen * Math.sin(rad);

  return (
    <div className="relative flex items-center justify-center" style={{ width: size, height: size }}>
      <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`}>
        <defs>
          <linearGradient id="gaugeGradient" x1="0%" y1="0%" x2="100%" y2="0%">
            <stop offset="0%" stopColor="#ef4444" />
            <stop offset="50%" stopColor="#f59e0b" />
            <stop offset="100%" stopColor="#10b981" />
          </linearGradient>
        </defs>
        {/* 背景弧 */}
        <circle
          cx={center} cy={center} r={radius}
          fill="none" stroke="#1f2937" strokeWidth={strokeWidth}
          strokeDasharray={`${arcLength} ${circumference}`}
          strokeLinecap="round"
          transform={`rotate(135 ${center} ${center})`}
        />
        {/* 进度弧 */}
        <circle
          cx={center} cy={center} r={radius}
          fill="none" stroke="url(#gaugeGradient)" strokeWidth={strokeWidth}
          strokeDasharray={`${arcLength} ${circumference}`}
          strokeDashoffset={dashOffset}
          strokeLinecap="round"
          transform={`rotate(135 ${center} ${center})`}
          style={{ transition: 'stroke-dashoffset 1s ease-out' }}
        />
        {/* 指针 */}
        <line
          x1={center} y1={center}
          x2={needleX} y2={needleY}
          stroke={color}
          strokeWidth={3}
          strokeLinecap="round"
          style={{ transition: 'all 1s ease-out' }}
        />
        {/* 中心圆点 */}
        <circle cx={center} cy={center} r={5} fill={color} />
      </svg>
      {/* 中心文字 */}
      <div className="absolute inset-0 flex flex-col items-center justify-center pt-10">
        <span className="text-4xl font-bold text-white" style={{ color }}>{value.toFixed(1)}</span>
        <span className="text-xs text-gray-400 mt-1">{label}</span>
      </div>
    </div>
  );
}

/* ───────────────────────────────
   小型指标卡片
   ─────────────────────────────── */
function MetricCard({
  title, value, subValue, icon: Icon, trend,
  loading = false,
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
   计数卡片（看涨/中性/看跌）
   ─────────────────────────────── */
function CountCard({
  label, count, icon: Icon, colorClass, active = false,
}: {
  label: string;
  count: number;
  icon: React.ElementType;
  colorClass: string;
  active?: boolean;
}) {
  return (
    <div className={`flex items-center gap-3 px-4 py-3 rounded-xl border transition ${
      active
        ? `${colorClass} bg-opacity-10`
        : 'bg-gray-800/30 border-white/5 text-gray-400'
    }`}>
      <div className={`w-8 h-8 rounded-lg flex items-center justify-center ${colorClass} bg-opacity-20`}>
        <Icon className="w-4 h-4" />
      </div>
      <div>
        <div className={`text-lg font-bold ${active ? colorClass : 'text-gray-300'}`}>{count}</div>
        <div className="text-xs text-gray-500">{label}</div>
      </div>
    </div>
  );
}

/* ───────────────────────────────
   情绪 Tab 1: 总览
   ─────────────────────────────── */
function SentimentOverview({ sentiment, loading, t }: { sentiment: SentimentData | null; loading: boolean; t: (key: string) => string }) {
  if (loading || !sentiment) {
    return (
      <div className="space-y-6">
        <div className="flex flex-col md:flex-row items-center gap-8">
          <ShimmerBox className="w-[220px] h-[220px] rounded-full" />
          <div className="flex-1 space-y-3 w-full">
            <ShimmerBox className="w-32 h-10" />
            <ShimmerBox className="w-20 h-6" />
            <ShimmerBox className="w-40 h-4" />
          </div>
        </div>
        <div className="grid grid-cols-3 gap-3">
          <ShimmerBox className="h-16" />
          <ShimmerBox className="h-16" />
          <ShimmerBox className="h-16" />
        </div>
      </div>
    );
  }

  const { sentiment_index, bullish_count, neutral_count, bearish_count, timestamp, data_freshness } = sentiment;
  const label = getSentimentLabel(sentiment_index, t);
  const color = getSentimentColor(sentiment_index);

  return (
    <div className="space-y-6">
      {/* 上排: Gauge + 大数字 */}
      <div className="flex flex-col md:flex-row items-center gap-6 md:gap-10">
        <SentimentGauge value={sentiment_index} label={t('dashboard.marketSentiment')} />
        <div className="flex-1 text-center md:text-left space-y-2">
          <div className="text-sm text-gray-400">{t('dashboard.currentSentimentIndex')}</div>
          <div className="text-5xl font-bold" style={{ color }}>{sentiment_index.toFixed(1)}</div>
          <div className={`inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-sm font-medium border ${getSentimentBg(sentiment_index)}`}>
            {sentiment_index >= 70 ? <ChevronUp className="w-3.5 h-3.5" /> :
             sentiment_index < 40 ? <ChevronDown className="w-3.5 h-3.5" /> :
             <Minus className="w-3.5 h-3.5" />}
            {label}
          </div>
          <div className="flex items-center gap-1.5 text-xs text-gray-500 pt-1">
            <Clock className="w-3 h-3" />
            <span>{t('dashboard.updatedAt')} {formatTimeAgo(timestamp || data_freshness, t)}</span>
          </div>
        </div>
      </div>

      {/* 下排: 3 个计数 */}
      <div className="grid grid-cols-3 gap-3">
        <CountCard
          label={t('dashboard.bullish')}
          count={bullish_count}
          icon={TrendingUp}
          colorClass="text-emerald-400"
          active={sentiment_index >= 70}
        />
        <CountCard
          label={t('dashboard.neutral')}
          count={neutral_count}
          icon={Minus}
          colorClass="text-amber-400"
          active={sentiment_index >= 40 && sentiment_index < 70}
        />
        <CountCard
          label={t('dashboard.bearish')}
          count={bearish_count}
          icon={TrendingDown}
          colorClass="text-red-400"
          active={sentiment_index < 40}
        />
      </div>
    </div>
  );
}

/* ───────────────────────────────
   情绪 Tab 2: 数据来源
   ─────────────────────────────── */
function SentimentSources({ sentiment, loading, t }: { sentiment: SentimentData | null; loading: boolean; t: (key: string) => string }) {
  if (loading || !sentiment) {
    return (
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <ShimmerCard><ShimmerBox className="h-40" /></ShimmerCard>
        <ShimmerCard><ShimmerBox className="h-40" /></ShimmerCard>
      </div>
    );
  }

  const binanceWeight = 70;
  const mantleWeight = 30;
  const total = sentiment.total_analyzed || 1;
  const binanceCount = sentiment.bullish_count + sentiment.neutral_count + sentiment.bearish_count;
  const mantleScore = sentiment.mantle_data?.on_chain_score ?? 50;

  const binanceIndicators = [
    { label: t('dashboard.priceTrendAnalysis'), desc: t('dashboard.priceTrendDesc') },
    { label: t('dashboard.volumeEval'), desc: t('dashboard.volumeEvalDesc') },
    { label: t('dashboard.volatilityDetection'), desc: t('dashboard.volatilityDesc') },
    { label: t('dashboard.marketSentiment'), desc: t('dashboard.marketSentimentDesc') },
  ];

  const mantleIndicators = [
    { label: t('dashboard.blockActivity'), desc: `${t('dashboard.currentHeight')} ${sentiment.mantle_data?.block_number || '--'}` },
    { label: t('dashboard.txDensity'), desc: `24h ${t('dashboard.txCount')} ${sentiment.mantle_data?.tx_count || '--'}` },
    { label: t('dashboard.gasEfficiency'), desc: `Gas ${t('dashboard.gasRatio')} ${sentiment.mantle_data?.gas_ratio?.toFixed(2) || '--'}` },
    { label: t('dashboard.networkScore'), desc: `${t('dashboard.onchainScore')} ${mantleScore.toFixed(1)}` },
  ];

  return (
    <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
      {/* 币安市场数据 */}
      <div className="card p-5 space-y-4">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <BarChart3 className="w-5 h-5 text-[#4A9B8C]" />
            <span className="font-semibold text-white">{t('dashboard.binanceMarketData')}</span>
          </div>
          <span className="px-2 py-0.5 rounded-full text-xs bg-[#2D6B5E]/20 text-[#7ED7C4] border border-[#2D6B5E]/30">
            {t('dashboard.weight')} {binanceWeight}%
          </span>
        </div>
        <div className="space-y-1">
          <div className="flex justify-between text-xs text-gray-400 mb-1">
            <span>{t('dashboard.analyzedTokens')}</span>
            <span>{binanceCount} / {total}</span>
          </div>
          <div className="h-2 bg-gray-800 rounded-full overflow-hidden">
            <div className="h-full mantle-gradient rounded-full" style={{ width: `${binanceWeight}%` }} />
          </div>
        </div>
        <div className="space-y-2.5">
          {binanceIndicators.map((item, i) => (
            <div key={i} className="flex items-start gap-3 py-2 border-b border-white/5 last:border-0">
              <div className="w-1.5 h-1.5 rounded-full bg-[#4A9B8C] mt-2 flex-shrink-0" />
              <div>
                <div className="text-sm text-gray-200">{item.label}</div>
                <div className="text-xs text-gray-500">{item.desc}</div>
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* Mantle 链上数据 */}
      <div className="card p-5 space-y-4">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Layers className="w-5 h-5 text-[#7ED7C4]" />
            <span className="font-semibold text-white">{t('dashboard.mantleOnchainData')}</span>
          </div>
          <span className="px-2 py-0.5 rounded-full text-xs bg-[#7ED7C4]/10 text-[#7ED7C4] border border-[#7ED7C4]/20">
            {t('dashboard.weight')} {mantleWeight}%
          </span>
        </div>
        <div className="space-y-1">
          <div className="flex justify-between text-xs text-gray-400 mb-1">
            <span>{t('dashboard.onchainActivity')}</span>
            <span>{sentiment.mantle_data?.network_activity || '--'}</span>
          </div>
          <div className="h-2 bg-gray-800 rounded-full overflow-hidden">
            <div className="h-full bg-[#7ED7C4] rounded-full opacity-80" style={{ width: `${mantleWeight}%` }} />
          </div>
        </div>
        <div className="space-y-2.5">
          {mantleIndicators.map((item, i) => (
            <div key={i} className="flex items-start gap-3 py-2 border-b border-white/5 last:border-0">
              <div className="w-1.5 h-1.5 rounded-full bg-[#7ED7C4] mt-2 flex-shrink-0" />
              <div>
                <div className="text-sm text-gray-200">{item.label}</div>
                <div className="text-xs text-gray-500">{item.desc}</div>
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

/* ───────────────────────────────
   情绪 Tab 3: 分析逻辑
   ─────────────────────────────── */
function SentimentLogic({ sentiment, loading, t }: { sentiment: SentimentData | null; loading: boolean; t: (key: string) => string }) {
  if (loading || !sentiment) {
    return (
      <div className="flex items-center justify-center py-12">
        <ShimmerBox className="w-full h-32" />
      </div>
    );
  }

  const rawSteps: CalculationStep[] = sentiment.calculation_steps && sentiment.calculation_steps.length > 0
    ? sentiment.calculation_steps
    : [
        { step: t('dashboard.stepBinanceAggregation'), value: sentiment.bullish_count * 10 + sentiment.neutral_count * 5, description: t('dashboard.descBinanceAnalysis') },
        { step: t('dashboard.stepOnchainScore'), value: sentiment.mantle_data?.on_chain_score ?? 50, description: t('dashboard.descOnchainEval') },
        { step: t('dashboard.stepWeightedCalc'), value: Math.round((sentiment.sentiment_index * 0.7 + (sentiment.mantle_data?.on_chain_score ?? 50) * 0.3)), description: t('dashboard.descWeighted') },
        { step: t('dashboard.stepFinalIndex'), value: sentiment.sentiment_index, description: t('dashboard.descNormalized') },
      ];

  return (
    <div className="py-4">
      <div className="flex flex-col md:flex-row items-stretch gap-2 md:gap-0">
        {rawSteps.map((s, i) => {
          const isLast = i === rawSteps.length - 1;
          const color = getSentimentColor(s.value);
          return (
            <div key={i} className="flex flex-col md:flex-row items-stretch flex-1">
              {/* 步骤卡片 */}
              <div className="flex-1 card p-4 flex flex-col items-center text-center relative">
                <div
                  className="w-10 h-10 rounded-full flex items-center justify-center text-sm font-bold mb-2"
                  style={{ backgroundColor: `${color}20`, color, border: `1px solid ${color}40` }}
                >
                  {i + 1}
                </div>
                <div className="text-sm font-semibold text-gray-200">{translateCalcStep(s.step)}</div>
                <div className="text-2xl font-bold mt-1" style={{ color }}>{s.value.toFixed(1)}</div>
                {s.description && <div className="text-xs text-gray-500 mt-1">{translateCalcDescription(s.description)}</div>}
                {isLast && (
                  <div className="absolute -top-2 -right-2 px-2 py-0.5 rounded-full text-[10px] font-bold bg-[#2D6B5E] text-white">
                    {t('dashboard.final')}
                  </div>
                )}
              </div>
              {/* 箭头 */}
              {!isLast && (
                <div className="flex items-center justify-center py-2 md:py-0 md:px-2">
                  <ArrowRight className="w-5 h-5 text-gray-600 hidden md:block" />
                  <ChevronDown className="w-5 h-5 text-gray-600 md:hidden" />
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}


/* ───────────────────────────────
   主 Dashboard 组件
   ─────────────────────────────── */
const TIMEFRAME_LABELS: Record<string, string> = {
  '1h': '1h',
  '4h': '4h',
  '1d': '1d',
};

function Dashboard() {
  const app = useApp();
  const [sentiment, setSentiment] = useState<SentimentData | null>(null);
  const [overview, setOverview] = useState<OnChainOverview | null>(null);
  const [protocols, setProtocols] = useState<ProtocolData[]>([]);
  const [activeSentimentTab, setActiveSentimentTab] = useState<'overview' | 'sources' | 'logic'>('overview');
  const [activeChartTab, setActiveChartTab] = useState<'activity' | 'gas' | 'tvl'>('activity');
  const [loginRequired, setLoginRequired] = useState(false);
  const sentimentTimeframe = '1h';
  const { t } = useTranslation();

  // Sync data from AppContext to avoid duplicate requests
  useEffect(() => {
    if (app.sentiment) {
      setSentiment(app.sentiment);
      setLoginRequired(!!app.sentiment.login_required);
    }
    if (app.overview) setOverview(app.overview);
    if (app.protocols) setProtocols(app.protocols);
  }, [app.sentiment, app.overview, app.protocols]);

  const trends = app.trends;
  const tvlHistory = app.tvlHistory;
  const loading = app.loading;

  const allTokens = useMemo(() => {
    const tokens: TokenData[] = [];
    if (sentiment?.top_bullish) tokens.push(...sentiment.top_bullish);
    if (sentiment?.top_bearish) tokens.push(...sentiment.top_bearish);
    const seen = new Set<string>();
    return tokens.filter(t => {
      if (seen.has(t.symbol)) return false;
      seen.add(t.symbol);
      return true;
    });
  }, [sentiment]);

  const chartData = useMemo(() => {
    if (activeChartTab === 'activity' && trends?.activity) return trends.activity;
    if (activeChartTab === 'gas' && trends?.gas) return trends.gas;
    if (activeChartTab === 'tvl') return tvlHistory.map(d => ({ timestamp: d.timestamp, tvl: d.tvl }));
    return [];
  }, [activeChartTab, trends, tvlHistory]);

  const chartDataKey = activeChartTab === 'tvl' ? 'tvl' : activeChartTab === 'gas' ? 'gas_price' : 'activity_index';

  return (
    <div className="space-y-6 p-4 md:p-6 max-w-7xl mx-auto">
      {/* 区块 a: 情绪研判区 */}
      <section className="card p-5">
        <div className="flex items-center gap-2 mb-4">
          <Gauge className="w-5 h-5 text-[#7ED7C4]" />
          <div>
            <h2 className="text-lg font-semibold text-white">
              {t('dashboard.title')}
              <span className="ml-2 text-xs font-normal text-gray-500">({TIMEFRAME_LABELS[sentimentTimeframe] || sentimentTimeframe})</span>
            </h2>
            <p className="text-xs text-gray-500">{t('dashboard.agentDesc')}</p>
          </div>
        </div>
        <div className="flex gap-1 mb-4 bg-gray-800/50 p-1 rounded-lg w-fit">
          {([
            { key: 'overview' as const, label: t('dashboard.overview') },
            { key: 'sources' as const, label: t('dashboard.dataSources') },
            { key: 'logic' as const, label: t('dashboard.analysisLogic') },
          ]).map(tab => (
            <button
              key={tab.key}
              onClick={() => setActiveSentimentTab(tab.key)}
              className={`px-4 py-1.5 rounded-md text-sm font-medium transition ${
                activeSentimentTab === tab.key
                  ? 'bg-[#2D6B5E] text-white'
                  : 'text-gray-400 hover:text-gray-200'
              }`}
            >
              {tab.label}
            </button>
          ))}
        </div>
        {activeSentimentTab === 'overview' && <SentimentOverview sentiment={sentiment} loading={loading} t={t} />}
        {activeSentimentTab === 'sources' && <SentimentSources sentiment={sentiment} loading={loading} t={t} />}
        {activeSentimentTab === 'logic' && <SentimentLogic sentiment={sentiment} loading={loading} t={t} />}
      </section>

      {/* 区块 b: 链上数据区 */}
      <section className="space-y-4">
        <div className="flex items-center gap-2">
          <Blocks className="w-5 h-5 text-[#7ED7C4]" />
          <h2 className="text-lg font-semibold text-white">{t('dashboard.chainOverview')}</h2>
        </div>
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
          <MetricCard
            title={t('dashboard.totalTVL')}
            value={overview ? `$${formatNumber(overview.total_tvl)}` : '--'}
            subValue={`${protocols.length} ${t('dashboard.protocols')}`}
            icon={Layers}
            trend="up"
            loading={loading}
          />
          <MetricCard
            title={t('dashboard.volume24h')}
            value={overview ? `$${formatNumber(overview.total_volume_24h)}` : '--'}
            icon={BarChart3}
            loading={loading}
          />
          <MetricCard
            title={t('dashboard.activeProtocols')}
            value={overview ? `${overview.protocol_count}` : '--'}
            icon={Zap}
            loading={loading}
          />
          <MetricCard
            title={t('dashboard.fees24h')}
            value={overview ? `$${formatNumber(overview.total_fees_24h)}` : '--'}
            icon={Fuel}
            loading={loading}
          />
        </div>
        <div className="card p-5">
          <div className="flex items-center gap-3 mb-4">
            <div className="flex gap-1 bg-gray-800/50 p-1 rounded-lg w-fit">
              {([
                { key: 'activity' as const, label: t('dashboard.activity') },
                { key: 'gas' as const, label: t('dashboard.gas') },
                { key: 'tvl' as const, label: t('dashboard.tvl') },
              ]).map(tab => (
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
            {activeChartTab === 'activity' && (
              <div className="group relative">
                <HelpCircle className="w-4 h-4 text-gray-500 cursor-help" />
                <div className="absolute bottom-full left-1/2 -translate-x-1/2 mb-2 px-3 py-2 rounded-lg bg-gray-800 text-xs text-gray-300 whitespace-nowrap border border-white/10 opacity-0 group-hover:opacity-100 transition-opacity pointer-events-none z-10 shadow-lg">
                  {t('dashboard.activityTooltip')}
                </div>
              </div>
            )}
          </div>
          {activeChartTab === 'activity' && (
            <p className="text-xs text-gray-500 mb-2">
              {t('dashboard.activityDescription')}
            </p>
          )}
          <div className="h-64 w-full relative">
            {loading ? (
              <ShimmerBox className="h-full w-full" />
            ) : chartData.length > 0 ? (
              <ResponsiveContainer key={activeChartTab} width="100%" height="100%" minWidth={0} minHeight={0}>
                <AreaChart data={chartData}>
                  <defs>
                    <linearGradient id="chartGrad" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="5%" stopColor="#7ED7C4" stopOpacity={0.3} />
                      <stop offset="95%" stopColor="#7ED7C4" stopOpacity={0} />
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
                    stroke="#7ED7C4"
                    fill="url(#chartGrad)"
                    strokeWidth={2}
                  />
                </AreaChart>
              </ResponsiveContainer>
            ) : (
              <div className="flex items-center justify-center h-full text-gray-500">
                {t('dashboard.noData')}
              </div>
            )}
          </div>
        </div>
      </section>

      {/* 区块 c: 强势/弱势币种 (wallet or whitelist) */}
      {(!loginRequired) && (
      <section>
        <div className="flex items-center gap-2 mb-4">
          <TrendingUp className="w-5 h-5 text-[#7ED7C4]" />
          <h2 className="text-lg font-semibold text-white">{t('dashboard.tokenStrengthAnalysis')}</h2>
        </div>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {/* 强势 */}
          <div className="card p-5">
            <div className="flex items-center gap-2 mb-4">
              <ChevronUp className="w-4 h-4 text-emerald-400" />
              <span className="font-semibold text-white">{t('dashboard.strongTokens')}</span>
            </div>
            {loading ? (
              <div className="space-y-2">
                <ShimmerBox className="h-12" />
                <ShimmerBox className="h-12" />
                <ShimmerBox className="h-12" />
              </div>
            ) : sentiment?.top_bullish && sentiment.top_bullish.length > 0 ? (
              <div className="space-y-2">
                {sentiment.top_bullish.map((token, i) => (
                  <div key={token.symbol} className="flex items-center justify-between px-3 py-2.5 rounded-lg bg-gray-800/40 border border-white/5">
                    <div className="flex items-center gap-3">
                      <span className="text-xs text-gray-500 w-4">{i + 1}</span>
                      <span className="font-medium text-white">{token.symbol}</span>
                    </div>
                    <div className="flex items-center gap-4">
                      <span className="text-sm text-gray-400">${token.price?.toFixed(4) ?? '--'}</span>
                      <span className={`text-sm font-medium ${(token.price_change_24h ?? 0) >= 0 ? 'text-emerald-400' : 'text-red-400'}`}>
                        {(token.price_change_24h ?? 0) > 0 ? '+' : ''}{token.price_change_24h?.toFixed(2) ?? '--'}%
                      </span>
                    </div>
                  </div>
                ))}
              </div>
            ) : (
              <div className="text-gray-500 text-sm py-4 text-center">{t('dashboard.noData')}</div>
            )}
          </div>
          {/* 弱势 */}
          <div className="card p-5">
            <div className="flex items-center gap-2 mb-4">
              <ChevronDown className="w-4 h-4 text-red-400" />
              <span className="font-semibold text-white">{t('dashboard.weakTokens')}</span>
            </div>
            {loading ? (
              <div className="space-y-2">
                <ShimmerBox className="h-12" />
                <ShimmerBox className="h-12" />
                <ShimmerBox className="h-12" />
              </div>
            ) : sentiment?.top_bearish && sentiment.top_bearish.length > 0 ? (
              <div className="space-y-2">
                {sentiment.top_bearish.map((token, i) => (
                  <div key={token.symbol} className="flex items-center justify-between px-3 py-2.5 rounded-lg bg-gray-800/40 border border-white/5">
                    <div className="flex items-center gap-3">
                      <span className="text-xs text-gray-500 w-4">{i + 1}</span>
                      <span className="font-medium text-white">{token.symbol}</span>
                    </div>
                    <div className="flex items-center gap-4">
                      <span className="text-sm text-gray-400">${token.price?.toFixed(4) ?? '--'}</span>
                      <span className={`text-sm font-medium ${(token.price_change_24h ?? 0) >= 0 ? 'text-emerald-400' : 'text-red-400'}`}>
                        {(token.price_change_24h ?? 0) > 0 ? '+' : ''}{token.price_change_24h?.toFixed(2) ?? '--'}%
                      </span>
                    </div>
                  </div>
                ))}
              </div>
            ) : (
              <div className="text-gray-500 text-sm py-4 text-center">{t('dashboard.noData')}</div>
            )}
          </div>
        </div>
      </section>
      )}

      {/* 区块 d: 全市场分析表格 (wallet or whitelist) */}
      {(!loginRequired) && (
      <section className="card p-5">
        <div className="flex items-center gap-2 mb-4">
          <PieChart className="w-5 h-5 text-[#7ED7C4]" />
          <h2 className="text-lg font-semibold text-white">{t('dashboard.fullMarketAnalysis')}</h2>
        </div>
        {loading ? (
          <div className="space-y-2">
            <ShimmerBox className="h-10" />
            <ShimmerBox className="h-10" />
            <ShimmerBox className="h-10" />
            <ShimmerBox className="h-10" />
          </div>
        ) : allTokens.length > 0 ? (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-white/10 text-gray-400">
                  <th className="text-left py-2 px-3 font-medium">{t('dashboard.symbol')}</th>
                  <th className="text-right py-2 px-3 font-medium">{t('dashboard.price')}</th>
                  <th className="text-right py-2 px-3 font-medium">{t('dashboard.change24h')}</th>
                  <th className="text-right py-2 px-3 font-medium">{t('dashboard.sentiment')}</th>
                  <th className="text-right py-2 px-3 font-medium">{t('dashboard.strength')}</th>
                  <th className="text-right py-2 px-3 font-medium">{t('dashboard.score')}</th>
                  <th className="text-right py-2 px-3 font-medium">{t('dashboard.volumeTrend')}</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-white/5">
                {allTokens.map(token => (
                  <tr key={token.symbol} className="hover:bg-white/5 transition">
                    <td className="py-2.5 px-3 font-medium text-white">{token.symbol}</td>
                    <td className="py-2.5 px-3 text-right text-gray-300">${token.price?.toFixed(4) ?? '--'}</td>
                    <td className={`py-2.5 px-3 text-right font-medium ${(token.price_change_24h ?? 0) >= 0 ? 'text-emerald-400' : 'text-red-400'}`}>
                      {(token.price_change_24h ?? 0) > 0 ? '+' : ''}{token.price_change_24h?.toFixed(2) ?? '--'}%
                    </td>
                    <td className="py-2.5 px-3 text-right">
                      <span className={`inline-flex items-center px-2 py-0.5 rounded text-xs font-medium ${
                        token.alignment === 'bullish' ? 'bg-emerald-500/10 text-emerald-400' :
                        token.alignment === 'bearish' ? 'bg-red-500/10 text-red-400' :
                        'bg-amber-500/10 text-amber-400'
                      }`}>
                        {token.alignment === 'bullish' ? t('dashboard.bullish') : token.alignment === 'bearish' ? t('dashboard.bearish') : t('dashboard.neutral')}
                      </span>
                    </td>
                    <td className="py-2.5 px-3 text-right text-gray-300">{token.strength ?? '--'}</td>
                    <td className="py-2.5 px-3 text-right text-gray-300">{token.score?.toFixed(1) ?? '--'}</td>
                    <td className="py-2.5 px-3 text-right text-gray-400">{token.volume_trend ?? '--'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <div className="text-gray-500 text-sm py-8 text-center">{t('dashboard.noMarketData')}</div>
        )}
      </section>
      )}
    </div>
  );
}

export default Dashboard;
