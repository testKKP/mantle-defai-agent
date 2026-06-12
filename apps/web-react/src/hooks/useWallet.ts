import { useState, useEffect, useCallback, useRef } from 'react';
import { ethers } from 'ethers';
import {
  useAccount,
  useConnect,
  useDisconnect,
  useSwitchChain,
  useChainId,
  useWalletClient,
} from 'wagmi';
import type { Connector } from 'wagmi';
import type { WalletState } from '../types';
import { getWalletBalance } from '../services/api';

const MANTLE_CHAIN_ID = 5000;
const MANTLE_SEPOLIA_CHAIN_ID = 5003;

const TOKEN_CONFIG: Record<string, { address: string; decimals: number; isNative: boolean }> = {
  MNT: { address: '0x78c1b0C915c4FAA5FffA6CAbf0219DA63d7f4cb8', decimals: 18, isNative: true },
  USDC: { address: '0x09Bc4E0D864854c6aFB6eB9A9cdF58aC190D0dF9', decimals: 6, isNative: false },
  USDT: { address: '0x201EBa5CC46D216Ce6DC03F6a759e8E766e956aE', decimals: 6, isNative: false },
};

const ROUTER_ADDRESS = '0x013e138EF6008ae5FDFDE29700e3f2Bc61d21E3a';
const ROUTER_ABI = [
  'function swapExactNATIVEForTokens(uint256 amountOutMin, tuple(address token, uint256 binStep, uint8 version)[] path, address to, uint256 deadline) payable returns (uint256)',
  'function swapExactTokensForTokens(uint256 amountIn, uint256 amountOutMin, tuple(address token, uint256 binStep, uint8 version)[] path, address to, uint256 deadline) returns (uint256)',
  'function swapExactTokensForNATIVE(uint256 amountIn, uint256 amountOutMinNATIVE, tuple(address token, uint256 binStep, uint8 version)[] path, address to, uint256 deadline) returns (uint256)',
];

