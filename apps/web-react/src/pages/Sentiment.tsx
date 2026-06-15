import { useState, useEffect, useCallback, useMemo, useRef } from 'react';
import { useTranslation } from 'react-i18next';
import {
  TrendingUp, TrendingDown, Minus, Clock, Gauge, ChevronUp, ChevronDown,
  AlertTriangle, ShieldAlert, Activity, BarChart3, Bitcoin, Layers,
  Target, Eye, Zap, ArrowUpRight, ArrowDownRight, Timer,
  LineChart, Skull, Wallet, RefreshCw
} from 'lucide-react';
// Recharts available if needed: import { BarChart, Bar, XAxis, YAxis, ResponsiveContainer, Cell } from 'recharts';
import { getLatestSentiment, analyzeSentiment, getBacktestResult, getElliottWave } from '../services/api';
import { useApp } from '../context/AppContext';
import { useWallet } from '../hooks/useWallet';
import type { SentimentData as BaseSentimentData, TokenData, BacktestResult, BacktestSignal, ElliottWaveResult } from '../types';
import { translatePattern, translateConfidenceLabel, translateWatch, translateRiskWarning, translateReason } from '../utils/translateBackend';

/* ───────────────────────────────
   扩展类型（后端即将支持的新字段）
   ─────────────────────────────── */
interface PositionItem {
  symbol: string;
  reason: string;
  confidence: 'high' | 'medium' | 'low';
  confidence_label: string;
}

interface TimeframeReport {
  long: PositionItem[];
  short: PositionItem[];
  watch: string;
}

interface SignalData {
  symbol: string;
  timeframe: '1d' | '4h' | '1w';
  direction: 'long' | 'short';
  primary_pattern: string;
  secondary_patterns: string[];
  confidence: 'high' | 'medium' | 'low';
}

interface FNGData {
  value: number;
  classification: string;
  timestamp: string;
}

interface ExtendedSentimentData extends BaseSentimentData {
  market_bias?: 'bullish' | 'bearish' | 'neutral';
  bias_strength?: 'strong' | 'moderate' | 'weak';
  fng?: FNGData;
  market_breadth?: string;
  btc_change_24h?: number;
  position_report?: {
    '1d': TimeframeReport;
    '4h': TimeframeReport;
    '1w': TimeframeReport;
  };
  risk_warning?: string;
  signals?: SignalData[];
  symbol_scores?: TokenData[];
}

/* ───────────────────────────────
   工具函数
   ─────────────────────────────── */
function getSentimentColor(value: number): string {
  if (value >= 70) return '#10b981';
  if (value >= 40) return '#f59e0b';
  return '#ef4444';
}

function getSentimentLabel(value: number): string {
  if (value >= 70) return 'sentiment.bullish';
  if (value >= 40) return 'sentiment.neutral';
  return 'sentiment.bearish';
}

function getSentimentBg(value: number): string {
  if (value >= 70) return 'bg-emerald-500/10 text-emerald-400 border-emerald-500/20';
  if (value >= 40) return 'bg-amber-500/10 text-amber-400 border-amber-500/20';
  return 'bg-red-500/10 text-red-400 border-red-500/20';
}

function formatTimeAgo(dateStr?: string): string {
  if (!dateStr) return '--';
  const d = new Date(dateStr);
  const now = new Date();
  const diff = Math.floor((now.getTime() - d.getTime()) / 1000);
  if (diff < 60) return `${diff}s`;
  if (diff < 3600) return `${Math.floor(diff / 60)}m`;
  if (diff < 86400) return `${Math.floor(diff / 3600)}h`;
  return `${Math.floor(diff / 86400)}d`;
}

function getBiasLabel(bias?: string): string {
  if (bias === 'bullish') return 'sentiment.biasBullish';
  if (bias === 'bearish') return 'sentiment.biasBearish';
  return 'sentiment.neutral';
}

function getBiasColor(bias?: string): string {
  if (bias === 'bullish') return 'text-emerald-400';
  if (bias === 'bearish') return 'text-red-400';
  return 'text-amber-400';
}

function getBiasBg(bias?: string): string {
  if (bias === 'bullish') return 'bg-emerald-500/15 text-emerald-400 border-emerald-500/30';
  if (bias === 'bearish') return 'bg-red-500/15 text-red-400 border-red-500/30';
  return 'bg-amber-500/15 text-amber-400 border-amber-500/30';
}

function getStrengthLabel(strength?: string): string {
  if (strength === 'strong') return 'sentiment.strong';
  if (strength === 'moderate') return 'sentiment.moderate';
  return 'sentiment.weak';
}

function getConfidenceStyle(confidence?: string): string {
  if (confidence === 'high') return 'border-emerald-500/30 bg-emerald-500/10 text-emerald-400';
  if (confidence === 'medium') return 'border-amber-500/30 bg-amber-500/10 text-amber-400';
  return 'border-red-500/30 bg-red-500/10 text-red-400';
}

function getConfidenceLabel(confidence?: string): string {
  if (confidence === 'high') return 'sentiment.high';
  if (confidence === 'medium') return 'sentiment.medium';
  return 'sentiment.low';
}

function getFNGColor(value: number): string {
  if (value <= 20) return '#ef4444';
  if (value <= 40) return '#f97316';
  if (value <= 60) return '#f59e0b';
  if (value <= 80) return '#84cc16';
  return '#10b981';
}

function getFNGLabel(value: number): string {
  if (value <= 20) return 'fng.extremeFear';
  if (value <= 40) return 'fng.fear';
  if (value <= 60) return 'fng.neutral';
  if (value <= 80) return 'fng.greed';
  return 'fng.extremeGreed';
}

function parseMarketBreadth(breadth?: string): { up: number; down: number; flat: number } {
  if (!breadth) return { up: 0, down: 0, flat: 0 };
  const match = breadth.match(/(\d+)\s*up\s*\/\s*(\d+)\s*down\s*\/\s*(\d+)\s*flat/);
  if (match) {
    return { up: parseInt(match[1], 10), down: parseInt(match[2], 10), flat: parseInt(match[3], 10) };
  }
  return { up: 0, down: 0, flat: 0 };
}

/* ───────────────────────────────
   动画数字
   ─────────────────────────────── */
function AnimatedNumber({ value, duration = 1200, decimals = 1, prefix = '', suffix = '' }: {
  value: number;
  duration?: number;
  decimals?: number;
  prefix?: string;
  suffix?: string;
}) {
  const [display, setDisplay] = useState(0);
  const startRef = useRef<number | null>(null);
  const fromRef = useRef(0);
  const rafRef = useRef<number | null>(null);

  useEffect(() => {
    if (rafRef.current) cancelAnimationFrame(rafRef.current);
    fromRef.current = display;
    startRef.current = null;

    const animate = (timestamp: number) => {
      if (startRef.current === null) startRef.current = timestamp;
      const progress = Math.min((timestamp - startRef.current) / duration, 1);
      const easeOut = 1 - Math.pow(1 - progress, 3);
      const current = fromRef.current + (value - fromRef.current) * easeOut;
      setDisplay(current);
      if (progress < 1) {
        rafRef.current = requestAnimationFrame(animate);
      }
    };
    rafRef.current = requestAnimationFrame(animate);
    return () => { if (rafRef.current) cancelAnimationFrame(rafRef.current); };
  }, [value, duration]);

  return <>{prefix}{display.toFixed(decimals)}{suffix}</>;
}

/* ───────────────────────────────
   骨架屏
   ─────────────────────────────── */
function ShimmerBox({ className = '' }: { className?: string }) {
  return <div className={`shimmer rounded-lg ${className}`} />;
}

/* ───────────────────────────────
   情绪 Gauge（270° 弧形，带动画）
   ─────────────────────────────── */
function SentimentGauge({ value, size = 220 }: { value: number; size?: number }) {
  const { t } = useTranslation();
  const radius = (size - 40) / 2;
  const strokeWidth = 14;
  const center = size / 2;
  const circumference = 2 * Math.PI * radius;
  const arcLength = circumference * 0.75;
  const progress = Math.min(Math.max(value, 0), 100) / 100;
  const dashOffset = arcLength * (1 - progress);
  const color = getSentimentColor(value);

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
          <filter id="glow" x="-20%" y="-20%" width="140%" height="140%">
            <feGaussianBlur stdDeviation="3" result="blur" />
            <feComposite in="SourceGraphic" in2="blur" operator="over" />
          </filter>
        </defs>
        <circle
          cx={center} cy={center} r={radius}
          fill="none" stroke="#1f2937" strokeWidth={strokeWidth}
          strokeDasharray={`${arcLength} ${circumference}`}
          strokeLinecap="round"
          transform={`rotate(135 ${center} ${center})`}
        />
        <circle
          cx={center} cy={center} r={radius}
          fill="none" stroke="url(#gaugeGradient)" strokeWidth={strokeWidth}
          strokeDasharray={`${arcLength} ${circumference}`}
          strokeDashoffset={dashOffset}
          strokeLinecap="round"
          transform={`rotate(135 ${center} ${center})`}
          style={{ transition: 'stroke-dashoffset 1.2s cubic-bezier(0.4, 0, 0.2, 1)', filter: 'drop-shadow(0 0 4px rgba(126,215,196,0.3))' }}
        />
        <line
          x1={center} y1={center}
          x2={needleX} y2={needleY}
          stroke={color} strokeWidth={3} strokeLinecap="round"
          style={{ transition: 'all 1.2s cubic-bezier(0.4, 0, 0.2, 1)', filter: 'url(#glow)' }}
        />
        <circle cx={center} cy={center} r={5} fill={color} style={{ filter: 'url(#glow)' }} />
      </svg>
      <div className="absolute inset-0 flex flex-col items-center justify-center pt-10">
        <span className="text-4xl font-bold text-white" style={{ color }}>
          <AnimatedNumber value={value} decimals={1} />
        </span>
        <span className="text-xs text-gray-400 mt-1">{t('sentiment.marketSentiment')}</span>
      </div>
    </div>
  );
}

/* ───────────────────────────────
   FNG 恐惧贪婪 Gauge（圆形）
   ─────────────────────────────── */
