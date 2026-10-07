import { ArrowUpRight, CalendarClock } from 'lucide-react'
import { eur, filterQuery, number, useApi } from '../api'
import { HorizontalBars, LineChart } from '../components/Charts'
import { ErrorState, Kpi, Loading, PageIntro, Panel } from '../components/Shared'
import type { Filters } from '../types'

type OverviewData = {
  summary: {
    player_seasons: number
    unique_players: number
    total_market_value_eur: number
    median_market_value_eur: number
    earliest_valuation_date: string
    latest_valuation_date: string
  }
  byPosition: Array<{ position_group: string; player_seasons: number; total_market_value_eur: number; median_market_value_eur: number }>
  byCompetition: Array<{ competition_key: string; competition_name: string; player_seasons: number; total_market_value_eur: number; median_market_value_eur: number }>
  byAge: Array<{ age_band: string; player_seasons: number; median_market_value_eur: number; median_efficiency_score: number }>
}

export default function Overview({ filters, onExplore }: { filters: Filters; onExplore: () => void }) {
  const query = filterQuery(filters)
  const { data, loading, error } = useApi<OverviewData>(`/api/overview?${query}`)
  if (loading) return <Loading label="Building the market view" />
  if (error || !data) return <ErrorState message={error || 'No overview data returned.'} />
  const { summary } = data
  return (
    <div className="page">
      <PageIntro
        code="01 / MARKET"
        title="Read the market. Not the hype."
        description="A dated view of value, age and opportunity across five European leagues. Every number below belongs to the active season and peer context."
        aside={<button className="primary-action" onClick={onExplore}>Explore player signals <ArrowUpRight size={17} /></button>}
      />
      <section className="kpi-grid">
        <Kpi label="Aligned market value" value={eur(summary.total_market_value_eur)} detail={`${number(summary.player_seasons)} eligible player-seasons`} tone="cyan" />
        <Kpi label="Median player value" value={eur(summary.median_market_value_eur)} detail="Preferred benchmark for a skewed market" />
        <Kpi label="Unique players" value={number(summary.unique_players)} detail="Outfield · minimum 900 minutes" />
        <Kpi label="Valuation window" value={summary.latest_valuation_date?.slice(0, 7) ?? '—'} detail={`Earliest ${summary.earliest_valuation_date ?? '—'}`} tone="amber" />
      </section>
      <div className="dashboard-grid two-thirds">
        <Panel title="Where the value sits" eyebrow="Competition allocation">
          <HorizontalBars data={data.byCompetition.map((row) => ({ label: row.competition_name, value: row.total_market_value_eur, secondary: `${number(row.player_seasons)} player-seasons · median ${eur(row.median_market_value_eur)}` }))} />
        </Panel>
        <Panel title="Position benchmark" eyebrow="Median, not mean">
          <div className="position-stack">
            {data.byPosition.map((row) => <article key={row.position_group}><span>{row.position_group}</span><strong>{eur(row.median_market_value_eur)}</strong><small>{number(row.player_seasons)} observations</small></article>)}
          </div>
        </Panel>
      </div>
      <Panel title="The age curve carries a price" eyebrow="Median market value by age band" action={<span className="context-chip"><CalendarClock size={14} /> Dated season-end values</span>}>
        <LineChart data={data.byAge as unknown as Array<Record<string, unknown>>} valueKey="median_market_value_eur" labelKey="age_band" />
      </Panel>
      <aside className="method-strip"><strong>Interpretation line</strong><p>Market value is an estimate, not a fee. Older players can rank efficiently because current performance is strong relative to a lower market estimate—not because the model predicts a bargain.</p></aside>
    </div>
  )
}
