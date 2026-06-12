import { useState, useEffect } from 'react';
import { useTranslation } from 'react-i18next';
import { mantleSepoliaTestnet } from 'viem/chains';
import { useReadContract } from 'wagmi';
import {
  Radio, ChevronDown, Link, AlertCircle,
  Hash, User, Clock, ExternalLink, ChevronRight,
  FileJson, Database,
} from 'lucide-react';
import { useRegistry } from '../hooks/useRegistry';
import { shortenAddress } from '../hooks/useWallet';
import registryAbi from '../abi/MantleDeFAIRegistry.json';
import { getRecentOnChainSignals } from '../services/api';
import type { OnChainSignalRecord } from '../types';

/* ───────────────────────────────
   Helpers
   ─────────────────────────────── */
function ShimmerBox({ className = '' }: { className?: string }) {
  return <div className={`shimmer rounded-lg ${className}`} />;
}

function truncateHash(hash: string, prefix = 16, suffix = 8): string {
  if (!hash || hash.length <= prefix + suffix + 3) return hash;
  return `${hash.slice(0, prefix)}...${hash.slice(-suffix)}`;
}

function formatTimestamp(ts: number): string {
  return new Date(ts * 1000).toLocaleString();
}

const SYMBOLS = ['BTC', 'ETH', 'MNT', 'SOL', 'ARB'];
const TIMEFRAMES = ['4h', '1d', '1w'];
const MANTLE_SEPOLIA_EXPLORER = 'https://sepolia.mantlescan.xyz/tx/';

/* ───────────────────────────────
   Main Component
   ─────────────────────────────── */
