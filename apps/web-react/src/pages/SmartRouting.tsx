import { useState, useEffect, useCallback, useRef } from 'react';
import { useWallet } from '../hooks/useWallet';
import { useTranslation } from 'react-i18next';
import {
  startWizard,
  getWizardSession,
  submitWizardStep,
  analyzeRoutes,
  getAnalysisStatus,
  selectRoute,
  checkWallet,
  executeRoute,
  getSupportedChains,
  getSupportedTokens,
} from '../services/api';
import type {
  WizardSessionData,
  WizardStepType,
  ChainInfo,
  TokenInfo,
  RouteOption,
  RouteStepDetail,
  AnalysisProgress,
  WalletCheckResult,
  ExecutionResult,
} from '../types';
import {
  ArrowRight,
  ArrowLeft,
  RefreshCw,
  Loader2,
  CheckCircle2,
  // Circle,
  AlertTriangle,
  Wallet,
  Globe,
  Coins,
  DollarSign,
  BrainCircuit,
  Route,
  ShieldCheck,
  Send,
  ChevronRight,
  ExternalLink,
  Clock,
  Fuel,
  TrendingUp,
  TrendingDown,
  Minus,
  Zap,
  Sparkles,
  // Timer,
  Activity,
  Check,
  X,
  Info,
} from 'lucide-react';

// ============ Step Configuration ============

const STEP_ORDER: WizardStepType[] = [
  'chain_select',
  'token_select',
  'amount_input',
  'smart_analysis',
  'route_display',
  'route_select',
  'wallet_check',
  'execute_confirm',
];

function getStepIndex(step: WizardStepType): number {
  return STEP_ORDER.indexOf(step);
}

function getStepStatus(
  stepId: WizardStepType,
  currentStep: WizardStepType,
  completedSteps: WizardStepType[]
): 'completed' | 'current' | 'pending' {
  if (completedSteps.includes(stepId)) return 'completed';
  if (stepId === currentStep) return 'current';
  return 'pending';
}

// ============ Component ============

