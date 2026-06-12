import i18n from '../i18n';

const PATTERN_MAP: Record<string, string> = {
  '五线顺上': 'pattern.bullishAlignment',
  '5线顺上': 'pattern.bullishAlignment',
  '五线顺下': 'pattern.bearishAlignment',
  '5线顺下': 'pattern.bearishAlignment',
  '阳包阴': 'pattern.bullishEngulfing',
  '阴包阳': 'pattern.bearishEngulfing',
  '早晨之星': 'pattern.morningStar',
  '早晨十字星': 'pattern.morningDojiStar',
  '内包孕线多': 'pattern.bullishHarami',
  '内包孕线空': 'pattern.bearishHarami',
  '启明星': 'pattern.morningStar',
  '多方炮': 'pattern.bullishThreeSoldiers',
};

const CONFIDENCE_MAP: Record<string, string> = {
  '高': 'confidence.high',
  '中': 'confidence.medium',
  '低': 'confidence.low',
};

const WATCH_MAP: Record<string, string> = {
  '其余币种无明确信号': 'watch.noClearSignals',
};

const RISK_SUB_MAP: Record<string, string> = {
  '明确信号较少，建议控制仓位或观望。': 'risk.fewSignals',
  '恐惧贪婪指数处于贪婪区间，注意追高风险。': 'risk.fngGreed',
  '恐惧贪婪指数处于恐惧区间，可能存在超跌反弹机会。': 'risk.fngFear',
  '市场整体方向不明，建议减少操作频率。': 'risk.marketNeutral',
  '市场研判仅供参考，不构成投资建议。': 'risk.disclaimerOnly',
  '快速结果，完整分析进行中...': 'risk.quickResult',
};

const CALC_STEP_MAP: Record<string, string> = {
  '币安信号聚合': 'calculation.binanceAggregation',
  '币安权重贡献': 'calculation.binanceWeight',
  '链上评分': 'calculation.onchainScore',
  '加权计算': 'calculation.weightedCalc',
  '最终指数': 'calculation.finalIndex',
};

export function translatePattern(name: string | undefined): string {
  if (!name) return name || '';
  const key = PATTERN_MAP[name];
  if (key) return i18n.t(key, { defaultValue: name });
  return name;
}

export function translateConfidenceLabel(label: string | undefined): string {
  if (!label) return label || '';
  const key = CONFIDENCE_MAP[label];
  if (key) return i18n.t(key, { defaultValue: label });
  return label;
}

export function translateWatch(text: string | undefined): string {
  if (!text) return text || '';
  const key = WATCH_MAP[text];
  if (key) return i18n.t(key, { defaultValue: text });
  return text;
}

export function translateRiskWarning(warning: string | undefined): string {
  if (!warning) return warning || '';
  let result = warning;
  for (const [cn, key] of Object.entries(RISK_SUB_MAP)) {
    if (result.includes(cn)) {
      result = result.replace(cn, i18n.t(key, { defaultValue: cn }));
    }
  }
  return result;
}

export function translateCalcStep(step: string | undefined): string {
  if (!step) return step || '';
  const key = CALC_STEP_MAP[step];
  if (key) return i18n.t(key, { defaultValue: step });
  return step;
}

export function translateCalcDescription(desc: string | undefined): string {
  if (!desc) return desc || '';

  // "24 看涨 / 18 看跌 / 8 中性"
  const m1 = desc.match(/(\d+)\s*看涨\s*\/\s*(\d+)\s*看跌\s*\/\s*(\d+)\s*中性/);
  if (m1) {
    return i18n.t('calculation.bullishBearishNeutral', {
      bullish: m1[1], bearish: m1[2], neutral: m1[3],
      defaultValue: desc,
    });
  }

  // "权重 0.7"
  const m2 = desc.match(/权重\s*([\d.]+)/);
  if (m2) {
    return i18n.t('calculation.weightDesc', {
      weight: m2[1],
      defaultValue: desc,
    });
  }

  return desc;
}

/** 翻译由 "+" 拼接的 pattern reason 字符串，如 "5线顺上+阳包阴" */
export function translateReason(reason: string | undefined): string {
  if (!reason) return reason || '';
  return reason.split('+').map(p => translatePattern(p.trim())).join(' + ');
}
