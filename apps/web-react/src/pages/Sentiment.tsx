import { useState, useMemo, useRef, useEffect, useCallback } from 'react';
import { useTranslation } from 'react-i18next';
import {
  TrendingUp, TrendingDown, Minus, Clock, Gauge, ChevronUp, ChevronDown,
  AlertTriangle, ShieldAlert, Activity, BarChart3, Bitcoin, Layers,
  Target, Eye, Zap, ArrowUpRight, ArrowDownRight, Timer,
  LineChart, Skull
} from 'lucide-react';
import type { SentimentData as BaseSentimentData, TokenData } from '../types';
import { translatePattern, translateConfidenceLabel, translateWatch, translateRiskWarning, translateReason } from '../utils/translateBackend';
import { useReadContract } from 'wagmi';
import { mantleSepoliaTestnet } from 'viem/chains';
import registryAbi from '../abi/MantleDeFAIRegistry.json';
import { parseSignalData } from '../hooks/useSignalDecrypt';
import sha256 from 'crypto-js/sha256';
import { getLatestSentiment, getElliottWave, getAllElliottWaves } from '../services/api';

/* ───────────────────────────────
   扩展类型
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

function getBacktestActionStyle(action?: string): string {
  if (action === 'strong_long') return 'bg-emerald-500/20 text-emerald-300';
  if (action === 'strong_short') return 'bg-red-500/20 text-red-300';
  if (action === 'long') return 'bg-emerald-500/10 text-emerald-400';
  if (action === 'short') return 'bg-red-500/10 text-red-400';
  return 'bg-gray-500/10 text-gray-400';
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
  loading,
  verificationStatus = 'pending',
}: { 
  signals?: SignalData[]; 
  backtest_results?: Record<string, any>;
  loading: boolean;
  verificationStatus?: 'verified' | 'mismatch' | 'pending';
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
          const winRate = ps.win_rate;
          // 跳过 win_rate 为 null 的条目，避免 NaN 污染
          if (winRate != null) {
            totalWins += winRate * (ps.total_signals ?? 0);
            totalCount += ps.total_signals ?? 0;
          }
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
        <div className="flex items-center justify-between mb-4">
          <div className="flex items-center gap-2">
            <Zap className="w-5 h-5 text-[#7ED7C4]" />
            <h2 className="text-lg font-semibold text-white">{t('sentiment.patternDetection')}</h2>
          </div>
          <VerificationBadge status={verificationStatus} />
        </div>
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
        <div className="flex items-center justify-between mb-4">
          <div className="flex items-center gap-2">
            <Zap className="w-5 h-5 text-[#7ED7C4]" />
            <h2 className="text-lg font-semibold text-white">{t('sentiment.patternDetection')}</h2>
          </div>
          <VerificationBadge status={verificationStatus} />
        </div>
        <div className="text-gray-500 text-sm py-8 text-center">{t('common.noData')}</div>
      </div>
    );
  }

  return (
    <div className="card p-5">
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-2">
          <Zap className="w-5 h-5 text-[#7ED7C4]" />
          <h2 className="text-lg font-semibold text-white">{t('sentiment.patternDetection')}</h2>
          <span className="ml-2 text-xs text-gray-500">{`${signals.length} ${t('backtest.signals')}`}</span>
        </div>
        <VerificationBadge status={verificationStatus} />
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
   最近信号表格
   ─────────────────────────────── */
