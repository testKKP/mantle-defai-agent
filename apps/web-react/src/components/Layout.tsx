import { useState } from 'react';
import { NavLink } from 'react-router-dom';
import { useApp } from '../context/AppContext';
import { useWallet } from '../hooks/useWallet';
import { shortenAddress } from '../hooks/useWallet';
import { useTranslation } from 'react-i18next';
import WalletModal from './WalletModal';
import LanguageSwitcher from './LanguageSwitcher';
import {
  Activity,
  BarChart3,
  Layers,
  Globe,
  Wallet,
  TrendingUp,
  Radio,
} from 'lucide-react';

export default function Layout({ children }: { children: React.ReactNode }) {
  const { apiStatus, lastRefresh } = useApp();
  const wallet = useWallet();
  const [showWalletModal, setShowWalletModal] = useState(false);
  const { t } = useTranslation();

  const navItems = [
    { path: '/', label: t('nav.dashboard'), icon: Activity },
    { path: '/protocols', label: t('nav.protocols'), icon: Layers },
    { path: '/sentiment', label: t('nav.sentiment'), icon: BarChart3 },
    { path: '/onchain', label: t('nav.onchain'), icon: Globe },
    { path: '/onchain-signals', label: t('nav.onchainSignals'), icon: Radio },
  ];

  return (
    <div className="min-h-screen bg-[#0a0e17] text-gray-100">
      {/* Header */}
      <header className="sticky top-0 z-50 border-b border-white/5 bg-[rgba(10,14,23,0.9)] backdrop-blur-lg">
        <div className="max-w-7xl mx-auto px-4 h-14 flex items-center justify-between">
          {/* Left: Logo + Title + Version */}
          <div className="flex items-center gap-3">
            <div className="w-8 h-8 rounded-lg mantle-gradient flex items-center justify-center shadow-lg shadow-[#2D6B5E]/20">
              <TrendingUp className="w-4 h-4 text-white" />
            </div>
            <span className="font-bold text-lg tracking-tight">Mantle DeFAI Agent</span>
            <span className="px-2 py-0.5 rounded-full text-xs bg-emerald-900/50 text-emerald-400 border border-emerald-700/50 font-medium">
              v2.0
            </span>
          </div>

          {/* Right: API Status + Refresh + Wallet */}
          <div className="flex items-center gap-3">
            {/* API Status */}
            <div
              className={`flex items-center gap-2 text-xs px-2.5 py-1.5 rounded-lg border ${
                apiStatus.checking
                  ? 'border-yellow-700/30 text-yellow-400 bg-yellow-900/10'
                  : apiStatus.online
                    ? 'border-emerald-700/30 text-emerald-400 bg-emerald-900/10'
                    : 'border-red-700/30 text-red-400 bg-red-900/10'
              }`}
            >
              <span
                className={`w-2 h-2 rounded-full ${
                  apiStatus.checking
                    ? 'api-status-checking'
                    : apiStatus.online
                      ? 'api-status-online'
                      : 'api-status-offline'
                }`}
              />
              <span className="hidden sm:inline font-medium">
                {apiStatus.checking ? t('layout.apiChecking') : apiStatus.online ? t('layout.apiOnline') : t('layout.apiOffline')}
              </span>
            </div>


            {/* Wallet Button */}
            {wallet.connected ? (
              <button
                onClick={wallet.disconnect}
                className="flex items-center gap-2 px-3 py-1.5 rounded-lg text-sm font-medium bg-white/5 border border-white/10 hover:bg-white/10 transition"
              >
                <Wallet className="w-4 h-4 text-[#7ED7C4]" />
                <span className="hidden sm:inline">
                  {shortenAddress(wallet.address || '')}
                </span>
              </button>
            ) : (
              <button
                onClick={() => setShowWalletModal(true)}
                disabled={wallet.connecting}
                className="flex items-center gap-2 px-4 py-1.5 rounded-lg text-sm font-medium text-white mantle-gradient hover:opacity-90 transition shadow-lg shadow-[#2D6B5E]/20 disabled:opacity-50"
              >
                <Wallet className="w-4 h-4" />
                <span>{wallet.connecting ? t('layout.connecting') : t('layout.connectWallet')}</span>
              </button>
            )}

            {/* Language Switcher */}
            <LanguageSwitcher />

            {/* Last Refresh */}
            {lastRefresh && (
              <span className="text-xs text-gray-500 hidden md:inline">
                {lastRefresh.toLocaleTimeString()}
              </span>
            )}
          </div>
        </div>
      </header>

      {/* Navigation */}
      <nav className="border-b border-white/5 bg-[rgba(10,14,23,0.8)] backdrop-blur-md">
        <div className="max-w-7xl mx-auto px-4">
          <div className="flex gap-1 overflow-x-auto scrollbar-hide">
            {navItems.map((item) => {
              const Icon = item.icon;
              return (
                <NavLink
                  key={item.path}
                  to={item.path}
                  end={item.path === '/'}
                  className={({ isActive }) =>
                    `flex items-center gap-2 px-4 py-3 text-sm font-medium border-b-2 transition whitespace-nowrap ${
                      isActive
                        ? 'border-[#4A9B8C] text-[#7ED7C4]'
                        : 'border-transparent text-gray-400 hover:text-gray-200 hover:border-gray-700'
                    }`
                  }
                >
                  <Icon className="w-4 h-4" />
                  <span className="hidden sm:inline">{item.label}</span>
                </NavLink>
              );
            })}
          </div>
        </div>
      </nav>

      {/* API Offline Banner */}
      {!apiStatus.online && !apiStatus.checking && (
        <div className="bg-red-900/20 border-b border-red-800/30 px-4 py-2">
          <div className="max-w-7xl mx-auto flex items-center gap-2 text-sm text-red-400">
            <span className="w-2 h-2 rounded-full bg-red-500 api-status-offline" />
            <span>{t('layout.apiOfflineBanner')}</span>
          </div>
        </div>
      )}

      {/* Main Content */}
      <main className="max-w-7xl mx-auto px-4 py-6">{children}</main>

      {/* Wallet Modal */}
      <WalletModal
        isOpen={showWalletModal}
        onClose={() => setShowWalletModal(false)}
        connectors={wallet.connectors}
        onConnect={(connector) => {
          wallet.connect(connector);
          setShowWalletModal(false);
        }}
        connecting={wallet.connecting}
        connectError={wallet.connectError}
      />
    </div>
  );
}
