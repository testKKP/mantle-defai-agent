import { useCallback } from 'react'
import { useReadContract, useWriteContract, useAccount, useWaitForTransactionReceipt } from 'wagmi'
import { parseEther } from 'viem'
import abi from '../abi/MantleDeFAIRegistry.json'

const REGISTRY_ADDRESS = (import.meta.env.VITE_REGISTRY_ADDRESS || '') as `0x${string}`

export interface Subscription {
  expiry: bigint
  totalPaid: bigint
  active: boolean
}

export function useRegistry() {
  const { address } = useAccount()
  const registryAddress = REGISTRY_ADDRESS
  const enabled = !!address && !!registryAddress

  const isSubscribed = useReadContract({
    address: registryAddress || undefined,
    abi,
    functionName: 'isSubscribed',
    args: address ? [address] : undefined,
    query: { enabled },
  })

  const subscription = useReadContract({
    address: registryAddress || undefined,
    abi,
    functionName: 'getSubscription',
    args: address ? [address] : undefined,
    query: { enabled },
  })

  const { writeContract, data: hash, isPending, error } = useWriteContract()

  const { isLoading: isConfirming, isSuccess: isConfirmed } = useWaitForTransactionReceipt({
    hash,
  })

  const subscribe = useCallback(() => {
    if (!registryAddress) return
    writeContract({
      address: registryAddress,
      abi,
      functionName: 'subscribe',
      value: parseEther('10'),
    })
  }, [registryAddress, writeContract])

  return {
    registryAddress,
    enabled,
    isSubscribed: isSubscribed.data as boolean | undefined,
    isSubscribedLoading: isSubscribed.isLoading,
    subscription: subscription.data as [bigint, bigint, boolean] | undefined,
    subscriptionLoading: subscription.isLoading,
    subscribe,
    subscribeHash: hash,
    isSubscribing: isPending,
    isConfirming,
    isConfirmed,
    subscribeError: error,
  }
}
