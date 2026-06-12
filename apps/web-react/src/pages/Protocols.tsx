import { useState, useMemo } from 'react';
import { useTranslation } from 'react-i18next';
import {
  Layers, TrendingUp, ArrowUpDown, Search
} from 'lucide-react';
import { useApp } from '../context/AppContext';
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Cell
} from 'recharts';

/* ───────────────────────────────
   工具函数
   ─────────────────────────────── */
function formatNumber(n: number, digits = 2): string {
  if (n >= 1e9) return `${(n / 1e9).toFixed(digits)}B`;
  if (n >= 1e6) return `${(n / 1e6).toFixed(digits)}M`;
  if (n >= 1e3) return `${(n / 1e3).toFixed(digits)}K`;
  return n.toFixed(digits);
}

/* ───────────────────────────────
   骨架屏
   ─────────────────────────────── */
function ShimmerBox({ className = '' }: { className?: string }) {
  return <div className={`shimmer rounded-lg ${className}`} />;
}

/* ───────────────────────────────
   主组件
   ─────────────────────────────── */
type CategoryFilter = 'all' | 'DEX' | 'Lending' | 'Yield';

export default function Protocols() {
  const { protocols, loading } = useApp();
  const [category, setCategory] = useState<CategoryFilter>('all');
  const [sortBy, setSortBy] = useState<'tvl' | 'name'>('tvl');
  const [sortDesc, setSortDesc] = useState(true);
  const [filter, setFilter] = useState('');
  const { t } = useTranslation();

  const filtered = useMemo(() => {
    let list = [...protocols];
    if (category !== 'all') {
      list = list.filter(p => (p.category || '').toLowerCase() === category.toLowerCase());
    }
    if (filter.trim()) {
      const q = filter.toLowerCase();
      list = list.filter(p => {
        const name = (p.protocol_name || p.name || '').toLowerCase();
        const cat = (p.category || '').toLowerCase();
        return name.includes(q) || cat.includes(q);
      });
    }
    list.sort((a, b) => {
      if (sortBy === 'tvl') {
        return sortDesc ? b.tvl - a.tvl : a.tvl - b.tvl;
      }
      return sortDesc
        ? (b.protocol_name || b.name || '').localeCompare(a.protocol_name || a.name || '')
        : (a.protocol_name || a.name || '').localeCompare(b.protocol_name || b.name || '');
    });
    return list;
  }, [protocols, category, filter, sortBy, sortDesc]);

  const top10TVL = useMemo(() => {
    return [...protocols]
      .sort((a, b) => b.tvl - a.tvl)
      .slice(0, 10)
      .map(p => ({
        name: p.protocol_name || p.name || 'Unknown',
        tvl: p.tvl,
        tvlFormatted: formatNumber(p.tvl),
      }));
  }, [protocols]);

  const toggleSort = (field: 'tvl' | 'name') => {
    if (sortBy === field) {
      setSortDesc(!sortDesc);
    } else {
      setSortBy(field);
      setSortDesc(true);
    }
  };

  const categories: { key: CategoryFilter; label: string }[] = [
    { key: 'all', label: t('protocols.all') },
    { key: 'DEX', label: 'DEX' },
    { key: 'Lending', label: 'Lending' },
    { key: 'Yield', label: 'Yield' },
  ];

  return (
    <div className="space-y-6 p-4 md:p-6 max-w-7xl mx-auto">
      {/* Header */}
      <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4">
        <div className="flex items-center gap-2">
          <Layers className="w-5 h-5 text-[#7ED7C4]" />
          <h2 className="text-lg font-semibold text-white">Mantle {t('protocols.ecosystem')}</h2>
          <span className="text-sm text-gray-400 ml-2">{t('protocols.totalProtocols', { count: protocols.length })}</span>
        </div>
      </div>

      {/* Category Tabs */}
      <div className="flex gap-1 bg-gray-800/50 p-1 rounded-lg w-fit">
        {categories.map(cat => (
          <button
            key={cat.key}
            onClick={() => setCategory(cat.key)}
            className={`px-4 py-1.5 rounded-md text-sm font-medium transition ${
              category === cat.key
                ? 'mantle-gradient text-white'
                : 'text-gray-400 hover:text-gray-200'
            }`}
          >
            {cat.label}
          </button>
        ))}
      </div>

      {/* Top 5 TVL Bar Chart */}
      <div className="card p-5">
        <div className="flex items-center gap-2 mb-4">
          <TrendingUp className="w-5 h-5 text-[#7ED7C4]" />
          <h3 className="text-lg font-semibold text-white">{t('protocols.top10TVL')}</h3>
        </div>
        {loading ? (
          <ShimmerBox className="h-64" />
        ) : top10TVL.length > 0 ? (
          <div className="h-64">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={top10TVL} layout="vertical" margin={{ left: 20, right: 20 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#374151" horizontal={false} />
                <XAxis type="number" tick={{ fill: '#9ca3af', fontSize: 12 }} tickFormatter={(v: number) => formatNumber(v)} />
                <YAxis dataKey="name" type="category" tick={{ fill: '#9ca3af', fontSize: 12 }} width={100} />
                <Tooltip
                  contentStyle={{ backgroundColor: '#1f2937', border: '1px solid #374151', borderRadius: '8px' }}
                  labelStyle={{ color: '#e5e7eb' }}
                  formatter={((value: any) => [`$${formatNumber(value)}`, 'TVL']) as any}
                />
                <Bar dataKey="tvl" radius={[0, 4, 4, 0]}>
                  {top10TVL.map((_, i) => (
                    <Cell key={i} fill={i === 0 ? '#4A9B8C' : i === 1 ? '#2D6B5E' : '#1f2937'} />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </div>
        ) : (
          <div className="text-gray-500 text-sm py-8 text-center">{t('common.noData')}</div>
        )}
      </div>

      {/* Search */}
      <div className="relative">
        <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-500" />
        <input
          type="text"
          placeholder={t('protocols.searchPlaceholder')}
          value={filter}
          onChange={e => setFilter(e.target.value)}
          className="w-full bg-[#111827] border border-white/5 rounded-xl pl-10 pr-4 py-2.5 text-sm text-gray-200 placeholder-gray-500 focus:outline-none focus:border-[#4A9B8C] transition"
        />
      </div>

      {/* Protocol Cards Grid */}
      {loading ? (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {[...Array(6)].map((_, i) => (
            <div key={i} className="card p-5 space-y-3">
              <div className="flex items-center justify-between">
                <ShimmerBox className="w-24 h-5" />
                <ShimmerBox className="w-16 h-5 rounded-full" />
              </div>
              <ShimmerBox className="w-full h-8" />
              <div className="grid grid-cols-2 gap-2">
                <ShimmerBox className="h-4" />
                <ShimmerBox className="h-4" />
              </div>
            </div>
          ))}
        </div>
      ) : filtered.length > 0 ? (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {filtered.map((p, i) => (
            <div key={i} className="card p-5 hover:border-white/10 transition-all duration-200">
              <div className="flex items-center justify-between mb-3">
                <span className="font-semibold text-white">{p.protocol_name || p.name}</span>
                <span className="px-2 py-0.5 rounded-full text-xs bg-gray-800 text-gray-400 border border-white/5">
                  {p.category}
                </span>
              </div>
              <div className="text-2xl font-bold text-white mb-3">
                ${formatNumber(p.tvl)}
              </div>
              <div className="grid grid-cols-2 gap-3 text-sm">
                <div>
                  <div className="text-xs text-gray-500">{t('protocols.change24h')}</div>
                  <div className={`font-medium ${(p.tvl_change_24h || 0) >= 0 ? 'text-emerald-400' : 'text-red-400'}`}>
                    {(p.tvl_change_24h || 0) >= 0 ? '+' : ''}{(p.tvl_change_24h || 0).toFixed(2)}%
                  </div>
                </div>
                <div>
                  <div className="text-xs text-gray-500">{t('protocols.change7d')}</div>
                  <div className={`font-medium ${(p.tvl_change_7d || 0) >= 0 ? 'text-emerald-400' : 'text-red-400'}`}>
                    {(p.tvl_change_7d || 0) >= 0 ? '+' : ''}{(p.tvl_change_7d || 0).toFixed(2)}%
                  </div>
                </div>
                <div>
                  <div className="text-xs text-gray-500">{t('protocols.volume24h')}</div>
                  <div className="font-medium text-gray-300">
                    {p.volume_24h > 0 ? `$${formatNumber(p.volume_24h)}` : '--'}
                  </div>
                </div>
                <div>
                  <div className="text-xs text-gray-500">{t('protocols.chain')}</div>
                  <div className="font-medium text-gray-300">{p.chain}</div>
                </div>
              </div>
            </div>
          ))}
        </div>
      ) : (
        <div className="text-gray-500 text-sm py-8 text-center">{t('protocols.noMatchingProtocols')}</div>
      )}

      {/* Full Table */}
      <div className="card p-5">
        <div className="flex items-center gap-2 mb-4">
          <Layers className="w-5 h-5 text-[#7ED7C4]" />
          <h3 className="text-lg font-semibold text-white">{t('protocols.protocolList')}</h3>
        </div>
        {loading ? (
          <div className="space-y-2">
            <ShimmerBox className="h-10" />
            <ShimmerBox className="h-10" />
            <ShimmerBox className="h-10" />
            <ShimmerBox className="h-10" />
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-white/10 text-gray-400">
                  <th className="text-left py-2 px-3 font-medium">{t('protocols.rank')}</th>
                  <th
                    className="text-left py-2 px-3 font-medium cursor-pointer hover:text-gray-200"
                    onClick={() => toggleSort('name')}
                  >
                    <div className="flex items-center gap-1">
                      {t('protocols.protocol')}
                      {sortBy === 'name' && <ArrowUpDown className="w-3 h-3" />}
                    </div>
                  </th>
                  <th className="text-left py-2 px-3 font-medium">{t('protocols.category')}</th>
                  <th className="text-right py-2 px-3 font-medium">{t('protocols.volume24h')}</th>
                  <th
                    className="text-right py-2 px-3 font-medium cursor-pointer hover:text-gray-200"
                    onClick={() => toggleSort('tvl')}
                  >
                    <div className="flex items-center justify-end gap-1">
                      TVL
                      {sortBy === 'tvl' && <ArrowUpDown className="w-3 h-3" />}
                    </div>
                  </th>
                  <th className="text-right py-2 px-3 font-medium">{t('protocols.change24h')}</th>
                  <th className="text-right py-2 px-3 font-medium">{t('protocols.change7d')}</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-white/5">
                {filtered.map((p, i) => (
                  <tr key={i} className="hover:bg-white/5 transition">
                    <td className="py-2.5 px-3 text-gray-500">{i + 1}</td>
                    <td className="py-2.5 px-3 font-medium text-white">{p.protocol_name || p.name}</td>
                    <td className="py-2.5 px-3">
                      <span className="px-2 py-0.5 rounded-full text-xs bg-gray-800 text-gray-400 border border-white/5">
                        {p.category}
                      </span>
                    </td>
                    <td className="py-2.5 px-3 text-right text-gray-300">
                      {p.volume_24h > 0 ? `$${formatNumber(p.volume_24h)}` : '--'}
                    </td>
                    <td className="py-2.5 px-3 text-right text-gray-300">${formatNumber(p.tvl)}</td>
                    <td className="py-2.5 px-3 text-right">
                      <span className={`text-sm font-medium ${(p.tvl_change_24h || 0) >= 0 ? 'text-emerald-400' : 'text-red-400'}`}>
                        {(p.tvl_change_24h || 0) >= 0 ? '+' : ''}{(p.tvl_change_24h || 0).toFixed(2)}%
                      </span>
                    </td>
                    <td className="py-2.5 px-3 text-right">
                      <span className={`text-sm font-medium ${(p.tvl_change_7d || 0) >= 0 ? 'text-emerald-400' : 'text-red-400'}`}>
                        {(p.tvl_change_7d || 0) >= 0 ? '+' : ''}{(p.tvl_change_7d || 0).toFixed(2)}%
                      </span>
                    </td>
                  </tr>
                ))}
                {filtered.length === 0 && (
                  <tr>
                    <td colSpan={7} className="py-8 text-center text-gray-500">{t('protocols.noMatchingProtocols')}</td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}
