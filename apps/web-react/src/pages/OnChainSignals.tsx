import { useState, useMemo, useCallback } from 'react';
import { useTranslation } from 'react-i18next';
import { useAccount } from 'wagmi';
import { useReadContract } from 'wagmi';
import {
  Radio,
  Lock,
  Unlock,
  Eye,
  EyeOff,
  Link,
  Calendar,
  CheckCircle2,
  XCircle,
  AlertCircle,
  ChevronDown,
  Hash,
  User,
  Clock,
  Shield,
  TrendingUp,
  TrendingDown,
  Activity,
  BarChart3,
  Waves,
} from 'lucide-react';
import { useRegistry } from '../hooks/useRegistry';
import { useSignalDecrypt } from '../hooks/useSignalDecrypt';
import { shortenAddress } from '../hooks/useWallet';
import registryAbi from '../abi/MantleDeFAIRegistry.json';

/* ───────────────────────────────
   Helpers
   ─────────────────────────────── */
function ShimmerBox({ className = '' }: { className?: string }) {
  return <div className={`shimmer rounded-lg ${className}`} />;
}

function hexToUtf8(hex: string): string {
  if (!hex || hex === '0x') return '';
  const clean = hex.startsWith('0x') ? hex.slice(2) : hex;
  try {
    const bytes = new Uint8Array(clean.length / 2);
    for (let i = 0; i < clean.length; i += 2) {
      bytes[i / 2] = parseInt(clean.substring(i, i + 2), 16);
    }
    return new TextDecoder().decode(bytes);
  } catch {
    return '';
  }
}

const SYMBOLS = ['BTC', 'ETH', 'MNT', 'SOL', 'ARB'];
const TIMEFRAMES = ['1h', '4h', '1d', '1w'];

/* ───────────────────────────────
   StatusBadge
   ─────────────────────────────── */
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

/* ───────────────────────────────
   Main Component
   ─────────────────────────────── */
