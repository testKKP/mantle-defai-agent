import { keccak256, toBytes } from 'viem'

const EXPECTED_SUBMITTER = '0x909f854B246E4c97130f6d23Cd4fcF051B9241C0'

export interface VerificationResult {
  valid: boolean
  reason: string
  checks: {
    submitter: boolean
    hash: boolean
    fresh: boolean
  }
}

export function verifySignal(
  data: string,
  dataHash: string,
  submitter: string,
  timestamp: bigint
): VerificationResult {
  const checks = {
    submitter: submitter.toLowerCase() === EXPECTED_SUBMITTER.toLowerCase(),
    hash: keccak256(toBytes(data)) === dataHash,
    fresh: Date.now() / 1000 - Number(timestamp) < 24 * 3600,
  }

  const valid = checks.submitter && checks.hash && checks.fresh

  let reason = 'VERIFIED'
  if (!checks.submitter) reason = 'UNAUTHORIZED'
  else if (!checks.hash) reason = 'TAMPERED'
  else if (!checks.fresh) reason = 'EXPIRED'

  return { valid, reason, checks }
}
