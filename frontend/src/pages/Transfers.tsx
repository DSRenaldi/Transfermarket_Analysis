import { useMemo, useState } from 'react'
import { eur, number, pct, useApi } from '../api'
import { ErrorState, Kpi, Loading, PageIntro, Panel } from '../components/Shared'

type Summary = { fee_status: string; transfer_count: number; matured_transfer_count: number; value_change_eligible_count: number; value_change_coverage_pct: number; median_value_change_eur: number; median_value_growth_pct: number }
type Outcome = { transfer_key: number; player_name: string; transfer_date: string; from_club_name: string | null; to_club_name: string | null; fee_status: string; transfer_fee_eur: number | null; baseline_market_value_eur: number; post_market_value_eur: number; post_transfer_value_change_eur: number; post_transfer_value_growth_pct: number; post_valuation_date: string; post_club_match_status: string }
type Payload = { summary: Summary[]; outcomes: Outcome[] }

export default function Transfers() {
  const [horizon, setHorizon] = useState(12)
  const [fee, setFee] = useState('')
  const { data, loading, error } = useApi<Payload>(`/api/transfers?horizon=${horizon}${fee ? `&fee_status=${fee}` : ''}`)
  const totals = useMemo(() => data?.summary.reduce((acc, row) => ({ transfers: acc.transfers + row.transfer_count, matured: acc.matured + row.matured_transfer_count, eligible: acc.eligible + row.value_change_eligible_count }), { transfers: 0, matured: 0, eligible: 0 }) ?? { transfers: 0, matured: 0, eligible: 0 }, [data])
  return (
    <div className="page">
      <PageIntro code="05 / TRANSFERS" title="Follow the valuation—not a promise of ROI." description="Compare the last known value at transfer with a dated observation near the selected post-transfer horizon. Coverage is part of every result." aside={<div className="segmented" aria-label="Transfer outcome horizon">{[6, 12, 24].map((value) => <button key={value} className={horizon === value ? 'active' : ''} onClick={() => setHorizon(value)}>{value}M</button>)}</div>} />
      <div className="local-filter"><label>Fee state<select value={fee} onChange={(e) => setFee(e.target.value)}><option value="">All fee states</option><option value="numeric_fee">Numeric fee</option><option value="recorded_zero_ambiguous">Recorded zero — ambiguous</option><option value="unknown_or_undisclosed">Unknown / undisclosed</option></select></label></div>
      {loading && <Loading label="Aligning transfer horizons" />}
      {error && <ErrorState message={error} />}
      {data && <>
        <section className="kpi-grid kpi-grid-3">
          <Kpi label="Historical transfers" value={number(totals.transfers)} detail={`${horizon}-month rows in the selected fee state`} />
          <Kpi label="Matured horizon" value={number(totals.matured)} detail="Target date is inside valuation coverage" />
          <Kpi label="Comparable outcomes" value={number(totals.eligible)} detail={totals.matured ? `${pct((totals.eligible / totals.matured) * 100)} of matured rows` : 'No mature rows'} tone="cyan" />
        </section>
        <Panel title="Coverage before interpretation" eyebrow="Fee states are never merged silently">
          <div className="coverage-grid">{data.summary.map((row) => <article key={row.fee_status}><span>{row.fee_status.replaceAll('_', ' ')}</span><strong>{pct(row.value_change_coverage_pct)}</strong><small>{number(row.value_change_eligible_count)} comparable · median {eur(row.median_value_change_eur)}</small><div className="coverage-track"><i style={{ width: `${row.value_change_coverage_pct}%` }} /></div></article>)}</div>
        </Panel>
        <Panel title="Largest observed value changes" eyebrow={`${horizon}-month target · eligible observations only`}>
          <div className="table-wrap"><table><thead><tr><th>Player</th><th>Move</th><th>Transfer date</th><th>Baseline</th><th>Post value</th><th>Change</th><th>Post club status</th></tr></thead><tbody>{data.outcomes.map((row) => <tr key={row.transfer_key}><td><strong>{row.player_name || 'Player unavailable'}</strong><small>{row.fee_status.replaceAll('_', ' ')}</small></td><td>{row.from_club_name || 'Unknown'}<small>→ {row.to_club_name || 'Unknown'}</small></td><td>{row.transfer_date}</td><td className="numeric">{eur(row.baseline_market_value_eur)}</td><td className="numeric">{eur(row.post_market_value_eur)}</td><td><span className="score-pill positive">+{eur(row.post_transfer_value_change_eur)}</span></td><td>{row.post_club_match_status.replaceAll('_', ' ')}</td></tr>)}</tbody></table></div>
        </Panel>
        <aside className="method-strip"><strong>Selection warning</strong><p>Rows need a positive baseline and a post valuation within 90 days of target. Players who leave the destination club remain visible and are flagged. The table does not estimate causal transfer impact.</p></aside>
      </>}
    </div>
  )
}
