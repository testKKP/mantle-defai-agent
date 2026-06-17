import { useState, useEffect, useMemo } from 'react';
import { useTranslation } from 'react-i18next';
import { useAccount } from 'wagmi';
import {
  Radio,
  Lock,
  Unlock,
  Link,
  Calendar,
  CheckCircle2,
  XCircle,
  AlertCircle,
  ChevronDown,
  Clock,
  Shield,
  TrendingUp,
  TrendingDown,
  Activity,
  BarChart3,
  Waves,
  Filter,
} from 'lucide-react';
import { useRegistry } from '../hooks/useRegistry';
import { getRecentOnChainSignals } from '../services/api';
import type { OnChainSignal } from '../types';

/* ───────────────────────────────
   Helpers
   ─────────────────────────────── */
function ShimmerBox({ className = '' }: { className?: string }) {
  return <div className={`shimmer rounded-lg ${className}`} />;
}

function StatusBadge({ active, label }: { active: boolean; label: string }) {
  return (
    <span
      className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium border ${
        active
          ? 'bg-emerald-500/10 text-emerald-400 border-emerald-500/20'
          : 'bg-red-500/10 text-red-400 border-red-500/20'
      }`}
    >
      {active ? <CheckCircle2 className="w-3.5 h-3.5" /> : <XCircle className="w-3.5 h-3.5" />}
      {label}
    </span>
  );
}

function DirectionBadge({ direction }: { direction?: string }) {
  const d = (direction || '').toLowerCase();
  const isLong = d === 'long' || d.includes('bull');
  const isShort = d === 'short' || d.includes('bear');
  return (
    <span
      className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium ${
        isLong
          ? 'bg-emerald-500/10 text-emerald-400'
          : isShort
            ? 'bg-red-500/10 text-red-400'
            : 'bg-amber-500/10 text-amber-400'
      }`}
    >
      {isLong ? <TrendingUp className="w-3 h-3" /> : isShort ? <TrendingDown className="w-3 h-3" /> : null}
      {direction || '—'}
    </span>
  );
}

function ConfidenceBadge({ confidence }: { confidence?: string }) {
  const c = (confidence || '').toLowerCase();
  return (
    <span
      className={`inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium ${
        c === 'high'
          ? 'bg-emerald-500/10 text-emerald-400'
          : c === 'medium'
            ? 'bg-amber-500/10 text-amber-400'
            : 'bg-gray-500/10 text-gray-400'
      }`}
    >
      {confidence || '—'}
    </span>
  );
}

function useSignalData(signal: OnChainSignal) {
  const raw = signal.data as unknown;
  if (raw && typeof raw === 'object') return raw as OnChainSignal['data'];
  if (typeof raw === 'string') {
    try {
      return JSON.parse(raw) as OnChainSignal['data'];
    } catch {
      return undefined;
    }
  }
  return undefined;
}