export default function SmartRouting() {
  const { t } = useTranslation();
  const wallet = useWallet();

  const STEP_CONFIGS: { id: WizardStepType; label: string; description: string }[] = [
    { id: 'chain_select', label: t('routing.step.selectChain'), description: t('routing.step.selectChainDesc') },
    { id: 'token_select', label: t('routing.step.selectToken'), description: t('routing.step.selectTokenDesc') },
    { id: 'amount_input', label: t('routing.step.amount'), description: t('routing.step.amountDesc') },
    { id: 'smart_analysis', label: t('routing.step.analysis'), description: t('routing.step.analysisDesc') },
    { id: 'route_display', label: t('routing.step.viewRoutes'), description: t('routing.step.viewRoutesDesc') },
    { id: 'route_select', label: t('routing.step.selectRoute'), description: t('routing.step.selectRouteDesc') },
    { id: 'wallet_check', label: t('routing.step.walletCheck'), description: t('routing.step.walletCheckDesc') },
    { id: 'execute_confirm', label: t('routing.step.execute'), description: t('routing.step.executeDesc') },
  ];

  // Session state
  const [session, setSession] = useState<WizardSessionData | null>(null);
  const [sessionLoading, setSessionLoading] = useState(true);
  const [error, setError] = useState('');

  // Data state
  const [chains, setChains] = useState<ChainInfo[]>([]);
  const [tokensByChain, setTokensByChain] = useState<Record<string, TokenInfo[]>>({});

  // Step input state
  const [sourceChain, setSourceChain] = useState('');
  const [targetChain, setTargetChain] = useState('');
  const [tokenIn, setTokenIn] = useState('');
  const [tokenOut, setTokenOut] = useState('');
  const [amount, setAmount] = useState('');

  // Analysis state
  const [analysisProgress, setAnalysisProgress] = useState<AnalysisProgress | null>(null);
  const [isAnalyzing, setIsAnalyzing] = useState(false);
  const pollTimerRef = useRef<ReturnType<typeof setInterval> | null>(null);

  // Selection state
  const [selectedRouteId, setSelectedRouteId] = useState<string>('');
  const [walletCheckResult, setWalletCheckResult] = useState<WalletCheckResult | null>(null);
  const [executing, setExecuting] = useState(false);

  // ============ Initialization ============

  const initSession = useCallback(async () => {
    try {
      setSessionLoading(true);
      // Check URL query parameter first
      const urlParams = new URLSearchParams(window.location.search);
      const savedSessionId = urlParams.get('session') || localStorage.getItem('mantle_routing_session_id');
      if (savedSessionId) {
        try {
          const s = await getWizardSession(savedSessionId);
          setSession(s);
          // Restore inputs
          if (s.chain_data) {
            setSourceChain(s.chain_data.source_chain);
            setTargetChain(s.chain_data.target_chain);
          }
          if (s.token_data) {
            setTokenIn(s.token_data.token_in);
            setTokenOut(s.token_data.token_out);
          }
          if (s.amount_data) {
            setAmount(s.amount_data.amount);
          }
          if (s.selected_route_id) {
            setSelectedRouteId(s.selected_route_id);
          }
          localStorage.setItem('mantle_routing_session_id', s.session_id);
          setSessionLoading(false);
          return;
        } catch {
          localStorage.removeItem('mantle_routing_session_id');
        }
      }
      const s = await startWizard();
      setSession(s);
      localStorage.setItem('mantle_routing_session_id', s.session_id);
    } catch (e: any) {
      setError(e.message || t('routing.initFailed'));
    } finally {
      setSessionLoading(false);
    }
  }, [t]);

  const loadChains = useCallback(async () => {
    try {
      const c = await getSupportedChains();
      setChains(c);
    } catch (e) {
      console.error('Failed to load chains:', e);
    }
  }, []);

  useEffect(() => {
    initSession();
    loadChains();
    return () => {
      if (pollTimerRef.current) clearInterval(pollTimerRef.current);
    };
  }, [initSession, loadChains]);

  // Load tokens when chain changes
  useEffect(() => {
    if (!sourceChain) return;
    if (tokensByChain[sourceChain]) return;
    getSupportedTokens(sourceChain)
      .then((t) => setTokensByChain((prev) => ({ ...prev, [sourceChain]: t })))
      .catch(console.error);
  }, [sourceChain]);

  useEffect(() => {
    if (!targetChain || targetChain === sourceChain) return;
    if (tokensByChain[targetChain]) return;
    getSupportedTokens(targetChain)
      .then((t) => setTokensByChain((prev) => ({ ...prev, [targetChain]: t })))
      .catch(console.error);
  }, [targetChain, sourceChain]);

  // ============ Actions ============

  const submitStep = async (stepId: string, data: Record<string, any>, _advance = true) => {
    if (!session) return;
    try {
      setError('');
      const s = await submitWizardStep(session.session_id, stepId, data);
      setSession(s);
      return s;
    } catch (e: any) {
      setError(e.message || t('routing.submitFailed'));
      throw e;
    }
  };

  const handleChainSubmit = async () => {
    if (!sourceChain || !targetChain) {
      setError(t('routing.selectSourceTargetChain'));
      return;
    }
    await submitStep('chain_select', { source_chain: sourceChain, target_chain: targetChain });
  };

  const handleTokenSubmit = async () => {
    if (!tokenIn || !tokenOut) {
      setError(t('routing.selectInputOutputToken'));
      return;
    }
    await submitStep('token_select', {
      token_in: tokenIn,
      token_out: tokenOut,
      token_in_symbol: tokenIn,
      token_out_symbol: tokenOut,
    });
  };

  const handleAmountSubmit = async () => {
    if (!amount || parseFloat(amount) <= 0) {
      setError(t('routing.enterValidAmount'));
      return;
    }
    const tokenInfo = tokensByChain[sourceChain]?.find((t) => t.symbol === tokenIn);
    const amountUsd = tokenInfo ? parseFloat(amount) * tokenInfo.price_usd : undefined;
    await submitStep('amount_input', { amount, amount_usd: amountUsd });
    // Auto-start analysis after amount submission
    await startAnalysis();
  };

  const startAnalysis = async () => {
    if (!session) return;
    try {
      setIsAnalyzing(true);
      setError('');
      await analyzeRoutes(session.session_id);
      // Start polling
      pollTimerRef.current = setInterval(() => pollStatus(session.session_id), 1500);
    } catch (e: any) {
      setError(e.message || t('routing.analysisStartFailed'));
      setIsAnalyzing(false);
    }
  };

  const pollStatus = async (sessionId: string) => {
    try {
      const status = await getAnalysisStatus(sessionId);
      setAnalysisProgress(status.progress);

      if (status.analysis_status === 'completed') {
        if (pollTimerRef.current) clearInterval(pollTimerRef.current);
        setIsAnalyzing(false);
        // Refresh session to get routes
        const s = await getWizardSession(sessionId);
        setSession(s);
      } else if (status.analysis_status === 'failed') {
        if (pollTimerRef.current) clearInterval(pollTimerRef.current);
        setIsAnalyzing(false);
        setError(status.progress.error || t('routing.analysisFailed'));
      }
    } catch (e) {
      console.error('Poll error:', e);
    }
  };

  const handleSelectRoute = async (route: RouteOption) => {
    if (!session) return;
    try {
      setError('');
      setSelectedRouteId(route.route_id);
      await selectRoute(session.session_id, route.route_id);
      const s = await getWizardSession(session.session_id);
      setSession(s);
    } catch (e: any) {
      setError(e.message || t('routing.selectRouteFailed'));
    }
  };

  const handleWalletCheck = async () => {
    if (!session || !wallet.address) {
      setError(t('routing.connectWalletFirst'));
      return;
    }
    try {
      setError('');
      const result = await checkWallet(session.session_id, wallet.address);
      setWalletCheckResult(result);
      // Refresh session
      const s = await getWizardSession(session.session_id);
      setSession(s);
    } catch (e: any) {
      setError(e.message || t('routing.walletCheckFailed'));
    }
  };

  const handleExecute = async () => {
    if (!session || !wallet.address || !wallet.signer) return;
    try {
      setExecuting(true);
      setError('');
      
      // 1. Get unsigned transaction from backend
      const result = await executeRoute(session.session_id, wallet.address);
      
      // 2. Check if cross-chain (not supported)
      if (result.status === 'not_supported') {
        setError(result.error || t('routing.crossChainNotSupported'));
        return;
      }
      
      // 3. Sign and broadcast with MetaMask
      if (result.tx_params) {
        const tx = await wallet.signer.sendTransaction({
          to: result.tx_params.to,
          data: result.tx_params.data,
          value: BigInt(result.tx_params.value || 0),
          gasLimit: BigInt(result.tx_params.gasLimit),
          gasPrice: BigInt(result.tx_params.gasPrice),
          nonce: Number(result.tx_params.nonce),
          chainId: Number(result.tx_params.chainId),
        });
        
        await tx.wait();
        
        // 4. Refresh balances
        if (wallet.address) wallet.loadBalances(wallet.address);
        
        // 5. Show success
        setError('');
        alert(t('routing.txConfirmed', { hash: tx.hash }));
      }
      
      // Refresh session
      const s = await getWizardSession(session.session_id);
      setSession(s);
    } catch (e: any) {
      setError(e.message || t('routing.executeFailed'));
      console.error('Execution failed:', e);
    } finally {
      setExecuting(false);
    }
  };

  const handleReset = async () => {
    localStorage.removeItem('mantle_routing_session_id');
    setSourceChain('');
    setTargetChain('');
    setTokenIn('');
    setTokenOut('');
    setAmount('');
    setAnalysisProgress(null);
    setSelectedRouteId('');
    setWalletCheckResult(null);
    setError('');
    if (pollTimerRef.current) clearInterval(pollTimerRef.current);
    await initSession();
  };

  // ============ Helpers ============

  const currentStepIndex = session ? getStepIndex(session.current_step) : -1;

  const isStepAccessible = (stepId: WizardStepType): boolean => {
    if (!session) return false;
    const idx = getStepIndex(stepId);
    const currentIdx = getStepIndex(session.current_step);
    // Can go back to completed steps, or forward if prerequisites met
    if (idx <= currentIdx) return true;
    // Check if all previous required steps are completed
    for (let i = 0; i < idx; i++) {
      if (!session.completed_steps.includes(STEP_ORDER[i])) return false;
    }
    return true;
  };

  const handleStepClick = (stepId: WizardStepType) => {
    if (!isStepAccessible(stepId) || !session) return;
    // Only allow clicking to completed steps or current step
    const idx = getStepIndex(stepId);
    const currentIdx = getStepIndex(session.current_step);
    if (idx > currentIdx) return;
    // Update session current_step (visual only, doesn't change data)
    setSession({ ...session, current_step: stepId });
  };

  // ============ Render ============

  if (sessionLoading) {
    return (
      <div className="flex items-center justify-center h-96">
        <Loader2 className="w-8 h-8 animate-spin text-[#4A9B8C]" />
        <span className="ml-3 text-gray-400">{t('routing.initializing')}</span>
      </div>
    );
  }

  if (!session) {
    return (
      <div className="text-center py-20">
        <AlertTriangle className="w-12 h-12 text-yellow-500 mx-auto mb-4" />
        <p className="text-gray-400">{t('routing.sessionInitFailed')}</p>
        <button onClick={handleReset} className="mt-4 px-4 py-2 rounded-lg mantle-gradient text-white text-sm">
          {t('routing.retry')}
        </button>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-white flex items-center gap-2">
            <BrainCircuit className="w-6 h-6 text-[#7ED7C4]" />
            {t('routing.title')}
          </h1>
          <p className="text-gray-400 text-sm mt-1">{t('routing.subtitle')}</p>
        </div>
        <button
          onClick={handleReset}
          className="flex items-center gap-2 px-3 py-1.5 rounded-lg text-sm bg-white/5 border border-white/10 hover:bg-white/10 transition"
        >
          <RefreshCw className="w-4 h-4" />
          {t('routing.restart')}
        </button>
      </div>

      {/* Error Banner */}
      {error && (
        <div className="flex items-center gap-3 px-4 py-3 rounded-xl bg-red-900/20 border border-red-800/30 text-red-400 text-sm">
          <AlertTriangle className="w-5 h-5 shrink-0" />
          {error}
          <button onClick={() => setError('')} className="ml-auto text-xs hover:underline">
            {t('routing.close')}
          </button>
        </div>
      )}

      {/* Step Indicator */}
      <div className="bg-[#111827] rounded-2xl border border-white/5 p-4">
        <div className="flex items-center justify-between relative">
          {/* Progress Line */}
          <div className="absolute top-5 left-0 right-0 h-0.5 bg-white/5 mx-8" />
          <div
            className="absolute top-5 left-8 h-0.5 bg-[#4A9B8C] transition-all duration-500"
            style={{
              width: `calc(${Math.max(0, currentStepIndex) / (STEP_ORDER.length - 1) * 100}% - 4rem)`,
            }}
          />

          {STEP_CONFIGS.map((step, idx) => {
            const status = getStepStatus(step.id, session.current_step, session.completed_steps);
            const accessible = isStepAccessible(step.id);
            return (
              <button
                key={step.id}
                onClick={() => handleStepClick(step.id)}
                disabled={!accessible}
                className={`relative z-10 flex flex-col items-center gap-2 group ${
                  accessible ? 'cursor-pointer' : 'cursor-default opacity-50'
                }`}
              >
                <div
                  className={`w-10 h-10 rounded-full flex items-center justify-center border-2 transition-all duration-300 ${
                    status === 'completed'
                      ? 'bg-[#4A9B8C] border-[#4A9B8C] text-white'
                      : status === 'current'
                        ? 'bg-[#111827] border-[#7ED7C4] text-[#7ED7C4] shadow-lg shadow-[#7ED7C4]/20'
                        : 'bg-[#111827] border-white/10 text-gray-500'
                  }`}
                >
                  {status === 'completed' ? (
                    <Check className="w-5 h-5" />
                  ) : (
                    <span className="text-sm font-bold">{idx + 1}</span>
                  )}
                </div>
                <div className="text-center">
                  <div
                    className={`text-xs font-medium transition-colors ${
                      status === 'current' ? 'text-[#7ED7C4]' : status === 'completed' ? 'text-gray-300' : 'text-gray-600'
                    }`}
                  >
                    {step.label}
                  </div>
                  <div className="text-[10px] text-gray-600 hidden sm:block">{step.description}</div>
                </div>
              </button>
            );
          })}
        </div>
      </div>

      {/* Step Content */}
      <div className="min-h-[400px]">
        {session.current_step === 'chain_select' && (
          <ChainSelectStep
            chains={chains}
            sourceChain={sourceChain}
            targetChain={targetChain}
            onSourceChange={setSourceChain}
            onTargetChange={setTargetChain}
            onSubmit={handleChainSubmit}
          />
        )}

        {session.current_step === 'token_select' && (
          <TokenSelectStep
            sourceChain={sourceChain}
            targetChain={targetChain}
            tokensByChain={tokensByChain}
            tokenIn={tokenIn}
            tokenOut={tokenOut}
            onTokenInChange={setTokenIn}
            onTokenOutChange={setTokenOut}
            onSubmit={handleTokenSubmit}
            onBack={() => handleStepClick('chain_select')}
          />
        )}

        {session.current_step === 'amount_input' && (
          <AmountInputStep
            tokenIn={tokenIn}
            tokenOut={tokenOut}
            sourceChain={sourceChain}
            amount={amount}
            tokensByChain={tokensByChain}
            onAmountChange={setAmount}
            onSubmit={handleAmountSubmit}
            onBack={() => handleStepClick('token_select')}
          />
        )}

        {session.current_step === 'smart_analysis' && (
          <AnalysisStep
            isAnalyzing={isAnalyzing}
            progress={analysisProgress}
            onStartAnalysis={startAnalysis}
            onBack={() => handleStepClick('amount_input')}
          />
        )}

        {session.current_step === 'route_display' && (
          <RouteDisplayStep
            routes={session.analysis_data?.routes || []}
            summary={session.analysis_data?.analysis_summary}
            selectedRouteId={selectedRouteId}
            onSelectRoute={handleSelectRoute}
            onBack={() => handleStepClick('smart_analysis')}
          />
        )}

        {session.current_step === 'route_select' && (
          <RouteSelectStep
            selectedRoute={session.analysis_data?.routes?.find((r) => r.route_id === selectedRouteId)}
            walletConnected={wallet.connected}
            onWalletCheck={handleWalletCheck}
            onBack={() => handleStepClick('route_display')}
          />
        )}

        {session.current_step === 'wallet_check' && (
          <WalletCheckStep
            result={walletCheckResult}
            onCheck={handleWalletCheck}
            walletConnected={wallet.connected}
            walletAddress={wallet.address}
            onExecute={handleExecute}
            onBack={() => handleStepClick('route_select')}
          />
        )}

        {session.current_step === 'execute_confirm' && (
          <ExecutionStep
            result={session.execution_data}
            executing={executing}
            onExecute={handleExecute}
            onReset={handleReset}
          />
        )}
      </div>
    </div>
  );
}

// ============ Step Components ============

function ChainSelectStep({
  chains,
  sourceChain,
  targetChain,
  onSourceChange,
  onTargetChange,
  onSubmit,
}: {
  chains: ChainInfo[];
  sourceChain: string;
  targetChain: string;
  onSourceChange: (c: string) => void;
  onTargetChange: (c: string) => void;
  onSubmit: () => void;
}) {
  const { t } = useTranslation();
  return (
    <div className="space-y-6">
      <div className="text-center">
        <h2 className="text-xl font-bold text-white flex items-center justify-center gap-2">
          <Globe className="w-5 h-5 text-[#7ED7C4]" />
          {t('routing.selectChains')}
        </h2>
        <p className="text-gray-400 text-sm mt-2">{t('routing.selectChainsDesc')}</p>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        {/* Source Chain */}
        <div className="space-y-3">
          <label className="text-sm font-medium text-gray-300 flex items-center gap-2">
            <ArrowRight className="w-4 h-4 text-emerald-400" />
            {t('routing.sourceChain')}
          </label>
          <div className="grid grid-cols-2 gap-3">
            {chains.map((chain) => (
              <button
                key={chain.id}
                onClick={() => onSourceChange(chain.id)}
                className={`p-4 rounded-xl border-2 transition-all text-left ${
                  sourceChain === chain.id
                    ? 'border-[#4A9B8C] bg-[#4A9B8C]/10'
                    : 'border-white/5 bg-[#161b2e] hover:border-white/10 hover:bg-[#1e2438]'
                }`}
              >
                <div className="flex items-center gap-3">
                  <div
                    className="w-10 h-10 rounded-full flex items-center justify-center text-white font-bold text-sm"
                    style={{ backgroundColor: chain.color }}
                  >
                    {chain.name.slice(0, 2)}
                  </div>
                  <div>
                    <div className="font-semibold text-white">{chain.name}</div>
                    <div className="text-xs text-gray-500">Chain ID: {chain.chain_id}</div>
                  </div>
                </div>
                {sourceChain === chain.id && (
                  <div className="mt-2 flex items-center gap-1 text-xs text-[#7ED7C4]">
                    <CheckCircle2 className="w-3 h-3" /> {t('routing.selected')}
                  </div>
                )}
              </button>
            ))}
          </div>
        </div>

        {/* Target Chain */}
        <div className="space-y-3">
          <label className="text-sm font-medium text-gray-300 flex items-center gap-2">
            <ArrowLeft className="w-4 h-4 text-blue-400" />
            {t('routing.targetChain')}
          </label>
          <div className="grid grid-cols-2 gap-3">
            {chains.map((chain) => (
              <button
                key={chain.id}
                onClick={() => onTargetChange(chain.id)}
                className={`p-4 rounded-xl border-2 transition-all text-left ${
                  targetChain === chain.id
                    ? 'border-blue-500/50 bg-blue-500/10'
                    : 'border-white/5 bg-[#161b2e] hover:border-white/10 hover:bg-[#1e2438]'
                }`}
              >
                <div className="flex items-center gap-3">
                  <div
                    className="w-10 h-10 rounded-full flex items-center justify-center text-white font-bold text-sm"
                    style={{ backgroundColor: chain.color }}
                  >
                    {chain.name.slice(0, 2)}
                  </div>
                  <div>
                    <div className="font-semibold text-white">{chain.name}</div>
                    <div className="text-xs text-gray-500">Chain ID: {chain.chain_id}</div>
                  </div>
                </div>
                {targetChain === chain.id && (
                  <div className="mt-2 flex items-center gap-1 text-xs text-blue-400">
                    <CheckCircle2 className="w-3 h-3" /> {t('routing.selected')}
                  </div>
                )}
              </button>
            ))}
          </div>
        </div>
      </div>

      {/* Connection visualization */}
      {sourceChain && targetChain && (
        <div className="flex items-center justify-center gap-4 py-4">
          <div className="flex items-center gap-2 px-4 py-2 rounded-lg bg-[#4A9B8C]/10 border border-[#4A9B8C]/20">
            <Globe className="w-4 h-4 text-[#7ED7C4]" />
            <span className="text-sm text-[#7ED7C4] font-medium">
              {chains.find((c) => c.id === sourceChain)?.name}
            </span>
          </div>
          <div className="flex items-center gap-1">
            <div className="w-8 h-0.5 bg-[#4A9B8C]" />
            <ArrowRight className="w-4 h-4 text-[#4A9B8C]" />
            <div className="w-8 h-0.5 bg-blue-500/50" />
          </div>
          <div className="flex items-center gap-2 px-4 py-2 rounded-lg bg-blue-500/10 border border-blue-500/20">
            <Globe className="w-4 h-4 text-blue-400" />
            <span className="text-sm text-blue-400 font-medium">
              {chains.find((c) => c.id === targetChain)?.name}
            </span>
          </div>
          {sourceChain === targetChain ? (
            <span className="text-xs text-emerald-400 bg-emerald-400/10 px-2 py-1 rounded-full">{t('routing.sameChainTx')}</span>
          ) : (
            <span className="text-xs text-amber-400 bg-amber-400/10 px-2 py-1 rounded-full">{t('routing.crossChainTx')}</span>
          )}
        </div>
      )}

      <div className="flex justify-end">
        <button
          onClick={onSubmit}
          disabled={!sourceChain || !targetChain}
          className="flex items-center gap-2 px-6 py-3 rounded-xl font-medium text-white mantle-gradient hover:opacity-90 transition disabled:opacity-30 disabled:cursor-not-allowed shadow-lg shadow-[#2D6B5E]/20"
        >
          {t('routing.nextSelectToken')}
          <ChevronRight className="w-4 h-4" />
        </button>
      </div>
    </div>
  );
}

function TokenSelectStep({
  sourceChain,
  targetChain,
  tokensByChain,
  tokenIn,
  tokenOut,
  onTokenInChange,
  onTokenOutChange,
  onSubmit,
  onBack,
}: {
  sourceChain: string;
  targetChain: string;
  tokensByChain: Record<string, TokenInfo[]>;
  tokenIn: string;
  tokenOut: string;
  onTokenInChange: (t: string) => void;
  onTokenOutChange: (t: string) => void;
  onSubmit: () => void;
  onBack: () => void;
}) {
  const { t } = useTranslation();
  const sourceTokens = tokensByChain[sourceChain] || [];
  const targetTokens = tokensByChain[targetChain] || [];

  return (
    <div className="space-y-6">
      <div className="text-center">
        <h2 className="text-xl font-bold text-white flex items-center justify-center gap-2">
          <Coins className="w-5 h-5 text-[#7ED7C4]" />
          {t('routing.selectTokens')}
        </h2>
        <p className="text-gray-400 text-sm mt-2">{t('routing.selectTokensDesc')}</p>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        {/* Token In */}
        <div className="space-y-3">
          <label className="text-sm font-medium text-gray-300 flex items-center gap-2">
            <TrendingDown className="w-4 h-4 text-red-400" />
            {t('routing.payToken')}
          </label>
          <div className="grid grid-cols-2 gap-3">
            {sourceTokens.map((token) => (
              <button
                key={token.symbol}
                onClick={() => onTokenInChange(token.symbol)}
                className={`p-3 rounded-xl border-2 transition-all text-left ${
                  tokenIn === token.symbol
                    ? 'border-red-500/50 bg-red-500/10'
                    : 'border-white/5 bg-[#161b2e] hover:border-white/10 hover:bg-[#1e2438]'
                }`}
              >
                <div className="font-semibold text-white">{token.symbol}</div>
                <div className="text-xs text-gray-400">{token.name}</div>
                <div className="text-xs text-gray-500 mt-1">${token.price_usd.toFixed(2)}</div>
                {tokenIn === token.symbol && (
                  <div className="mt-1 text-xs text-red-400 flex items-center gap-1">
                    <CheckCircle2 className="w-3 h-3" /> {t('routing.tokenSelected')}
                  </div>
                )}
              </button>
            ))}
          </div>
        </div>

        {/* Token Out */}
        <div className="space-y-3">
          <label className="text-sm font-medium text-gray-300 flex items-center gap-2">
            <TrendingUp className="w-4 h-4 text-emerald-400" />
            {t('routing.receiveToken')}
          </label>
          <div className="grid grid-cols-2 gap-3">
            {targetTokens.map((token) => (
              <button
                key={token.symbol}
                onClick={() => onTokenOutChange(token.symbol)}
                className={`p-3 rounded-xl border-2 transition-all text-left ${
                  tokenOut === token.symbol
                    ? 'border-emerald-500/50 bg-emerald-500/10'
                    : 'border-white/5 bg-[#161b2e] hover:border-white/10 hover:bg-[#1e2438]'
                }`}
              >
                <div className="font-semibold text-white">{token.symbol}</div>
                <div className="text-xs text-gray-400">{token.name}</div>
                <div className="text-xs text-gray-500 mt-1">${token.price_usd.toFixed(2)}</div>
                {tokenOut === token.symbol && (
                  <div className="mt-1 text-xs text-emerald-400 flex items-center gap-1">
                    <CheckCircle2 className="w-3 h-3" /> {t('routing.tokenSelected')}
                  </div>
                )}
              </button>
            ))}
          </div>
        </div>
      </div>

      <div className="flex justify-between">
        <button
          onClick={onBack}
          className="flex items-center gap-2 px-4 py-2 rounded-lg text-sm text-gray-400 hover:text-white hover:bg-white/5 transition"
        >
          <ArrowLeft className="w-4 h-4" />
          {t('routing.prevStep')}
        </button>
        <button
          onClick={onSubmit}
          disabled={!tokenIn || !tokenOut}
          className="flex items-center gap-2 px-6 py-3 rounded-xl font-medium text-white mantle-gradient hover:opacity-90 transition disabled:opacity-30 disabled:cursor-not-allowed shadow-lg shadow-[#2D6B5E]/20"
        >
          {t('routing.nextInputAmount')}
          <ChevronRight className="w-4 h-4" />
        </button>
      </div>
    </div>
  );
}

function AmountInputStep({
  tokenIn,
  tokenOut,
  sourceChain,
  amount,
  tokensByChain,
  onAmountChange,
  onSubmit,
  onBack,
}: {
  tokenIn: string;
  tokenOut: string;
  sourceChain: string;
  amount: string;
  tokensByChain: Record<string, TokenInfo[]>;
  onAmountChange: (a: string) => void;
  onSubmit: () => void;
  onBack: () => void;
}) {
  const { t } = useTranslation();
  const tokenInfo = tokensByChain[sourceChain]?.find((t) => t.symbol === tokenIn);
  const amountUsd = tokenInfo && amount ? parseFloat(amount) * tokenInfo.price_usd : 0;

  return (
    <div className="space-y-6">
      <div className="text-center">
        <h2 className="text-xl font-bold text-white flex items-center justify-center gap-2">
          <DollarSign className="w-5 h-5 text-[#7ED7C4]" />
          {t('routing.inputAmount')}
        </h2>
        <p className="text-gray-400 text-sm mt-2">
          {t('routing.inputAmountDesc', { token: tokenIn })}
        </p>
      </div>

      <div className="max-w-md mx-auto space-y-4">
        <div className="bg-[#111827] rounded-2xl border border-white/5 p-6 space-y-4">
          <div className="flex items-center justify-between">
            <span className="text-sm text-gray-400">{t('routing.pay')}</span>
            <div className="flex items-center gap-2">
              <span className="text-sm font-medium text-white">{tokenIn}</span>
              <span className="text-xs text-gray-500">on {sourceChain}</span>
            </div>
          </div>

          <div className="relative">
            <input
              type="number"
              value={amount}
              onChange={(e) => onAmountChange(e.target.value)}
              placeholder="0.00"
              className="w-full bg-white/5 border border-white/10 rounded-xl px-4 py-4 text-2xl font-bold text-white placeholder-gray-600 focus:outline-none focus:border-[#4A9B8C] transition text-center"
            />
            <div className="absolute right-4 top-1/2 -translate-y-1/2">
              <span className="text-sm text-gray-500">{tokenIn}</span>
            </div>
          </div>

          {amountUsd > 0 && (
            <div className="text-center text-sm text-gray-400">
              ≈ <span className="text-[#7ED7C4] font-medium">${amountUsd.toFixed(2)}</span> USD
            </div>
          )}

          <div className="flex items-center justify-center gap-2 text-gray-500">
            <ArrowDown className="w-4 h-4" />
          </div>

          <div className="flex items-center justify-between">
            <span className="text-sm text-gray-400">{t('routing.receive')}</span>
            <div className="flex items-center gap-2">
              <span className="text-sm font-medium text-white">{tokenOut}</span>
            </div>
          </div>
        </div>

        {/* Quick amounts */}
        <div className="flex gap-2 justify-center">
          {['10', '50', '100', '500'].map((v) => (
            <button
              key={v}
              onClick={() => onAmountChange(v)}
              className="px-3 py-1.5 rounded-lg text-xs bg-white/5 border border-white/10 hover:bg-white/10 transition text-gray-300"
            >
              {v} {tokenIn}
            </button>
          ))}
        </div>
      </div>

      <div className="flex justify-between">
        <button
          onClick={onBack}
          className="flex items-center gap-2 px-4 py-2 rounded-lg text-sm text-gray-400 hover:text-white hover:bg-white/5 transition"
        >
          <ArrowLeft className="w-4 h-4" />
          {t('routing.prevStep')}
        </button>
        <button
          onClick={onSubmit}
          disabled={!amount || parseFloat(amount) <= 0}
          className="flex items-center gap-2 px-6 py-3 rounded-xl font-medium text-white mantle-gradient hover:opacity-90 transition disabled:opacity-30 disabled:cursor-not-allowed shadow-lg shadow-[#2D6B5E]/20"
        >
          <BrainCircuit className="w-4 h-4" />
          {t('routing.startAnalysis')}
        </button>
      </div>
    </div>
  );
}

function AnalysisStep({
  isAnalyzing,
  progress,
  onStartAnalysis,
  onBack,
}: {
  isAnalyzing: boolean;
  progress: AnalysisProgress | null;
  onStartAnalysis: () => void;
  onBack: () => void;
}) {
  const { t } = useTranslation();

  if (!isAnalyzing && (!progress || progress.status === 'idle')) {
    return (
      <div className="space-y-6 text-center py-10">
        <div className="w-20 h-20 rounded-full bg-[#4A9B8C]/10 flex items-center justify-center mx-auto">
          <BrainCircuit className="w-10 h-10 text-[#7ED7C4]" />
        </div>
        <h2 className="text-xl font-bold text-white">{t('routing.readyForAnalysis')}</h2>
        <p className="text-gray-400 max-w-md mx-auto">
          {t('routing.analysisDesc')}
        </p>
        <div className="flex justify-center gap-4">
          <button
            onClick={onBack}
            className="flex items-center gap-2 px-4 py-2 rounded-lg text-sm text-gray-400 hover:text-white hover:bg-white/5 transition"
          >
            <ArrowLeft className="w-4 h-4" />
            {t('routing.prevStep')}
          </button>
          <button
            onClick={onStartAnalysis}
            className="flex items-center gap-2 px-6 py-3 rounded-xl font-medium text-white mantle-gradient hover:opacity-90 transition shadow-lg shadow-[#2D6B5E]/20"
          >
            <Sparkles className="w-4 h-4" />
            {t('routing.startSmartAnalysis')}
          </button>
        </div>
      </div>
    );
  }

  const percent = progress?.progress_percent || 0;

  return (
    <div className="space-y-6 py-6">
      <div className="text-center">
        <h2 className="text-xl font-bold text-white flex items-center justify-center gap-2">
          <BrainCircuit className="w-5 h-5 text-[#7ED7C4] animate-pulse" />
          {t('routing.agentAnalyzing')}
        </h2>
        <p className="text-gray-400 text-sm mt-2">{t('routing.analyzingDesc')}</p>
      </div>

      {/* Progress Bar */}
      <div className="max-w-lg mx-auto">
        <div className="flex items-center justify-between mb-2">
          <span className="text-sm text-gray-400">{progress?.current_task || t('routing.preparing')}</span>
          <span className="text-sm font-medium text-[#7ED7C4]">{percent}%</span>
        </div>
        <div className="h-3 bg-white/5 rounded-full overflow-hidden">
          <div
            className="h-full bg-[#4A9B8C] rounded-full transition-all duration-500 relative"
            style={{ width: `${percent}%` }}
          >
            <div className="absolute inset-0 bg-white/20 animate-pulse" />
          </div>
        </div>
      </div>

      {/* Agent Logs */}
      <div className="max-w-lg mx-auto bg-[#111827] rounded-xl border border-white/5 overflow-hidden">
        <div className="px-4 py-2 border-b border-white/5 flex items-center gap-2">
          <Activity className="w-4 h-4 text-[#7ED7C4]" />
          <span className="text-xs font-medium text-gray-400">{t('routing.agentLogs')}</span>
        </div>
        <div className="p-4 h-48 overflow-y-auto space-y-1.5 font-mono text-xs">
          {(progress?.logs || []).map((log, i) => (
            <div key={i} className="text-gray-400">
              <span className="text-[#4A9B8C]">➜</span> {log}
            </div>
          ))}
          {isAnalyzing && (
            <div className="text-gray-500 animate-pulse">
              <span className="text-[#4A9B8C]">➜</span> {t('routing.processing')}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

function RouteDisplayStep({
  routes,
  summary,
  selectedRouteId,
  onSelectRoute,
  onBack,
}: {
  routes: RouteOption[];
  summary?: string;
  selectedRouteId: string;
  onSelectRoute: (r: RouteOption) => void;
  onBack: () => void;
}) {
  const { t } = useTranslation();

  if (routes.length === 0) {
    return (
      <div className="text-center py-10">
        <AlertTriangle className="w-12 h-12 text-yellow-500 mx-auto mb-4" />
        <p className="text-gray-400">{t('routing.noRoutesFound')}</p>
        <button onClick={onBack} className="mt-4 text-sm text-[#7ED7C4] hover:underline">
          {t('routing.reanalyze')}
        </button>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div className="text-center">
        <h2 className="text-xl font-bold text-white flex items-center justify-center gap-2">
          <Route className="w-5 h-5 text-[#7ED7C4]" />
          {t('routing.routeResults')}
        </h2>
        {summary && <p className="text-gray-400 text-sm mt-2 max-w-2xl mx-auto">{summary}</p>}
      </div>

      <div className="grid gap-4">
        {routes.map((route, idx) => (
          <RouteCard
            key={route.route_id}
            route={route}
            rank={idx + 1}
            isSelected={selectedRouteId === route.route_id}
            onSelect={() => onSelectRoute(route)}
          />
        ))}
      </div>

      <div className="flex justify-between">
        <button
          onClick={onBack}
          className="flex items-center gap-2 px-4 py-2 rounded-lg text-sm text-gray-400 hover:text-white hover:bg-white/5 transition"
        >
          <ArrowLeft className="w-4 h-4" />
          {t('routing.prevStep')}
        </button>
        {selectedRouteId && (
          <div className="text-sm text-[#7ED7C4]">
            {t('routing.routeSelectedAutoNext')}
          </div>
        )}
      </div>
    </div>
  );
}

function RouteCard({
  route,
  rank,
  isSelected,
  onSelect,
}: {
  route: RouteOption;
  rank: number;
  isSelected: boolean;
  onSelect: () => void;
}) {
  const { t } = useTranslation();
  const isPositive = route.net_return_usd >= 0;

  return (
    <div
      onClick={onSelect}
      className={`rounded-2xl border-2 transition-all cursor-pointer overflow-hidden ${
        isSelected
          ? 'border-[#4A9B8C] bg-[#4A9B8C]/5'
          : 'border-white/5 bg-[#111827] hover:border-white/15 hover:bg-[#1a2332]'
      }`}
    >
      {/* Header */}
      <div className="p-4 border-b border-white/5">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div
              className={`w-8 h-8 rounded-full flex items-center justify-center text-sm font-bold ${
                rank === 1 ? 'bg-yellow-500/20 text-yellow-400' : 'bg-white/5 text-gray-400'
              }`}
            >
              #{rank}
            </div>
            <div>
              <div className="font-semibold text-white flex items-center gap-2">
                {route.name}
                {route.steps.some((s) => s.details?.is_real_quote) && (
                  <span className="px-2 py-0.5 rounded-full text-[10px] bg-emerald-500/20 text-emerald-400 border border-emerald-500/30">
                    {t('routing.onChainRealData')}
                  </span>
                )}
                {route.tags.includes('recommended') && (
                  <span className="px-2 py-0.5 rounded-full text-[10px] bg-[#4A9B8C]/20 text-[#7ED7C4] border border-[#4A9B8C]/30">
                    {t('routing.recommended')}
                  </span>
                )}
                {route.tags.includes('fastest') && (
                  <span className="px-2 py-0.5 rounded-full text-[10px] bg-blue-500/20 text-blue-400 border border-blue-500/30">
                    {t('routing.fastest')}
                  </span>
                )}
                {route.tags.includes('cheapest') && (
                  <span className="px-2 py-0.5 rounded-full text-[10px] bg-emerald-500/20 text-emerald-400 border border-emerald-500/30">
                    {t('routing.cheapest')}
                  </span>
                )}
              </div>
              <div className="text-xs text-gray-500 mt-0.5">{route.description}</div>
            </div>
          </div>
          <div className="text-right">
            <div className="text-lg font-bold text-white">{route.score.toFixed(1)}</div>
            <div className="text-xs text-gray-500">{t('routing.overallScore')}</div>
          </div>
        </div>
      </div>

      {/* Route Visualization */}
      <div className="p-4">
        <div className="flex items-center gap-2 overflow-x-auto pb-2">
          {route.steps.map((step, i) => (
            <RouteStepVisual key={i} step={step} isLast={i === route.steps.length - 1} />
          ))}
        </div>
      </div>

      {/* Stats */}
      <div className="px-4 pb-4">
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
          <StatItem icon={<DollarSign className="w-4 h-4" />} label={t('routing.input')} value={`$${route.total_input_usd.toFixed(2)}`} />
          <StatItem
            icon={<TrendingUp className="w-4 h-4" />}
            label={t('routing.estimatedOutput')}
            value={`$${route.total_output_usd.toFixed(2)}`}
          />
          <StatItem
            icon={isPositive ? <TrendingUp className="w-4 h-4 text-emerald-400" /> : <TrendingDown className="w-4 h-4 text-red-400" />}
            label={t('routing.netReturn')}
            value={`${isPositive ? '+' : ''}${route.net_return_percent.toFixed(3)}%`}
            valueClass={isPositive ? 'text-emerald-400' : 'text-red-400'}
          />
          <StatItem icon={<Clock className="w-4 h-4" />} label={t('routing.estimatedTime')} value={formatTime(route.total_time_sec, t)} />
        </div>
        <div className="grid grid-cols-3 gap-3 mt-2">
          <StatItem icon={<DollarSign className="w-4 h-4" />} label={t('routing.totalFee')} value={`$${route.total_fee_usd.toFixed(4)}`} />
          <StatItem icon={<Fuel className="w-4 h-4" />} label={t('routing.gas')} value={`$${route.total_gas_usd.toFixed(4)}`} />
          <StatItem icon={<Minus className="w-4 h-4" />} label={t('routing.slippage')} value={`${route.total_slippage.toFixed(2)}%`} />
        </div>
      </div>

      {/* Risk */}
      <div className="px-4 pb-4">
        <div className={`inline-flex items-center gap-1.5 px-2 py-1 rounded-lg text-xs ${
          route.risk_level === 'low'
            ? 'bg-emerald-500/10 text-emerald-400 border border-emerald-500/20'
            : route.risk_level === 'medium'
              ? 'bg-amber-500/10 text-amber-400 border border-amber-500/20'
              : 'bg-red-500/10 text-red-400 border border-red-500/20'
        }`}>
          <ShieldCheck className="w-3 h-3" />
          {t('routing.riskLevel')}: {route.risk_level === 'low' ? t('routing.riskLow') : route.risk_level === 'medium' ? t('routing.riskMedium') : t('routing.riskHigh')}
        </div>
      </div>

      {isSelected && (
        <div className="px-4 pb-4">
          <div className="flex items-center justify-center gap-2 py-3 rounded-xl bg-[#4A9B8C]/10 border border-[#4A9B8C]/20 text-[#7ED7C4] text-sm font-medium">
            <CheckCircle2 className="w-5 h-5" />
            {t('routing.routeSelected')}
          </div>
        </div>
      )}
    </div>
  );
}

function RouteStepVisual({ step, isLast }: { step: RouteStepDetail; isLast: boolean }) {
  const { t } = useTranslation();
  const typeColors: Record<string, string> = {
    swap: 'bg-purple-500/20 text-purple-400 border-purple-500/30',
    bridge: 'bg-amber-500/20 text-amber-400 border-amber-500/30',
    wrap: 'bg-blue-500/20 text-blue-400 border-blue-500/30',
    unwrap: 'bg-blue-500/20 text-blue-400 border-blue-500/30',
    approve: 'bg-gray-500/20 text-gray-400 border-gray-500/30',
  };

  return (
    <div className="flex items-center gap-2 shrink-0">
      <div className={`px-3 py-2 rounded-xl border text-xs ${typeColors[step.step_type] || typeColors.approve}`}>
        <div className="font-medium">{step.protocol}</div>
        <div className="text-[10px] opacity-80 mt-0.5">
          {step.from_token} → {step.to_token}
        </div>
        <div className="text-[10px] opacity-60">
          {step.from_chain_name} → {step.to_chain_name}
        </div>
        {step.details?.is_real_quote && (
          <div className="text-[9px] text-emerald-400 mt-0.5 flex items-center gap-0.5">
            <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 inline-block" />
            {t('routing.onChainRealTime')}
          </div>
        )}
      </div>
      {!isLast && <ChevronRight className="w-4 h-4 text-gray-600 shrink-0" />}
    </div>
  );
}

function StatItem({
  icon,
  label,
  value,
  valueClass = 'text-white',
}: {
  icon: React.ReactNode;
  label: string;
  value: string;
  valueClass?: string;
}) {
  return (
    <div className="flex items-center gap-2 px-3 py-2 rounded-lg bg-white/5">
      <div className="text-gray-500">{icon}</div>
      <div>
        <div className={`text-sm font-semibold ${valueClass}`}>{value}</div>
        <div className="text-[10px] text-gray-500">{label}</div>
      </div>
    </div>
  );
}

function RouteSelectStep({
  selectedRoute,
  walletConnected,
  onWalletCheck,
  onBack,
}: {
  selectedRoute: RouteOption | undefined;
  // onConfirm: () => void;
  walletConnected: boolean;
  onWalletCheck: () => void;
  onBack: () => void;
}) {
  const { t } = useTranslation();

  if (!selectedRoute) {
    return (
      <div className="text-center py-10">
        <AlertTriangle className="w-12 h-12 text-yellow-500 mx-auto mb-4" />
        <p className="text-gray-400">{t('routing.selectRouteFirst')}</p>
        <button onClick={onBack} className="mt-4 text-sm text-[#7ED7C4] hover:underline">
          {t('routing.returnToSelect')}
        </button>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div className="text-center">
        <h2 className="text-xl font-bold text-white flex items-center justify-center gap-2">
          <CheckCircle2 className="w-5 h-5 text-[#7ED7C4]" />
          {t('routing.confirmRoute')}
        </h2>
        <p className="text-gray-400 text-sm mt-2">{t('routing.confirmRouteDesc')}</p>
      </div>

      <RouteCard route={selectedRoute} rank={1} isSelected={true} onSelect={() => {}} />

      <div className="flex justify-between">
        <button
          onClick={onBack}
          className="flex items-center gap-2 px-4 py-2 rounded-lg text-sm text-gray-400 hover:text-white hover:bg-white/5 transition"
        >
          <ArrowLeft className="w-4 h-4" />
          {t('routing.reselect')}
        </button>
        <button
          onClick={onWalletCheck}
          className="flex items-center gap-2 px-6 py-3 rounded-xl font-medium text-white mantle-gradient hover:opacity-90 transition shadow-lg shadow-[#2D6B5E]/20"
        >
          <Wallet className="w-4 h-4" />
          {walletConnected ? t('routing.checkWallet') : t('routing.connectAndCheck')}
        </button>
      </div>
    </div>
  );
}

function WalletCheckStep({
  result,
  onCheck,
  walletConnected,
  walletAddress,
  onExecute,
  onBack,
}: {
  result: WalletCheckResult | null;
  onCheck: () => void;
  walletConnected: boolean;
  walletAddress: string | null;
  onExecute: () => void;
  onBack: () => void;
}) {
  const { t } = useTranslation();

  if (!result) {
    return (
      <div className="space-y-6 text-center py-10">
        <div className="w-20 h-20 rounded-full bg-[#4A9B8C]/10 flex items-center justify-center mx-auto">
          <Wallet className="w-10 h-10 text-[#7ED7C4]" />
        </div>
        <h2 className="text-xl font-bold text-white">{t('routing.walletCheck')}</h2>
        <p className="text-gray-400 max-w-md mx-auto">
          {t('routing.walletCheckDesc')}
        </p>
        {!walletConnected && (
          <div className="text-amber-400 text-sm bg-amber-400/10 border border-amber-400/20 rounded-xl p-4 max-w-md mx-auto">
            <AlertTriangle className="w-4 h-4 inline mr-2" />
            {t('routing.connectWalletToCheck')}
          </div>
        )}
        <div className="flex justify-center gap-4">
          <button
            onClick={onBack}
            className="flex items-center gap-2 px-4 py-2 rounded-lg text-sm text-gray-400 hover:text-white hover:bg-white/5 transition"
          >
            <ArrowLeft className="w-4 h-4" />
            {t('routing.prevStep')}
          </button>
          <button
            onClick={onCheck}
            disabled={!walletConnected}
            className="flex items-center gap-2 px-6 py-3 rounded-xl font-medium text-white mantle-gradient hover:opacity-90 transition disabled:opacity-30 disabled:cursor-not-allowed shadow-lg shadow-[#2D6B5E]/20"
          >
            <ShieldCheck className="w-4 h-4" />
            {t('routing.startCheck')}
          </button>
        </div>
      </div>
    );
  }

  const checks = [
    {
      label: t('routing.balanceSufficient', { token: result.token_in }),
      ok: result.balance_ok,
      detail: t('routing.detailCurrentRequired', { current: result.balance_current, required: result.balance_required }),
    },
    {
      label: t('routing.tokenApproval'),
      ok: result.allowance_ok,
      detail: t('routing.detailCurrentRequired', { current: result.allowance_current, required: result.allowance_required }),
    },
    {
      label: t('routing.sourceGasSufficient'),
      ok: result.source_gas_ok,
      detail: t('routing.detailCurrentRequired', { current: result.source_gas_balance, required: result.source_gas_required }),
    },
    {
      label: t('routing.targetGasSufficient'),
      ok: result.target_gas_ok,
      detail: t('routing.detailCurrentRequired', { current: result.target_gas_balance, required: result.target_gas_required }),
    },
  ];

  return (
    <div className="space-y-6">
      <div className="text-center">
        <h2 className="text-xl font-bold text-white flex items-center justify-center gap-2">
          <ShieldCheck className="w-5 h-5 text-[#7ED7C4]" />
          {t('routing.walletCheckResult')}
        </h2>
        <p className="text-gray-400 text-sm mt-2">
          Wallet: {walletAddress?.slice(0, 6)}...{walletAddress?.slice(-4)}
        </p>
      </div>

      <div className="max-w-lg mx-auto space-y-3">
        {checks.map((check, i) => (
          <div
            key={i}
            className={`flex items-center justify-between p-4 rounded-xl border ${
              check.ok
                ? 'bg-emerald-500/5 border-emerald-500/20'
                : 'bg-red-500/5 border-red-500/20'
            }`}
          >
            <div className="flex items-center gap-3">
              {check.ok ? (
                <CheckCircle2 className="w-5 h-5 text-emerald-400" />
              ) : (
                <X className="w-5 h-5 text-red-400" />
              )}
              <div>
                <div className={`text-sm font-medium ${check.ok ? 'text-emerald-400' : 'text-red-400'}`}>
                  {check.label}
                </div>
                <div className="text-xs text-gray-500">{check.detail}</div>
              </div>
            </div>
          </div>
        ))}

        {result.warnings.length > 0 && (
          <div className="p-4 rounded-xl bg-amber-500/5 border border-amber-500/20">
            <div className="flex items-center gap-2 text-amber-400 text-sm font-medium mb-2">
              <AlertTriangle className="w-4 h-4" />
              {t('routing.warnings')}
            </div>
            <ul className="space-y-1">
              {result.warnings.map((w, i) => (
                <li key={i} className="text-xs text-amber-400/80 flex items-start gap-2">
                  <Info className="w-3 h-3 mt-0.5 shrink-0" />
                  {w}
                </li>
              ))}
            </ul>
          </div>
        )}
      </div>

      <div className="flex justify-between">
        <button
          onClick={onBack}
          className="flex items-center gap-2 px-4 py-2 rounded-lg text-sm text-gray-400 hover:text-white hover:bg-white/5 transition"
        >
          <ArrowLeft className="w-4 h-4" />
          {t('routing.prevStep')}
        </button>
        <button
          onClick={onExecute}
          disabled={!result.can_proceed}
          className="flex items-center gap-2 px-6 py-3 rounded-xl font-medium text-white mantle-gradient hover:opacity-90 transition disabled:opacity-30 disabled:cursor-not-allowed shadow-lg shadow-[#2D6B5E]/20"
        >
          <Send className="w-4 h-4" />
          {result.can_proceed ? t('routing.executeTx') : t('routing.cannotExecute')}
        </button>
      </div>
    </div>
  );
}

function ExecutionStep({
  result,
  executing,
  onExecute,
  onReset,
}: {
  result: ExecutionResult | undefined;
  executing: boolean;
  onExecute: () => void;
  onReset: () => void;
}) {
  const { t } = useTranslation();

  if (executing) {
    return (
      <div className="text-center py-16">
        <Loader2 className="w-12 h-12 animate-spin text-[#4A9B8C] mx-auto mb-4" />
        <h2 className="text-xl font-bold text-white">{t('routing.executingTx')}</h2>
        <p className="text-gray-400 text-sm mt-2">{t('routing.submittingToChain')}</p>
      </div>
    );
  }

  if (!result) {
    return (
      <div className="space-y-6 text-center py-10">
        <div className="w-20 h-20 rounded-full bg-[#4A9B8C]/10 flex items-center justify-center mx-auto">
          <Send className="w-10 h-10 text-[#7ED7C4]" />
        </div>
        <h2 className="text-xl font-bold text-white">{t('routing.confirmExecution')}</h2>
        <p className="text-gray-400 max-w-md mx-auto">{t('routing.allChecksPassed')}</p>
        <button
          onClick={onExecute}
          className="flex items-center gap-2 px-6 py-3 rounded-xl font-medium text-white mantle-gradient hover:opacity-90 transition shadow-lg shadow-[#2D6B5E]/20 mx-auto"
        >
          <Zap className="w-4 h-4" />
          {t('routing.confirmExecuteTx')}
        </button>
      </div>
    );
  }

  const isSuccess = result.status === 'confirmed' || result.status === 'success';

  return (
    <div className="space-y-6 text-center py-6">
      {isSuccess ? (
        <>
          <div className="w-20 h-20 rounded-full bg-emerald-500/10 flex items-center justify-center mx-auto">
            <CheckCircle2 className="w-10 h-10 text-emerald-400" />
          </div>
          <h2 className="text-xl font-bold text-white">{t('routing.txSuccess')}</h2>

          <div className="max-w-md mx-auto bg-[#111827] rounded-2xl border border-white/5 p-6 space-y-4 text-left">
            <div className="flex items-center justify-between">
              <span className="text-sm text-gray-400">{t('routing.status')}</span>
              <span className="text-sm font-medium text-emerald-400 flex items-center gap-1">
                <CheckCircle2 className="w-4 h-4" /> {t('routing.confirmed')}
              </span>
            </div>
            {result.tx_hash && (
              <div className="flex items-center justify-between">
                <span className="text-sm text-gray-400">{t('routing.txHash')}</span>
                <span className="text-sm font-mono text-white">{result.tx_hash.slice(0, 14)}...{result.tx_hash.slice(-6)}</span>
              </div>
            )}
            {result.gas_used && (
              <div className="flex items-center justify-between">
                <span className="text-sm text-gray-400">{t('routing.gasUsed')}</span>
                <span className="text-sm text-white">{result.gas_used}</span>
              </div>
            )}
            {result.timestamp && (
              <div className="flex items-center justify-between">
                <span className="text-sm text-gray-400">{t('routing.time')}</span>
                <span className="text-sm text-white">{new Date(result.timestamp).toLocaleString()}</span>
              </div>
            )}
            {result.explorer_url && (
              <a
                href={result.explorer_url}
                target="_blank"
                rel="noopener noreferrer"
                className="flex items-center justify-center gap-2 w-full py-2.5 rounded-xl bg-white/5 border border-white/10 hover:bg-white/10 transition text-sm text-[#7ED7C4]"
              >
                <ExternalLink className="w-4 h-4" />
                {t('routing.viewOnExplorer')}
              </a>
            )}
          </div>
        </>
      ) : (
        <>
          <div className="w-20 h-20 rounded-full bg-red-500/10 flex items-center justify-center mx-auto">
            <X className="w-10 h-10 text-red-400" />
          </div>
          <h2 className="text-xl font-bold text-white">{t('routing.txFailed')}</h2>
          {result.error && <p className="text-red-400 text-sm mt-2">{result.error}</p>}
        </>
      )}

      <button
        onClick={onReset}
        className="flex items-center gap-2 px-6 py-3 rounded-xl font-medium text-white mantle-gradient hover:opacity-90 transition shadow-lg shadow-[#2D6B5E]/20 mx-auto"
      >
        <RefreshCw className="w-4 h-4" />
        {t('routing.startNewRoute')}
      </button>
    </div>
  );
}

// ============ Utilities ============

function formatTime(seconds: number, t: (key: string, options?: Record<string, unknown>) => string): string {
  if (seconds < 60) return t('routing.seconds', { count: seconds });
  if (seconds < 3600) return t('routing.minutes', { count: Math.ceil(seconds / 60) });
  const hours = Math.floor(seconds / 3600);
  const mins = Math.ceil((seconds % 3600) / 60);
  return mins > 0 ? t('routing.hoursMinutes', { hours, minutes: mins }) : t('routing.hours', { count: hours });
}

// Re-export ArrowDown for AmountInputStep
function ArrowDown(props: React.SVGProps<SVGSVGElement>) {
  return (
    <svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" {...props}>
      <path d="M12 5v14" /><path d="m19 12-7 7-7-7" />
    </svg>
  );
}