export function useWallet() {
  const [state, setState] = useState<WalletState>({
    connected: false,
    address: null,
    chainId: null,
    balances: { MNT: '0', USDC: '0', USDT: '0' },
  });
  const balanceTimer = useRef<ReturnType<typeof setInterval> | null>(null);
  const signerRef = useRef<ethers.JsonRpcSigner | null>(null);

  const { address, isConnected, chainId: wagmiChainId } = useAccount();
  const { connect, connectors, isPending: connectPending, error: connectError } = useConnect();
  const { disconnect: wagmiDisconnect } = useDisconnect();
  const { switchChain } = useSwitchChain();
  const currentChainId = useChainId();
  const { data: walletClient } = useWalletClient();

  const loadBalances = useCallback(async (addr: string) => {
    try {
      const balances = await getWalletBalance(addr);
      setState(s => ({ ...s, balances }));
    } catch (e) {
      console.error('Failed to load balances:', e);
    }
  }, []);

  const disconnect = useCallback(() => {
    if (balanceTimer.current) {
      clearInterval(balanceTimer.current);
      balanceTimer.current = null;
    }
    signerRef.current = null;
    wagmiDisconnect();
    setState({
      connected: false,
      address: null,
      chainId: null,
      balances: { MNT: '0', USDC: '0', USDT: '0' },
    });
  }, [wagmiDisconnect]);

  const switchToMantle = useCallback(
    async (useSepolia = false): Promise<boolean> => {
      const targetChainId = useSepolia ? MANTLE_SEPOLIA_CHAIN_ID : MANTLE_CHAIN_ID;
      try {
        await switchChain({ chainId: targetChainId });
        return true;
      } catch (err: any) {
        // User rejected or wallet does not support switching
        console.error('Switch chain failed:', err);
        return false;
      }
    },
    [switchChain]
  );

  // Sync wagmi state to local state
  useEffect(() => {
    if (isConnected && address) {
      const cid = wagmiChainId ?? currentChainId;
      setState({
        connected: true,
        address,
        chainId: cid,
        balances: { MNT: '0', USDC: '0', USDT: '0' },
      });
      loadBalances(address);
      if (balanceTimer.current) clearInterval(balanceTimer.current);
      balanceTimer.current = setInterval(() => loadBalances(address), 60000);
    } else {
      if (balanceTimer.current) {
        clearInterval(balanceTimer.current);
        balanceTimer.current = null;
      }
      setState({
        connected: false,
        address: null,
        chainId: null,
        balances: { MNT: '0', USDC: '0', USDT: '0' },
      });
    }
  }, [isConnected, address, wagmiChainId, currentChainId, loadBalances]);

  // Build ethers signer from walletClient for swap execution
  // walletClient transport works for both injected and WalletConnect connectors
  useEffect(() => {
    let cancelled = false;
    if (walletClient && address) {
      try {
        // Create an EIP-1193 compatible provider from walletClient
        // This works universally for MetaMask, WalletConnect, and other connectors
        const eip1193Provider = {
          request: async (args: { method: string; params?: any[] }) => {
            return (walletClient as any).request(args);
          },
        };
        const provider = new ethers.BrowserProvider(eip1193Provider as any);
        provider.getSigner(address).then((s) => {
          if (!cancelled) signerRef.current = s;
        }).catch((err) => {
          console.error('Failed to get signer:', err);
          signerRef.current = null;
        });
      } catch (err) {
        console.error('Failed to build ethers provider:', err);
        signerRef.current = null;
      }
    } else {
      signerRef.current = null;
    }
    return () => {
      cancelled = true;
    };
  }, [walletClient, address]);

  const executeSwap = useCallback(
    async (
      tokenIn: string,
      tokenOut: string,
      amount: string,
      expectedOutput: string,
    ): Promise<{ hash: string; status: number }> => {
      if (!isConnected || !signerRef.current || !address) {
        throw new Error('请先连接钱包');
      }

      const inDecimals = TOKEN_CONFIG[tokenIn].decimals;
      const outDecimals = TOKEN_CONFIG[tokenOut].decimals;
      const amountInWei = ethers.parseUnits(amount, inDecimals);
      const minAmountOut = ethers.parseUnits(
        (parseFloat(ethers.formatUnits(expectedOutput, outDecimals)) * 0.995).toFixed(outDecimals),
        outDecimals,
      );
      const deadline = Math.floor(Date.now() / 1000) + 1200;

      const router = new ethers.Contract(ROUTER_ADDRESS, ROUTER_ABI, signerRef.current);
      const tokenInAddr = TOKEN_CONFIG[tokenIn].address;
      const tokenOutAddr = TOKEN_CONFIG[tokenOut].address;
      const path = [
        { token: tokenInAddr, binStep: 20n, version: 2 },
        { token: tokenOutAddr, binStep: 20n, version: 2 },
      ];

      let tx: ethers.ContractTransactionResponse;
      const isNativeIn = TOKEN_CONFIG[tokenIn].isNative;
      const isNativeOut = TOKEN_CONFIG[tokenOut].isNative;

      if (isNativeIn) {
        tx = await router.swapExactNATIVEForTokens(minAmountOut, path, address, deadline, {
          value: amountInWei,
          gasLimit: 300000,
        });
      } else if (isNativeOut) {
        tx = await router.swapExactTokensForNATIVE(amountInWei, minAmountOut, path, address, deadline, {
          gasLimit: 300000,
        });
      } else {
        tx = await router.swapExactTokensForTokens(amountInWei, minAmountOut, path, address, deadline, {
          gasLimit: 300000,
        });
      }

      const receipt = await tx.wait();
      if (!receipt) throw new Error('交易未确认');

      if (address) loadBalances(address);

      return { hash: tx.hash, status: receipt.status ?? 0 };
    },
    [isConnected, address, loadBalances],
  );

  useEffect(() => {
    return () => {
      if (balanceTimer.current) clearInterval(balanceTimer.current);
    };
  }, []);

  return {
    ...state,
    connecting: connectPending,
    connect: (connector: Connector) => {
      connect({ connector });
    },
    disconnect,
    switchToMantle,
    connectors,
    connectError,
    executeSwap,
    loadBalances,
    signer: signerRef.current,
    tokenConfig: TOKEN_CONFIG,
  };
}

export function shortenAddress(addr: string): string {
  if (!addr) return '';
  return addr.slice(0, 6) + '...' + addr.slice(-4);
}
