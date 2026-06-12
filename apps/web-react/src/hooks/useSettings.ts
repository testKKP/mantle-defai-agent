import { useState, useEffect, useCallback, useRef } from 'react';
import type { AppSettings, ApiStatus } from '../types';
import { getSettings, saveSettings, checkHealth, refreshApiClient } from '../services/api';

export function useSettings() {
  const [settings, setSettingsState] = useState<AppSettings>(getSettings);

  const updateSettings = useCallback((partial: Partial<AppSettings>) => {
    saveSettings(partial);
    refreshApiClient();
    setSettingsState(getSettings());
  }, []);

  return { settings, updateSettings };
}

export function useApiStatus(pollInterval = 30000) {
  const [status, setStatus] = useState<ApiStatus>({ online: false, checking: true });

  const check = useCallback(async () => {
    setStatus(s => ({ ...s, checking: true }));
    const result = await checkHealth();
    setStatus({ online: result.online, services: result.services, checking: false });
  }, []);

  useEffect(() => {
    check();
    const timer = setInterval(check, pollInterval);
    return () => clearInterval(timer);
  }, [check, pollInterval]);

  return { status, check };
}

export function useAutoRefresh<T>(
  fetcher: () => Promise<T>,
  intervalMs: number = 900000,
  deps: unknown[] = []
) {
  const [data, setData] = useState<T | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [lastUpdated, setLastUpdated] = useState<Date | null>(null);
  const isFetching = useRef(false);

  const refresh = useCallback(async () => {
    if (isFetching.current) return;
    isFetching.current = true;
    setLoading(true);
    setError(null);
    try {
      const result = await fetcher();
      setData(result);
      setLastUpdated(new Date());
    } catch (err: any) {
      setError(err.message || '加载失败');
    } finally {
      setLoading(false);
      isFetching.current = false;
    }
  }, [fetcher]);

  useEffect(() => {
    refresh();
    const timer = setInterval(refresh, intervalMs);
    return () => clearInterval(timer);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [intervalMs, ...deps]);

  return { data, loading, error, lastUpdated, refresh };
}

export function useCountdown(targetDate: Date | null) {
  const [secondsLeft, setSecondsLeft] = useState(0);

  useEffect(() => {
    if (!targetDate) return;
    const tick = () => {
      const diff = Math.max(0, Math.floor((targetDate.getTime() + 900000 - Date.now()) / 1000));
      setSecondsLeft(diff);
    };
    tick();
    const timer = setInterval(tick, 1000);
    return () => clearInterval(timer);
  }, [targetDate]);

  return secondsLeft;
}
