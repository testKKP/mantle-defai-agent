import { useCallback, useMemo } from 'react';
import { X, Wallet } from 'lucide-react';
import type { Connector } from 'wagmi';
import { useTranslation } from 'react-i18next';

interface WalletModalProps {
  isOpen: boolean;
  onClose: () => void;
  connectors: readonly Connector[];
  onConnect: (connector: Connector) => void;
  connecting: boolean;
  connectError?: Error | null;
}

function isMobile(): boolean {
  if (typeof window === 'undefined') return false;
  return /Android|webOS|iPhone|iPad|iPod|BlackBerry|IEMobile|Opera Mini/i.test(navigator.userAgent);
}

function getWalletMeta(connector: Connector, t: (key: string) => string): { name: string; icon: string } {
  const id = connector.id.toLowerCase();
  if (id.includes('walletconnect')) {
    return { name: 'WalletConnect', icon: '🔗' };
  }
  if (id.includes('coinbase')) {
    return { name: 'Coinbase Wallet', icon: '🅒' };
  }
  if (id === 'metamask' || id === 'io.metamask' || id.includes('metamask')) {
    return { name: 'MetaMask', icon: '🦊' };
  }
  if (id === 'injected') {
    return { name: t('wallet.browserWallet'), icon: '💉' };
  }
  if (id.includes('phantom')) {
    return { name: 'Phantom', icon: '👻' };
  }
  if (id.includes('rainbow')) {
    return { name: 'Rainbow', icon: '🌈' };
  }
  if (id.includes('trust')) {
    return { name: 'Trust Wallet', icon: '🛡️' };
  }
  return { name: connector.name, icon: '💼' };
}

export default function WalletModal({ isOpen, onClose, connectors, onConnect, connecting, connectError }: WalletModalProps) {
  const { t } = useTranslation();
  const mobile = useMemo(() => isMobile(), []);

  const handleConnect = useCallback(
    (connector: Connector) => {
      onConnect(connector);
    },
    [onConnect],
  );

  const sortedConnectors = useMemo(() => {
    const list = [...connectors];
    // Mobile: WalletConnect first; Desktop: injected first
    list.sort((a, b) => {
      const aIsWC = a.id.toLowerCase().includes('walletconnect');
      const bIsWC = b.id.toLowerCase().includes('walletconnect');
      const aIsInjected = a.id.toLowerCase().includes('injected');
      const bIsInjected = b.id.toLowerCase().includes('injected');
      if (mobile) {
        if (aIsWC && !bIsWC) return -1;
        if (!aIsWC && bIsWC) return 1;
      } else {
        if (aIsInjected && !bIsInjected) return -1;
        if (!aIsInjected && bIsInjected) return 1;
      }
      return 0;
    });
    return list;
  }, [connectors, mobile]);

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-[100] flex items-center justify-center p-4">
      {/* Backdrop */}
      <div className="absolute inset-0 bg-black/70 backdrop-blur-sm" onClick={onClose} />

      {/* Modal */}
      <div className="relative w-full max-w-sm rounded-2xl border border-white/10 bg-[#0f1520] p-6 shadow-2xl shadow-black/50">
        {/* Header */}
        <div className="flex items-center justify-between mb-6">
          <div className="flex items-center gap-2">
            <Wallet className="w-5 h-5 text-[#7ED7C4]" />
            <h2 className="text-lg font-bold text-white">{t('wallet.connectWalletTitle')}</h2>
          </div>
          <button
            onClick={onClose}
            className="p-1.5 rounded-lg hover:bg-white/10 transition text-gray-400 hover:text-white"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Wallet list */}
        <div className="space-y-3">
          {sortedConnectors.length === 0 ? (
            <div className="text-center py-8 px-4">
              <div className="text-3xl mb-3">🔍</div>
              <div className="text-white font-medium mb-2">{t('wallet.noWalletDetected')}</div>
              <div className="text-sm text-gray-400">
                {t('wallet.installWalletHint')}
              </div>
            </div>
          ) : (
            sortedConnectors.map((connector) => {
            const meta = getWalletMeta(connector, t);
            const isRecommended = mobile
              ? connector.id.toLowerCase().includes('walletconnect')
              : connector.id.toLowerCase().includes('injected');

            return (
              <button
                key={connector.id}
                onClick={() => handleConnect(connector)}
                disabled={connecting}
                className={`w-full flex items-center gap-4 px-4 py-4 rounded-xl border transition text-left
                  ${
                    isRecommended
                      ? 'border-[#4A9B8C]/40 bg-[#4A9B8C]/10 hover:bg-[#4A9B8C]/20'
                      : 'border-white/10 bg-white/5 hover:bg-white/10'
                  }
                  disabled:opacity-50 disabled:cursor-not-allowed
                `}
              >
                <span className="text-2xl">{meta.icon}</span>
                <div className="flex-1 min-w-0">
                  <div className="font-semibold text-white text-base">{meta.name}</div>
                  <div className="text-xs text-gray-400 mt-0.5">
                    {connector.id.toLowerCase().includes('walletconnect')
                      ? t('wallet.walletConnectDesc')
                      : connector.id.toLowerCase() === 'metamask' || connector.id.toLowerCase().includes('metamask')
                        ? t('wallet.metaMaskDesc')
                        : connector.id.toLowerCase() === 'injected'
                          ? t('wallet.browserWalletDesc')
                          : t('wallet.walletConnectGeneric')}
                  </div>
                </div>
                {isRecommended && (
                  <span className="px-2 py-0.5 rounded-full text-[10px] font-medium bg-[#4A9B8C]/20 text-[#7ED7C4] border border-[#4A9B8C]/30">
                    {t('wallet.recommended')}
                  </span>
                )}
              </button>
            );
          })
          )}
        </div>

        {connectError && (
          <div className="mt-4 text-center text-sm text-red-400 bg-red-900/20 border border-red-800/30 rounded-lg px-3 py-2">
            {t('wallet.connectFailed')}{connectError.message}
          </div>
        )}

        {connecting && (
          <div className="mt-4 text-center text-sm text-[#7ED7C4]">
            {t('wallet.connecting')}
          </div>
        )}

        {/* Footer hint */}
        <p className="mt-5 text-center text-xs text-gray-500">
          {t('wallet.connectAgreement')}
        </p>
      </div>
    </div>
  );
}
