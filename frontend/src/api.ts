import { useEffect, useState } from 'react'
import type { Filters } from './types'

export function filterQuery(filters: Filters): string {
  const params = new URLSearchParams()
  if (filters.season) params.set('season', filters.season)
  if (filters.competition) params.set('competition', filters.competition)
  if (filters.position) params.set('position', filters.position)
  return params.toString()
}

export function useApi<T>(url: string | null): { data: T | null; loading: boolean; error: string | null } {
  const [data, setData] = useState<T | null>(null)
  const [loading, setLoading] = useState(Boolean(url))
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (!url) {
      setLoading(false)
      return
    }
    const controller = new AbortController()
    setLoading(true)
    setError(null)
    fetch(url, { signal: controller.signal })
      .then(async (response) => {
        const payload = await response.json()
        if (!response.ok) throw new Error(payload.error || `Request failed (${response.status})`)
        return payload as T
      })
      .then(setData)
      .catch((reason: Error) => {
        if (reason.name !== 'AbortError') setError(reason.message)
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false)
      })
    return () => controller.abort()
  }, [url])

  return { data, loading, error }
}

export const eur = (value: number | null | undefined, compact = true): string => {
  if (value == null) return '—'
  return new Intl.NumberFormat('en-GB', {
    style: 'currency',
    currency: 'EUR',
    notation: compact ? 'compact' : 'standard',
    maximumFractionDigits: compact ? 1 : 0,
  }).format(value)
}

export const number = (value: number | null | undefined, digits = 0): string =>
  value == null ? '—' : new Intl.NumberFormat('en-GB', { maximumFractionDigits: digits }).format(value)

export const pct = (value: number | null | undefined, digits = 1): string =>
  value == null ? '—' : `${number(value, digits)}%`
