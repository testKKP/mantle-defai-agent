import { useState, useCallback } from 'react'
import CryptoJS from 'crypto-js'

export interface DecryptedSignal {
  version?: string
  timestamp?: string
  agent_id?: string
  decision: {
    symbol: string
    timeframe: string
    direction: string
    confidence: string
    reason: string
  }
  elliott_wave?: {
    wave_pattern?: string
    current_wave?: string
    direction?: string
    projections?: Array<{
      scenario?: string
      target_price?: number
      confidence?: number
      stop_loss?: number
    }>
  }
  backtest?: {
    win_rate?: number
    avg_pnl?: number
    profit_factor?: number
    total_signals?: number
  }
  sentiment?: {
    sentiment_index?: number
    market_bias?: string
  }
  raw: string
}

export function useSignalDecrypt() {
  const [decryptKey, setDecryptKey] = useState<string | null>(null)
  const [fetchingKey, setFetchingKey] = useState(false)
  const [fetchError, setFetchError] = useState<string | null>(null)

  const fetchDecryptKey = useCallback(async (walletAddress: string) => {
    setFetchingKey(true)
    setFetchError(null)
    try {
      const response = await fetch(`/api/signals/decrypt-key?address=${walletAddress}`)
      if (!response.ok) throw new Error('Failed to fetch decrypt key')
      const data = await response.json()
      if (data.key) {
        setDecryptKey(data.key)
        return data.key as string
      }
      throw new Error('No key in response')
    } catch (err: any) {
      setFetchError(err.message || 'Unknown error')
      return null
    } finally {
      setFetchingKey(false)
    }
  }, [])

  const decryptSignal = useCallback((encryptedData: string, key: string): DecryptedSignal => {
    try {
      const decrypted = CryptoJS.AES.decrypt(encryptedData, key)
      const plaintext = decrypted.toString(CryptoJS.enc.Utf8)
      if (!plaintext) throw new Error('Decryption failed')
      try {
        const parsed = JSON.parse(plaintext)
        return {
          version: parsed.version,
          timestamp: parsed.timestamp,
          agent_id: parsed.agent_id,
          decision: parsed.decision || {
            symbol: '',
            timeframe: '',
            direction: parsed.direction || '',
            confidence: parsed.confidence || '',
            reason: '',
          },
          elliott_wave: parsed.elliott_wave,
          backtest: parsed.backtest,
          sentiment: parsed.sentiment,
          raw: plaintext,
        }
      } catch {
        return {
          decision: {
            symbol: '',
            timeframe: '',
            direction: '',
            confidence: '',
            reason: plaintext,
          },
          raw: plaintext,
        }
      }
    } catch (err: any) {
      return {
        decision: {
          symbol: '',
          timeframe: '',
          direction: '',
          confidence: '',
          reason: `Decryption error: ${err.message}`,
        },
        raw: `Decryption error: ${err.message}`,
      }
    }
  }, [])

  return {
    decryptKey,
    fetchingKey,
    fetchError,
    fetchDecryptKey,
    decryptSignal,
  }
}