export default function OnChainSignals() {
  const { t } = useTranslation();
  const { registryAddress } = useRegistry();

  const [selectedSymbol, setSelectedSymbol] = useState('BTC');
  const [selectedTimeframe, setSelectedTimeframe] = useState('1d');

  /* Recent on-chain submissions */
  const [recentSignals, setRecentSignals] = useState<OnChainSignalRecord[]>([]);
  const [loadingRecent, setLoadingRecent] = useState(false);
  const [recentError, setRecentError] = useState<string | null>(null);
  const [expandedId, setExpandedId] = useState<number | null>(null);

  const signalCount = useReadContract({
    address: registryAddress || undefined,
    abi: registryAbi,
    functionName: 'getSignalCount',
    args: [selectedSymbol, selectedTimeframe],
    chainId: mantleSepoliaTestnet.id,
    query: { enabled: !!registryAddress },
  });

  const latestSignal = useReadContract({
    address: registryAddress || undefined,
    abi: registryAbi,
    functionName: 'getLatestSignal',
    args: [selectedSymbol, selectedTimeframe],
    chainId: mantleSepoliaTestnet.id,
    query: { enabled: !!registryAddress },
  });

  const signalData = latestSignal.data as
    | { data: string; dataHash: string; timestamp: bigint; submitter: string }
    | undefined;

  const countValue = signalCount.data as bigint | undefined;

  /* Load recent submissions from backend */
  useEffect(() => {
    let cancelled = false;
    async function load() {
      setLoadingRecent(true);
      setRecentError(null);
      try {
        const result = await getRecentOnChainSignals(100);
        if (!cancelled) setRecentSignals(result.data || []);
      } catch (e: any) {
        if (!cancelled) setRecentError(e.message || 'Failed to load');
      } finally {
        if (!cancelled) setLoadingRecent(false);
      }
    }
    load();
    return () => { cancelled = true; };
  }, []);

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

      {/* Signal Browser */}
      <div className="card p-5">
        <div className="flex items-center gap-2 mb-4">
          <Link className="w-4 h-4 text-[#7ED7C4]" />
          <h3 className="font-semibold text-white">{t('onchainSignals.latestSignal')}</h3>
        </div>

        <div className="flex flex-wrap gap-4 mb-4">
          <div className="relative">
            <label className="block text-xs text-gray-500 mb-1.5">{t('onchainSignals.selectSymbol')}</label>
            <div className="relative">
              <select value={selectedSymbol} onChange={(e) => setSelectedSymbol(e.target.value)}
                className="appearance-none bg-[#0a0e17] border border-white/10 rounded-lg px-4 py-2 pr-10 text-sm text-gray-200 focus:outline-none focus:border-[#4A9B8C] w-32">
                {SYMBOLS.map((s) => <option key={s} value={s}>{s}</option>)}
              </select>
              <ChevronDown className="absolute right-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-500 pointer-events-none" />
            </div>
          </div>

          <div className="relative">
            <label className="block text-xs text-gray-500 mb-1.5">{t('onchainSignals.selectTimeframe')}</label>
            <div className="relative">
              <select value={selectedTimeframe} onChange={(e) => setSelectedTimeframe(e.target.value)}
                className="appearance-none bg-[#0a0e17] border border-white/10 rounded-lg px-4 py-2 pr-10 text-sm text-gray-200 focus:outline-none focus:border-[#4A9B8C] w-32">
                {TIMEFRAMES.map((tf) => <option key={tf} value={tf}>{tf}</option>)}
              </select>
              <ChevronDown className="absolute right-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-500 pointer-events-none" />
            </div>
          </div>

          <div>
            <label className="block text-xs text-gray-500 mb-1.5">{t('onchainSignals.signalCount')}</label>
            <div className="text-sm text-gray-200 font-medium py-2">
              {signalCount.isLoading ? (
                <ShimmerBox className="h-5 w-16" />
              ) : countValue !== undefined ? (
                <span className="bg-[#2D6B5E]/20 text-[#7ED7C4] px-3 py-1.5 rounded-lg text-sm font-semibold">{countValue.toString()}</span>
              ) : '--'}
            </div>
          </div>
        </div>

        {signalCount.error && (
          <div className="flex items-center gap-2 py-2 text-red-400 text-sm">
            <AlertCircle className="w-4 h-4" />
            <span>Count query error: {signalCount.error.message}</span>
          </div>
        )}
        {latestSignal.error && (
          <div className="flex items-center gap-2 py-2 text-red-400 text-sm">
            <AlertCircle className="w-4 h-4" />
            <span>Signal query error: {latestSignal.error.message}</span>
          </div>
        )}
        {latestSignal.isLoading ? (
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
                <span className="text-gray-200">{new Date(Number(signalData.timestamp) * 1000).toLocaleString()}</span>
              </div>
            </div>
          </div>
        )}
      </div>

      {/* Recent On-Chain Submissions */}
      <div className="card p-5">
        <div className="flex items-center gap-2 mb-4">
          <Database className="w-4 h-4 text-[#7ED7C4]" />
          <h3 className="font-semibold text-white">{t('onchainSignals.recentSignals')}</h3>
          <span className="text-xs text-gray-500 ml-2">({recentSignals.length})</span>
        </div>

        {loadingRecent ? (
          <div className="space-y-3 py-4">
            <ShimmerBox className="h-6" />
            <ShimmerBox className="h-6" />
            <ShimmerBox className="h-6" />
            <ShimmerBox className="h-6" />
            <ShimmerBox className="h-6" />
          </div>
        ) : recentError ? (
          <div className="flex items-center justify-center py-8 text-red-400 border border-dashed border-white/10 rounded-lg">
            <span>{recentError}</span>
          </div>
        ) : recentSignals.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-8 text-gray-500 border border-dashed border-white/10 rounded-lg gap-2">
            <Database className="w-5 h-5 text-gray-600" />
            <span>{t('onchainSignals.noData')}</span>
            <span className="text-xs text-amber-400/80">链上已有信号，本地记录同步中...</span>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-white/10 text-gray-500">
                  <th className="text-left py-2 px-2 font-medium">{t('table.symbol')}</th>
                  <th className="text-left py-2 px-2 font-medium">{t('table.timeframe')}</th>
                  <th className="text-left py-2 px-2 font-medium">{t('onchainSignals.dataHash')}</th>
                  <th className="text-left py-2 px-2 font-medium">{t('onchainSignals.blockNumber')}</th>
                  <th className="text-left py-2 px-2 font-medium">{t('onchainSignals.submittedAt')}</th>
                  <th className="text-left py-2 px-2 font-medium">{t('onchainSignals.txHash')}</th>
                  <th className="text-left py-2 px-2 font-medium w-10"></th>
                </tr>
              </thead>
              <tbody>
                {recentSignals.map((sig) => {
                  const isExpanded = expandedId === sig.id;
                  return (
                    <>
                      <tr
                        key={sig.id}
                        className="border-b border-white/5 hover:bg-white/5 transition cursor-pointer"
                        onClick={() => setExpandedId(isExpanded ? null : sig.id)}
                      >
                        <td className="py-2.5 px-2 text-gray-200 font-medium">{sig.symbol}</td>
                        <td className="py-2.5 px-2 text-gray-400">{sig.timeframe}</td>
                        <td className="py-2.5 px-2 text-gray-400 font-mono text-xs">{truncateHash(sig.data_hash)}</td>
                        <td className="py-2.5 px-2 text-gray-400 font-mono">#{sig.block_number}</td>
                        <td className="py-2.5 px-2 text-gray-400">{formatTimestamp(sig.timestamp)}</td>
                        <td className="py-2.5 px-2">
                          <a
                            href={`${MANTLE_SEPOLIA_EXPLORER}${sig.tx_hash}`}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="inline-flex items-center gap-1 text-[#7ED7C4] hover:text-[#4A9B8C] transition font-mono text-xs"
                            onClick={(e) => e.stopPropagation()}
                          >
                            {truncateHash(sig.tx_hash, 10, 6)}
                            <ExternalLink className="w-3 h-3" />
                          </a>
                        </td>
                        <td className="py-2.5 px-2">
                          <button
                            className="text-gray-500 hover:text-gray-300 transition"
                            onClick={() => setExpandedId(isExpanded ? null : sig.id)}
                          >
                            {isExpanded ? (
                              <ChevronDown className="w-4 h-4" />
                            ) : (
                              <ChevronRight className="w-4 h-4" />
                            )}
                          </button>
                        </td>
                      </tr>
                      {isExpanded && (
                        <tr>
                          <td colSpan={7} className="px-2 pb-3">
                            <div className="bg-[#0a0e17] border border-white/10 rounded-lg p-3">
                              <div className="flex items-center gap-2 mb-2">
                                <FileJson className="w-3.5 h-3.5 text-[#7ED7C4]" />
                                <span className="text-xs font-medium text-white">Data (JSON)</span>
                              </div>
                              <pre className="text-xs text-gray-400 font-mono overflow-x-auto whitespace-pre-wrap break-all max-h-64 overflow-y-auto">
                                {(() => {
                                  try {
                                    const parsed = JSON.parse(sig.data);
                                    return JSON.stringify(parsed, null, 2);
                                  } catch {
                                    return sig.data;
                                  }
                                })()}
                              </pre>
                            </div>
                          </td>
                        </tr>
                      )}
                    </>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}