function SignalCard({ signal }: { signal: OnChainSignal }) {
  const { t } = useTranslation();
  const data = useSignalData(signal);
  const decision = data?.decision;
  const ew = data?.elliott_wave;
  const bt = data?.backtest;
  const sentiment = data?.sentiment;
  const submittedAt = signal.created_at
    ? new Date(signal.created_at).toLocaleString()
    : signal.timestamp
      ? new Date(signal.timestamp * 1000).toLocaleString()
      : '—';

  return (
    <div className="bg-[#0a0e17] border border-white/10 rounded-lg p-4 space-y-4">
      {/* Header */}
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-3">
          <span className="text-lg font-semibold text-white">{signal.symbol || decision?.symbol || '—'}</span>
          <span className="px-2 py-0.5 rounded-md bg-white/5 text-gray-300 text-xs font-medium border border-white/10">
            {signal.timeframe || decision?.timeframe || '—'}
          </span>
          <DirectionBadge direction={decision?.direction} />
          <ConfidenceBadge confidence={decision?.confidence} />
        </div>
        <a
          href={`https://sepolia.mantlescan.xyz/tx/${signal.tx_hash}`}
          target="_blank"
          rel="noopener noreferrer"
          className="inline-flex items-center gap-1.5 text-xs text-[#7ED7C4] hover:text-[#4A9B8C] transition"
        >
          <Link className="w-3.5 h-3.5" />
          {signal.tx_hash ? `${signal.tx_hash.slice(0, 10)}...${signal.tx_hash.slice(-8)}` : '—'}
        </a>
      </div>

      {/* Decision reason */}
      {decision?.reason && (
        <div className="text-sm">
          <span className="text-gray-500 text-xs block mb-1">{t('onchainSignals.reason', 'Reason')}</span>
          <p className="text-gray-200 leading-relaxed">{decision.reason}</p>
        </div>
      )}

      {/* Elliott Wave */}
      {ew ? (
        <div className="border-t border-white/5 pt-3">
          <div className="flex items-center gap-2 mb-2">
            <Waves className="w-4 h-4 text-[#7ED7C4]" />
            <h4 className="text-sm font-medium text-white">{t('onchainSignals.elliottWave', 'Elliott Wave')}</h4>
          </div>
          <div className="grid grid-cols-2 md:grid-cols-3 gap-3 text-sm">
            {ew.wave_pattern && (
              <div>
                <span className="text-gray-500 text-xs block">{t('onchainSignals.wavePattern', 'Wave Pattern')}</span>
                <span className="text-gray-200 font-medium">{ew.wave_pattern}</span>
              </div>
            )}
            {ew.current_wave && (
              <div>
                <span className="text-gray-500 text-xs block">{t('onchainSignals.currentWave', 'Current Wave')}</span>
                <span className="text-gray-200 font-medium">{ew.current_wave}</span>
              </div>
            )}
            {ew.direction && (
              <div>
                <span className="text-gray-500 text-xs block">{t('onchainSignals.waveDirection', 'Direction')}</span>
                <span className="text-gray-200 font-medium">{ew.direction}</span>
              </div>
            )}
          </div>
          {ew.projections && ew.projections.length > 0 && (
            <div className="mt-3">
              <span className="text-gray-500 text-xs block mb-2">{t('onchainSignals.projections', 'Projections')}</span>
              <div className="space-y-2">
                {ew.projections.map((proj, idx) => (
                  <div key={idx} className="flex flex-wrap items-center gap-3 bg-white/5 rounded px-3 py-2 text-xs">
                    {proj.scenario && (
                      <span
                        className={`px-2 py-0.5 rounded-full font-medium ${
                          (proj.scenario || '').toLowerCase().includes('bull')
                            ? 'bg-emerald-500/10 text-emerald-400'
                            : (proj.scenario || '').toLowerCase().includes('bear')
                              ? 'bg-red-500/10 text-red-400'
                              : 'bg-gray-500/10 text-gray-400'
                        }`}
                      >
                        {proj.scenario}
                      </span>
                    )}
                    {proj.target_price !== undefined && (
                      <span className="text-gray-300">
                        Target: <span className="text-gray-200 font-medium">{proj.target_price}</span>
                      </span>
                    )}
                    {proj.stop_loss !== undefined && (
                      <span className="text-gray-300">
                        Stop: <span className="text-gray-200 font-medium">{proj.stop_loss}</span>
                      </span>
                    )}
                    {proj.confidence !== undefined && (
                      <span className="text-gray-300">
                        Conf: <span className="text-gray-200 font-medium">{proj.confidence}</span>
                      </span>
                    )}
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      ) : (
        <div className="border-t border-white/5 pt-3">
          <div className="flex items-center gap-2 mb-2">
            <Waves className="w-4 h-4 text-[#7ED7C4]" />
            <h4 className="text-sm font-medium text-white">{t('onchainSignals.elliottWave', 'Elliott Wave')}</h4>
          </div>
          <p className="text-sm text-gray-500">
            {t('onchainSignals.noElliottWave', 'No Elliott Wave analysis available for this signal.')}
          </p>
        </div>
      )}

      {/* Backtest */}
      {bt && (
        <div className="border-t border-white/5 pt-3">
          <div className="flex items-center gap-2 mb-2">
            <BarChart3 className="w-4 h-4 text-[#7ED7C4]" />
            <h4 className="text-sm font-medium text-white">{t('onchainSignals.backtest', 'Backtest')}</h4>
          </div>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3 text-sm">
            {bt.win_rate !== undefined && (
              <div>
                <span className="text-gray-500 text-xs block">{t('onchainSignals.winRate', 'Win Rate')}</span>
                <span
                  className={`font-medium ${
                    bt.win_rate > 60 ? 'text-emerald-400' : bt.win_rate >= 40 ? 'text-amber-400' : 'text-red-400'
                  }`}
                >
                  {bt.win_rate}%
                </span>
              </div>
            )}
            {bt.avg_pnl !== undefined && (
              <div>
                <span className="text-gray-500 text-xs block">{t('onchainSignals.avgPnl', 'Avg PnL')}</span>
                <span className="text-gray-200 font-medium">{bt.avg_pnl}</span>
              </div>
            )}
            {bt.profit_factor !== undefined && (
              <div>
                <span className="text-gray-500 text-xs block">{t('onchainSignals.profitFactor', 'Profit Factor')}</span>
                <span className="text-gray-200 font-medium">{bt.profit_factor}</span>
              </div>
            )}
            {bt.total_signals !== undefined && (
              <div>
                <span className="text-gray-500 text-xs block">{t('onchainSignals.totalSignals', 'Total Signals')}</span>
                <span className="text-gray-200 font-medium">{bt.total_signals}</span>
              </div>
            )}
          </div>
        </div>
      )}

      {/* Sentiment */}
      {sentiment && (
        <div className="border-t border-white/5 pt-3">
          <div className="flex items-center gap-2 mb-2">
            <Activity className="w-4 h-4 text-[#7ED7C4]" />
            <h4 className="text-sm font-medium text-white">{t('onchainSignals.sentiment', 'Sentiment')}</h4>
          </div>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3 text-sm">
            {sentiment.sentiment_index !== undefined && (
              <div>
                <span className="text-gray-500 text-xs block">{t('onchainSignals.sentimentIndex', 'Sentiment Index')}</span>
                <div className="mt-1">
                  <span className="text-gray-200 font-medium">{sentiment.sentiment_index}</span>
                  <div className="mt-1 h-1.5 w-full bg-white/10 rounded-full overflow-hidden">
                    <div
                      className="h-full bg-[#7ED7C4] rounded-full"
                      style={{ width: `${Math.min(100, Math.max(0, sentiment.sentiment_index))}%` }}
                    />
                  </div>
                </div>
              </div>
            )}
            {sentiment.market_bias && (
              <div>
                <span className="text-gray-500 text-xs block">{t('onchainSignals.marketBias', 'Market Bias')}</span>
                <span
                  className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium ${
                    (sentiment.market_bias || '').toLowerCase().includes('bull')
                      ? 'bg-emerald-500/10 text-emerald-400'
                      : (sentiment.market_bias || '').toLowerCase().includes('bear')
                        ? 'bg-red-500/10 text-red-400'
                        : 'bg-gray-500/10 text-gray-400'
                  }`}
                >
                  {sentiment.market_bias}
                </span>
              </div>
            )}
            {sentiment.bullish_count !== undefined && (
              <div>
                <span className="text-gray-500 text-xs block">{t('onchainSignals.bullishCount', 'Bullish')}</span>
                <span className="text-gray-200 font-medium">{sentiment.bullish_count}</span>
              </div>
            )}
            {sentiment.bearish_count !== undefined && (
              <div>
                <span className="text-gray-500 text-xs block">{t('onchainSignals.bearishCount', 'Bearish')}</span>
                <span className="text-gray-200 font-medium">{sentiment.bearish_count}</span>
              </div>
            )}
            {sentiment.neutral_count !== undefined && (
              <div>
                <span className="text-gray-500 text-xs block">{t('onchainSignals.neutralCount', 'Neutral')}</span>
                <span className="text-gray-200 font-medium">{sentiment.neutral_count}</span>
              </div>
            )}
            {sentiment.total_analyzed !== undefined && (
              <div>
                <span className="text-gray-500 text-xs block">{t('onchainSignals.totalAnalyzed', 'Total Analyzed')}</span>
                <span className="text-gray-200 font-medium">{sentiment.total_analyzed}</span>
              </div>
            )}
          </div>
        </div>
      )}

      {/* Footer */}
      <div className="border-t border-white/5 pt-3 flex items-center gap-2 text-xs text-gray-500">
        <Clock className="w-3.5 h-3.5" />
        <span>
          {t('onchainSignals.submittedAt', 'Submitted At')}: {submittedAt}
        </span>
      </div>
    </div>
  );
}

const SYMBOLS = ['BTC', 'ETH', 'MNT', 'SOL', 'ARB'];
const TIMEFRAMES = ['1h', '4h', '1d', '1w'];

/* ───────────────────────────────
   Main Component
   ─────────────────────────────── */
export default function OnChainSignals() {
  const { t } = useTranslation();
  const { isConnected } = useAccount();
  const {
    registryAddress,
    isSubscribedLoading,
    subscription,
    subscriptionLoading,
    subscribe,
    isSubscribing,
    isConfirming,
    subscribeError,
  } = useRegistry();

  const [signals, setSignals] = useState<OnChainSignal[]>([]);
  const [signalsLoading, setSignalsLoading] = useState(false);
  const [signalsError, setSignalsError] = useState<string | null>(null);
  const [symbolFilter, setSymbolFilter] = useState('All');
  const [timeframeFilter, setTimeframeFilter] = useState('All');

  useEffect(() => {
    let cancelled = false;
    async function loadSignals() {
      setSignalsLoading(true);
      setSignalsError(null);
      try {
        const data = await getRecentOnChainSignals(50);
        if (!cancelled) setSignals(data);
      } catch (e) {
        if (!cancelled) {
          setSignalsError(
            e instanceof Error ? e.message : t('onchainSignals.loadError', 'Failed to load on-chain signals')
          );
        }
      } finally {
        if (!cancelled) setSignalsLoading(false);
      }
    }
    loadSignals();
    return () => {
      cancelled = true;
    };
  }, [t]);

  const filteredSignals = useMemo(() => {
    return signals.filter((s) => {
      if (symbolFilter !== 'All' && s.symbol !== symbolFilter) return false;
      if (timeframeFilter !== 'All' && s.timeframe !== timeframeFilter) return false;
      return true;
    });
  }, [signals, symbolFilter, timeframeFilter]);

  const expiryDate = useMemo(() => {
    if (!subscription || !subscription[0]) return null;
    const expirySec = Number(subscription[0]);
    if (expirySec === 0) return null;
    return new Date(expirySec * 1000);
  }, [subscription]);

  const isSubscriptionActive = subscription ? subscription[2] : false;
  const loadingSubscription = isSubscribedLoading || subscriptionLoading;

  return (
    <div className="space-y-6 p-4 md:p-6 max-w-7xl mx-auto">
      {/* Header */}
      <div className="flex items-center gap-3">
        <div className="w-10 h-10 rounded-lg bg-[#2D6B5E]/20 flex items-center justify-center">
          <Radio className="w-5 h-5 text-[#7ED7C4]" />
        </div>
        <div>
          <h2 className="text-lg font-semibold text-white">{t('onchainSignals.pageTitle')}</h2>
          <p className="text-sm text-gray-400">{t('onchainSignals.pageSubtitle')}</p>
        </div>
        {!registryAddress && (
          <span className="ml-auto inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-medium bg-amber-500/10 text-amber-400 border border-amber-500/20">
            <AlertCircle className="w-3.5 h-3.5" />
            {t('onchainSignals.comingSoon')}
          </span>
        )}
      </div>

      {/* Testnet Beta Notice */}
      <div className="rounded-lg border border-amber-500/20 bg-amber-500/10 p-4 flex items-start gap-3">
        <AlertCircle className="w-5 h-5 text-amber-400 flex-shrink-0 mt-0.5" />
        <div>
          <h3 className="text-sm font-semibold text-amber-300">
            {t('onchainSignals.testnetBetaTitle', 'Testnet Beta')}
          </h3>
          <p className="text-sm text-amber-200/80 mt-1">
            {t(
              'onchainSignals.testnetBetaDescription',
              'Signals are publicly visible during testing. Subscription is optional in this beta phase.'
            )}
          </p>
        </div>
      </div>

      {/* Subscription Panel */}
      <div className="card p-5">
        <div className="flex items-center gap-2 mb-4">
          <Shield className="w-4 h-4 text-[#7ED7C4]" />
          <h3 className="font-semibold text-white">{t('onchainSignals.subscribed')}</h3>
        </div>

        {!isConnected ? (
          <div className="flex items-center gap-3 py-4 text-gray-400">
            <Lock className="w-5 h-5" />
            <span>{t('wallet.connectToViewFull')}</span>
          </div>
        ) : loadingSubscription ? (
          <div className="space-y-3">
            <ShimmerBox className="h-6 w-40" />
            <ShimmerBox className="h-6 w-56" />
            <ShimmerBox className="h-10 w-32" />
          </div>
        ) : !registryAddress ? (
          <div className="flex items-center gap-3 py-4 text-amber-400">
            <AlertCircle className="w-5 h-5" />
            <span>{t('onchainSignals.contractNotDeployed')}</span>
          </div>
        ) : (
          <div className="space-y-4">
            <div className="flex flex-wrap items-center gap-4">
              <StatusBadge
                active={!!isSubscriptionActive}
                label={isSubscriptionActive ? t('onchainSignals.subscribed') : t('onchainSignals.notSubscribed')}
              />
              {expiryDate && isSubscriptionActive && (
                <span className="inline-flex items-center gap-1.5 text-sm text-gray-300">
                  <Calendar className="w-4 h-4 text-gray-400" />
                  {t('onchainSignals.expiry')}: {expiryDate.toLocaleDateString()}
                </span>
              )}
            </div>

            {!isSubscriptionActive && (
              <div className="flex flex-wrap items-center gap-3">
                <button
                  onClick={subscribe}
                  disabled={isSubscribing || isConfirming}
                  className="flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium text-white mantle-gradient hover:opacity-90 transition shadow-lg shadow-[#2D6B5E]/20 disabled:opacity-50"
                >
                  <Unlock className="w-4 h-4" />
                  {isSubscribing
                    ? t('common.loading')
                    : isConfirming
                      ? t('onchainSignals.confirming')
                      : `${t('onchainSignals.subscribe')} (${t('onchainSignals.price')})`}
                </button>
                <span className="text-xs text-gray-500">{t('onchainSignals.price')}</span>
              </div>
            )}

            {subscribeError && (
              <div className="text-sm text-red-400 flex items-center gap-2">
                <AlertCircle className="w-4 h-4" />
                {subscribeError.message}
              </div>
            )}
          </div>
        )}
      </div>

      {/* Signal Browser */}
      <div className="card p-5">
        <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-4 mb-4">
          <div className="flex items-center gap-2">
            <Link className="w-4 h-4 text-[#7ED7C4]" />
            <h3 className="font-semibold text-white">{t('onchainSignals.recentSignals', 'Recent On-Chain Signals')}</h3>
          </div>
          <div className="flex flex-wrap items-center gap-3">
            <div className="relative">
              <div className="relative">
                <Filter className="absolute left-3 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-gray-500" />
                <select
                  value={symbolFilter}
                  onChange={(e) => setSymbolFilter(e.target.value)}
                  className="appearance-none bg-[#0a0e17] border border-white/10 rounded-lg pl-9 pr-10 py-2 text-sm text-gray-200 focus:outline-none focus:border-[#4A9B8C] w-36"
                >
                  <option value="All">{t('onchainSignals.allSymbols', 'All Symbols')}</option>
                  {SYMBOLS.map((s) => (
                    <option key={s} value={s}>
                      {s}
                    </option>
                  ))}
                </select>
                <ChevronDown className="absolute right-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-500 pointer-events-none" />
              </div>
            </div>
            <div className="relative">
              <div className="relative">
                <Filter className="absolute left-3 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-gray-500" />
                <select
                  value={timeframeFilter}
                  onChange={(e) => setTimeframeFilter(e.target.value)}
                  className="appearance-none bg-[#0a0e17] border border-white/10 rounded-lg pl-9 pr-10 py-2 text-sm text-gray-200 focus:outline-none focus:border-[#4A9B8C] w-40"
                >
                  <option value="All">{t('onchainSignals.allTimeframes', 'All Timeframes')}</option>
                  {TIMEFRAMES.map((tf) => (
                    <option key={tf} value={tf}>
                      {tf}
                    </option>
                  ))}
                </select>
                <ChevronDown className="absolute right-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-500 pointer-events-none" />
              </div>
            </div>
          </div>
        </div>

        {signalsLoading ? (
          <div className="space-y-3 py-4">
            <ShimmerBox className="h-32" />
            <ShimmerBox className="h-32" />
            <ShimmerBox className="h-32" />
          </div>
        ) : signalsError ? (
          <div className="flex items-center justify-center gap-3 py-8 text-red-400 border border-dashed border-red-500/20 rounded-lg bg-red-500/5">
            <AlertCircle className="w-5 h-5" />
            <span>{signalsError}</span>
          </div>
        ) : filteredSignals.length === 0 ? (
          <div className="flex items-center justify-center py-8 text-gray-500 border border-dashed border-white/10 rounded-lg">
            <span>{t('onchainSignals.noSignals')}</span>
          </div>
        ) : (
          <div className="space-y-4">
            {filteredSignals.map((signal) => (
              <SignalCard key={signal.id} signal={signal} />
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
