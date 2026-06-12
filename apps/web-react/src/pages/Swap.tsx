import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useWallet, shortenAddress } from '../hooks/useWallet';
import { getSwapQuote, saveTransaction } from '../services/api';
import { ArrowDown, Wallet, AlertCircle, Loader2, CheckCircle, XCircle, ExternalLink } from 'lucide-react';

const TOKENS = [
  { symbol: 'MNT', name: 'Mantle', decimals: 18 },
  { symbol: 'USDC', name: 'USD Coin', decimals: 6 },
  { symbol: 'USDT', name: 'Tether', decimals: 6 },
];

export default function Swap() {
  const { t } = useTranslation();
  const [tokenIn, setTokenIn] = useState('MNT');
  const [tokenOut, setTokenOut] = useState('USDC');
  const [amount, setAmount] = useState('');
  const [slippage, setSlippage] = useState(0.5);
  const [quote, setQuote] = useState<any>(null);
  const [quoting, setQuoting] = useState(false);
  const [quoteError, setQuoteError] = useState('');
  const [swapping, setSwapping] = useState(false);
  const [swapResult, setSwapResult] = useState<{ success: boolean; message: string; txHash?: string } | null>(null);

  const wallet = useWallet();

  const handleSwapTokens = () => {
    setTokenIn(tokenOut);
    setTokenOut(tokenIn);
    setQuote(null);
    setQuoteError('');
  };

  const getQuote = async () => {
    if (!amount || parseFloat(amount) <= 0) return;
    setQuoting(true);
    setQuoteError('');
    setSwapResult(null);
    try {
      const decimals = TOKENS.find(t => t.symbol === tokenIn)?.decimals || 18;
      const amountInWei = BigInt(Math.floor(parseFloat(amount) * Math.pow(10, decimals))).toString();
      const quoteData = await getSwapQuote(tokenIn, tokenOut, amountInWei, slippage / 100);
      setQuote(quoteData);
    } catch (e: any) {
      setQuoteError(e.message || t('swap.quoteFailed'));
      setQuote(null);
    } finally {
      setQuoting(false);
    }
  };

  const handleSwap = async () => {
    if (!quote) return;

    if (!wallet.connected) {
      try {
        await wallet.connect(wallet.connectors[0]);
      } catch (e: any) {
        setSwapResult({ success: false, message: e.message || t('swap.connectWalletFailed') });
        return;
      }
    }

    setSwapping(true);
    setSwapResult(null);
    try {
      const result = await wallet.executeSwap(
        tokenIn,
        tokenOut,
        amount,
        quote.expected_output,
      );
      saveTransaction({
        tx_hash: result.hash,
        status: result.status,
        sender: wallet.address,
        token_in: tokenIn,
        token_out: tokenOut,
        amount_in: amount,
        expected_output: quote.expected_output,
        explorer_url: `https://mantlescan.xyz/tx/${result.hash}`,
      });
      setSwapResult({
        success: true,
        message: t('swap.tradeSubmitted'),
        txHash: result.hash,
      });
      setQuote(null);
      setAmount('');
    } catch (e: any) {
      setSwapResult({ success: false, message: e.message || t('swap.tradeFailed') });
    } finally {
      setSwapping(false);
    }
  };

  const formatAmount = (value: string, decimals: number) => {
    try {
      const num = parseFloat(value) / Math.pow(10, decimals);
      return num.toFixed(decimals === 18 ? 6 : 4);
    } catch {
      return value;
    }
  };

  return (
    <div className="max-w-lg mx-auto">
      <h2 className="text-xl font-bold mb-6">Swap</h2>

      {/* Wallet Status */}
      {wallet.connected && wallet.address && (
        <div className="mb-4 bg-gray-800/50 rounded-lg p-3 flex items-center justify-between">
          <div className="flex items-center gap-2">
            <div className="w-2 h-2 rounded-full bg-emerald-400" />
            <span className="text-sm text-gray-300">{shortenAddress(wallet.address)}</span>
          </div>
          <div className="flex gap-3 text-xs">
            <span className="text-gray-400">MNT: <span className="text-gray-200">{parseFloat(wallet.balances.MNT || '0').toFixed(4)}</span></span>
            <span className="text-gray-400">USDC: <span className="text-gray-200">{parseFloat(wallet.balances.USDC || '0').toFixed(2)}</span></span>
            <span className="text-gray-400">USDT: <span className="text-gray-200">{parseFloat(wallet.balances.USDT || '0').toFixed(2)}</span></span>
          </div>
        </div>
      )}

      <div className="bg-[#111827] border border-gray-800 rounded-xl p-6 space-y-4">
        {/* From */}
        <div>
          <label className="text-sm text-gray-400 mb-2 block">{t('swap.pay')}</label>
          <div className="flex gap-3">
            <select
              value={tokenIn}
              onChange={e => { setTokenIn(e.target.value); setQuote(null); setQuoteError(''); }}
              className="bg-gray-800 border border-gray-700 rounded-lg px-3 py-2.5 text-sm text-gray-200 focus:outline-none focus:border-[#4A9B8C]"
            >
              {TOKENS.map(t => <option key={t.symbol} value={t.symbol}>{t.symbol}</option>)}
            </select>
            <input
              type="number"
              value={amount}
              onChange={e => { setAmount(e.target.value); setQuote(null); setQuoteError(''); }}
              placeholder="0.0"
              className="flex-1 bg-gray-800 border border-gray-700 rounded-lg px-4 py-2.5 text-sm text-gray-200 placeholder-gray-500 focus:outline-none focus:border-[#4A9B8C]"
            />
          </div>
        </div>

        {/* Swap Button */}
        <div className="flex justify-center">
          <button
            onClick={handleSwapTokens}
            className="p-2 rounded-lg bg-gray-800 hover:bg-gray-700 transition"
          >
            <ArrowDown className="w-5 h-5 text-gray-400" />
          </button>
        </div>

        {/* To */}
        <div>
          <label className="text-sm text-gray-400 mb-2 block">{t('swap.receive')}</label>
          <div className="flex gap-3">
            <select
              value={tokenOut}
              onChange={e => { setTokenOut(e.target.value); setQuote(null); setQuoteError(''); }}
              className="bg-gray-800 border border-gray-700 rounded-lg px-3 py-2.5 text-sm text-gray-200 focus:outline-none focus:border-[#4A9B8C]"
            >
              {TOKENS.map(t => <option key={t.symbol} value={t.symbol}>{t.symbol}</option>)}
            </select>
            <input
              type="text"
              value={quote ? formatAmount(quote.expected_output, TOKENS.find(t => t.symbol === tokenOut)?.decimals || 18) : ''}
              readOnly
              placeholder="0.0"
              className="flex-1 bg-gray-800/50 border border-gray-700 rounded-lg px-4 py-2.5 text-sm text-gray-400"
            />
          </div>
        </div>

        {/* Slippage */}
        <div>
          <label className="text-sm text-gray-400 mb-2 block">{t('swap.slippageTolerance')}</label>
          <div className="flex gap-2">
            {[0.1, 0.5, 1.0].map(s => (
              <button
                key={s}
                onClick={() => { setSlippage(s); setQuote(null); }}
                className={`px-3 py-1.5 rounded-lg text-xs font-medium transition ${
                  slippage === s
                    ? 'bg-[#2D6B5E] text-white'
                    : 'bg-gray-800 text-gray-400 hover:bg-gray-700'
                }`}
              >
                {s}%
              </button>
            ))}
          </div>
        </div>

        {/* Quote Details */}
        {quote && (
          <div className="bg-gray-800/50 rounded-lg p-4 space-y-2">
            <div className="flex justify-between text-sm">
              <span className="text-gray-400">{t('swap.priceImpact')}</span>
              <span className={quote.price_impact > 1 ? 'text-red-400' : 'text-yellow-400'}>
                {quote.price_impact}%
              </span>
            </div>
            <div className="flex justify-between text-sm">
              <span className="text-gray-400">{t('swap.minimumReceived')}</span>
              <span className="text-gray-200">
                {formatAmount(quote.minimum_output, TOKENS.find(t => t.symbol === tokenOut)?.decimals || 18)} {tokenOut}
              </span>
            </div>
            <div className="flex justify-between text-sm">
              <span className="text-gray-400">{t('swap.fee')}</span>
              <span className="text-gray-200">{quote.fee_amount}</span>
            </div>
            <div className="flex justify-between text-sm">
              <span className="text-gray-400">{t('swap.route')}</span>
              <span className="text-gray-200">{quote.route.join(' → ')}</span>
            </div>
            <div className="flex justify-between text-sm">
              <span className="text-gray-400">{t('swap.gasEstimate')}</span>
              <span className="text-gray-200">{quote.gas_estimate}</span>
            </div>
          </div>
        )}

        {/* Error */}
        {quoteError && (
          <div className="bg-red-900/20 border border-red-700/50 rounded-lg p-3 flex items-center gap-2 text-sm text-red-400">
            <AlertCircle className="w-4 h-4 flex-shrink-0" />
            <span>{quoteError}</span>
          </div>
        )}

        {/* Swap Result */}
        {swapResult && (
          <div className={`rounded-lg p-3 flex items-center gap-2 text-sm ${
            swapResult.success
              ? 'bg-emerald-900/20 border border-emerald-700/50 text-emerald-400'
              : 'bg-red-900/20 border border-red-700/50 text-red-400'
          }`}>
            {swapResult.success ? <CheckCircle className="w-4 h-4 flex-shrink-0" /> : <XCircle className="w-4 h-4 flex-shrink-0" />}
            <span>{swapResult.message}</span>
            {swapResult.txHash && (
              <a
                href={`https://mantlescan.xyz/tx/${swapResult.txHash}`}
                target="_blank"
                rel="noopener noreferrer"
                className="ml-auto flex items-center gap-1 text-[#4A9B8C] hover:text-[#7ED7C4]"
              >
                <ExternalLink className="w-3 h-3" />
                {t('swap.view')}
              </a>
            )}
          </div>
        )}

        {/* Actions */}
        <div className="flex gap-3">
          <button
            onClick={getQuote}
            disabled={quoting || !amount || parseFloat(amount) <= 0}
            className="flex-1 py-3 rounded-lg bg-gray-800 text-gray-200 text-sm font-medium hover:bg-gray-700 transition disabled:opacity-50 flex items-center justify-center gap-2"
          >
            {quoting && <Loader2 className="w-4 h-4 animate-spin" />}
            {quoting ? t('swap.gettingQuote') : t('swap.getQuote')}
          </button>
          <button
            onClick={handleSwap}
            disabled={!quote || swapping}
            className="flex-1 py-3 rounded-lg bg-gradient-to-r from-[#2D6B5E] to-[#4A9B8C] text-white text-sm font-medium hover:opacity-90 transition disabled:opacity-50 flex items-center justify-center gap-2"
          >
            {swapping && <Loader2 className="w-4 h-4 animate-spin" />}
            {!wallet.connected ? (
              <><Wallet className="w-4 h-4" /> {t('swap.connectWalletToTrade')}</>
            ) : swapping ? (
              t('swap.trading')
            ) : (
              <><Wallet className="w-4 h-4" /> {t('swap.confirmTrade')}</>
            )}
          </button>
        </div>

        {!wallet.connected && (
          <div className="flex items-center gap-2 text-xs text-gray-500">
            <AlertCircle className="w-3 h-3" />
            <span>{t('swap.connectWalletPrompt')}</span>
          </div>
        )}
      </div>
    </div>
  );
}
