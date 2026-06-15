import { createContext, useContext, useState, useEffect, useCallback, type ReactNode } from 'react';
import type { ApiStatus, AppSettings, SentimentData, OnChainOverview, ProtocolData, BlockData, GasData, NetworkData, TrendsData, TVLHistory } from '../types';
import { checkHealth, getLatestSentiment, getOnChainOverview, getProtocols, getBlockData, getGasData, getNetworkData, getMantleTrends, getMantleTVLHistory } from '../services/api';

interface AppContextType {
  apiStatus: ApiStatus;
  settings: AppSettings;
  sentiment: SentimentData | null;
  overview: OnChainOverview | null;
  protocols: ProtocolData[];
  block: BlockData | null;
  gas: GasData | null;
  network: NetworkData | null;
  trends: TrendsData | null;
  tvlHistory: TVLHistory;
  loading: boolean;
  lastRefresh: Date | null;
  refresh: () => void;
}

const defaultSettings: AppSettings = {
  apiBase: import.meta.env.VITE_API_BASE || 'http://localhost:8000',
  refreshInterval: 900000,
};

const AppContext = createContext<AppContextType | null>(null);

export function AppProvider({ children }: { children: ReactNode }) {
  const [apiStatus, setApiStatus] = useState<ApiStatus>({ online: false, checking: true });
  const [settings] = useState<AppSettings>(defaultSettings);
  const [sentiment, setSentiment] = useState<SentimentData | null>(null);
  const [overview, setOverview] = useState<OnChainOverview | null>(null);
  const [protocols, setProtocols] = useState<ProtocolData[]>([]);
  const [block, setBlock] = useState<BlockData | null>(null);
  const [gas, setGas] = useState<GasData | null>(null);
  const [network, setNetwork] = useState<NetworkData | null>(null);
  const [trends, setTrends] = useState<TrendsData | null>(null);
  const [tvlHistory, setTvlHistory] = useState<TVLHistory>([]);
  const [loading, setLoading] = useState(true);
  const [lastRefresh, setLastRefresh] = useState<Date | null>(null);

  const checkApi = useCallback(async () => {
    setApiStatus(prev => ({ ...prev, checking: true }));
    const health = await checkHealth();
    setApiStatus({ online: health.online, services: health.services, checking: false });
    return health.online;
  }, []);

  const loadData = useCallback(async () => {
    setLoading(true);
    try {
      const isOnline = await checkApi();
      if (!isOnline) {
        setLoading(false);
        return;
      }

      const [sentimentRes, overviewRes, protocolsRes, blockRes, gasRes, networkRes, trendsRes, tvlHistoryRes] = await Promise.allSettled([
        getLatestSentiment(),
        getOnChainOverview(),
        getProtocols(),
        getBlockData(),
        getGasData(),
        getNetworkData(),
        getMantleTrends(),
        getMantleTVLHistory(),
      ]);

      if (sentimentRes.status === 'fulfilled') setSentiment(sentimentRes.value);
      if (overviewRes.status === 'fulfilled') setOverview(overviewRes.value);
      if (protocolsRes.status === 'fulfilled') setProtocols(protocolsRes.value);
      if (blockRes.status === 'fulfilled') setBlock(blockRes.value);
      if (gasRes.status === 'fulfilled') setGas(gasRes.value);
      if (networkRes.status === 'fulfilled') setNetwork(networkRes.value);
      if (trendsRes.status === 'fulfilled') setTrends(trendsRes.value);
      if (tvlHistoryRes.status === 'fulfilled') setTvlHistory(tvlHistoryRes.value);

      setLastRefresh(new Date());
    } catch (e) {
      console.error('Load data failed:', e);
    } finally {
      setLoading(false);
    }
  }, [checkApi]);

  useEffect(() => {
    loadData();
    const interval = setInterval(loadData, settings.refreshInterval);
    return () => clearInterval(interval);
  }, [loadData, settings.refreshInterval]);

  return (
    <AppContext.Provider value={{
      apiStatus, settings, sentiment, overview, protocols, block, gas, network, trends, tvlHistory, loading, lastRefresh,
      refresh: loadData,
    }}>
      {children}
    </AppContext.Provider>
  );
}

export function useApp() {
  const ctx = useContext(AppContext);
  if (!ctx) throw new Error('useApp must be used within AppProvider');
  return ctx;
}
