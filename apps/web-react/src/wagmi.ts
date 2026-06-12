import { createConfig, http, createStorage } from 'wagmi'
import { mantle, mantleSepoliaTestnet } from 'viem/chains'
import { injected, walletConnect } from 'wagmi/connectors'

const WALLETCONNECT_PROJECT_ID = import.meta.env.VITE_WALLETCONNECT_PROJECT_ID || ''

export const config = createConfig({
  chains: [mantle, mantleSepoliaTestnet],
  connectors: [
    injected(), // 通用 injected，依赖 EIP-6963 自动发现所有钱包
    ...(WALLETCONNECT_PROJECT_ID
      ? [
          walletConnect({
            projectId: WALLETCONNECT_PROJECT_ID,
            metadata: {
              name: 'Mantle DeFAI Agent',
              description: 'Autonomous AI Agent for DeFi on Mantle',
              url: typeof window !== 'undefined' ? window.location.origin : 'https://mantle-defai-trader.app',
              icons: typeof window !== 'undefined'
                ? [`${window.location.origin}/favicon.svg`]
                : ['https://mantle-defai-trader.app/favicon.svg'],
            },
            showQrModal: true,
          }),
        ]
      : []),
  ],
  transports: {
    [mantle.id]: http('https://rpc.mantle.xyz'),
    [mantleSepoliaTestnet.id]: http('https://rpc.sepolia.mantle.xyz'),
  },
  // Enable persistent connection state for better UX
  storage: typeof window !== 'undefined' ? createStorage({ storage: window.localStorage }) : undefined,
})
