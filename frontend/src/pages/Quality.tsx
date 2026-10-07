import { CheckCircle2, Database, TriangleAlert } from 'lucide-react'
import { number, pct, useApi } from '../api'
import { ErrorState, Loading, PageIntro, Panel } from '../components/Shared'

type Payload = {
  snapshots: Array<{ source_table: string; min_business_date: string; max_business_date: string; row_count: number }>
  coverage: Array<{ competition_key: string; season_key: number; game_count: number; games_with_appearances: number; appearance_game_coverage_pct: number; appearance_coverage_status: string }>
  validation: Array<{ phase: string; checks: number; passed: number; failed: number; audited_at_utc: string }>
  parameters: { methodology_version: string; minimum_minutes: number; maximum_season_valuation_lag_days: number; minimum_peer_group_size: number; winsor_lower_percentile: number; winsor_upper_percentile: number; maximum_transfer_target_lag_days: number; transfer_horizons_months: number[] }
  weights: Array<{ position_group: string; metric_name: string; metric_weight: number; direction: string }>
  limitations: string[]
}

export default function Quality() {
  const { data, loading, error } = useApi<Payload>('/api/quality')
  if (loading) return <Loading label="Reading audit evidence" />
  if (error || !data) return <ErrorState message={error || 'No methodology data returned.'} />
  return (
    <div className="page">
      <PageIntro code="07 / TRUST" title="Show the seams." description="Freshness, coverage, exclusions and weights are part of the product—not footnotes hidden behind a ranking." />
      <section className="validation-grid">{data.validation.map((row) => <article key={row.phase}><CheckCircle2 size={22} /><div><span>{row.phase}</span><strong>{row.checks} checks · {row.failed} failures</strong><small>{row.passed} enforced checks passed · {row.audited_at_utc.slice(0, 10)}</small></div></article>)}</section>
      <div className="dashboard-grid equal">
        <Panel title="Methodology controls" eyebrow={`Version ${data.parameters.methodology_version}`}>
          <dl className="method-list"><div><dt>Minimum minutes</dt><dd>{number(data.parameters.minimum_minutes)}</dd></div><div><dt>Maximum valuation lag</dt><dd>{data.parameters.maximum_season_valuation_lag_days} days</dd></div><div><dt>Minimum peer size</dt><dd>{data.parameters.minimum_peer_group_size}</dd></div><div><dt>Winsor limits</dt><dd>{pct(data.parameters.winsor_lower_percentile * 100, 0)} / {pct(data.parameters.winsor_upper_percentile * 100, 0)}</dd></div><div><dt>Transfer target lag</dt><dd>{data.parameters.maximum_transfer_target_lag_days} days</dd></div><div><dt>Outcome horizons</dt><dd>{data.parameters.transfer_horizons_months.join(' / ')} months</dd></div></dl>
        </Panel>
        <Panel title="Known limitations" eyebrow="Read before using a shortlist">
          <ul className="limitation-list">{data.limitations.map((item) => <li key={item}><TriangleAlert size={15} />{item}</li>)}</ul>
        </Panel>
      </div>
      <Panel title="Position-specific score weights" eyebrow="Stored in PostgreSQL · lower cards is better">
        <div className="weight-grid">{['Defender', 'Midfielder', 'Forward'].map((position) => <article key={position}><h3>{position}</h3>{data.weights.filter((row) => row.position_group === position).map((row) => <div key={row.metric_name}><span>{row.metric_name.replaceAll('_', ' ')}</span><strong>{pct(row.metric_weight * 100, 0)}</strong><i style={{ width: `${row.metric_weight * 100}%` }} /></div>)}</article>)}</div>
      </Panel>
      <Panel title="Source freshness" eyebrow="Actual dates, never a generic “current” label" action={<Database size={17} />}>
        <div className="table-wrap"><table><thead><tr><th>Source</th><th>Rows</th><th>First observed</th><th>Last observed</th></tr></thead><tbody>{data.snapshots.map((row) => <tr key={row.source_table}><td><strong>{row.source_table.replaceAll('_', ' ')}</strong></td><td className="numeric">{number(row.row_count)}</td><td>{row.min_business_date}</td><td>{row.max_business_date}</td></tr>)}</tbody></table></div>
      </Panel>
      <Panel title="Competition-season coverage" eyebrow="Games with appearance rows">
        <div className="coverage-matrix">{data.coverage.map((row) => <article key={`${row.competition_key}-${row.season_key}`} className={row.appearance_coverage_status === 'FULL' ? 'full' : 'high'}><span>{row.competition_key}</span><strong>{row.season_key}</strong><small>{row.games_with_appearances}/{row.game_count} · {pct(row.appearance_game_coverage_pct, 2)}</small></article>)}</div>
      </Panel>
    </div>
  )
}