function RecentSignalsTable({ signals, loading }: { signals: any[]; loading: boolean }) {
  useTranslation(); // i18n hook loaded for future use

  if (loading) {
    return (
      <div className="card p-5">
        <div className="flex items-center gap-2 mb-4">
          <Timer className="w-5 h-5 text-[#7ED7C4]" />
          <h2 className="text-lg font-semibold text-white">最近信号</h2>
        </div>
        <div className="space-y-2">
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
          <Timer className="w-5 h-5 text-[#7ED7C4]" />
          <h2 className="text-lg font-semibold text-white">最近信号</h2>
        </div>
        <div className="text-gray-500 text-sm py-8 text-center">暂无最近信号数据</div>
      </div>
    );
  }

  return (
    <div className="card p-5">
      <div className="flex items-center gap-2 mb-4">
        <Timer className="w-5 h-5 text-[#7ED7C4]" />
        <h2 className="text-lg font-semibold text-white">最近信号</h2>
        <span className="ml-2 text-xs text-gray-500">{signals.length} 条</span>
      </div>
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-white/10 text-gray-400">
              <th className="text-left py-2.5 px-3 font-medium text-xs">币种</th>
              <th className="text-center py-2.5 px-3 font-medium text-xs">周期</th>
              <th className="text-center py-2.5 px-3 font-medium text-xs">方向</th>
              <th className="text-right py-2.5 px-3 font-medium text-xs">入场价</th>
              <th className="text-right py-2.5 px-3 font-medium text-xs">出场价</th>
              <th className="text-right py-2.5 px-3 font-medium text-xs">盈亏</th>
              <th className="text-center py-2.5 px-3 font-medium text-xs">持仓时长</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-white/5">
            {signals.map((s, i) => (
              <tr key={i} className="hover:bg-white/[0.03] transition">
                <td className="py-2.5 px-3">
                  <span className="font-bold text-white">{s.symbol ?? '--'}</span>
                </td>
                <td className="py-2.5 px-3 text-center">
                  <span className="text-xs text-gray-400 px-2 py-0.5 rounded bg-gray-800">{s.timeframe ?? '--'}</span>
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
                    {s.direction === 'long' ? '多' : s.direction === 'short' ? '空' : '观望'}
                  </span>
                </td>
                <td className="py-2.5 px-3 text-right text-gray-300 font-mono">
                  {s.entry_price != null ? `$${s.entry_price.toLocaleString()}` : '--'}
                </td>
                <td className="py-2.5 px-3 text-right text-gray-300 font-mono">
                  {s.exit_price != null ? `$${s.exit_price.toLocaleString()}` : '--'}
                </td>
                <td className={`py-2.5 px-3 text-right font-mono font-medium ${(s.pnl_pct ?? 0) >= 0 ? 'text-emerald-400' : 'text-red-400'}`}>
                  {(s.pnl_pct ?? 0) >= 0 ? '+' : ''}{s.pnl_pct?.toFixed(2) ?? '--'}%
                </td>
                <td className="py-2.5 px-3 text-center text-gray-400 text-xs">
                  {s.duration ?? '--'}
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
   分桶统计折叠面板
   ─────────────────────────────── */
function StatsAccordion({ stats }: { stats?: Record<string, any> }) {
  if (!stats || Object.keys(stats).length === 0) return null;

  return (
    <details className="mt-3 group">
      <summary className="flex items-center gap-2 cursor-pointer list-none text-xs text-gray-400 hover:text-gray-300">
        <BarChart3 className="w-3.5 h-3.5" />
        <span>分桶统计</span>
        <ChevronDown className="w-3.5 h-3.5 ml-auto transition-transform group-open:rotate-180" />
      </summary>
      <div className="mt-2 overflow-x-auto">
        <table className="w-full text-xs">
          <thead>
            <tr className="border-b border-white/10 text-gray-500">
              <th className="text-left py-2 px-2 font-medium">Pattern</th>
              <th className="text-right py-2 px-2 font-medium">Signals</th>
              <th className="text-right py-2 px-2 font-medium">Win Rate</th>
              <th className="text-right py-2 px-2 font-medium">Avg PnL</th>
              <th className="text-right py-2 px-2 font-medium">Max PnL</th>
              <th className="text-right py-2 px-2 font-medium">Min PnL</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-white/5">
            {Object.entries(stats).map(([pattern, st]) => (
              <tr key={pattern} className="hover:bg-white/[0.03]">
                <td className="py-2 px-2 text-gray-300">{pattern}</td>
                <td className="py-2 px-2 text-right text-gray-400">{(st as any).total_signals ?? 0}</td>
                <td className={`py-2 px-2 text-right font-medium ${(st as any).win_rate == null ? 'text-gray-500' : ((st as any).win_rate ?? 0) >= 50 ? 'text-emerald-400' : 'text-red-400'}`}>
                  {(st as any).win_rate == null ? '—' : `${((st as any).win_rate ?? 0).toFixed(1)}%`}
                </td>
                <td className={`py-2 px-2 text-right font-medium ${(st as any).avg_pnl == null ? 'text-gray-500' : ((st as any).avg_pnl ?? 0) >= 0 ? 'text-emerald-400' : 'text-red-400'}`}>
                  {(st as any).avg_pnl == null ? '—' : `${((st as any).avg_pnl ?? 0) >= 0 ? '+' : ''}${((st as any).avg_pnl ?? 0).toFixed(2)}%`}
                </td>
                <td className="py-2 px-2 text-right text-emerald-400">
                  +{((st as any).max_pnl ?? 0).toFixed(2)}%
                </td>
                <td className="py-2 px-2 text-right text-red-400">
                  {((st as any).min_pnl ?? 0).toFixed(2)}%
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </details>
  );
}

/* ───────────────────────────────
   主组件
   ─────────────────────────────── */
export default function Sentiment() {
  const { t } = useTranslation();
  const [timeframe, setTimeframe] = useState<'1h' | '4h' | '1d'>('1h');
  const [activeTab, setActiveTab] = useState<'sentiment' | 'backtest'>('sentiment');

  // API 数据状态
  const [apiData, setApiData] = useState<any>(null);
  const [elliottWaveData, setElliottWaveData] = useState<any>(null);
  const [availableEWSymbols, setAvailableEWSymbols] = useState<Array<{symbol: string; wave_pattern: string | null}>>([]);
  const [selectedEWSymbol, setSelectedEWSymbol] = useState<string>('');
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
    try { return parseSignalData(signalData.data); } catch { return null; }
  }, [signalData]);

  const loading = apiLoading;

  const loadElliottWaveForSymbol = async (sym: string, tf: string) => {
    try {
      const ewData = await getElliottWave(sym, tf);
      if (ewData) {
        const d = ewData as any;
        const candidate = d.candidates?.[0];
        const kimi = d.kimi_analysis;
        setElliottWaveData({
          chart_path: d.chart_paths?.[0],
          wave_pattern: candidate?.wave_pattern ?? kimi?.wave_pattern,
          direction: candidate?.direction ?? kimi?.direction,
          current_wave: candidate?.current_wave ?? (candidate?.waves ? `Wave ${candidate.waves.length}` : undefined),
          score: candidate?.score ?? kimi?.overall_confidence ?? (candidate?.waves ? candidate.waves.length / 10 : 0.5),
          projections: candidate?.projections ?? [],
          raw: d,
        });
      }
    } catch {
      // ignore
    }
  };

  // A. 从 API 获取完整数据
  const fetchData = useCallback(async () => {
    try {
      const data = await getLatestSentiment();
      setApiData(data);
      // 同时获取 Elliott Wave 数据
      const symbol = (data?.decision?.symbol ?? 'BTC').replace('USDT', '');
      const tf = data?.decision?.timeframe ?? '1d';
      try {
        // 获取所有可用的艾略特波浪币种
        const ewList = await getAllElliottWaves(tf);
        setAvailableEWSymbols(ewList.map((w: any) => ({ symbol: w.symbol, wave_pattern: w.wave_pattern })));
        // 如果 decision.symbol 不在列表中，选择第一个有图表的币种
        const hasDecision = ewList.some((w: any) => w.symbol === symbol);
        const defaultSymbol = hasDecision ? symbol : (ewList[0]?.symbol || symbol);
        setSelectedEWSymbol(defaultSymbol);

        // 用默认币种获取艾略特波浪数据
        await loadElliottWaveForSymbol(defaultSymbol, tf);
      } catch {
        // ignore Elliott Wave errors
      }
      setApiLoading(false);
    } catch (err: any) {
      setApiError(err.message);
      setApiLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  // C. 独立加载 Elliott Wave 数据（即使 sentiment API 失败也能加载）
  useEffect(() => {
    const loadEW = async () => {
      try {
        const tf = '1d'; // 默认 timeframe
        const ewList = await getAllElliottWaves(tf);
        setAvailableEWSymbols(ewList.map((w: any) => ({ symbol: w.symbol, wave_pattern: w.wave_pattern })));
        const defaultSymbol = ewList[0]?.symbol || 'BTC';
        setSelectedEWSymbol(defaultSymbol);
        await loadElliottWaveForSymbol(defaultSymbol, tf);
      } catch {
        // ignore Elliott Wave errors
      }
    };
    loadEW();
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

  // Sentiment 情绪指标 - 全部从 apiData 读取
  const sentiment_index = apiData?.sentiment_index ?? apiData?.sentiment?.sentiment_index;
  const market_bias = apiData?.market_bias ?? apiData?.sentiment?.market_bias;
  const bias_strength = apiData?.bias_strength ?? apiData?.sentiment?.bias_strength;
  const fng = apiData?.fng?.value !== undefined
    ? { value: apiData.fng.value, classification: apiData.fng.classification ?? '', timestamp: '' }
    : apiData?.sentiment?.fng_value !== undefined
    ? { value: apiData.sentiment.fng_value, classification: apiData.sentiment.fng_label ?? '', timestamp: '' }
    : null;
  const bullish_count = apiData?.bullish_count ?? apiData?.sentiment?.bullish_count ?? 0;
  const bearish_count = apiData?.bearish_count ?? apiData?.sentiment?.bearish_count ?? 0;
  const neutral_count = apiData?.neutral_count ?? apiData?.sentiment?.neutral_count ?? 0;

  // 持仓建议
  const positionReport = useMemo<ExtendedSentimentData['position_report'] | undefined>(() => {
    const raw = apiData?.position_report as any;
    if (!raw) return undefined;
    const mapped: any = {};
    for (const [tf, data] of Object.entries(raw) as [string, any][]) {
      mapped[tf] = {
        long: (data.long || []).map((item: any) => ({ ...item, confidence_label: item.confidence })),
        short: (data.short || []).map((item: any) => ({ ...item, confidence_label: item.confidence })),
        watch: data.watch || '',
      };
    }
    return mapped;
  }, [apiData]);

  // Elliott Wave data is loaded separately via API

  // Backtest - 从 apiData 读取所有币种
  const allBacktestData = useMemo(() => {
    const results = apiData?.backtest_results as Record<string, any> | undefined;
    if (!results) return apiData?.backtest ? [{ key: 'default', ...apiData.backtest }] : [];
    return Object.entries(results)
      .filter(([, v]) => v && (v.total_signals ?? 0) > 0)
      .map(([key, data]) => ({ key, ...data }));
  }, [apiData]);

  const allRecentSignals = useMemo(() => {
    const signals: any[] = [];
    const results = apiData?.backtest_results as Record<string, any> | undefined;
    if (!results) {
      const bt = apiData?.backtest as any;
      if (bt?.recent_signals) {
        signals.push(...bt.recent_signals.map((s: any) => ({ ...s, sourceKey: 'default' })));
      }
      return signals.sort((a, b) => new Date(b.entry_time || 0).getTime() - new Date(a.entry_time || 0).getTime()).slice(0, 20);
    }
    for (const [key, data] of Object.entries(results)) {
      if ((data as any)?.recent_signals) {
        signals.push(...(data as any).recent_signals.map((s: any) => ({ ...s, sourceKey: key })));
      }
    }
    return signals.sort((a, b) => new Date(b.entry_time || 0).getTime() - new Date(a.entry_time || 0).getTime()).slice(0, 20);
  }, [apiData]);

  // 风险警告
  const riskWarning = apiData?.risk_warning ?? apiData?.risk ?? '';

  // 完整币种分析
  const symbolScores = apiData?.symbol_scores ?? [];

  // Signals - 优先使用 apiData.signals，fallback 从 position_report 重建
  const signals: SignalData[] = useMemo(() => {
    const apiSignals = apiData?.signals as SignalData[] | undefined;
    if (apiSignals && apiSignals.length > 0) {
      return apiSignals;
    }

    const result: SignalData[] = [];
    const raw = apiData?.position_report as any;
    if (!raw) return result;
    for (const [tf, data] of Object.entries(raw) as [string, any][]) {
      if (data.long) {
        for (const item of data.long) {
          const parts = item.reason ? item.reason.split('+').map((p: string) => p.trim()).filter(Boolean) : [];
          result.push({
            symbol: item.symbol,
            timeframe: tf as '1d' | '4h' | '1w',
            direction: 'long',
            primary_pattern: parts[0] || 'unknown',
            secondary_patterns: parts.slice(1),
            confidence: item.confidence,
          });
        }
      }
      if (data.short) {
        for (const item of data.short) {
          const parts = item.reason ? item.reason.split('+').map((p: string) => p.trim()).filter(Boolean) : [];
          result.push({
            symbol: item.symbol,
            timeframe: tf as '1d' | '4h' | '1w',
            direction: 'short',
            primary_pattern: parts[0] || 'unknown',
            secondary_patterns: parts.slice(1),
            confidence: item.confidence,
          });
        }
      }
    }
    return result;
  }, [apiData]);

  // Backtest results for SignalDetectionTable (all symbols from API)
  const backtestResults = apiData?.backtest_results ?? {};

  // Timestamp - 从 apiData 读取
  const timestamp = apiData?.data_freshness ?? apiData?.timestamp ?? '';
  const data_freshness = apiData?.data_freshness ?? apiData?.timestamp ?? '';

  const label = sentiment_index !== undefined ? t(getSentimentLabel(sentiment_index)) : '--';

  // BTC 24h change - 从 apiData 读取
  const btcChange24h = useMemo(() => {
    const scores = apiData?.symbol_scores as any[];
    if (!scores) return undefined;
    const btc = scores.find((s: any) => s.symbol === 'BTC' || s.symbol === 'BTCUSDT');
    return btc?.change_24h ?? btc?.price_change_24h;
  }, [apiData]);

  const breadth = useMemo(() => ({
    up: bullish_count,
    down: bearish_count,
    flat: neutral_count,
  }), [bullish_count, bearish_count, neutral_count]);

  // Backtest stats helper - 优先从 current_signal.similar_state_stats 读取，fallback 到 stats 加权平均
  const getBacktestStats = (bt: any) => {
    const currentStats = bt?.current_signal?.similar_state_stats;
    if (currentStats && !currentStats.insufficient_data) {
      return {
        win_rate: currentStats.win_rate,
        avg_pnl: currentStats.avg_pnl ?? currentStats.avg_net_pnl,
        avg_net_pnl: currentStats.avg_net_pnl,
        profit_factor: currentStats.profit_factor,
        total_signals: currentStats.total_signals,
        max_pnl: currentStats.max_pnl,
        min_pnl: currentStats.min_pnl,
        avg_win: currentStats.avg_win,
        avg_loss: currentStats.avg_loss,
      };
    }

    const overallStats = bt?.stats;
    if (overallStats) {
      let totalWins = 0;
      let totalCount = 0;
      let totalAvgPnl = 0;
      let totalProfitFactor = 0;
      let totalMaxPnl = 0;
      let totalMinPnl = 0;
      let totalAvgWin = 0;
      let totalAvgLoss = 0;
      let validBuckets = 0;

      for (const [, patternStats] of Object.entries(overallStats)) {
        if (typeof patternStats === 'object' && patternStats && 'total_signals' in patternStats) {
          const ps = patternStats as any;
          const count = ps.total_signals ?? 0;
          if (count > 0) {
            totalCount += count;
            if (ps.win_rate != null) totalWins += ps.win_rate * count;
            if (ps.avg_pnl != null) totalAvgPnl += ps.avg_pnl * count;
            if (ps.avg_net_pnl != null) totalAvgPnl += ps.avg_net_pnl * count;
            if (ps.profit_factor != null && ps.profit_factor !== 999.99) {
              totalProfitFactor += ps.profit_factor * count;
            }
            if (ps.max_pnl != null) totalMaxPnl += ps.max_pnl * count;
            if (ps.min_pnl != null) totalMinPnl += ps.min_pnl * count;
            if (ps.avg_win != null) totalAvgWin += ps.avg_win * count;
            if (ps.avg_loss != null) totalAvgLoss += ps.avg_loss * count;
            validBuckets++;
          }
        }
      }

      if (totalCount > 0) {
        return {
          win_rate: totalWins / totalCount,
          avg_pnl: totalAvgPnl / totalCount,
          avg_net_pnl: totalAvgPnl / totalCount,
          profit_factor: validBuckets > 0 ? totalProfitFactor / totalCount : undefined,
          total_signals: totalCount,
          max_pnl: validBuckets > 0 ? totalMaxPnl / totalCount : undefined,
          min_pnl: validBuckets > 0 ? totalMinPnl / totalCount : undefined,
          avg_win: validBuckets > 0 ? totalAvgWin / totalCount : undefined,
          avg_loss: validBuckets > 0 ? totalAvgLoss / totalCount : undefined,
        };
      }
    }

    return {
      win_rate: bt?.win_rate,
      avg_pnl: bt?.avg_pnl ?? bt?.avg_net_pnl,
      avg_net_pnl: bt?.avg_net_pnl,
      profit_factor: bt?.profit_factor,
      total_signals: bt?.total_signals,
      max_pnl: bt?.max_pnl,
      min_pnl: bt?.min_pnl,
      avg_win: bt?.avg_win,
      avg_loss: bt?.avg_loss,
    };
  };

  const getImageUrl = (path: string | undefined): string => {
    if (!path) return '';
    if (path.startsWith('http')) return path;
    if (path.startsWith('/screenshots/')) {
      if (window.location.hostname === 'localhost') {
        return `http://localhost:8000${path}`;
      }
      // 生产环境：使用 VITE_API_BASE（后端API地址），确保 /screenshots 走正确的服务
      const baseUrl = import.meta.env.VITE_API_BASE || window.location.origin;
      return `${baseUrl}${path}`;
    }
    const baseUrl = import.meta.env.VITE_API_BASE || '';
    return `${baseUrl}${path}`;
  };

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
          <VerificationBadge status={verificationStatus} />
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
        </div>
      </div>

      {/* 数据准备中提示（仅当后端返回 message 占位数据时显示） */}
      {!apiLoading && apiData && typeof apiData === 'object' && 'message' in apiData && (
        <div className="relative overflow-hidden rounded-xl border border-amber-500/20 bg-gradient-to-r from-amber-950/60 via-amber-900/30 to-amber-950/60 px-5 py-3.5">
          <div className="relative flex items-center gap-3">
            <AlertTriangle className="w-5 h-5 text-amber-400" />
            <div className="flex-1">
              <span className="text-sm font-semibold text-amber-300">{t('sentiment.dataPreparingTitle')}</span>
              <p className="text-sm text-amber-200/80 mt-0.5">{t('sentiment.dataPreparingDesc')}</p>
            </div>
          </div>
        </div>
      )}

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
      {activeTab === 'sentiment' && riskWarning && <RiskWarningBanner warning={translateRiskWarning(riskWarning)} />}

      {activeTab === 'sentiment' && (
        <div className="space-y-6">
          {/* Hero Dashboard */}
          <div className="card p-5 md:p-6">
            {loading ? (
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
                <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
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

                  {/* FNG + 市场偏向 */}
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

                  {/* 市场宽度 + BTC */}
                  <div className="flex flex-col justify-between bg-gray-900/40 rounded-2xl p-4 border border-white/5 space-y-4">
                    <div>
                      <div className="text-xs text-gray-500 mb-3 flex items-center gap-1.5">
                        <BarChart3 className="w-3.5 h-3.5 text-[#7ED7C4]" />
                        {t('sentiment.marketBreadth')}
                      </div>
                      <MarketBreadthMini up={breadth.up} down={breadth.down} flat={breadth.flat} />
                    </div>

                    <div className="grid grid-cols-2 gap-3">
                      <div className="bg-gray-800/50 rounded-xl p-3 border border-white/5">
                        <div className="flex items-center gap-1.5 mb-1">
                          <Bitcoin className="w-3.5 h-3.5 text-orange-400" />
                          <span className="text-[10px] text-gray-500">BTC 24h</span>
                        </div>
                        <div className={`text-lg font-bold ${btcChange24h != null ? (btcChange24h >= 0 ? 'text-emerald-400' : 'text-red-400') : 'text-gray-600'}`}>
                          {btcChange24h != null ? `${btcChange24h >= 0 ? '+' : ''}${btcChange24h.toFixed(2)}%` : '--'}
                        </div>
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
                </div>

                {/* 计数卡片 */}
                <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
                  <CountCard
                    label={t('sentiment.bullishTokens')}
                    count={bullish_count}
                    icon={TrendingUp}
                    colorClass="text-emerald-400"
                    active={(sentiment_index ?? 0) >= 70}
                  />
                  <CountCard
                    label={t('sentiment.neutralTokens')}
                    count={neutral_count}
                    icon={Minus}
                    colorClass="text-amber-400"
                    active={(sentiment_index ?? 0) >= 40 && (sentiment_index ?? 0) < 70}
                  />
                  <CountCard
                    label={t('sentiment.bearishTokens')}
                    count={bearish_count}
                    icon={TrendingDown}
                    colorClass="text-red-400"
                    active={(sentiment_index ?? 0) < 40}
                  />
                  <CountCard
                    label={t('sentiment.totalAnalyzed')}
                    count={(bullish_count ?? 0) + (neutral_count ?? 0) + (bearish_count ?? 0)}
                    icon={Layers}
                    colorClass="text-[#7ED7C4]"
                    active={false}
                  />
                </div>
              </div>
            )}
          </div>

          {/* 持仓建议 */}
          {positionReport || !loading ? (
            <div className="space-y-4">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <Target className="w-5 h-5 text-[#7ED7C4]" />
                  <h2 className="text-lg font-semibold text-white">{t('position.reportTitle')}</h2>
                </div>
                <VerificationBadge status={verificationStatus} />
              </div>
              <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                <PositionReportCard
                  title={t('position.daily')}
                  subtitle={t('position.dailyDesc')}
                  report={positionReport?.['1d']}
                  accentColor="#7ED7C4"
                />
                <PositionReportCard
                  title={t('position.fourHour')}
                  subtitle={t('position.fourHourDesc')}
                  report={positionReport?.['4h']}
                  accentColor="#4A9B8C"
                />
                <PositionReportCard
                  title={t('position.weekly')}
                  subtitle={t('position.weeklyDesc')}
                  report={positionReport?.['1w']}
                  accentColor="#2D6B5E"
                />
              </div>
            </div>
          ) : null}

          {/* 艾略特波浪分析 */}
          <div className="card p-5 mt-4">
            <div className="flex items-center justify-between mb-4">
              <div className="flex items-center gap-2">
                <TrendingUp className="w-5 h-5 text-[#7ED7C4]" />
                <h3 className="text-lg font-semibold text-white">艾略特波浪分析</h3>
              </div>
              <VerificationBadge status={verificationStatus} />
            </div>

            {/* 币种选择器 */}
            {availableEWSymbols.length > 0 && (
              <div className="flex flex-wrap gap-2 mb-3">
                {availableEWSymbols.map((item) => (
                  <button
                    key={item.symbol}
                    onClick={async () => {
                      setSelectedEWSymbol(item.symbol);
                      await loadElliottWaveForSymbol(item.symbol, (apiData?.decision?.timeframe ?? '1d'));
                    }}
                    className={`px-3 py-1 rounded-full text-xs font-medium transition ${
                      selectedEWSymbol === item.symbol
                        ? 'bg-[#7ED7C4] text-gray-900'
                        : 'bg-white/[0.05] text-gray-400 hover:bg-white/[0.1] hover:text-white'
                    }`}
                  >
                    {item.symbol}
                    {item.wave_pattern && (
                      <span className="ml-1 opacity-60">{item.wave_pattern}</span>
                    )}
                  </button>
                ))}
              </div>
            )}

            {elliottWaveData ? (
              <div className="space-y-4">
                {/* 图表 */}
                {(elliottWaveData as any).chart_path ? (
                  <div className="rounded-lg overflow-hidden border border-gray-800 bg-gray-900">
                    <img
                      src={getImageUrl((elliottWaveData as any).chart_path)}
                      alt={`Elliott Wave ${(elliottWaveData as any).wave_pattern ?? ''}`}
                      className="w-full h-auto"
                      style={{ display: 'block', minHeight: '200px' }}
                      onError={(e) => {
                        const target = e.target as HTMLImageElement;
                        target.style.display = 'none';
                        const parent = target.parentElement;
                        if (parent) {
                          parent.innerHTML = `<div class="text-sm text-gray-500 text-center py-8">图表加载失败，请刷新页面重试</div>`;
                        }
                      }}
                    />
                  </div>
                ) : (
                  <div className="text-sm text-gray-500 text-center py-8">
                    暂无艾略特波浪图表
                  </div>
                )}

                {/* 波浪信息 */}
                <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
                  <div className="bg-gray-800/50 rounded-lg p-3">
                    <div className="text-xs text-gray-500">浪型</div>
                    <div className="text-sm font-semibold text-white">{(elliottWaveData as any).wave_pattern ?? '--'}</div>
                  </div>
                  <div className="bg-gray-800/50 rounded-lg p-3">
                    <div className="text-xs text-gray-500">方向</div>
                    <div className={`text-sm font-semibold ${(elliottWaveData as any).direction === 'up' ? 'text-emerald-400' : 'text-red-400'}`}>
                      {(elliottWaveData as any).direction === 'up' ? '上涨' : (elliottWaveData as any).direction === 'down' ? '下跌' : '--'}
                    </div>
                  </div>
                  <div className="bg-gray-800/50 rounded-lg p-3">
                    <div className="text-xs text-gray-500">当前浪</div>
                    <div className="text-sm font-semibold text-white">
                      {typeof (elliottWaveData as any).current_wave === 'string'
                        ? (elliottWaveData as any).current_wave.replace(/_/g, ' ').replace(/\b\w/g, (l: string) => l.toUpperCase())
                        : (elliottWaveData as any).current_wave !== undefined
                          ? `Wave ${(elliottWaveData as any).current_wave}`
                          : '--'}
                    </div>
                  </div>
                  <div className="bg-gray-800/50 rounded-lg p-3">
                    <div className="text-xs text-gray-500">置信度</div>
                    <div className="text-sm font-semibold text-[#7ED7C4]">
                      {typeof (elliottWaveData as any).score === 'number' ? `${((elliottWaveData as any).score * 100).toFixed(0)}%` : '--'}
                    </div>
                  </div>
                </div>

                {/* 支撑与阻力位 */}
                {(() => {
                  const raw = (elliottWaveData as any).raw;
                  const projections = raw?.kimi_analysis?.projections || raw?.projections || (elliottWaveData as any).projections || [];
                  const firstProj = projections[0];
                  const supportLevels = firstProj?.support_levels || [];
                  const resistanceLevels = firstProj?.resistance_levels || [];
                  if (supportLevels.length === 0 && resistanceLevels.length === 0) return null;
                  return (
                    <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                      {supportLevels.length > 0 && (
                        <div className="bg-gray-800/50 rounded-lg p-3">
                          <div className="text-xs text-gray-500">支撑位</div>
                          <div className="text-sm font-semibold text-emerald-400">
                            {supportLevels.map((l: number) => `$${l.toLocaleString?.() || l}`).join(', ')}
                          </div>
                        </div>
                      )}
                      {resistanceLevels.length > 0 && (
                        <div className="bg-gray-800/50 rounded-lg p-3">
                          <div className="text-xs text-gray-500">阻力位</div>
                          <div className="text-sm font-semibold text-red-400">
                            {resistanceLevels.map((l: number) => `$${l.toLocaleString?.() || l}`).join(', ')}
                          </div>
                        </div>
                      )}
                    </div>
                  );
                })()}

                {/* Annotations 点评 */}
                {(() => {
                  const raw = (elliottWaveData as any).raw;
                  const annotations = raw?.kimi_analysis?.annotations || raw?.annotations || (elliottWaveData as any).annotations;
                  if (!annotations) return null;
                  return (
                    <div className="bg-gray-800/30 rounded-lg p-3">
                      <div className="text-xs text-gray-500 mb-1">AI 点评</div>
                      <div className="text-sm text-gray-300 leading-relaxed">{annotations}</div>
                    </div>
                  );
                })()}

                {/* 走势预测 */}
                {(elliottWaveData as any).projections && (elliottWaveData as any).projections.length > 0 && (
                  <div className="bg-gray-800/30 rounded-lg p-3 space-y-2">
                    <div className="text-xs text-gray-500">走势预测</div>
                    <div className="grid grid-cols-1 md:grid-cols-3 gap-2 mt-2">
                      {(elliottWaveData as any).projections.map((proj: any, pidx: number) => (
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
                          <div className="text-sm text-white mt-0.5">{proj.description ?? '--'}</div>
                          <div className="text-sm font-semibold text-[#7ED7C4]">
                            ${proj.target_price?.toLocaleString?.() || proj.target_price || '--'}
                          </div>
                        </div>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            ) : (
              <div className="text-sm text-gray-500 text-center py-8">
                暂无链上艾略特波浪数据
              </div>
            )}
          </div>

          {/* 形态信号检测 */}
          <SignalDetectionTable signals={signals} backtest_results={backtestResults} loading={loading} verificationStatus={verificationStatus} />

          {/* 币种分析表格 */}
          <div className="card p-5">
            <div className="flex items-center justify-between mb-4">
              <div className="flex items-center gap-2">
                <LineChart className="w-5 h-5 text-[#7ED7C4]" />
                <h2 className="text-lg font-semibold text-white">{t('sentiment.fullTokenAnalysis')}</h2>
                <span className="ml-2 text-xs text-gray-500">{symbolScores.length} {t('common.tokensCount')}</span>
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
            ) : symbolScores.length > 0 ? (
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
                    {symbolScores.map((token: any) => {
                      const change24h = token.change_24h ?? token.price_change_24h ?? 0;
                      return (
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
                        <td className={`py-2.5 px-3 text-right font-medium font-mono ${change24h >= 0 ? 'text-emerald-400' : 'text-red-400'}`}>
                          <span className="inline-flex items-center gap-0.5">
                            {change24h > 0 ? <ChevronUp className="w-3 h-3" /> :
                             change24h < 0 ? <ChevronDown className="w-3 h-3" /> : null}
                            {Math.abs(change24h).toFixed(2)}%
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
                    );})}
                  </tbody>
                </table>
              </div>
            ) : (
              <div className="text-gray-500 text-sm py-8 text-center">{t('dashboard.noMarketData')}</div>
            )}
          </div>
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

          {/* 回测数据 - 所有币种 */}
          {allBacktestData.length > 0 ? (
            <div className="space-y-4">
              <div className="card p-5">
                <div className="flex items-center justify-between mb-4">
                  <div className="flex items-center gap-2">
                    <LineChart className="w-5 h-5 text-[#7ED7C4]" />
                    <h2 className="text-lg font-semibold text-white">{t('backtest.recommendedSignals')}</h2>
                  </div>
                  <VerificationBadge status={verificationStatus} />
                </div>
                <div className="space-y-4">
                  {allBacktestData.map((bt) => {
                    const stats = getBacktestStats(bt);
                    return (
                    <div key={bt.key} className="bg-white/[0.03] rounded-lg p-4">
                      <div className="flex items-center gap-2 mb-3">
                        <span className="font-bold text-white">{(bt as any).symbol ?? bt.key.split('_')[0] ?? 'BTC'}</span>
                        <span className="text-xs text-gray-500">{(bt as any).timeframe ?? bt.key.split('_')[1] ?? '1d'}</span>
                      </div>
                      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
                        <div className="bg-gray-800/50 rounded-xl p-3 border border-white/5">
                          <div className="text-[10px] text-gray-500 mb-1">{t('backtest.winRate')}</div>
                          <div className={`text-lg font-bold ${stats.win_rate == null ? 'text-gray-500' : (stats.win_rate ?? 0) >= 50 ? 'text-emerald-400' : 'text-red-400'}`}>
                            {stats.win_rate == null ? '—' : `${(stats.win_rate ?? 0).toFixed(1)}%`}
                          </div>
                        </div>
                        <div className="bg-gray-800/50 rounded-xl p-3 border border-white/5">
                          <div className="text-[10px] text-gray-500 mb-1">{t('backtest.avgNetPnl')}</div>
                          <div className={`text-lg font-bold ${stats.avg_pnl == null ? 'text-gray-500' : (stats.avg_pnl ?? 0) >= 0 ? 'text-emerald-400' : 'text-red-400'}`}>
                            {stats.avg_pnl == null ? '—' : `${(stats.avg_pnl ?? 0) >= 0 ? '+' : ''}${(stats.avg_pnl ?? 0).toFixed(2)}%`}
                          </div>
                        </div>
                        <div className="bg-gray-800/50 rounded-xl p-3 border border-white/5">
                          <div className="text-[10px] text-gray-500 mb-1">{t('backtest.profitFactor')}</div>
                          <div className="text-lg font-bold text-white">
                            {stats.profit_factor == null || stats.profit_factor === 999.99 ? '∞' : (stats.profit_factor ?? 0).toFixed(2)}
                          </div>
                        </div>
                        <div className="bg-gray-800/50 rounded-xl p-3 border border-white/5">
                          <div className="text-[10px] text-gray-500 mb-1">{t('backtest.signals')}</div>
                          <div className="text-lg font-bold text-white">{stats.total_signals ?? 0}</div>
                        </div>
                        <div className="bg-gray-800/50 rounded-xl p-3 border border-white/5">
                          <div className="text-[10px] text-gray-500 mb-1">Max PnL</div>
                          <div className="text-lg font-bold text-emerald-400">
                            +{(stats.max_pnl ?? 0).toFixed(2)}%
                          </div>
                        </div>
                        <div className="bg-gray-800/50 rounded-xl p-3 border border-white/5">
                          <div className="text-[10px] text-gray-500 mb-1">Min PnL</div>
                          <div className="text-lg font-bold text-red-400">
                            {(stats.min_pnl ?? 0).toFixed(2)}%
                          </div>
                        </div>
                        <div className="bg-gray-800/50 rounded-xl p-3 border border-white/5">
                          <div className="text-[10px] text-gray-500 mb-1">Avg Win</div>
                          <div className="text-lg font-bold text-emerald-400">
                            {(stats.avg_win ?? 0) >= 0 ? '+' : ''}{(stats.avg_win ?? 0).toFixed(2)}%
                          </div>
                        </div>
                        <div className="bg-gray-800/50 rounded-xl p-3 border border-white/5">
                          <div className="text-[10px] text-gray-500 mb-1">Avg Loss</div>
                          <div className="text-lg font-bold text-red-400">
                            {(stats.avg_loss ?? 0).toFixed(2)}%
                          </div>
                        </div>
                      </div>
                      {(bt as any).current_signal && (
                        <div className="mt-3 space-y-2">
                          <div className="grid grid-cols-2 md:grid-cols-4 gap-2 text-xs">
                            <div>
                              <span className="text-gray-500">{t('backtest.recommendedAction')}</span>
                              <div className="font-medium">
                                <span className={`px-1.5 py-0.5 rounded ${getBacktestActionStyle((bt as any).current_signal.recommendation?.action)}`}>
                                  {(bt as any).current_signal.recommendation?.action === 'strong_long' || (bt as any).current_signal.recommendation?.action === 'long' ? t('trade.long') :
                                   (bt as any).current_signal.recommendation?.action === 'strong_short' || (bt as any).current_signal.recommendation?.action === 'short' ? t('trade.short') :
                                   t('trade.wait')}
                                </span>
                              </div>
                            </div>
                            <div>
                              <span className="text-gray-500">{t('backtest.confidence')}</span>
                              <div className="font-medium">
                                <span className={`inline-flex items-center px-1.5 py-0.5 rounded border text-[10px] ${getConfidenceStyle((bt as any).current_signal.recommendation?.confidence)}`}>
                                  {t(getConfidenceLabel((bt as any).current_signal.recommendation?.confidence))}
                                </span>
                              </div>
                            </div>
                            <div>
                              <span className="text-gray-500">{t('backtest.score')}</span>
                              <div className={`font-medium ${((bt as any).current_signal.recommendation?.score ?? 0) >= 80 ? 'text-emerald-400' : ((bt as any).current_signal.recommendation?.score ?? 0) >= 50 ? 'text-amber-400' : 'text-red-400'}`}>
                                {((bt as any).current_signal.recommendation?.score ?? 0).toFixed(0)}
                              </div>
                            </div>
                          </div>
                        </div>
                      )}
                      <StatsAccordion stats={(bt as any).stats} />
                    </div>
                  );})}
                </div>
              </div>

              {/* 最近信号表格 */}
              <RecentSignalsTable signals={allRecentSignals} loading={loading} />
            </div>
          ) : (
            <div className="card p-8 text-center text-gray-500">
              <LineChart className="w-10 h-10 mx-auto mb-3 opacity-30" />
              <p className="text-sm">{t('backtest.noRecommendedData')}</p>
              <p className="text-xs text-gray-600 mt-1">Waiting for sentiment analysis, data will load automatically</p>
            </div>
          )}

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
