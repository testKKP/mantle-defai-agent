import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { WagmiProvider } from 'wagmi'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { config } from './wagmi'
import './i18n'
import './index.css'
import App from './App'

const queryClient = new QueryClient()

const app = (
  <WagmiProvider config={config}>
    <QueryClientProvider client={queryClient}>
      <App />
    </QueryClientProvider>
  </WagmiProvider>
)

createRoot(document.getElementById('root')!).render(
  import.meta.env.DEV ? <StrictMode>{app}</StrictMode> : app,
)