export default function OnChainSignals() {
  const { t } = useTranslation();
  const { address, isConnected } = useAccount();
  const {
    registryAddress,
    isSubscribed,
    isSubscribedLoading,
    subscription,
    subscriptionLoading,
    subscribe,
    isSubscribing,
    isConfirming,
    subscribeError,
  } = useRegistry();

  const {
    decryptKey,
    fetchingKey,
    fetchError,
    fetchDecryptKey,
    decryptSignal,
  } = useSignalDecrypt();

  const [selectedSymbol, setSelectedSymbol] = useState('BTC');
  const [selectedTimeframe, setSelectedTimeframe] = useState('1d');
  const [showDecrypted, setShowDecrypted] = useState(false);
  const [decryptedResult, setDecryptedResult] = useState<ReturnType<typeof decryptSignal> | null>(null);

  const contractEnabled = !!registryAddress && !!address;

  // Signal count (public read)
  const signalCount = useReadContract({
    address: registryAddress || undefined,
    abi: registryAbi,
    functionName: 'getSignalCount',
    args: [selectedSymbol, selectedTimeframe],
    query: { enabled: !!registryAddress },
  });

  // Latest signal (only if subscribed)
  const latestSignal = useReadContract({
    address: registryAddress || undefined,
    abi: registryAbi,
    functionName: 'getLatestSignal',
    args: [selectedSymbol, selectedTimeframe],
    query: { enabled: contractEnabled && isSubscribed === true },
  });

  const signalData = latestSignal.data as
    | { encryptedData: string; dataHash: string; timestamp: bigint; submitter: string }
    | undefined;

  const countValue = signalCount.data as bigint | undefined;

  const expiryDate = useMemo(() => {
    if (!subscription || !subscription[0]) return null;
    const expirySec = Number(subscription[0]);
    if (expirySec === 0) return null;
    return new Date(expirySec * 1000);
  }, [subscription]);

  const isSubscriptionActive = subscription ? subscription[2] : false;

  const handleDecrypt = useCallback(async () => {
    if (!signalData || !address) return;

    let key = decryptKey;
    if (!key) {
      key = await fetchDecryptKey(address);
    }
    if (!key) return;

    const encryptedStr = hexToUtf8(signalData.encryptedData);
    const result = decryptSignal(encryptedStr, key);
    setDecryptedResult(result);
    setShowDecrypted(true);
  }, [signalData, address, decryptKey, fetchDecryptKey, decryptSignal]);

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
        <div className="flex items-center gap-2 mb-4">
          <Link className="w-4 h-4 text-[#7ED7C4]" />
          <h3 className="font-semibold text-white">{t('onchainSignals.latestSignal')}</h3>
        </div>

        <div className="flex flex-wrap gap-4 mb-4">
          {/* Symbol Select */}
          <div className="relative">
            <label className="block text-xs text-gray-500 mb-1.5">{t('onchainSignals.selectSymbol')}</label>
            <div className="relative">
              <select
                value={selectedSymbol}
                onChange={(e) => setSelectedSymbol(e.target.value)}
                className="appearance-none bg-[#0a0e17] border border-white/10 rounded-lg px-4 py-2 pr-10 text-sm text-gray-200 focus:outline-none focus:border-[#4A9B8C] w-32"
              >
                {SYMBOLS.map((s) => (
                  <option key={s} value={s}>
                    {s}
                  </option>
                ))}
              </select>
              <ChevronDown className="absolute right-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-500 pointer-events-none" />
            </div>
          </div>

          {/* Timeframe Select */}
          <div className="relative">
            <label className="block text-xs text-gray-500 mb-1.5">{t('onchainSignals.selectTimeframe')}</label>
            <div className="relative">
              <select
                value={selectedTimeframe}
                onChange={(e) => setSelectedTimeframe(e.target.value)}
                className="appearance-none bg-[#0a0e17] border border-white/10 rounded-lg px-4 py-2 pr-10 text-sm text-gray-200 focus:outline-none focus:border-[#4A9B8C] w-32"
              >
                {TIMEFRAMES.map((tf) => (
                  <option key={tf} value={tf}>
                    {tf}
                  </option>
                ))}
              </select>
              <ChevronDown className="absolute right-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-500 pointer-events-none" />
            </div>
          </div>

          {/* Signal Count */}
          <div>
            <label className="block text-xs text-gray-500 mb-1.5">{t('onchainSignals.signalCount')}</label>
            <div className="text-sm text-gray-200 font-medium py-2">
              {signalCount.isLoading ? (
                <ShimmerBox className="h-5 w-16" />
              ) : countValue !== undefined ? (
                <span className="bg-[#2D6B5E]/20 text-[#7ED7C4] px-3 py-1.5 rounded-lg text-sm font-semibold">
                  {countValue.toString()}
                </span>
              ) : (
                '--'
              )}
            </div>
          </div>
        </div>

        {/* Signal display area */}
        {!isConnected ? (
          <div className="flex items-center justify-center gap-3 py-8 text-gray-400 border border-dashed border-white/10 rounded-lg">
            <Lock className="w-5 h-5" />
            <span>{t('wallet.connectToViewFull')}</span>
          </div>
        ) : !isSubscriptionActive ? (
          <div className="flex items-center justify-center gap-3 py-8 text-amber-400 border border-dashed border-amber-500/20 rounded-lg bg-amber-500/5">
            <AlertCircle className="w-5 h-5" />
            <span>{t('onchainSignals.subscribePrompt')}</span>
          </div>
        ) : latestSignal.isLoading ? (
          <div className="space-y-3 py-4">
            <ShimmerBox className="h-6" />
            <ShimmerBox className="h-6" />
            <ShimmerBox className="h-6" />
          </div>
        ) : !signalData || !countValue || countValue === 0n ? (
          <div className="flex items-center justify-center py-8 text-gray-500 border border-dashed border-white/10 rounded-lg">
            <span>{t('onchainSignals.noSignals')}</span>
          </div>
        ) : (
          <div className="space-y-4">
            {/* Signal metadata */}
            <div className="grid grid-cols-1 md:grid-cols-2 gap-3 text-sm">
              <div className="flex items-center gap-2">
                <Hash className="w-4 h-4 text-gray-500" />
                <span className="text-gray-500">{t('onchainSignals.integrityHash')}:</span>
                <span className="text-gray-200 font-mono truncate">{signalData.dataHash}</span>
              </div>
              <div className="flex items-center gap-2">
                <User className="w-4 h-4 text-gray-500" />
                <span className="text-gray-500">{t('onchainSignals.submitter')}:</span>
                <span className="text-gray-200 font-mono">{shortenAddress(signalData.submitter)}</span>
              </div>
              <div className="flex items-center gap-2">
                <Clock className="w-4 h-4 text-gray-500" />
                <span className="text-gray-500">{t('onchainSignals.submittedAt')}:</span>
                <span className="text-gray-200">
                  {new Date(Number(signalData.timestamp) * 1000).toLocaleString()}
                </span>
              </div>
            </div>

            {/* Decrypt action */}
            {!showDecrypted ? (
              <div className="flex flex-wrap items-center gap-3 pt-2">
                <button
                  onClick={handleDecrypt}
                  disabled={fetchingKey || !signalData.encryptedData}
                  className="flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium text-white mantle-gradient hover:opacity-90 transition shadow-lg shadow-[#2D6B5E]/20 disabled:opacity-50"
                >
                  <Eye className="w-4 h-4" />
                  {fetchingKey ? t('common.loading') : t('onchainSignals.decrypt')}
                </button>
                {fetchError && (
                  <span className="text-sm text-red-400 flex items-center gap-1">
                    <AlertCircle className="w-4 h-4" />
                    {fetchError}
                  </span>
                )}
              </div>
            ) : (
              <div className="space-y-3">
                <div className="flex items-center gap-3">
                  <button
                    onClick={() => setShowDecrypted(false)}
                    className="flex items-center gap-2 px-3 py-1.5 rounded-lg text-sm bg-white/5 border border-white/10 hover:bg-white/10 transition"
                  >
                    <EyeOff className="w-4 h-4" />
                    {t('onchainSignals.hide')}
                  </button>
                </div>

                {decryptedResult && (
                  <div className="space-y-4">
                    {/* Decision Card */}
                    <div className="bg-[#0a0e17] border border-white/10 rounded-lg p-4">
                      <div className="flex items-center gap-2 mb-3">
                        <TrendingUp className="w-4 h-4 text-[#7ED7C4]" />
                        <h4 className="text-sm font-medium text-white">{t('onchainSignals.decision') || 'Decision'}</h4>
                      </div>
                      <div className="grid grid-cols-2 md:grid-cols-3 gap-3 text-sm">
                        <div>
                          <span className="text-gray-500 text-xs block">{t('onchainSignals.symbol') || 'Symbol'}</span>
                          <span className="text-gray-200 font-medium">{decryptedResult.decision.symbol || 'N/A'}</span>
                        </div>
                        <div>
                          <span className="text-gray-500 text-xs block">{t('onchainSignals.timeframe') || 'Timeframe'}</span>
                          <span className="text-gray-200 font-medium">{decryptedResult.decision.timeframe || 'N/A'}</span>
                        </div>
                        <div>
                          <span className="text-gray-500 text-xs block">{t('onchainSignals.direction') || 'Direction'}</span>
                          <span
                            className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium ${
                              decryptedResult.decision.direction.toLowerCase() === 'long' || decryptedResult.decision.direction.toLowerCase().includes('bull')
                                ? 'bg-emerald-500/10 text-emerald-400'
                                : decryptedResult.decision.direction.toLowerCase() === 'short' || decryptedResult.decision.direction.toLowerCase().includes('bear')
                                  ? 'bg-red-500/10 text-red-400'
                                  : 'bg-amber-500/10 text-amber-400'
                            }`}
                          >
                            {decryptedResult.decision.direction.toLowerCase() === 'long' ? (
                              <TrendingUp className="w-3 h-3" />
                            ) : decryptedResult.decision.direction.toLowerCase() === 'short' ? (
                              <TrendingDown className="w-3 h-3" />
                            ) : null}
                            {decryptedResult.decision.direction || 'N/A'}
                          </span>
                        </div>
                        <div>
                          <span className="text-gray-500 text-xs block">{t('onchainSignals.confidence') || 'Confidence'}</span>
                          <span className="text-gray-200 font-medium">{decryptedResult.decision.confidence || 'N/A'}</span>
                        </div>
                        <div className="col-span-2 md:col-span-2">
                          <span className="text-gray-500 text-xs block">{t('onchainSignals.reason') || 'Reason'}</span>
                          <span className="text-gray-200 font-medium">{decryptedResult.decision.reason || 'N/A'}</span>
                        </div>
                      </div>
                    </div>

                    {/* Elliott Wave Card */}
                    {decryptedResult.elliott_wave && (
                      <div className="bg-[#0a0e17] border border-white/10 rounded-lg p-4">
                        <div className="flex items-center gap-2 mb-3">
                          <Waves className="w-4 h-4 text-[#7ED7C4]" />
                          <h4 className="text-sm font-medium text-white">{t('onchainSignals.elliottWave') || 'Elliott Wave'}</h4>
                        </div>
                        <div className="grid grid-cols-2 gap-3 text-sm mb-3">
                          {decryptedResult.elliott_wave.wave_pattern && (
                            <div>
                              <span className="text-gray-500 text-xs block">{t('onchainSignals.wavePattern') || 'Wave Pattern'}</span>
                              <span className="text-gray-200 font-medium">{decryptedResult.elliott_wave.wave_pattern}</span>
                            </div>
                          )}
                          <div>
                            <span className="text-gray-500 text-xs block">{t('onchainSignals.currentWave') || 'Current Wave'}</span>
                            <span className="text-gray-200 font-medium">{decryptedResult.elliott_wave.current_wave || 'N/A'}</span>
                          </div>
                          <div>
                            <span className="text-gray-500 text-xs block">{t('onchainSignals.waveDirection') || 'Direction'}</span>
                            <span className="text-gray-200 font-medium">{decryptedResult.elliott_wave.direction || 'N/A'}</span>
                          </div>
                        </div>
                        {decryptedResult.elliott_wave.projections && decryptedResult.elliott_wave.projections.length > 0 && (
                          <div>
                            <span className="text-gray-500 text-xs block mb-2">{t('onchainSignals.projections') || 'Projections'}</span>
                            <div className="space-y-2">
                              {decryptedResult.elliott_wave.projections.map((proj, idx) => (
                                <div key={idx} className="flex flex-wrap items-center gap-3 bg-white/5 rounded px-3 py-2 text-xs">
                                  <span
                                    className={`px-2 py-0.5 rounded-full font-medium ${
                                      (proj.scenario || '').toLowerCase().includes('bull')
                                        ? 'bg-emerald-500/10 text-emerald-400'
                                        : (proj.scenario || '').toLowerCase().includes('bear')
                                          ? 'bg-red-500/10 text-red-400'
                                          : 'bg-gray-500/10 text-gray-400'
                                    }`}
                                  >
                                    {proj.scenario || 'N/A'}
                                  </span>
                                  <span className="text-gray-300">
                                    Target: <span className="text-gray-200 font-medium">{proj.target_price}</span>
                                  </span>
                                  <span className="text-gray-300">
                                    Stop: <span className="text-gray-200 font-medium">{proj.stop_loss}</span>
                                  </span>
                                  <span className="text-gray-300">
                                    Conf: <span className="text-gray-200 font-medium">{proj.confidence}</span>
                                  </span>
                                </div>
                              ))}
                            </div>
                          </div>
                        )}
                      </div>
                    )}

                    {/* Backtest Card */}
                    {decryptedResult.backtest && (
                      <div className="bg-[#0a0e17] border border-white/10 rounded-lg p-4">
                        <div className="flex items-center gap-2 mb-3">
                          <BarChart3 className="w-4 h-4 text-[#7ED7C4]" />
                          <h4 className="text-sm font-medium text-white">{t('onchainSignals.backtest') || 'Backtest'}</h4>
                        </div>
                        <div className="grid grid-cols-2 md:grid-cols-4 gap-3 text-sm">
                          <div>
                            <span className="text-gray-500 text-xs block">{t('onchainSignals.winRate') || 'Win Rate'}</span>
                            <span className={`font-medium ${
                              decryptedResult.backtest.win_rate !== undefined
                                ? decryptedResult.backtest.win_rate > 60
                                  ? 'text-emerald-400'
                                  : decryptedResult.backtest.win_rate >= 40
                                    ? 'text-amber-400'
                                    : 'text-red-400'
                                : 'text-gray-200'
                            }`}>
                              {decryptedResult.backtest.win_rate !== undefined ? `${decryptedResult.backtest.win_rate}%` : 'N/A'}
                            </span>
                          </div>
                          <div>
                            <span className="text-gray-500 text-xs block">{t('onchainSignals.avgPnl') || 'Avg PnL'}</span>
                            <span className="text-gray-200 font-medium">{decryptedResult.backtest.avg_pnl !== undefined ? decryptedResult.backtest.avg_pnl : 'N/A'}</span>
                          </div>
                          <div>
                            <span className="text-gray-500 text-xs block">{t('onchainSignals.profitFactor') || 'Profit Factor'}</span>
                            <span className="text-gray-200 font-medium">{decryptedResult.backtest.profit_factor !== undefined ? decryptedResult.backtest.profit_factor : 'N/A'}</span>
                          </div>
                          <div>
                            <span className="text-gray-500 text-xs block">{t('onchainSignals.totalSignals') || 'Total Signals'}</span>
                            <span className="text-gray-200 font-medium">{decryptedResult.backtest.total_signals !== undefined ? decryptedResult.backtest.total_signals : 'N/A'}</span>
                          </div>
                        </div>
                      </div>
                    )}

                    {/* Sentiment Card */}
                    {decryptedResult.sentiment && (
                      <div className="bg-[#0a0e17] border border-white/10 rounded-lg p-4">
                        <div className="flex items-center gap-2 mb-3">
                          <Activity className="w-4 h-4 text-[#7ED7C4]" />
                          <h4 className="text-sm font-medium text-white">{t('onchainSignals.sentiment') || 'Sentiment'}</h4>
                        </div>
                        <div className="grid grid-cols-2 gap-3 text-sm">
                          <div>
                            <span className="text-gray-500 text-xs block">{t('onchainSignals.sentimentIndex') || 'Sentiment Index'}</span>
                            <div className="mt-1">
                              <span className="text-gray-200 font-medium">{decryptedResult.sentiment.sentiment_index !== undefined ? decryptedResult.sentiment.sentiment_index : 'N/A'}</span>
                              {decryptedResult.sentiment.sentiment_index !== undefined && (
                                <div className="mt-1 h-1.5 w-full bg-white/10 rounded-full overflow-hidden">
                                  <div
                                    className="h-full bg-[#7ED7C4] rounded-full"
                                    style={{ width: `${Math.min(100, Math.max(0, decryptedResult.sentiment.sentiment_index))}%` }}
                                  />
                                </div>
                              )}
                            </div>
                          </div>
                          <div>
                            <span className="text-gray-500 text-xs block">{t('onchainSignals.marketBias') || 'Market Bias'}</span>
                            <span
                              className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium ${
                                (decryptedResult.sentiment.market_bias || '').toLowerCase().includes('bull')
                                  ? 'bg-emerald-500/10 text-emerald-400'
                                  : (decryptedResult.sentiment.market_bias || '').toLowerCase().includes('bear')
                                    ? 'bg-red-500/10 text-red-400'
                                    : 'bg-gray-500/10 text-gray-400'
                              }`}
                            >
                              {decryptedResult.sentiment.market_bias || 'N/A'}
                            </span>
                          </div>
                        </div>
                      </div>
                    )}

                    {/* Raw Data */}
                    <div className="bg-[#0a0e17] border border-white/10 rounded-lg p-4">
                      <span className="text-gray-500 text-xs">{t('onchainSignals.rawData')}</span>
                      <pre className="mt-1 text-xs text-gray-300 font-mono whitespace-pre-wrap break-all">
                        {decryptedResult.raw}
                      </pre>
                    </div>
                  </div>
                )}
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