function FNGGauge({ value, size = 160 }: { value: number; size?: number }) {
  const { t } = useTranslation();
  const radius = (size - 32) / 2;
  const strokeWidth = 10;
  const center = size / 2;
  const circumference = 2 * Math.PI * radius;
  const progress = Math.min(Math.max(value, 0), 100) / 100;
  const dashOffset = circumference * (1 - progress);
  const color = getFNGColor(value);

  return (
    <div className="relative flex items-center justify-center" style={{ width: size, height: size }}>
      <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`}>
        <defs>
          <linearGradient id="fngGradient" x1="0%" y1="0%" x2="100%" y2="100%">
            <stop offset="0%" stopColor="#ef4444" />
            <stop offset="25%" stopColor="#f97316" />
            <stop offset="50%" stopColor="#f59e0b" />
            <stop offset="75%" stopColor="#84cc16" />
            <stop offset="100%" stopColor="#10b981" />
          </linearGradient>
        </defs>
        <circle
          cx={center} cy={center} r={radius}
          fill="none" stroke="#1f2937" strokeWidth={strokeWidth}
        />
        <circle
          cx={center} cy={center} r={radius}
          fill="none" stroke="url(#fngGradient)" strokeWidth={strokeWidth}
          strokeDasharray={circumference}
          strokeDashoffset={dashOffset}
          strokeLinecap="round"
          transform={`rotate(-90 ${center} ${center})`}
          style={{ transition: 'stroke-dashoffset 1.2s cubic-bezier(0.4, 0, 0.2, 1)' }}
        />
      </svg>
      <div className="absolute inset-0 flex flex-col items-center justify-center">
        <span className="text-2xl font-bold" style={{ color }}>
          <AnimatedNumber value={value} decimals={0} />
        </span>
        <span className="text-[10px] text-gray-400 mt-0.5">{t('fng.fear')}&{t('fng.greed')}</span>
      </div>
    </div>
  );
}

/* ───────────────────────────────
   市场宽度迷你柱状图
   ─────────────────────────────── */
function MarketBreadthMini({ up, down, flat }: { up: number; down: number; flat: number }) {
  const { t } = useTranslation();
  const data = [
    { name: t('market.up'), value: up, fill: '#10b981' },
    { name: t('market.down'), value: down, fill: '#ef4444' },
    { name: t('market.flat'), value: flat, fill: '#f59e0b' },
  ];
  const max = Math.max(up + down + flat, 1);

  return (
    <div className="w-full">
      <div className="flex items-end justify-between gap-1 h-16">
        {data.map((d) => (
          <div key={d.name} className="flex flex-col items-center flex-1">
            <span className="text-xs font-semibold mb-1" style={{ color: d.fill }}>{d.value}</span>
            <div
              className="w-full rounded-t-md transition-all duration-700 ease-out"
              style={{
                height: `${(d.value / max) * 100}%`,
                minHeight: d.value > 0 ? 4 : 0,
                backgroundColor: d.fill,
                opacity: 0.7,
              }}
            />
          </div>
        ))}
      </div>
      <div className="flex justify-between mt-1">
        {data.map((d) => (
          <span key={d.name} className="text-[10px] text-gray-500 flex-1 text-center">{d.name}</span>
        ))}
      </div>
    </div>
  );
}

/* ───────────────────────────────
   计数卡片
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
    <div className={`flex items-center gap-3 px-4 py-3 rounded-xl border transition-all duration-300 hover:scale-[1.02] ${
      active
        ? `${colorClass} bg-opacity-10 border-opacity-30`
        : 'bg-gray-800/30 border-white/5 text-gray-400'
    }`}>
      <div className={`w-9 h-9 rounded-lg flex items-center justify-center ${colorClass} bg-opacity-20`}>
        <Icon className="w-4 h-4" />
      </div>
      <div>
        <div className={`text-xl font-bold ${active ? colorClass : 'text-gray-300'}`}>
          <AnimatedNumber value={count} decimals={0} />
        </div>
        <div className="text-xs text-gray-500">{label}</div>
      </div>
    </div>
  );
}

/* ───────────────────────────────
   风险警告横幅
   ─────────────────────────────── */
function RiskWarningBanner({ warning }: { warning?: string }) {
  const { t } = useTranslation();
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
          <p className="text-sm text-red-200/80 mt-0.5">{warning}</p>
        </div>
        <AlertTriangle className="w-5 h-5 text-red-400/50 flex-shrink-0" />
      </div>
    </div>
  );
}

/* ───────────────────────────────
   持仓建议卡片
   ─────────────────────────────── */
function PositionReportCard({
  title, subtitle, report, accentColor,
}: {
  title: string;
  subtitle: string;
  report?: TimeframeReport;
  accentColor: string;
}) {
  const { t } = useTranslation();
  return (
    <div className="card p-4 flex flex-col h-full" style={{ borderTop: `2px solid ${accentColor}` }}>
      <div className="flex items-center gap-2 mb-3 pb-3 border-b border-white/5">
        <Timer className="w-4 h-4" style={{ color: accentColor }} />
        <div>
          <h3 className="text-sm font-semibold text-white">{title}</h3>
          <p className="text-[10px] text-gray-500">{subtitle}</p>
        </div>
      </div>

      <div className="space-y-3 flex-1">
        {/* 做多 */}
        <div>
          <div className="flex items-center gap-1.5 mb-1.5">
            <ArrowUpRight className="w-3.5 h-3.5 text-emerald-400" />
            <span className="text-xs font-medium text-emerald-400">{t('position.longSuggestion')}</span>
            <span className="text-[10px] text-gray-500 ml-auto">{report?.long?.length ?? 0}</span>
          </div>
          {report && report.long.length > 0 ? (
            <div className="space-y-1.5">
              {report.long.map((item) => (
                <div key={item.symbol} className="flex items-center gap-2 px-2.5 py-1.5 rounded-lg bg-emerald-500/5 border border-emerald-500/10">
                  <span className="text-xs font-bold text-white min-w-[48px]">{item.symbol}</span>
                  <span className="text-[11px] text-gray-400 flex-1 truncate">{translateReason(item.reason)}</span>
                  <span className={`text-[10px] px-1.5 py-0.5 rounded border ${getConfidenceStyle(item.confidence)}`}>
                    {translateConfidenceLabel(item.confidence_label) || t(getConfidenceLabel(item.confidence))}
                  </span>
                </div>
              ))}
            </div>
          ) : (
            <div className="text-[11px] text-gray-600 py-1">{t('position.noLongSignals')}</div>
          )}
        </div>

        {/* 做空 */}
        <div>
          <div className="flex items-center gap-1.5 mb-1.5">
            <ArrowDownRight className="w-3.5 h-3.5 text-red-400" />
            <span className="text-xs font-medium text-red-400">{t('position.shortSuggestion')}</span>
            <span className="text-[10px] text-gray-500 ml-auto">{report?.short?.length ?? 0}</span>
          </div>
          {report && report.short.length > 0 ? (
            <div className="space-y-1.5">
              {report.short.map((item) => (
                <div key={item.symbol} className="flex items-center gap-2 px-2.5 py-1.5 rounded-lg bg-red-500/5 border border-red-500/10">
                  <span className="text-xs font-bold text-white min-w-[48px]">{item.symbol}</span>
                  <span className="text-[11px] text-gray-400 flex-1 truncate">{translateReason(item.reason)}</span>
                  <span className={`text-[10px] px-1.5 py-0.5 rounded border ${getConfidenceStyle(item.confidence)}`}>
                    {translateConfidenceLabel(item.confidence_label) || t(getConfidenceLabel(item.confidence))}
                  </span>
                </div>
              ))}
            </div>
          ) : (
            <div className="text-[11px] text-gray-600 py-1">{t('position.noShortSignals')}</div>
          )}
        </div>

        {/* 观望 */}
        {report?.watch && (
          <div className="flex items-start gap-1.5 px-2.5 py-2 rounded-lg bg-amber-500/5 border border-amber-500/10">
            <Eye className="w-3.5 h-3.5 text-amber-400 mt-0.5 flex-shrink-0" />
            <span className="text-[11px] text-amber-200/70">{translateWatch(report.watch)}</span>
          </div>
        )}
      </div>
    </div>
  );
}

/* ───────────────────────────────
   信号检测表格
   ─────────────────────────────── */
function SignalDetectionTable({ 
  signals, 
  backtest_results,
  loading 
}: { 
  signals?: SignalData[]; 
  backtest_results?: Record<string, any>;
  loading: boolean;
}) {
  const { t } = useTranslation();
  const getWinRate = (symbol: string, timeframe: string) => {
    const key = `${symbol.replace(/USDT$/, '')}_${timeframe}`;
    const bt = backtest_results?.[key];

    // 优先从 current_signal 的 similar_state_stats 读取
    const currentStats = bt?.current_signal?.similar_state_stats;
    if (currentStats && !currentStats.insufficient_data) {
      const winRate = currentStats.win_rate ?? 0;
      return {
        text: `${winRate.toFixed(1)}%`,
        colorClass: winRate >= 55 ? 'text-emerald-400' : winRate >= 45 ? 'text-amber-400' : 'text-red-400',
      };
    }

    // fallback：从 bt.stats 整体统计读取综合胜率
    const overallStats = bt?.stats;
    if (overallStats) {
      let totalWins = 0;
      let totalCount = 0;
      for (const [, patternStats] of Object.entries(overallStats)) {
        if (typeof patternStats === 'object' && patternStats && 'win_rate' in patternStats && 'total_signals' in patternStats) {
          const ps = patternStats as any;
          totalWins += (ps.win_rate ?? 0) * (ps.total_signals ?? 0);
          totalCount += ps.total_signals ?? 0;
        }
      }
      if (totalCount > 0) {
        const avgWinRate = totalWins / totalCount;
        return {
          text: `${avgWinRate.toFixed(1)}%`,
          colorClass: avgWinRate >= 55 ? 'text-emerald-400' : avgWinRate >= 45 ? 'text-amber-400' : 'text-red-400',
        };
      }
    }

    return { text: '样本不足', colorClass: 'text-gray-500' };
  };
  if (loading) {
    return (
      <div className="card p-5">
        <div className="space-y-2">
          <ShimmerBox className="h-10" />
          <ShimmerBox className="h-10" />
          <ShimmerBox className="h-10" />
          <ShimmerBox className="h-10" />
        </div>
      </div>
    );
  }

  if (!signals || signals.length === 0) {
    return (
      <div className="card p-5">
        <div className="flex items-center gap-2 mb-4">
          <Zap className="w-5 h-5 text-[#7ED7C4]" />
          <h2 className="text-lg font-semibold text-white">{t('sentiment.patternDetection')}</h2>
        </div>
        <div className="text-gray-500 text-sm py-8 text-center">{t('common.noData')}</div>
      </div>
    );
  }

  return (
    <div className="card p-5">
      <div className="flex items-center gap-2 mb-4">
        <Zap className="w-5 h-5 text-[#7ED7C4]" />
        <h2 className="text-lg font-semibold text-white">{t('sentiment.patternDetection')}</h2>
        <span className="ml-auto text-xs text-gray-500">{`${signals.length} ${t('backtest.signals')}`}</span>
      </div>
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-white/10 text-gray-400">
              <th className="text-left py-2.5 px-3 font-medium text-xs">{t('table.symbol')}</th>
              <th className="text-center py-2.5 px-3 font-medium text-xs">{t('table.timeframe')}</th>
              <th className="text-center py-2.5 px-3 font-medium text-xs">{t('table.direction')}</th>
              <th className="text-left py-2.5 px-3 font-medium text-xs">{t('table.primaryPattern')}</th>
              <th className="text-left py-2.5 px-3 font-medium text-xs">{t('table.secondaryPatterns')}</th>
              <th className="text-center py-2.5 px-3 font-medium text-xs">历史胜率</th>
              <th className="text-center py-2.5 px-3 font-medium text-xs">{t('table.confidence')}</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-white/5">
            {signals.map((s, i) => (
              <tr
                key={`${s.symbol}-${s.timeframe}-${i}`}
                className={`transition hover:bg-white/[0.03] ${s.direction === 'long' ? 'hover:bg-emerald-500/[0.02]' : s.direction === 'short' ? 'hover:bg-red-500/[0.02]' : ''}`}
              >
                <td className="py-2.5 px-3">
                  <span className="font-bold text-white">{s.symbol}</span>
                </td>
                <td className="py-2.5 px-3 text-center">
                  <span className="text-xs text-gray-400 px-2 py-0.5 rounded bg-gray-800">{s.timeframe}</span>
                </td>
                <td className="py-2.5 px-3 text-center">
                  <span className={`inline-flex items-center gap-1 text-xs font-medium px-2 py-0.5 rounded-full ${
                    s.direction === 'long'
                      ? 'bg-emerald-500/10 text-emerald-400'
                      : s.direction === 'short'
                        ? 'bg-red-500/10 text-red-400'
                        : 'bg-amber-500/10 text-amber-400'
                  }`}>
                    {s.direction === 'long' ? <TrendingUp className="w-3 h-3" /> : <TrendingDown className="w-3 h-3" />}
                    {s.direction === 'long' ? t('trade.long') : s.direction === 'short' ? t('trade.short') : t('trade.wait')}
                  </span>
                </td>
                <td className="py-2.5 px-3">
                  <span className="text-xs text-[#7ED7C4] bg-[#7ED7C4]/10 px-2 py-0.5 rounded border border-[#7ED7C4]/20">{translatePattern(s.primary_pattern)}</span>
                </td>
                <td className="py-2.5 px-3">
                  <div className="flex flex-wrap gap-1">
                    {s.secondary_patterns.map((p, j) => (
                      <span key={j} className="text-[10px] text-gray-400 bg-gray-800/60 px-1.5 py-0.5 rounded">{translatePattern(p)}</span>
                    ))}
                  </div>
                </td>
                <td className="py-2.5 px-3 text-center">
                  {(() => {
                    const wr = getWinRate(s.symbol, s.timeframe);
                    return <span className={`text-xs font-medium ${wr.colorClass}`}>{wr.text}</span>;
                  })()}
                </td>
                <td className="py-2.5 px-3 text-center">
                  <span className={`text-xs px-2 py-0.5 rounded border ${getConfidenceStyle(s.confidence)}`}>
                    {t(getConfidenceLabel(s.confidence))}
                  </span>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

/* ───────────────────────────────
   主组件
   ─────────────────────────────── */
export default function Sentiment() {
  const { t } = useTranslation();
  const [timeframe, setTimeframe] = useState<'1h' | '4h' | '1d'>('1h');
  const [sentiment, setSentiment] = useState<ExtendedSentimentData | null>(null);
  const [loading, setLoading] = useState(true);
  const app = useApp();
  const { connected, address, connect, connectors } = useWallet();
  const [loginRequired, setLoginRequired] = useState(false);
  const [walletRestoring, setWalletRestoring] = useState(false);
  const isConnected = connected && !!address;

  // 检测钱包恢复状态
  useEffect(() => {
    if (connected && !address) {
      setWalletRestoring(true);
    } else {
      setWalletRestoring(false);
    }
  }, [connected, address]);

  /* ── Elliott Wave state ── */
  const [ewData, setEwData] = useState<ElliottWaveResult | null>(null);
  const [ewLoading, setEwLoading] = useState(false);
  const [ewSymbol, setEwSymbol] = useState('BTC');
  const [ewTimeframe, setEwTimeframe] = useState('1d');

  const getBacktestDisplayInfo = (key: string, bt: any) => {
    const [sym, tf] = key.split('_');
    const currentSignal = bt.current_signal;

    const longItem = sentiment?.position_report?.[tf as '1d' | '4h' | '1w']?.long.find((x: PositionItem) => x.symbol === sym);
    const shortItem = sentiment?.position_report?.[tf as '1d' | '4h' | '1w']?.short.find((x: PositionItem) => x.symbol === sym);
    const fallbackDirection: 'long' | 'short' | undefined = longItem ? 'long' : shortItem ? 'short' : undefined;
    const fallbackItem = longItem || shortItem;

    const direction = currentSignal?.direction || fallbackDirection;
    const recommendation = currentSignal?.recommendation || (fallbackItem && fallbackDirection ? {
      action: fallbackDirection,
      confidence: fallbackItem.confidence,
      score: 50,
      reason: fallbackItem.reason,
    } : { action: 'watch', confidence: 'low' as const, score: 50, reason: '暂无信号推荐，建议观望' });

    return { direction, recommendation, currentSignal };
  };

  const getImageUrl = (path: string | undefined): string => {
    if (!path) return '';
    if (path.startsWith('http')) return path;
    const baseUrl = import.meta.env.VITE_API_BASE || '';
    return `${baseUrl}${path}`;
  };

  // 自动加载艾略特波浪缓存
  useEffect(() => {
    const loadCache = async () => {
      setEwLoading(true);
      try {
        const result = await getElliottWave(ewSymbol, ewTimeframe);
        setEwData(result);
      } catch (e) {
        console.error('Failed to load Elliott Wave cache:', e);
        setEwData(null);
      } finally {
        setEwLoading(false);
      }
    };
    loadCache();
  }, [ewSymbol, ewTimeframe]);

  /* ── Backtest state ── */
  const [activeTab, setActiveTab] = useState<'sentiment' | 'backtest'>('sentiment');
  const [backtestTf] = useState<'1h' | '4h' | '1d'>('1d');
  const [backtestSymbol, setBacktestSymbol] = useState<string>('BTCUSDT');
  const [backtestResult, setBacktestResult] = useState<BacktestResult | null>(null);
  const [backtestLoading, setBacktestLoading] = useState(false);

  // Sync initial sentiment from AppContext
  useEffect(() => {
    if (app.sentiment) {
      setSentiment(app.sentiment as ExtendedSentimentData);
      setLoginRequired(!!app.sentiment.login_required);
    }
    setLoading(app.loading);
  }, [app.sentiment, app.loading]);

  // Fetch wallet-specific sentiment when address changes
  useEffect(() => {
    if (!address) return;
    const fetchWalletData = async () => {
      setLoading(true);
      try {
        const data = await getLatestSentiment(address);
        setSentiment(data as ExtendedSentimentData);
        setLoginRequired(!!data.login_required);
      } catch (e) {
        console.error('Wallet sentiment fetch error:', e);
      } finally {
        setLoading(false);
      }
    };
    fetchWalletData();
  }, [address]);

  const refreshData = useCallback(async () => {
    setLoading(true);
    try {
      const data = await analyzeSentiment(timeframe, address || undefined);
      setSentiment(data as ExtendedSentimentData);
      setLoginRequired(!!data.login_required);
    } catch (e) {
      console.error('Sentiment refresh error:', e);
    } finally {
      setLoading(false);
    }
  }, [timeframe, address]);

  /* ── Backtest loaders ── */
  const loadBacktest = useCallback(async () => {
    setBacktestLoading(true);
    try {
      const data = await getBacktestResult(backtestSymbol, backtestTf);
      setBacktestResult(data);
    } catch (e) {
      console.error('Backtest load error:', e);
      setBacktestResult(null);
    } finally {
      setBacktestLoading(false);
    }
  }, [backtestSymbol, backtestTf]);

  const allTokens = useMemo(() => {
    const tokens: TokenData[] = [];
    if (sentiment?.symbol_scores && sentiment.symbol_scores.length > 0) {
      tokens.push(...sentiment.symbol_scores);
    } else {
      if (sentiment?.top_bullish) tokens.push(...sentiment.top_bullish);
      if (sentiment?.top_bearish) tokens.push(...sentiment.top_bearish);
    }
    const seen = new Set<string>();
    return tokens.filter(t => {
      if (seen.has(t.symbol)) return false;
      seen.add(t.symbol);
      return true;
    });
  }, [sentiment]);

  const {
    sentiment_index, bullish_count, neutral_count, bearish_count,
    timestamp, data_freshness, market_bias, bias_strength, fng,
    market_breadth, btc_change_24h, position_report, risk_warning, signals,
  } = sentiment || {};

  const label = sentiment_index !== undefined ? t(getSentimentLabel(sentiment_index)) : '--';
  const breadth = parseMarketBreadth(market_breadth);

  return (
    <div className="space-y-6 p-4 md:p-6 max-w-7xl mx-auto">
      {/* Header */}
      <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-[#2D6B5E] to-[#4A9B8C] flex items-center justify-center shadow-lg shadow-[#2D6B5E]/20">
            <Gauge className="w-5 h-5 text-white" />
          </div>
          <div>
            <h1 className="text-xl font-bold text-white tracking-tight">{t('sentiment.pageTitle')}</h1>
            <p className="text-xs text-gray-500">{t('sentiment.pageSubtitle')}</p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <div className="flex gap-1 bg-gray-800/50 p-1 rounded-xl border border-white/5">
            {(['1h', '4h', '1d'] as const).map(tf => (
              <button
                key={tf}
                onClick={() => setTimeframe(tf)}
                className={`px-4 py-2 rounded-lg text-sm font-medium transition-all duration-200 ${
                  timeframe === tf
                    ? 'mantle-gradient text-white shadow-lg shadow-[#2D6B5E]/20'
                    : 'text-gray-400 hover:text-gray-200 hover:bg-white/5'
                }`}
              >
                {tf === '1h' ? t('timeframe.1h') : tf === '4h' ? t('timeframe.4h') : t('timeframe.1d')}
              </button>
            ))}
          </div>
          <button
            onClick={refreshData}
            disabled={loading || walletRestoring}
            className="p-2 rounded-lg bg-gray-800/50 border border-white/5 text-gray-400 hover:text-white hover:bg-white/5 transition disabled:opacity-50"
            title={t('common.forceRefresh')}
          >
            <RefreshCw className={`w-4 h-4 ${loading || walletRestoring ? 'animate-spin' : ''}`} />
          </button>
        </div>
      </div>

      {/* Tab switcher */}
      <div className="flex gap-1 bg-gray-800/50 p-1 rounded-xl border border-white/5 w-fit">
        {([
          { key: 'sentiment', label: t('tab.sentiment') },
          { key: 'backtest', label: t('tab.backtest') },
        ] as const).map(t => (
          <button
            key={t.key}
            onClick={() => setActiveTab(t.key)}
            className={`px-5 py-2 rounded-lg text-sm font-medium transition-all duration-200 ${
              activeTab === t.key
                ? 'bg-[#2D6B5E] text-white shadow-lg shadow-[#2D6B5E]/20'
                : 'text-gray-400 hover:text-gray-200 hover:bg-white/5'
            }`}
          >
            {t.label}
          </button>
        ))}
      </div>

      {/* 风险警告横幅 */}
      {activeTab === 'sentiment' && (!loginRequired || isConnected) && risk_warning && <RiskWarningBanner warning={translateRiskWarning(risk_warning)} />}

      {activeTab === 'sentiment' && (
      <div className="space-y-6">
      {/* Hero Dashboard */}
      <div className="card p-5 md:p-6">
        {(loading || walletRestoring) || !sentiment ? (
          <div className="space-y-6">
            <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
              <ShimmerBox className="w-full h-[220px] rounded-2xl" />
              <ShimmerBox className="w-full h-[220px] rounded-2xl" />
              <ShimmerBox className="w-full h-[220px] rounded-2xl" />
            </div>
            <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
              <ShimmerBox className="h-16" />
              <ShimmerBox className="h-16" />
              <ShimmerBox className="h-16" />
              <ShimmerBox className="h-16" />
            </div>
          </div>
        ) : (
          <div className="space-y-6">
            {/* 顶部仪表盘：Gauge + 关键指标 */}
            <div className={`grid grid-cols-1 gap-6 ${(!loginRequired || isConnected) ? 'lg:grid-cols-3' : 'lg:grid-cols-1 max-w-md mx-auto'}`}>
              {/* 情绪指数 Gauge */}
              <div className="flex flex-col items-center justify-center bg-gray-900/40 rounded-2xl p-4 border border-white/5">
                <div className="text-xs text-gray-500 mb-2 flex items-center gap-1.5">
                  <Activity className="w-3.5 h-3.5 text-[#7ED7C4]" />
                  {t('sentiment.sentimentIndex')}
                </div>
                <SentimentGauge value={sentiment_index ?? 50} />
                <div className={`mt-2 inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-sm font-medium border ${getSentimentBg(sentiment_index ?? 50)}`}>
                  {(sentiment_index ?? 0) >= 70 ? <ChevronUp className="w-3.5 h-3.5" /> :
                   (sentiment_index ?? 0) < 40 ? <ChevronDown className="w-3.5 h-3.5" /> :
                   <Minus className="w-3.5 h-3.5" />}
                  {label}
                </div>
              </div>

              {/* FNG + 市场偏向 (wallet or whitelist) */}
              {(!loginRequired || isConnected) ? (
                <div className="flex flex-col items-center justify-center bg-gray-900/40 rounded-2xl p-4 border border-white/5 space-y-4">
                  <div className="text-xs text-gray-500 mb-1 flex items-center gap-1.5">
                    <Skull className="w-3.5 h-3.5 text-orange-400" />
                    {t('sentiment.fearGreedIndex')}
                  </div>
                  {fng ? (
                    <>
                      <FNGGauge value={fng.value} />
                      <div className="text-center">
                        <div className="text-lg font-bold" style={{ color: getFNGColor(fng.value) }}>
                          {t(getFNGLabel(fng.value))}
                        </div>
                        <div className="text-[10px] text-gray-500">{formatTimeAgo(fng.timestamp)}</div>
                      </div>
                    </>
                  ) : (
                    <div className="flex flex-col items-center justify-center h-32 text-gray-600">
                      <LineChart className="w-8 h-8 mb-2 opacity-30" />
                      <span className="text-xs">{t('sentiment.noFngData')}</span>
                    </div>
                  )}

                  {/* 市场偏向 */}
                  {market_bias && (
                    <div className={`flex items-center gap-2 px-3 py-1.5 rounded-lg border ${getBiasBg(market_bias)}`}>
                      <Target className="w-3.5 h-3.5" />
                      <span className="text-sm font-medium">
                        {t('sentiment.marketBias')}：<span className={getBiasColor(market_bias)}>{t(getBiasLabel(market_bias))}</span>
                        {bias_strength && (
                          <span className="text-gray-400 ml-1">({t(getStrengthLabel(bias_strength))})</span>
                        )}
                      </span>
                    </div>
                  )}
                </div>
              ) : loginRequired && !isConnected && !loading && (
                <div className="flex flex-col items-center justify-center bg-gray-900/40 rounded-2xl p-4 border border-white/5 space-y-4">
                  <ShimmerBox className="h-4 w-24" />
                  <ShimmerBox className="h-16 w-16 rounded-full" />
                  <ShimmerBox className="h-3 w-20" />
                </div>
              )}

              {/* 市场宽度 + BTC (wallet or whitelist) */}
              {(!loginRequired || isConnected) ? (
                <div className="flex flex-col justify-between bg-gray-900/40 rounded-2xl p-4 border border-white/5 space-y-4">
                  <div>
                    <div className="text-xs text-gray-500 mb-3 flex items-center gap-1.5">
                      <BarChart3 className="w-3.5 h-3.5 text-[#7ED7C4]" />
                      {t('sentiment.marketBreadth')}
                      {market_breadth && <span className="text-gray-600">({market_breadth})</span>}
                    </div>
                    <MarketBreadthMini up={breadth.up} down={breadth.down} flat={breadth.flat} />
                  </div>

                  <div className="grid grid-cols-2 gap-3">
                    <div className="bg-gray-800/50 rounded-xl p-3 border border-white/5">
                      <div className="flex items-center gap-1.5 mb-1">
                        <Bitcoin className="w-3.5 h-3.5 text-orange-400" />
                        <span className="text-[10px] text-gray-500">BTC 24h</span>
                      </div>
                      {btc_change_24h !== undefined ? (
                        <div className={`text-lg font-bold ${btc_change_24h >= 0 ? 'text-emerald-400' : 'text-red-400'}`}>
                          {btc_change_24h > 0 ? '+' : ''}{(btc_change_24h ?? 0).toFixed(2)}%
                        </div>
                      ) : (
                        <div className="text-lg font-bold text-gray-600">--</div>
                      )}
                    </div>
                    <div className="bg-gray-800/50 rounded-xl p-3 border border-white/5">
                      <div className="flex items-center gap-1.5 mb-1">
                        <Clock className="w-3.5 h-3.5 text-gray-500" />
                        <span className="text-[10px] text-gray-500">{t('common.updatedAt')}</span>
                      </div>
                      <div className="text-sm font-medium text-gray-300">
                        {formatTimeAgo(timestamp || data_freshness)}
                      </div>
                    </div>
                  </div>
                </div>
              ) : loginRequired && !isConnected && !loading && (
                <div className="flex flex-col justify-between bg-gray-900/40 rounded-2xl p-4 border border-white/5 space-y-4">
                  <ShimmerBox className="h-4 w-32" />
                  <ShimmerBox className="h-20 w-full" />
                  <div className="grid grid-cols-2 gap-3">
                    <ShimmerBox className="h-16" />
                    <ShimmerBox className="h-16" />
                  </div>
                </div>
              )}
            </div>

            {/* 计数卡片 */}
            <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
              <CountCard
                label={t('sentiment.bullishTokens')}
                count={bullish_count ?? 0}
                icon={TrendingUp}
                colorClass="text-emerald-400"
                active={(sentiment_index ?? 0) >= 70}
              />
              <CountCard
                label={t('sentiment.neutralTokens')}
                count={neutral_count ?? 0}
                icon={Minus}
                colorClass="text-amber-400"
                active={(sentiment_index ?? 0) >= 40 && (sentiment_index ?? 0) < 70}
              />
              <CountCard
                label={t('sentiment.bearishTokens')}
                count={bearish_count ?? 0}
                icon={TrendingDown}
                colorClass="text-red-400"
                active={(sentiment_index ?? 0) < 40}
              />
              <CountCard
                label={t('sentiment.totalAnalyzed')}
                count={sentiment?.total_analyzed ?? (bullish_count ?? 0) + (neutral_count ?? 0) + (bearish_count ?? 0)}
                icon={Layers}
                colorClass="text-[#7ED7C4]"
                active={false}
              />
            </div>

            {/* 连接钱包提示 - 仅当服务端要求登录时显示 */}
            {loginRequired && !isConnected && !loading && (
              <div
                className="relative overflow-hidden rounded-xl border border-blue-500/20 bg-gradient-to-r from-blue-950/60 via-blue-900/30 to-blue-950/60 px-5 py-4 cursor-pointer transition hover:scale-[1.01]"
                onClick={() => connect(connectors[0])}
              >
                <div className="absolute inset-0 animate-pulse bg-blue-500/5" />
                <div className="relative flex items-center gap-3">
                  <div className="flex-shrink-0">
                    <Wallet className="w-5 h-5 text-blue-400" />
                  </div>
                  <div className="flex-1">
                    <div className="flex items-center gap-2">
                      <span className="text-sm font-semibold text-blue-300">{t('wallet.connectToViewFull')}</span>
                      <span className="text-xs text-blue-400/70 px-1.5 py-0.5 rounded bg-blue-500/10 border border-blue-500/20">{t('wallet.unlockFeatures')}</span>
                    </div>
                    <p className="text-sm text-blue-200/80 mt-0.5">{t('wallet.connectBenefits')}</p>
                  </div>
                </div>
              </div>
            )}
          </div>
        )}
      </div>

      {/* 持仓建议 (wallet or whitelist) */}
      {(!loginRequired || isConnected) && (position_report || !loading) ? (
        <div className="space-y-4">
          <div className="flex items-center gap-2">
            <Target className="w-5 h-5 text-[#7ED7C4]" />
            <h2 className="text-lg font-semibold text-white">{t('position.reportTitle')}</h2>
          </div>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            <PositionReportCard
              title={t('position.daily')}
              subtitle={t('position.dailyDesc')}
              report={position_report?.['1d']}
              accentColor="#7ED7C4"
            />
            <PositionReportCard
              title={t('position.fourHour')}
              subtitle={t('position.fourHourDesc')}
              report={position_report?.['4h']}
              accentColor="#4A9B8C"
            />
            <PositionReportCard
              title={t('position.weekly')}
              subtitle={t('position.weeklyDesc')}
              report={position_report?.['1w']}
              accentColor="#2D6B5E"
            />
          </div>
        </div>
      ) : loginRequired && !isConnected && !loading && (
        <div className="space-y-4">
          <ShimmerBox className="h-6 w-48" />
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            <ShimmerBox className="h-32" />
            <ShimmerBox className="h-32" />
            <ShimmerBox className="h-32" />
          </div>
        </div>
      )}

      {/* 艾略特波浪分析 */}
      {(!loginRequired || isConnected) ? (
      <div className="card p-5 mt-4">
        <div className="flex items-center justify-between mb-4">
          <div className="flex items-center gap-2">
            <TrendingUp className="w-5 h-5 text-[#7ED7C4]" />
            <h3 className="text-lg font-semibold text-white">艾略特波浪分析</h3>
          </div>
        </div>

        {/* 控制栏 */}
        <div className="flex flex-wrap items-center gap-3 mb-4">
          <select
            value={ewSymbol}
            onChange={(e) => setEwSymbol(e.target.value)}
            className="bg-gray-800 border border-gray-700 rounded-lg px-3 py-1.5 text-sm text-white"
          >
            <option value="BTC">BTC</option>
            <option value="ETH">ETH</option>
            <option value="SOL">SOL</option>
            <option value="BNB">BNB</option>
            <option value="XRP">XRP</option>
            <option value="DOGE">DOGE</option>
          </select>
          <select
            value={ewTimeframe}
            onChange={(e) => setEwTimeframe(e.target.value)}
            className="bg-gray-800 border border-gray-700 rounded-lg px-3 py-1.5 text-sm text-white"
          >
            <option value="1h">1小时</option>
            <option value="4h">4小时</option>
            <option value="1d">日线</option>
            <option value="1w">周线</option>
          </select>
          {/* 缓存状态 */}
          {ewData?.computed_at && (
            <span className="ml-auto text-xs text-gray-500">
              上次计算: {formatTimeAgo(ewData.computed_at)}
              {ewData.is_cached && <span className="ml-1 px-1.5 py-0.5 bg-gray-700/50 rounded text-[10px]">缓存</span>}
            </span>
          )}
        </div>

        {/* 结果展示 */}
        {ewLoading ? (
          <div className="space-y-3">
            <ShimmerBox className="h-48" />
            <ShimmerBox className="h-32" />
          </div>
        ) : ewData ? (
          <div className="space-y-4">
            {/* 缓存状态条 */}
            <div className="flex items-center justify-between mb-3">
              <div className="flex items-center gap-2">
                <span className="text-xs text-gray-400">
                  基于 {ewData.klines_count} 根K线计算
                </span>
                {ewData.is_cached && (
                  <span className="px-1.5 py-0.5 bg-emerald-500/10 text-emerald-400 text-[10px] rounded border border-emerald-500/20">
                    缓存数据
                  </span>
                )}
              </div>
              {ewData.computed_at && (
                <span className="text-xs text-gray-500">
                  {new Date(ewData.computed_at).toLocaleString()}
                </span>
              )}
            </div>
            {ewData.candidates.length === 0 ? (
              <div className="text-sm text-gray-500 text-center py-8">
                {ewData.message || '未在当前数据中发现艾略特波浪结构'}
              </div>
            ) : (
              ewData.candidates.slice(0, 1).map((candidate, idx) => (
                <div key={idx} className="space-y-3">
                  {/* 统一艾略特波浪图表（主图+信息面板） */}
                  {candidate.chart_path && (
                    <div className="rounded-lg overflow-hidden border border-gray-800">
                      <img
                        src={getImageUrl(candidate.chart_path)}
                        alt={`Elliott Wave ${candidate.wave_pattern}`}
                        className="w-full"
                        style={{ aspectRatio: '16/9', objectFit: 'cover' }}
                        onError={(e) => { (e.target as HTMLImageElement).style.display = 'none'; }}
                      />
                    </div>
                  )}

                  {/* 波浪信息 */}
                  <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
                    <div className="bg-gray-800/50 rounded-lg p-3">
                      <div className="text-xs text-gray-500">浪型</div>
                      <div className="text-sm font-semibold text-white">{candidate.wave_pattern}</div>
                      {candidate.kimi_analysis?.confirmed_wave && (
                        <div className="text-[10px] text-[#7ED7C4] mt-0.5 truncate" title={candidate.kimi_analysis.confirmed_wave}>
                          Kimi: {candidate.kimi_analysis.confirmed_wave}
                        </div>
                      )}
                    </div>
                    <div className="bg-gray-800/50 rounded-lg p-3">
                      <div className="text-xs text-gray-500">方向</div>
                      <div className={`text-sm font-semibold ${candidate.direction === 'up' ? 'text-emerald-400' : 'text-red-400'}`}>
                        {candidate.direction === 'up' ? '上涨' : '下跌'}
                      </div>
                    </div>
                    <div className="bg-gray-800/50 rounded-lg p-3">
                      <div className="text-xs text-gray-500">当前浪</div>
                      <div className="text-sm font-semibold text-white">
                        {typeof candidate.current_wave === 'string'
                          ? candidate.current_wave.replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase())
                          : `Wave ${candidate.current_wave}`}
                      </div>
                    </div>
                    <div className="bg-gray-800/50 rounded-lg p-3">
                      <div className="text-xs text-gray-500">置信度</div>
                      <div className="text-sm font-semibold text-[#7ED7C4]">{(candidate.score * 100).toFixed(0)}%</div>
                      {candidate.kimi_analysis && candidate.kimi_analysis.overall_confidence > 0 && (
                        <div className="text-[10px] text-gray-400 mt-0.5">
                          Kimi: {(candidate.kimi_analysis.overall_confidence * 100).toFixed(0)}%
                        </div>
                      )}
                    </div>
                  </div>

                  {/* Kimi AI 分析 */}
                  {candidate.kimi_analysis && (
                    <div className="bg-gradient-to-r from-[#2D6B5E]/10 to-transparent rounded-lg p-3 border border-[#2D6B5E]/20 space-y-2">
                      <div className="flex items-center gap-2">
                        <Zap className="w-3.5 h-3.5 text-[#7ED7C4]" />
                        <span className="text-xs font-medium text-[#7ED7C4]">Kimi AI 分析</span>
                        {candidate.kimi_annotated && (
                          <span className="text-[10px] px-1.5 py-0.5 rounded bg-[#7ED7C4]/10 text-[#7ED7C4] border border-[#7ED7C4]/20">AI标注</span>
                        )}
                      </div>

                      {candidate.kimi_analysis.corrections && candidate.kimi_analysis.corrections.length > 0 && (
                        <div className="space-y-1">
                          <div className="text-xs text-gray-500">修正建议:</div>
                          <ul className="space-y-1">
                            {candidate.kimi_analysis.corrections.map((corr, ci) => (
                              <li key={ci} className="text-xs text-amber-300/80 flex items-start gap-1.5">
                                <span className="mt-1 w-1 h-1 rounded-full bg-amber-400 flex-shrink-0" />
                                {corr}
                              </li>
                            ))}
                          </ul>
                        </div>
                      )}

                      {candidate.kimi_analysis.raw_analysis && (
                        <details className="group">
                          <summary className="flex items-center gap-1 cursor-pointer list-none text-xs text-gray-400 hover:text-gray-300 w-fit">
                            <ChevronDown className="w-3 h-3 transition-transform group-open:rotate-180" />
                            查看完整分析
                          </summary>
                          <div className="mt-2 text-xs text-gray-400 whitespace-pre-wrap max-h-48 overflow-y-auto bg-gray-900/50 rounded p-2">
                            {candidate.kimi_analysis.raw_analysis}
                          </div>
                        </details>
                      )}
                    </div>
                  )}

                  {/* 当前浪概率 — 优先使用 Kimi 结果 */}
                  {(() => {
                    const kimiProbs = candidate.kimi_analysis?.current_wave_probabilities;
                    const algoProbs = candidate.current_wave_probabilities;
                    const probs = (kimiProbs && Object.keys(kimiProbs).length > 0) ? kimiProbs : algoProbs;
                    const probSource = (kimiProbs && Object.keys(kimiProbs).length > 0) ? 'AI研判' : '算法推算';

                    return probs && Object.keys(probs).length > 0 ? (
                      <div className="bg-gray-800/30 rounded-lg p-3">
                        <div className="flex items-center justify-between mb-2">
                          <span className="text-xs text-gray-500">当前浪概率</span>
                          <span className="text-[10px] px-1.5 py-0.5 rounded bg-gray-700/50 text-gray-400">
                            {probSource}
                          </span>
                        </div>
                        <div className="space-y-1.5">
                          {Object.entries(probs)
                            .sort(([,a], [,b]) => (b as number) - (a as number))
                            .slice(0, 3)
                            .map(([wave, prob]) => (
                              <div key={wave} className="flex items-center gap-2">
                                <div className="flex-1 h-2 bg-gray-700 rounded-full overflow-hidden">
                                  <div
                                    className="h-full bg-[#7ED7C4] rounded-full transition-all"
                                    style={{ width: `${(prob as number) * 100}%` }}
                                  />
                                </div>
                                <span className="text-xs text-gray-400 w-20">{wave.replace(/_/g, ' ')}</span>
                                <span className="text-xs font-medium text-white w-10 text-right">{((prob as number) * 100).toFixed(0)}%</span>
                              </div>
                            ))}
                        </div>
                        {candidate.current_wave_status === 'forming' && (
                          <div className="text-xs text-amber-400 mt-2">⚡ 正在形成中</div>
                        )}
                      </div>
                    ) : null;
                  })()}

                  {/* 斐波那契比例 */}
                  {candidate.fib_ratios && Object.keys(candidate.fib_ratios).length > 0 && (
                    <div className="bg-gray-800/30 rounded-lg p-3">
                      <div className="text-xs text-gray-500 mb-2">斐波那契比例</div>
                      <div className="flex flex-wrap gap-2">
                        {Object.entries(candidate.fib_ratios).map(([key, val]) => (
                          <span key={key} className="px-2 py-0.5 bg-gray-700/50 rounded text-xs text-gray-300">
                            {key}: {(val as number).toFixed(3)}
                          </span>
                        ))}
                      </div>
                    </div>
                  )}

                  {/* 走势预测卡片 */}
                  {candidate.projections && candidate.projections.length > 0 && (
                    <div className="bg-gray-800/30 rounded-lg p-3 space-y-2">
                      <div className="text-xs text-gray-500">走势预测</div>

                      {/* 概率堆叠进度条 */}
                      {(() => {
                        const bullishConf = candidate.projections!.find(p => p.scenario === 'bullish')?.confidence ?? 0;
                        const bearishConf = candidate.projections!.find(p => p.scenario === 'bearish')?.confidence ?? 0;
                        const neutralConf = candidate.projections!.find(p => p.scenario === 'neutral')?.confidence ?? 0;
                        const total = bullishConf + bearishConf + neutralConf;
                        const bullishPct = total > 0 ? (bullishConf / total) * 100 : 0;
                        const bearishPct = total > 0 ? (bearishConf / total) * 100 : 0;
                        const neutralPct = total > 0 ? (neutralConf / total) * 100 : 0;
                        return (
                          <>
                            <div className="flex h-2 rounded-full overflow-hidden mt-2">
                              {bullishPct > 0 && (
                                <div
                                  className="bg-emerald-500 h-full"
                                  style={{ width: `${bullishPct}%` }}
                                  title={`Bullish: ${bullishPct.toFixed(1)}%`}
                                />
                              )}
                              {neutralPct > 0 && (
                                <div
                                  className="bg-gray-500 h-full"
                                  style={{ width: `${neutralPct}%` }}
                                  title={`Neutral: ${neutralPct.toFixed(1)}%`}
                                />
                              )}
                              {bearishPct > 0 && (
                                <div
                                  className="bg-red-500 h-full"
                                  style={{ width: `${bearishPct}%` }}
                                  title={`Bearish: ${bearishPct.toFixed(1)}%`}
                                />
                              )}
                            </div>
                            <div className="flex justify-between text-[10px] text-gray-500 mt-1">
                              <span className={bullishConf > 0 ? 'text-emerald-400' : ''}>
                                {bullishConf > 0 ? `Bullish ${bullishPct.toFixed(1)}%` : ''}
                              </span>
                              <span className={neutralConf > 0 ? 'text-gray-400' : ''}>
                                {neutralConf > 0 ? `Neutral ${neutralPct.toFixed(1)}%` : ''}
                              </span>
                              <span className={bearishConf > 0 ? 'text-red-400' : ''}>
                                {bearishConf > 0 ? `Bearish ${bearishPct.toFixed(1)}%` : ''}
                              </span>
                            </div>
                          </>
                        );
                      })()}

                      <div className="grid grid-cols-1 md:grid-cols-3 gap-2 mt-2">
                        {candidate.projections.map((proj, pidx) => (
                          <div
                            key={pidx}
                            className={`p-2 rounded-lg border ${
                              proj.scenario === 'bullish'
                                ? 'border-emerald-500/30 bg-emerald-500/5'
                                : proj.scenario === 'bearish'
                                ? 'border-red-500/30 bg-red-500/5'
                                : 'border-gray-700 bg-gray-800/50'
                            }`}
                          >
                            <div className="text-xs font-medium text-gray-400">
                              {proj.scenario === 'bullish' ? '牛市' : proj.scenario === 'bearish' ? '熊市' : '中性'}
                            </div>
                            <div className="text-sm text-white mt-0.5">{proj.description}</div>
                            <div className="text-sm font-semibold text-[#7ED7C4]">
                              ${proj.target_price?.toLocaleString?.() || proj.target_price}
                            </div>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}
                </div>
              ))
            )}
          </div>
        ) : (
          <div className="text-sm text-gray-500 text-center py-8">
            暂无缓存数据
          </div>
        )}
      </div>
      ) : loginRequired && !isConnected && !loading && (
      <div className="card p-5 mt-4">
        <div className="flex items-center gap-2 mb-4">
          <TrendingUp className="w-5 h-5 text-[#7ED7C4]" />
          <h3 className="text-lg font-semibold text-white">艾略特波浪分析</h3>
        </div>
        <div className="space-y-3">
          <ShimmerBox className="h-8 w-32" />
          <ShimmerBox className="h-48" />
          <ShimmerBox className="h-32" />
        </div>
      </div>
      )}

      {/* Backtest results for recommended signals */}
      {(!loginRequired || isConnected) && sentiment?.backtest_results && Object.keys(sentiment.backtest_results).length > 0 ? (
        <div className="card p-5 mt-4">
          <div className="flex items-center gap-2 mb-4">
            <LineChart className="w-5 h-5 text-[#7ED7C4]" />
            <h3 className="text-lg font-semibold text-white">{t('backtest.recommendedSignals')}</h3>
          </div>
          <div className="space-y-3">
            {Object.entries(sentiment.backtest_results).map(([key, bt]: [string, any]) => {
              const [sym, tf] = key.split('_');
              const stats = bt.stats || {};
              const hasStats = Object.keys(stats).length > 0;
              const { direction, recommendation, currentSignal } = getBacktestDisplayInfo(key, bt);
              return (
                <div key={key} className="bg-white/[0.03] rounded-lg p-3">
                  <div className="flex items-center gap-2 mb-2">
                    <span className="font-bold text-white">{sym}</span>
                    <span className="text-xs text-gray-500">{tf}</span>
                    {direction && (
                      <span className={`text-xs px-2 py-0.5 rounded-full ${direction === 'long' ? 'bg-emerald-500/10 text-emerald-400' : 'bg-red-500/10 text-red-400'}`}>
                        {direction === 'long' ? t('trade.long') : t('trade.short')}
                      </span>
                    )}
                  </div>
                  {hasStats ? (
                    <>
                      <div className="grid grid-cols-3 gap-2 text-xs">
                        <div>
                          <span className="text-gray-500">{t('backtest.historicalSignals')}</span>
                          <div className="text-white font-medium">{bt.total_signals}</div>
                        </div>
                        <div>
                          <span className="text-gray-500">{t('backtest.bestWinRate')}</span>
                          <div className="text-emerald-400 font-medium">
                            {Math.max(0, ...Object.values(stats).filter((s: any) => !s.insufficient_data).map((s: any) => s.win_rate || 0)).toFixed(1)}%
                          </div>
                        </div>
                        <div>
                          <span className="text-gray-500">{t('backtest.bestProfitFactor')}</span>
                          <div className="text-white font-medium">
                            {(() => {
                              const validFactors = Object.values(stats).filter((s: any) => !s.insufficient_data && s.profit_factor != null).map((s: any) => s.profit_factor);
                              return validFactors.length > 0 ? Math.max(...validFactors).toFixed(2) : '—';
                            })()}
                          </div>
                        </div>
                      </div>
                      {recommendation && (
                        <div className="mt-2 space-y-2">
                          <div className="grid grid-cols-2 md:grid-cols-4 gap-2 text-xs">
                            <div>
                              <span className="text-gray-500">{t('backtest.recommendedAction')}</span>
                              <div className="font-medium">
                                <span className={`px-1.5 py-0.5 rounded ${
                                  recommendation.action === 'strong_long' ? 'bg-emerald-500/20 text-emerald-300' :
                                  recommendation.action === 'strong_short' ? 'bg-red-500/20 text-red-300' :
                                  recommendation.action === 'long' ? 'bg-emerald-500/10 text-emerald-400' :
                                  recommendation.action === 'short' ? 'bg-red-500/10 text-red-400' :
                                  'bg-gray-500/10 text-gray-400'
                                }`}>
                                  {recommendation.action === 'strong_long' || recommendation.action === 'long' ? t('trade.long') :
                                   recommendation.action === 'strong_short' || recommendation.action === 'short' ? t('trade.short') :
                                   t('trade.wait')}
                                </span>
                              </div>
                            </div>
                            <div>
                              <span className="text-gray-500">{t('backtest.confidence')}</span>
                              <div className="font-medium">
                                <span className={`inline-flex items-center px-1.5 py-0.5 rounded border text-[10px] ${getConfidenceStyle(recommendation.confidence)}`}>
                                  {t(getConfidenceLabel(recommendation.confidence))}
                                </span>
                              </div>
                            </div>
                            <div>
                              <span className="text-gray-500">{t('backtest.score')}</span>
                              <div className={`font-medium ${(recommendation.score ?? 0) >= 80 ? 'text-emerald-400' : (recommendation.score ?? 0) >= 50 ? 'text-amber-400' : 'text-red-400'}`}>
                                {(recommendation.score ?? 0).toFixed(0)}
                              </div>
                            </div>
                            <div>
                              <span className="text-gray-500">{t('backtest.currentWinRate')}</span>
                              <div className={`font-medium ${currentSignal?.similar_state_stats?.insufficient_data || !currentSignal ? 'text-gray-500' : (currentSignal.similar_state_stats?.win_rate ?? 0) >= 50 ? 'text-emerald-400' : 'text-red-400'}`}>
                                {currentSignal?.similar_state_stats?.insufficient_data || !currentSignal ? t('backtest.insufficientSamples') : `${(currentSignal.similar_state_stats?.win_rate ?? 0).toFixed(1)}%`}
                              </div>
                            </div>
                            <div>
                              <span className="text-gray-500">{t('backtest.signalStrength')}</span>
                              <div className="text-white font-medium">
                                {currentSignal ? t(getStrengthLabel(currentSignal.strength)) : '—'}
                              </div>
                            </div>
                          </div>
                          {recommendation.reason && (
                            <div className="text-xs">
                              <span className="text-gray-500">{t('backtest.reason')}</span>
                              <div className="text-gray-300 mt-0.5">{recommendation.reason}</div>
                            </div>
                          )}
                        </div>
                      )}
                    </>
                  ) : (
                    <div className="text-xs text-gray-500">{t('backtest.noData')}</div>
                  )}
                </div>
              );
            })}
          </div>
        </div>
      ) : loginRequired && !isConnected && !loading && (
        <div className="card p-5 mt-4">
          <ShimmerBox className="h-6 w-48 mb-4" />
          <div className="space-y-3">
            <ShimmerBox className="h-20" />
            <ShimmerBox className="h-20" />
          </div>
        </div>
      )}

      {/* 形态信号检测 (wallet or whitelist) */}
      {(!loginRequired || isConnected) ? <SignalDetectionTable 
        signals={signals} 
        backtest_results={sentiment?.backtest_results}
        loading={loading} 
      /> : loginRequired && !isConnected && !loading && (
        <div className="card p-5">
          <ShimmerBox className="h-6 w-40 mb-4" />
          <ShimmerBox className="h-48" />
        </div>
      )}

      {/* 币种分析表格 (wallet or whitelist) */}
      {(!loginRequired || isConnected) ? (
      <div className="card p-5">
        <div className="flex items-center gap-2 mb-4">
          <LineChart className="w-5 h-5 text-[#7ED7C4]" />
          <h2 className="text-lg font-semibold text-white">{t('sentiment.fullTokenAnalysis')}</h2>
          <span className="ml-auto text-xs text-gray-500">{allTokens.length} {t('common.tokensCount')}</span>
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
                  <th className="text-left py-2.5 px-3 font-medium text-xs">{t('table.symbol')}</th>
                  <th className="text-right py-2.5 px-3 font-medium text-xs">{t('table.price')}</th>
                  <th className="text-right py-2.5 px-3 font-medium text-xs">{t('table.change24h')}</th>
                  <th className="text-right py-2.5 px-3 font-medium text-xs">{t('table.maTrend')}</th>
                  <th className="text-right py-2.5 px-3 font-medium text-xs">{t('table.signalStrength')}</th>
                  <th className="text-right py-2.5 px-3 font-medium text-xs">{t('table.score')}</th>
                  <th className="text-right py-2.5 px-3 font-medium text-xs">{t('table.volumeTrend')}</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-white/5">
                {allTokens.map(token => (
                  <tr key={token.symbol} className="hover:bg-white/[0.03] transition group">
                    <td className="py-2.5 px-3">
                      <div className="flex items-center gap-2">
                        <div className={`w-1.5 h-1.5 rounded-full ${
                          token.alignment === 'bullish' ? 'bg-emerald-400' :
                          token.alignment === 'bearish' ? 'bg-red-400' : 'bg-amber-400'
                        }`} />
                        <span className="font-bold text-white">{token.symbol}</span>
                      </div>
                    </td>
                    <td className="py-2.5 px-3 text-right text-gray-300 font-mono">${token.price?.toFixed(4) ?? '--'}</td>
                    <td className={`py-2.5 px-3 text-right font-medium font-mono ${(token.price_change_24h ?? 0) >= 0 ? 'text-emerald-400' : 'text-red-400'}`}>
                      <span className="inline-flex items-center gap-0.5">
                        {(token.price_change_24h ?? 0) > 0 ? <ChevronUp className="w-3 h-3" /> :
                         (token.price_change_24h ?? 0) < 0 ? <ChevronDown className="w-3 h-3" /> : null}
                        {Math.abs(token.price_change_24h ?? 0).toFixed(2)}%
                      </span>
                    </td>
                    <td className="py-2.5 px-3 text-right">
                      <span className={`inline-flex items-center px-2 py-0.5 rounded text-xs font-medium ${
                        token.alignment === 'bullish' ? 'bg-emerald-500/10 text-emerald-400 border border-emerald-500/20' :
                        token.alignment === 'bearish' ? 'bg-red-500/10 text-red-400 border border-red-500/20' :
                        'bg-amber-500/10 text-amber-400 border border-amber-500/20'
                      }`}>
                        {token.alignment === 'bullish' ? t('sentiment.bullish') : token.alignment === 'bearish' ? t('sentiment.bearish') : t('sentiment.neutral')}
                      </span>
                    </td>
                    <td className="py-2.5 px-3 text-right">
                      <span className="text-gray-300">{token.strength ?? '--'}</span>
                    </td>
                    <td className="py-2.5 px-3 text-right">
                      <span className={`font-mono font-medium ${
                        (token.score ?? 0) >= 70 ? 'text-emerald-400' :
                        (token.score ?? 0) >= 40 ? 'text-amber-400' : 'text-red-400'
                      }`}>{token.score?.toFixed(1) ?? '--'}</span>
                    </td>
                    <td className="py-2.5 px-3 text-right text-gray-400 text-xs">{token.volume_trend ?? '--'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <div className="text-gray-500 text-sm py-8 text-center">{t('dashboard.noMarketData')}</div>
        )}
      </div>
      ) : loginRequired && !isConnected && !loading && (
      <div className="card p-5">
        <ShimmerBox className="h-6 w-48 mb-4" />
        <div className="space-y-2">
          <ShimmerBox className="h-10" />
          <ShimmerBox className="h-10" />
          <ShimmerBox className="h-10" />
          <ShimmerBox className="h-10" />
        </div>
      </div>
      )}
      </div>
      )}

      {activeTab === 'backtest' && (
        <div className="space-y-6">
          {/* 风险提示横幅 */}
          <div className="relative overflow-hidden rounded-xl border border-amber-500/20 bg-gradient-to-r from-amber-950/60 via-amber-900/30 to-amber-950/60 px-5 py-3.5">
            <div className="relative flex items-center gap-3">
              <AlertTriangle className="w-5 h-5 text-amber-400" />
              <div className="flex-1">
                <span className="text-sm font-semibold text-amber-300">{t('risk.warning')}</span>
                <p className="text-sm text-amber-200/80 mt-0.5">{t('risk.disclaimer')}</p>
              </div>
            </div>
          </div>

          {/* 推荐信号回溯验证 */}
          {sentiment?.backtest_results && Object.keys(sentiment.backtest_results).length > 0 ? (
            <div className="card p-5">
              <div className="flex items-center gap-2 mb-4">
                <LineChart className="w-5 h-5 text-[#7ED7C4]" />
                <h2 className="text-lg font-semibold text-white">{t('backtest.recommendedSignals')}</h2>
              </div>
              <div className="space-y-3">
                {Object.entries(sentiment.backtest_results).map(([key, bt]: [string, any]) => {
                  const [sym, tf] = key.split('_');
                  const stats = bt.stats || {};
                  const hasStats = Object.keys(stats).length > 0;
                  const { direction, recommendation, currentSignal } = getBacktestDisplayInfo(key, bt);
                  return (
                    <div key={key} className="bg-white/[0.03] rounded-lg p-3">
                      <div className="flex items-center gap-2 mb-2">
                        <span className="font-bold text-white">{sym}</span>
                        <span className="text-xs text-gray-500">{tf}</span>
                        {direction && (
                          <span className={`text-xs px-2 py-0.5 rounded-full ${direction === 'long' ? 'bg-emerald-500/10 text-emerald-400' : 'bg-red-500/10 text-red-400'}`}>
                            {direction === 'long' ? t('trade.long') : t('trade.short')}
                          </span>
                        )}
                      </div>
                      {hasStats ? (
                        <>
                          <div className="grid grid-cols-3 gap-2 text-xs">
                            <div>
                              <span className="text-gray-500">{t('backtest.historicalSignals')}</span>
                              <div className="text-white font-medium">{bt.total_signals}</div>
                            </div>
                            <div>
                              <span className="text-gray-500">{t('backtest.bestWinRate')}</span>
                              <div className="text-emerald-400 font-medium">
                                {Math.max(0, ...Object.values(stats).filter((s: any) => !s.insufficient_data).map((s: any) => s.win_rate || 0)).toFixed(1)}%
                              </div>
                            </div>
                            <div>
                              <span className="text-gray-500">{t('backtest.bestProfitFactor')}</span>
                              <div className="text-white font-medium">
                                {(() => {
                                  const validFactors = Object.values(stats).filter((s: any) => !s.insufficient_data && s.profit_factor != null).map((s: any) => s.profit_factor);
                                  return validFactors.length > 0 ? Math.max(...validFactors).toFixed(2) : '—';
                                })()}
                              </div>
                            </div>
                          </div>
                          {recommendation && (
                            <div className="mt-2 space-y-2">
                              <div className="grid grid-cols-2 md:grid-cols-4 gap-2 text-xs">
                                <div>
                                  <span className="text-gray-500">{t('backtest.recommendedAction')}</span>
                                  <div className="font-medium">
                                    <span className={`px-1.5 py-0.5 rounded ${
                                      recommendation.action === 'strong_long' ? 'bg-emerald-500/20 text-emerald-300' :
                                      recommendation.action === 'strong_short' ? 'bg-red-500/20 text-red-300' :
                                      recommendation.action === 'long' ? 'bg-emerald-500/10 text-emerald-400' :
                                      recommendation.action === 'short' ? 'bg-red-500/10 text-red-400' :
                                      'bg-gray-500/10 text-gray-400'
                                    }`}>
                                      {recommendation.action === 'strong_long' || recommendation.action === 'long' ? t('trade.long') :
                                       recommendation.action === 'strong_short' || recommendation.action === 'short' ? t('trade.short') :
                                       t('trade.wait')}
                                    </span>
                                  </div>
                                </div>
                                <div>
                                  <span className="text-gray-500">{t('backtest.confidence')}</span>
                                  <div className="font-medium">
                                    <span className={`inline-flex items-center px-1.5 py-0.5 rounded border text-[10px] ${getConfidenceStyle(recommendation.confidence)}`}>
                                      {t(getConfidenceLabel(recommendation.confidence))}
                                    </span>
                                  </div>
                                </div>
                                <div>
                                  <span className="text-gray-500">{t('backtest.score')}</span>
                                  <div className={`font-medium ${(recommendation.score ?? 0) >= 80 ? 'text-emerald-400' : (recommendation.score ?? 0) >= 50 ? 'text-amber-400' : 'text-red-400'}`}>
                                    {(recommendation.score ?? 0).toFixed(0)}
                                  </div>
                                </div>
                                <div>
                                  <span className="text-gray-500">{t('backtest.currentWinRate')}</span>
                                  <div className={`font-medium ${currentSignal?.similar_state_stats?.insufficient_data || !currentSignal ? 'text-gray-500' : (currentSignal.similar_state_stats?.win_rate ?? 0) >= 50 ? 'text-emerald-400' : 'text-red-400'}`}>
                                    {currentSignal?.similar_state_stats?.insufficient_data || !currentSignal ? t('backtest.insufficientSamples') : `${(currentSignal.similar_state_stats?.win_rate ?? 0).toFixed(1)}%`}
                                  </div>
                                </div>
                                <div>
                                  <span className="text-gray-500">{t('backtest.signalStrength')}</span>
                                  <div className="text-white font-medium">
                                    {currentSignal ? t(getStrengthLabel(currentSignal.strength)) : '—'}
                                  </div>
                                </div>
                              </div>
                              {recommendation.reason && (
                                <div className="text-xs">
                                  <span className="text-gray-500">{t('backtest.reason')}</span>
                                  <div className="text-gray-300 mt-0.5">{recommendation.reason}</div>
                                </div>
                              )}
                            </div>
                          )}
                        </>
                      ) : (
                        <div className="text-xs text-gray-500">{t('backtest.noData')}</div>
                      )}
                    </div>
                  );
                })}
              </div>
            </div>
          ) : (
            <div className="card p-8 text-center text-gray-500">
              <LineChart className="w-10 h-10 mx-auto mb-3 opacity-30" />
              <p className="text-sm">{t('backtest.noRecommendedData')}</p>
              <p className="text-xs text-gray-600 mt-1">Waiting for sentiment analysis，data will load automatically</p>
            </div>
          )}

          {/* 单币种详细回测（次级功能） */}
          <div className="card p-5">
            <div className="flex items-center gap-2 mb-4">
              <LineChart className="w-5 h-5 text-[#7ED7C4]" />
              <h2 className="text-lg font-semibold text-white">{t('backtest.singleToken')}</h2>
            </div>
            <div className="flex flex-wrap items-center gap-3 mb-4">
              <select
                value={backtestSymbol}
                onChange={e => setBacktestSymbol(e.target.value)}
                className="bg-gray-800 border border-white/10 rounded-lg px-3 py-2 text-sm text-white focus:outline-none focus:border-[#2D6B5E]"
              >
                {allTokens.map(t => (
                  <option key={t.symbol} value={t.symbol}>{t.symbol}</option>
                ))}
                <option value="BTCUSDT">BTCUSDT</option>
                <option value="ETHUSDT">ETHUSDT</option>
                <option value="SOLUSDT">SOLUSDT</option>
                <option value="BNBUSDT">BNBUSDT</option>
                <option value="XRPUSDT">XRPUSDT</option>
                <option value="DOGEUSDT">DOGEUSDT</option>
                <option value="ADAUSDT">ADAUSDT</option>
                <option value="AVAXUSDT">AVAXUSDT</option>
                <option value="DOTUSDT">DOTUSDT</option>
                <option value="LINKUSDT">LINKUSDT</option>
              </select>
              <button
                onClick={loadBacktest}
                disabled={backtestLoading}
                className="px-4 py-2 rounded-lg text-sm font-medium bg-gray-700 text-white hover:bg-gray-600 transition disabled:opacity-50"
              >
                {backtestLoading ? t('common.loading') : t('common.viewDetails')}
              </button>
            </div>
            {backtestLoading ? (
              <div className="space-y-2">
                <ShimmerBox className="h-10" />
                <ShimmerBox className="h-10" />
                <ShimmerBox className="h-10" />
              </div>
            ) : backtestResult && Object.keys(backtestResult.stats || {}).length > 0 ? (
              <div className="space-y-4">
                <div className="overflow-x-auto">
                  <table className="w-full text-sm">
                    <thead>
                      <tr className="border-b border-white/10 text-gray-400">
                        <th className="text-left py-2.5 px-3 font-medium text-xs">{t('backtest.patternDuration')}</th>
                        <th className="text-center py-2.5 px-3 font-medium text-xs">{t('backtest.signals')}</th>
                        <th className="text-center py-2.5 px-3 font-medium text-xs">{t('backtest.winRate')}</th>
                        <th className="text-center py-2.5 px-3 font-medium text-xs">{t('backtest.avgNetPnl')}</th>
                        <th className="text-center py-2.5 px-3 font-medium text-xs">{t('backtest.maxProfit')}</th>
                        <th className="text-center py-2.5 px-3 font-medium text-xs">{t('backtest.maxLoss')}</th>
                        <th className="text-center py-2.5 px-3 font-medium text-xs">{t('backtest.profitFactor')}</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-white/5">
                      {Object.entries(backtestResult.stats).map(([key, stats]) => {
                        return (
                          <tr key={key} className="hover:bg-white/[0.03] transition">
                            <td className="py-2.5 px-3">
                              <span className={`text-xs font-bold px-2 py-0.5 rounded border ${
                                key.startsWith('bullish') ? 'border-emerald-500/30 bg-emerald-500/10 text-emerald-400' :
                                'border-red-500/30 bg-red-500/10 text-red-400'
                              }`}>
                                {key.replace('bullish_all_', t('pattern.bullishAll') + ' ').replace('bearish_all_', t('pattern.bearishAll') + ' ')}
                              </span>
                              {stats.insufficient_data && (
                                <span className="ml-2 text-[10px] text-amber-400">{t('backtest.insufficientSamples')}</span>
                              )}
                            </td>
                            <td className="py-2.5 px-3 text-center text-gray-300">{stats.total_signals}</td>
                            <td className="py-2.5 px-3 text-center">
                              <span className={`font-medium ${stats.win_rate >= 50 ? 'text-emerald-400' : 'text-red-400'}`}>
                                {(stats.win_rate ?? 0).toFixed(1)}%
                              </span>
                            </td>
                            <td className="py-2.5 px-3 text-center">
                              <span className={`font-medium ${(stats.avg_net_pnl ?? 0) >= 0 ? 'text-emerald-400' : 'text-red-400'}`}>
                                {(stats.avg_net_pnl ?? 0) >= 0 ? '+' : ''}{(stats.avg_net_pnl ?? 0).toFixed(2)}%
                              </span>
                            </td>
                            <td className="py-2.5 px-3 text-center text-emerald-400">
                              +{(stats.max_pnl ?? 0).toFixed(2)}%
                            </td>
                            <td className="py-2.5 px-3 text-center text-red-400">
                              {(stats.min_pnl ?? 0).toFixed(2)}%
                            </td>
                            <td className="py-2.5 px-3 text-center text-gray-300">
                              {stats.profit_factor == null || stats.profit_factor === 999.99 ? '∞' : stats.profit_factor}
                            </td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                </div>
                {/* 最近信号 */}
                {backtestResult.recent_signals && backtestResult.recent_signals.length > 0 && (
                  <div>
                    <h3 className="text-sm font-medium text-white mb-2">{t('backtest.recentSignals')}</h3>
                    <div className="overflow-x-auto">
                      <table className="w-full text-sm">
                        <thead>
                          <tr className="border-b border-white/10 text-gray-400">
                            <th className="text-left py-2 px-3 font-medium text-xs">{t('table.direction')}</th>
                            <th className="text-center py-2 px-3 font-medium text-xs">{t('table.duration')}</th>
                            <th className="text-right py-2 px-3 font-medium text-xs">{t('table.entryPrice')}</th>
                            <th className="text-right py-2 px-3 font-medium text-xs">{t('table.exitPrice')}</th>
                            <th className="text-center py-2 px-3 font-medium text-xs">{t('table.netPnl')}</th>
                          </tr>
                        </thead>
                        <tbody className="divide-y divide-white/5">
                          {backtestResult.recent_signals.slice(0, 10).map((sig: BacktestSignal, i: number) => (
                            <tr key={i} className="hover:bg-white/[0.03] transition">
                              <td className="py-2 px-3">
                                <span className={`text-xs px-2 py-0.5 rounded-full ${
                                  sig.direction === 'long'
                                    ? 'bg-emerald-500/10 text-emerald-400'
                                    : 'bg-red-500/10 text-red-400'
                                }`}>
                                  {sig.direction === 'long' ? t('trade.long') : t('trade.short')}
                                </span>
                              </td>
                              <td className="py-2 px-3 text-center text-gray-400 text-xs">{(sig as any).duration ?? '--'} {t('backtest.bars')}</td>
                              <td className="py-2 px-3 text-right text-gray-300 font-mono text-xs">${sig.entry_price?.toFixed(4) ?? '--'}</td>
                              <td className="py-2 px-3 text-right text-gray-300 font-mono text-xs">${(sig as any).exit_price?.toFixed(4) ?? '--'}</td>
                              <td className="py-2 px-3 text-center">
                                <span className={`text-xs font-medium ${(sig as any).net_pnl_pct >= 0 ? 'text-emerald-400' : 'text-red-400'}`}>
                                  {(sig as any).net_pnl_pct >= 0 ? '+' : ''}{(sig as any).net_pnl_pct?.toFixed(2) ?? '--'}%
                                </span>
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  </div>
                )}
              </div>
            ) : (
              <div className="flex flex-col items-center justify-center py-8 text-gray-500">
                <LineChart className="w-8 h-8 mb-2 opacity-30" />
                <span className="text-sm">{t('backtest.selectToken')}</span>
              </div>
            )}
          </div>

          {/* 回测方法论说明 */}
          <div className="card p-5">
            <details className="group">
              <summary className="flex items-center gap-2 cursor-pointer list-none">
                <Eye className="w-4 h-4 text-[#7ED7C4]" />
                <span className="text-sm font-medium text-white">{t('backtest.whatIsIt')}</span>
                <ChevronDown className="w-4 h-4 text-gray-500 ml-auto transition-transform group-open:rotate-180" />
              </summary>
              <div className="mt-4 space-y-3 text-sm text-gray-400">
                <p>
                  <strong className="text-gray-300">{t('backtest.methodology.coreLogic')}：</strong>
                  {t('backtest.methodology.coreLogicDesc')}
                </p>
                <p>
                  <strong className="text-gray-300">{t('backtest.methodology.holdingPeriod')}：</strong>
                  {t('backtest.methodology.holdingPeriodDesc')}
                </p>
                <p>
                  <strong className="text-gray-300">{t('backtest.methodology.signalStrength')}：</strong>
                  {t('backtest.methodology.signalStrengthDesc')}
                </p>
                <p>
                  <strong className="text-gray-300">{t('backtest.methodology.durationBuckets')}：</strong>
                  {t('backtest.methodology.durationBucketsDesc')}
                </p>
                <p>
                  <strong className="text-gray-300">{t('backtest.methodology.sampleSize')}：</strong>
                  {t('backtest.methodology.sampleSizeDesc')}
                </p>
                <p>
                  <strong className="text-gray-300">{t('backtest.methodology.tradingCost')}：</strong>
                  {t('backtest.methodology.tradingCostDesc')}
                </p>
              </div>
            </details>
          </div>
        </div>
      )}
    </div>
  );
}
