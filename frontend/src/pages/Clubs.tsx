import { eur, filterQuery, number, pct, useApi } from '../api'
import { HorizontalBars } from '../components/Charts'
import { Empty, ErrorState, Loading, PageIntro, Panel } from '../components/Shared'
import type { Filters } from '../types'

type ClubRow = { club_key: number; club_name: string; player_comparisons: number; total_value_change_eur: number; median_value_change_eur: number; median_value_growth_pct: number; players_with_value_gain: number }

export default function Clubs({ filters }: { filters: Filters }) {
  const { data, loading, error } = useApi<{ rows: ClubRow[]; minimumComparisons: number; interpretation: string }>(`/api/clubs?${filterQuery(filters)}`)
  if (loading) return <Loading label="Aggregating club cohorts" />
  if (error || !data) return <ErrorState message={error || 'No club data returned.'} />
  return (
    <div className="page">
      <PageIntro code="06 / CLUBS" title="Development leaves a trace, not a verdict." description="Summarize consecutive-season player value changes against the player’s season-end club. Every club shown clears the minimum comparison count." />
      <Panel title="Median value change by club" eyebrow={`At least ${data.minimumComparisons} comparable player-seasons`}>
        {data.rows.length ? <HorizontalBars data={data.rows.slice(0, 12).map((row) => ({ label: row.club_name, value: Math.max(row.median_value_change_eur, 0), secondary: `${number(row.player_comparisons)} comparisons · ${pct((row.players_with_value_gain / row.player_comparisons) * 100)} gained value` }))} /> : <Empty>No clubs clear the minimum sample for these filters.</Empty>}
      </Panel>
      <Panel title="Club cohort board" eyebrow="Association with season-end club">
        <div className="table-wrap"><table><thead><tr><th>Club</th><th>Comparisons</th><th>Players gaining value</th><th>Median change</th><th>Median growth</th><th>Total observed change</th></tr></thead><tbody>{data.rows.map((row) => <tr key={row.club_key}><td><strong>{row.club_name}</strong></td><td className="numeric">{number(row.player_comparisons)}</td><td className="numeric">{number(row.players_with_value_gain)} / {number(row.player_comparisons)}</td><td className="numeric">{eur(row.median_value_change_eur)}</td><td className="numeric">{pct(row.median_value_growth_pct)}</td><td className="numeric">{eur(row.total_value_change_eur)}</td></tr>)}</tbody></table></div>
      </Panel>
      <aside className="method-strip"><strong>Club attribution limit</strong><p>{data.interpretation} Recruitment date, playing role, contracts, injuries and later transfers are not controlled here.</p></aside>
    </div>
  )
}
