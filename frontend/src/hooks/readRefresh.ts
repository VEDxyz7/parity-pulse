// Read snapshots only: no writes/providers refreshed by a polling interval.
export const readRefresh = { retry: false as const, staleTime: 10_000, refetchInterval: 30_000, refetchIntervalInBackground: false, refetchOnWindowFocus: false }
