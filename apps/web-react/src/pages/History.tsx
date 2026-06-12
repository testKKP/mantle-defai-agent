import { useState, useEffect } from 'react';
import { useTranslation } from 'react-i18next';
import { getTransactions, clearTransactions } from '../services/api';
import { shortenAddress } from '../hooks/useWallet';
import { History, ExternalLink, Trash2, Clock, CheckCircle, XCircle, Loader2 } from 'lucide-react';

const getStatusText = (status: string, t: (key: string) => string) => {
  switch (status) {
    case 'success': return t('history.statusSuccess');
    case 'failed': return t('history.statusFailed');
    default: return t('history.statusPending');
  }
};

export default function HistoryPage() {
  const { t } = useTranslation();
  const [transactions, setTransactions] = useState<any[]>([]);
  const [filter, setFilter] = useState<'all' | 'success' | 'pending' | 'failed'>('all');

  useEffect(() => {
    loadTransactions();
  }, []);

  const loadTransactions = () => {
    setTransactions(getTransactions());
  };

  const handleClear = () => {
    if (confirm(t('history.confirmClear'))) {
      clearTransactions();
      loadTransactions();
    }
  };

  const filtered = transactions.filter(tx => {
    if (filter === 'all') return true;
    return tx.status === filter;
  });

  const getStatusIcon = (status: string) => {
    switch (status) {
      case 'success': return <CheckCircle className="w-4 h-4 text-emerald-400" />;
      case 'failed': return <XCircle className="w-4 h-4 text-red-400" />;
      default: return <Loader2 className="w-4 h-4 text-yellow-400 animate-spin" />;
    }
  };

  const formatTime = (iso: string) => {
    try {
      const d = new Date(iso);
      return d.toLocaleString('zh-CN', {
        month: 'short',
        day: 'numeric',
        hour: '2-digit',
        minute: '2-digit',
      });
    } catch {
      return iso;
    }
  };

  return (
    <div className="max-w-4xl mx-auto">
      <div className="flex items-center justify-between mb-6">
        <h2 className="text-xl font-bold flex items-center gap-2">
          <History className="w-5 h-5" />
          {t('history.pageTitle')}
        </h2>
        <div className="flex items-center gap-3">
          <div className="flex gap-1">
            {(['all', 'success', 'pending', 'failed'] as const).map(f => (
              <button
                key={f}
                onClick={() => setFilter(f)}
                className={`px-3 py-1 rounded-lg text-xs font-medium transition ${
                  filter === f
                    ? 'bg-[#2D6B5E] text-white'
                    : 'bg-gray-800 text-gray-400 hover:bg-gray-700'
                }`}
              >
                {f === 'all' ? t('common.all') : f === 'success' ? t('history.statusSuccess') : f === 'pending' ? t('history.statusPending') : t('history.statusFailed')}
              </button>
            ))}
          </div>
          {transactions.length > 0 && (
            <button
              onClick={handleClear}
              className="p-2 rounded-lg bg-gray-800 text-gray-400 hover:bg-red-900/30 hover:text-red-400 transition"
              title={t('history.clearRecordsTitle')}
            >
              <Trash2 className="w-4 h-4" />
            </button>
          )}
        </div>
      </div>

      {filtered.length === 0 ? (
        <div className="bg-[#111827] border border-gray-800 rounded-xl p-12 text-center">
          <Clock className="w-12 h-12 text-gray-600 mx-auto mb-4" />
          <p className="text-gray-400">
            {transactions.length === 0 ? t('history.noTransactions') : t('history.noMatchingTransactions')}
          </p>
          {transactions.length === 0 && (
            <p className="text-gray-500 text-sm mt-2">{t('history.swapRecordsWillAppearHere')}</p>
          )}
        </div>
      ) : (
        <div className="space-y-3">
          {filtered.map(tx => (
            <div
              key={tx.id}
              className="bg-[#111827] border border-gray-800 rounded-xl p-4 hover:border-gray-700 transition"
            >
              <div className="flex items-center justify-between mb-3">
                <div className="flex items-center gap-2">
                  {getStatusIcon(tx.status)}
                  <span className={`text-sm font-medium ${
                    tx.status === 'success' ? 'text-emerald-400' :
                    tx.status === 'failed' ? 'text-red-400' :
                    'text-yellow-400'
                  }`}>
                    {getStatusText(tx.status, t)}
                  </span>
                </div>
                <span className="text-xs text-gray-500">{formatTime(tx.timestamp)}</span>
              </div>

              <div className="grid grid-cols-2 gap-4 mb-3">
                <div>
                  <div className="text-xs text-gray-500 mb-1">{t('history.pay')}</div>
                  <div className="text-sm text-gray-200">
                    {tx.amount_in} {tx.token_in}
                  </div>
                </div>
                <div>
                  <div className="text-xs text-gray-500 mb-1">{t('history.receive')}</div>
                  <div className="text-sm text-gray-200">
                    {tx.expected_output} {tx.token_out}
                  </div>
                </div>
              </div>

              <div className="flex items-center justify-between">
                <div className="text-xs text-gray-500">
                  {t('history.sender')}: <span className="text-gray-400">{shortenAddress(tx.sender)}</span>
                </div>
                <a
                  href={tx.explorer_url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="flex items-center gap-1 text-xs text-[#4A9B8C] hover:text-[#7ED7C4] transition"
                >
                  <ExternalLink className="w-3 h-3" />
                  {t('history.viewTransaction')}
                </a>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
