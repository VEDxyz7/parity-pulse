import { useQuery } from '@tanstack/react-query'
import { fetchFoundationStatus } from '../services/system'

export function useSystemStatus() {
  return useQuery({
    queryKey: ['foundation-status'],
    queryFn: ({ signal }) => fetchFoundationStatus(signal),
    retry: false,
    refetchInterval: 30_000,
    staleTime: 5_000,
  })
}
