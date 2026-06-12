import { useState, useMemo, useEffect } from 'react';
import {
  TrendingUp, TrendingDown, Minus, Blocks, Fuel,
  BarChart3, PieChart, Zap, ArrowRight, Clock, ChevronUp,
  ChevronDown, Layers, Gauge, AlertTriangle,
  ShieldAlert, Target, Eye, Timer, ArrowUpRight, ArrowDownRight,
  Users, Skull
} from 'lucide-react';
import type { SentimentData, CalculationStep } from '../types';
import { useTranslation } from 'react-i18next';
import { translateCalcStep, translateCalcDescription, translateRiskWarning } from '../utils/translateBackend';
import { useReadContract } from 'wagmi';
import { mantleSepoliaTestnet } from 'viem/chains';
import registryAbi from '../abi/MantleDeFAIRegistry.json';
import { parseSignalData } from '../hooks/useSignalDecrypt';
import sha256 from 'crypto-js/sha256';
import { getLatestSentiment, getOnChainOverview } from '../services/api';

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

function getFNGColor(value: number): string {
  if (value <= 20) return '#ef4444';
  if (value <= 40) return '#f97316';
  if (value <= 60) return '#f59e0b';
  if (value <= 80) return '#84cc16';
  return '#10b981';
}

function getFNGLabel(value: number, t: (key: string) => string): string {
  if (value <= 20) return t('fng.extremeFear');
  if (value <= 40) return t('fng.fear');
  if (value <= 60) return t('fng.neutral');
  if (value <= 80) return t('fng.greed');
  return t('fng.extremeGreed');
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
   风险警告横幅
   ─────────────────────────────── */
function RiskWarningBanner({ warning, t }: { warning?: string; t: (key: string) => string }) {
  if (!warning) return null;
  return (
    <div className="relative overflow-hidden rounded-xl border border-red-500/20 bg-gradient-to-r from-red-950/60 via-red-900/30 to-red-950/60 px-5 py-3.5">
      <div className="absolute inset-0 animate-pulse bg-red-500/5" />
      <div className="relative flex items-center gap-3">
        <div className="flex-shrink-0">
          <ShieldAlert className="w-5 h-5 text-red-400 animate-pulse" />
        </div>
        <div className="flex-1">
          <div className="flex items-center gap-2">
            <span className="text-sm font-semibold text-red-300">{t('risk.warning')}</span>
            <span className="text-xs text-red-400/70 px-1.5 py-0.5 rounded bg-red-500/10 border border-red-500/20">{t('risk.highRisk')}</span>
          </div>
          <p className="text-sm text-red-200/80 mt-0.5">{translateRiskWarning(warning)}</p>
        </div>
        <AlertTriangle className="w-5 h-5 text-red-400/50 flex-shrink-0" />
      </div>
    </div>
  );
}

/* ───────────────────────────────
   Hash 验证徽章
   ─────────────────────────────── */
function VerificationBadge({ status }: { status: 'verified' | 'mismatch' | 'pending' }) {
  if (status === 'verified') {
    return (
      <span className="inline-flex items-center gap-1 text-[10px] font-medium px-2 py-0.5 rounded-full bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">
        ✓ Verified
      </span>
    );
  }
  if (status === 'mismatch') {
    return (
      <span className="inline-flex items-center gap-1 text-[10px] font-medium px-2 py-0.5 rounded-full bg-red-500/10 text-red-400 border border-red-500/20">
        ⚠ Data Mismatch
      </span>
    );
  }
  return (
    <span className="inline-flex items-center gap-1 text-[10px] font-medium px-2 py-0.5 rounded-full bg-gray-500/10 text-gray-400 border border-gray-500/20">
      Verifying...
    </span>
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

  const { sentiment_index, bullish_count, neutral_count, bearish_count, timestamp, data_freshness, fng } = sentiment;
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

      {/* 下排: 3 个计数 + FNG */}
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

      {/* FNG 恐惧贪婪指数 */}
      {fng && (
        <div className="flex items-center gap-3 px-4 py-3 rounded-xl border border-white/5 bg-gray-800/30">
          <div className="w-8 h-8 rounded-lg flex items-center justify-center bg-orange-500/10">
            <Skull className="w-4 h-4 text-orange-400" />
          </div>
          <div className="flex-1">
            <div className="text-xs text-gray-500">{t('sentiment.fearGreedIndex')}</div>
            <div className="flex items-center gap-2">
              <span className="text-lg font-bold" style={{ color: getFNGColor(fng.value) }}>{fng.value}</span>
              <span className="text-sm font-medium" style={{ color: getFNGColor(fng.value) }}>{t(getFNGLabel(fng.value, t))}</span>
            </div>
          </div>
        </div>
      )}
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
  const [activeSentimentTab, setActiveSentimentTab] = useState<'overview' | 'sources' | 'logic'>('overview');
  const loginRequired = false;
  const sentimentTimeframe = '1h';
  const { t } = useTranslation();

  // API 数据状态
  const [apiData, setApiData] = useState<any>(null);
  const [onchainData, setOnchainData] = useState<any>(null);
  const [apiLoading, setApiLoading] = useState(true);
  const [_apiError, setApiError] = useState<string | null>(null);

  // Hash 验证状态
  const [verificationStatus, setVerificationStatus] = useState<'verified' | 'mismatch' | 'pending'>('pending');

  const registryAddress = import.meta.env.VITE_REGISTRY_ADDRESS;

  const latestSignal = useReadContract({
    address: registryAddress || undefined,
    abi: registryAbi,
    functionName: 'getLatestSignal',
    args: ['BTC', '1d'],
    chainId: mantleSepoliaTestnet.id,
    query: { enabled: !!registryAddress },
  });

  const signalData = latestSignal.data as { data: string; dataHash: string; timestamp: bigint; submitter: string } | undefined;

  const onchainPayload = useMemo(() => {
    if (!signalData) return null;
    try {
      return parseSignalData(signalData.data);
    } catch {
      return null;
    }
  }, [signalData]);

  const loading = apiLoading;

  // A. 从 API 获取完整数据
  useEffect(() => {
    Promise.allSettled([
      getLatestSentiment(),
      getOnChainOverview(),
    ])
      .then(([sentimentRes, onchainRes]) => {
        if (sentimentRes.status === 'fulfilled') {
          setApiData(sentimentRes.value);
        } else {
          setApiError(sentimentRes.reason?.message || 'Failed to load sentiment');
        }
        if (onchainRes.status === 'fulfilled') {
          setOnchainData(onchainRes.value);
        }
        setApiLoading(false);
      })
      .catch(err => {
        setApiError(err.message);
        setApiLoading(false);
      });
  }, []);

  // B. Hash 验证
  useEffect(() => {
    if (!onchainPayload?.full_data_hash || !apiData) {
      setVerificationStatus('pending');
      return;
    }
    try {
      const cleanData = { ...apiData };
      delete cleanData._cache_ttl;
      delete cleanData._cached_at;
      const jsonStr = JSON.stringify(cleanData);
      const hash = sha256(jsonStr).toString();
      setVerificationStatus(hash === onchainPayload.full_data_hash ? 'verified' : 'mismatch');
    } catch {
      setVerificationStatus('mismatch');
    }
  }, [onchainPayload?.full_data_hash, apiData]);

  // Sentiment 数据从 API 读取
  const sentimentData: SentimentData | null = useMemo(() => {
    if (!apiData) return null;
    const s = apiData;
    return {
      sentiment_index: s.sentiment_index ?? 50,
      market_bias: (s.market_bias ?? 'neutral') as SentimentData['market_bias'],
      bias_strength: (s.bias_strength ?? 'medium') as SentimentData['bias_strength'],
      bullish_count: s.bullish_count ?? 0,
      bearish_count: s.bearish_count ?? 0,
      neutral_count: s.neutral_count ?? 0,
      total_analyzed: s.total_analyzed ?? ((s.bullish_count ?? 0) + (s.neutral_count ?? 0) + (s.bearish_count ?? 0)),
      timeframe: s.timeframe ?? '1d',
      timestamp: s.timestamp ?? '',
      data_freshness: s.data_freshness ?? s.timestamp ?? '',
      top_bullish: (s.top_bullish ?? []).map((item: any) => ({
        symbol: item.symbol ?? item.asset ?? '',
        price: item.price ?? 0,
        price_change_24h: item.price_change_24h ?? item.change_24h ?? 0,
        alignment: 'bullish' as const,
        strength: 'strong',
        score: item.score ?? 0,
        volume_trend: 'up',
      })),
      top_bearish: (s.top_bearish ?? []).map((item: any) => ({
        symbol: item.symbol ?? item.asset ?? '',
        price: item.price ?? 0,
        price_change_24h: item.price_change_24h ?? item.change_24h ?? 0,
        alignment: 'bearish' as const,
        strength: 'weak',
        score: item.score ?? 0,
        volume_trend: 'down',
      })),
      mantle_data: s.mantle_data ?? {
        block_number: s.block_number ?? 0,
        tx_count: 0,
        gas_ratio: 0,
        gas_price_gwei: s.gas_gwei ?? 0,
        on_chain_score: 50,
        network_activity: 'active',
      },
      calculation_steps: s.calculation_steps ?? [],
      fng: s.fng?.value !== undefined
        ? { value: s.fng.value, classification: s.fng.classification ?? s.fng.label ?? '', timestamp: '' }
        : s.fng_value !== undefined
        ? { value: s.fng_value, classification: s.fng_label ?? '', timestamp: '' }
        : undefined,
    } as SentimentData;
  }, [apiData]);

  // 风险警告
  const riskWarning = apiData?.risk_warning ?? apiData?.risk ?? '';

  // AI 交易决策
  const decision = apiData?.decision ?? null;

  // 多周期持仓报告
  const positionReport = useMemo(() => {
    const raw = apiData?.position_report as any;
    if (!raw) return null;
    const mapped: any = {};
    for (const [tf, data] of Object.entries(raw) as [string, any][]) {
      mapped[tf] = {
        long: data.long || [],
        short: data.short || [],
        watch: data.watch || '',
      };
    }
    return mapped;
  }, [apiData]);

  // 艾略特波浪
  const elliottWave = apiData?.elliott_wave ?? null;

  // OnChain 指标
  const mantleTvl = onchainData?.total_tvl ?? onchainData?.tvl;
  const protocolCount = onchainData?.protocol_count ?? onchainData?.count;
  const tvlChange24h = onchainData?.tvl_change_24h;
  const activeAddresses = onchainData?.active_addresses;
  // Protocols
  const protocols = onchainData?.protocols ?? [];

  // Overview
  const overview = onchainData ?? null;

  // 全市场分析表格从 API 读取
  const allTokens = useMemo(() => {
    const source = apiData?.symbol_scores ?? [];
    return source.map((s: any) => ({
      symbol: s.symbol,
      price: s.price ?? 0,
      price_change_24h: s.change_24h ?? s.price_change_24h ?? 0,
      alignment: (s.score ?? 50) >= 70 ? 'bullish' as const : (s.score ?? 50) >= 40 ? 'neutral' as const : 'bearish' as const,
      strength: (s.score ?? 50) >= 70 ? 'strong' : (s.score ?? 50) >= 40 ? 'medium' : 'weak',
      score: s.score ?? 0,
      volume_trend: s.volume_trend ?? '--',
    }));
  }, [apiData]);


  // 空状态
  if (!loading && !apiData) {
    return (
      <div className="space-y-6 p-4 md:p-6 max-w-7xl mx-auto">
        <div className="card p-8 flex items-center justify-center min-h-[60vh]">
          <div className="text-center space-y-4">
            <Blocks className="w-12 h-12 text-gray-500 mx-auto" />
            <p className="text-gray-400 text-lg">暂无链上数据</p>
            <p className="text-gray-500 text-sm">请检查网络连接和合约地址配置</p>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-6 p-4 md:p-6 max-w-7xl mx-auto">
      {/* 风险警告横幅 */}
      {riskWarning && <RiskWarningBanner warning={riskWarning} t={t} />}

      {/* 区块 a: 情绪研判区 */}
      <section className="card p-5">
        <div className="flex items-center justify-between mb-4">
          <div className="flex items-center gap-2">
            <Gauge className="w-5 h-5 text-[#7ED7C4]" />
            <div>
              <h2 className="text-lg font-semibold text-white">
                {t('dashboard.title')}
                <span className="ml-2 text-xs font-normal text-gray-500">({TIMEFRAME_LABELS[sentimentTimeframe] || sentimentTimeframe})</span>
              </h2>
              <p className="text-xs text-gray-500">{t('dashboard.agentDesc')}</p>
            </div>
          </div>
          <VerificationBadge status={verificationStatus} />
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
        {activeSentimentTab === 'overview' && <SentimentOverview sentiment={sentimentData} loading={loading} t={t} />}
        {activeSentimentTab === 'sources' && <SentimentSources sentiment={sentimentData} loading={loading} t={t} />}
        {activeSentimentTab === 'logic' && <SentimentLogic sentiment={sentimentData} loading={loading} t={t} />}
      </section>

      {/* AI 交易决策 */}
      {decision && (
        <section className="card p-5">
          <div className="flex items-center justify-between mb-4">
            <div className="flex items-center gap-2">
              <Target className="w-5 h-5 text-[#7ED7C4]" />
              <h2 className="text-lg font-semibold text-white">{t('dashboard.aiDecision')}</h2>
            </div>
            <VerificationBadge status={verificationStatus} />
          </div>
          <div className="flex flex-wrap items-center gap-4">
            <div className="flex items-center gap-2">
              <span className="text-sm text-gray-400">{t('table.symbol')}</span>
              <span className="text-sm font-bold text-white">{(decision as any).symbol ?? '--'}</span>
            </div>
            <div className="flex items-center gap-2">
              <span className="text-sm text-gray-400">{t('table.timeframe')}</span>
              <span className="text-xs text-gray-300 px-2 py-0.5 rounded bg-gray-800">{(decision as any).timeframe ?? '--'}</span>
            </div>
            <div className="flex items-center gap-2">
              <span className="text-sm text-gray-400">{t('table.direction')}</span>
              <span className={`inline-flex items-center gap-1 text-xs font-medium px-2 py-0.5 rounded-full ${
                (decision as any).direction === 'long'
                  ? 'bg-emerald-500/10 text-emerald-400'
                  : (decision as any).direction === 'short'
                    ? 'bg-red-500/10 text-red-400'
                    : 'bg-amber-500/10 text-amber-400'
              }`}>
                {(decision as any).direction === 'long' ? <TrendingUp className="w-3 h-3" /> : (decision as any).direction === 'short' ? <TrendingDown className="w-3 h-3" /> : <Minus className="w-3 h-3" />}
                {(decision as any).direction === 'long' ? t('trade.long') : (decision as any).direction === 'short' ? t('trade.short') : t('trade.wait')}
              </span>
            </div>
            <div className="flex items-center gap-2">
              <span className="text-sm text-gray-400">{t('table.confidence')}</span>
              <span className="text-sm font-bold text-[#7ED7C4]">{(decision as any).confidence || 'N/A'}</span>
            </div>
            {(decision as any).reason && (
              <div className="w-full mt-1">
                <span className="text-xs text-gray-500">{t('backtest.reason')}</span>
                <p className="text-sm text-gray-300 mt-0.5">{(decision as any).reason}</p>
              </div>
            )}
          </div>
        </section>
      )}


      {/* 区块 b: 链上数据区 */}
      <section className="space-y-4">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Blocks className="w-5 h-5 text-[#7ED7C4]" />
            <h2 className="text-lg font-semibold text-white">{t('dashboard.chainOverview')}</h2>
          </div>
          <VerificationBadge status={verificationStatus} />
        </div>
        <div className="grid grid-cols-2 lg:grid-cols-6 gap-3">
          <MetricCard
            title={t('dashboard.totalTVL')}
            value={mantleTvl != null ? `$${formatNumber(mantleTvl)}` : '--'}
            subValue={`${protocols.length} ${t('dashboard.protocols')}`}
            icon={Layers}
            trend="up"
            loading={loading}
          />
          <MetricCard
            title={t('dashboard.volume24h')}
            value={overview?.total_volume_24h != null ? `$${formatNumber(overview.total_volume_24h)}` : '--'}
            icon={BarChart3}
            loading={loading}
          />
          <MetricCard
            title={t('dashboard.activeProtocols')}
            value={protocolCount != null ? `${protocolCount}` : '--'}
            icon={Zap}
            loading={loading}
          />
          <MetricCard
            title={t('dashboard.fees24h')}
            value={overview?.total_fees_24h != null ? `$${formatNumber(overview.total_fees_24h)}` : '--'}
            icon={Fuel}
            loading={loading}
          />
          <MetricCard
            title={t('dashboard.tvlChange24h')}
            value={tvlChange24h != null ? `${tvlChange24h >= 0 ? '+' : ''}${tvlChange24h.toFixed(2)}%` : '--'}
            icon={TrendingUp}
            trend={tvlChange24h != null ? (tvlChange24h >= 0 ? 'up' : 'down') : 'neutral'}
            loading={loading}
          />
          <MetricCard
            title={t('dashboard.activeAddresses')}
            value={activeAddresses != null ? `${formatNumber(activeAddresses, 0)}` : '--'}
            icon={Users}
            loading={loading}
          />
        </div>
      </section>

      {/* 区块 c: 强势/弱势币种 (wallet or whitelist) */}
      {(!loginRequired) && (
      <section>
        <div className="flex items-center justify-between mb-4">
          <div className="flex items-center gap-2">
            <TrendingUp className="w-5 h-5 text-[#7ED7C4]" />
            <h2 className="text-lg font-semibold text-white">{t('dashboard.tokenStrengthAnalysis')}</h2>
          </div>
          <VerificationBadge status={verificationStatus} />
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
            ) : sentimentData?.top_bullish && sentimentData.top_bullish.length > 0 ? (
              <div className="space-y-2">
                {sentimentData.top_bullish.map((token, i) => (
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
            ) : sentimentData?.top_bearish && sentimentData.top_bearish.length > 0 ? (
              <div className="space-y-2">
                {sentimentData.top_bearish.map((token, i) => (
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

      {/* 多周期持仓报告 */}
      {positionReport && (
        <section className="space-y-4">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <Target className="w-5 h-5 text-[#7ED7C4]" />
              <h2 className="text-lg font-semibold text-white">{t('position.reportTitle')}</h2>
            </div>
            <VerificationBadge status={verificationStatus} />
          </div>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            {(['1d', '4h', '1w'] as const).map((tf, idx) => {
              const report = positionReport[tf];
              const accentColors = ['#7ED7C4', '#4A9B8C', '#2D6B5E'];
              const titles = [t('position.daily'), t('position.fourHour'), t('position.weekly')];
              const subtitles = [t('position.dailyDesc'), t('position.fourHourDesc'), t('position.weeklyDesc')];
              return (
                <div key={tf} className="card p-4 flex flex-col h-full" style={{ borderTop: `2px solid ${accentColors[idx]}` }}>
                  <div className="flex items-center gap-2 mb-3 pb-3 border-b border-white/5">
                    <Timer className="w-4 h-4" style={{ color: accentColors[idx] }} />
                    <div>
                      <h3 className="text-sm font-semibold text-white">{titles[idx]}</h3>
                      <p className="text-[10px] text-gray-500">{subtitles[idx]}</p>
                    </div>
                  </div>
                  <div className="space-y-3 flex-1">
                    {/* Long */}
                    <div>
                      <div className="flex items-center gap-1.5 mb-1.5">
                        <ArrowUpRight className="w-3.5 h-3.5 text-emerald-400" />
                        <span className="text-xs font-medium text-emerald-400">{t('position.longSuggestion')}</span>
                        <span className="text-[10px] text-gray-500 ml-auto">{report?.long?.length ?? 0}</span>
                      </div>
                      {report?.long?.length > 0 ? (
                        <div className="space-y-1">
                          {report.long.map((item: any) => (
                            <div key={item.symbol} className="flex items-center gap-2 px-2 py-1 rounded bg-emerald-500/5 border border-emerald-500/10">
                              <span className="text-xs font-bold text-white">{item.symbol}</span>
                              <span className={`text-[10px] px-1.5 py-0.5 rounded border ${
                                item.confidence === 'high' ? 'border-emerald-500/30 bg-emerald-500/10 text-emerald-400' :
                                item.confidence === 'medium' ? 'border-amber-500/30 bg-amber-500/10 text-amber-400' :
                                'border-red-500/30 bg-red-500/10 text-red-400'
                              }`}>
                                {item.confidence}
                              </span>
                            </div>
                          ))}
                        </div>
                      ) : (
                        <div className="text-[11px] text-gray-600 py-1">{t('position.noLongSignals')}</div>
                      )}
                    </div>
                    {/* Short */}
                    <div>
                      <div className="flex items-center gap-1.5 mb-1.5">
                        <ArrowDownRight className="w-3.5 h-3.5 text-red-400" />
                        <span className="text-xs font-medium text-red-400">{t('position.shortSuggestion')}</span>
                        <span className="text-[10px] text-gray-500 ml-auto">{report?.short?.length ?? 0}</span>
                      </div>
                      {report?.short?.length > 0 ? (
                        <div className="space-y-1">
                          {report.short.map((item: any) => (
                            <div key={item.symbol} className="flex items-center gap-2 px-2 py-1 rounded bg-red-500/5 border border-red-500/10">
                              <span className="text-xs font-bold text-white">{item.symbol}</span>
                              <span className={`text-[10px] px-1.5 py-0.5 rounded border ${
                                item.confidence === 'high' ? 'border-emerald-500/30 bg-emerald-500/10 text-emerald-400' :
                                item.confidence === 'medium' ? 'border-amber-500/30 bg-amber-500/10 text-amber-400' :
                                'border-red-500/30 bg-red-500/10 text-red-400'
                              }`}>
                                {item.confidence}
                              </span>
                            </div>
                          ))}
                        </div>
                      ) : (
                        <div className="text-[11px] text-gray-600 py-1">{t('position.noShortSignals')}</div>
                      )}
                    </div>
                    {/* Watch */}
                    {report?.watch && (
                      <div className="flex items-start gap-1.5 px-2 py-2 rounded bg-amber-500/5 border border-amber-500/10">
                        <Eye className="w-3.5 h-3.5 text-amber-400 mt-0.5 flex-shrink-0" />
                        <span className="text-[11px] text-amber-200/70">{report.watch}</span>
                      </div>
                    )}
                  </div>
                </div>
              );
            })}
          </div>
        </section>
      )}

      {/* 艾略特波浪简要 */}
      {elliottWave && (
        <section className="card p-5">
          <div className="flex items-center justify-between mb-4">
            <div className="flex items-center gap-2">
              <TrendingUp className="w-5 h-5 text-[#7ED7C4]" />
              <h3 className="text-lg font-semibold text-white">{t('elliottWave.title')}</h3>
            </div>
            <VerificationBadge status={verificationStatus} />
          </div>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
            <div className="bg-gray-800/50 rounded-lg p-3">
              <div className="text-xs text-gray-500">{t('elliottWave.pattern')}</div>
              <div className="text-sm font-semibold text-white">{(elliottWave as any).wave_pattern ?? '--'}</div>
            </div>
            <div className="bg-gray-800/50 rounded-lg p-3">
              <div className="text-xs text-gray-500">{t('elliottWave.direction')}</div>
              <div className={`text-sm font-semibold ${(elliottWave as any).direction === 'up' ? 'text-emerald-400' : 'text-red-400'}`}>
                {(elliottWave as any).direction === 'up' ? t('trade.long') : (elliottWave as any).direction === 'down' ? t('trade.short') : '--'}
              </div>
            </div>
            <div className="bg-gray-800/50 rounded-lg p-3">
              <div className="text-xs text-gray-500">{t('elliottWave.currentWave')}</div>
              <div className="text-sm font-semibold text-white">
                {typeof (elliottWave as any).current_wave === 'string'
                  ? (elliottWave as any).current_wave.replace(/_/g, ' ').replace(/\b\w/g, (l: string) => l.toUpperCase())
                  : (elliottWave as any).current_wave !== undefined
                    ? `Wave ${(elliottWave as any).current_wave}`
                    : '--'}
              </div>
            </div>
            <div className="bg-gray-800/50 rounded-lg p-3">
              <div className="text-xs text-gray-500">{t('elliottWave.score')}</div>
              <div className="text-sm font-semibold text-[#7ED7C4]">
                {typeof (elliottWave as any).score === 'number' ? `${((elliottWave as any).score * 100).toFixed(0)}%` : '--'}
              </div>
            </div>
          </div>
          {(elliottWave as any).chart_path && (
            <div className="mt-4 rounded-lg overflow-hidden border border-gray-800">
              <img
                src={`${import.meta.env.VITE_API_BASE || ''}${(elliottWave as any).chart_path}`}
                alt={`Elliott Wave ${(elliottWave as any).wave_pattern ?? ''}`}
                className="w-full"
                style={{ maxHeight: 200, objectFit: 'cover' }}
                onError={(e) => { (e.target as HTMLImageElement).style.display = 'none'; }}
              />
            </div>
          )}
        </section>
      )}

      {/* 区块 d: 全市场分析表格 (wallet or whitelist) */}
      {(!loginRequired) && (
      <section className="card p-5">
        <div className="flex items-center justify-between mb-4">
          <div className="flex items-center gap-2">
            <PieChart className="w-5 h-5 text-[#7ED7C4]" />
            <h2 className="text-lg font-semibold text-white">{t('dashboard.fullMarketAnalysis')}</h2>
          </div>
          <VerificationBadge status={verificationStatus} />
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
                {allTokens.map((token: any) => (
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
