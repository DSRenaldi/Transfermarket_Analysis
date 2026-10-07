import { Info, MoveUpRight } from 'lucide-react'
import { eur, filterQuery, number, useApi } from '../api'
import { ScatterPlot } from '../components/Charts'
import { ErrorState, Kpi, Loading, PageIntro, Panel } from '../components/Shared'
import type { EfficiencyRow, Filters } from '../types'

type Payload = { rows: EfficiencyRow[]; returnedRows: number }

export default function Efficiency({ filters, onPlayer }: { filters: Filters; onPlayer: (key: number) => void }) {
  const query = filterQuery(filters)
  const { data, loading, error } = useApi<Payload>(`/api/efficiency?${query}&limit=1600`)
  if (loading) return <Loading label="Standardizing the peer groups" />
  if (error || !data) return <ErrorState message={error || 'No efficiency data returned.'} />
  const rows = data.rows
  const high = rows.filter((row) => row.value_efficiency_percentile >= 90).length
  const medianMinutes = [...rows].sort((a, b) => a.minutes_played - b.minutes_played)[Math.floor(rows.length / 2)]?.minutes_played
  return (
    <div className="page">
      <PageIntro code="02 / SIGNAL" title="Performance, priced in context." description="Compare current output and dated market value only inside the same season, competition and position group. Select a point or row to open the player journey." />
      <section className="kpi-grid kpi-grid-3">
        <Kpi label="Players in view" value={number(rows.length)} detail="Filtered and score-eligible" />
        <Kpi label="High relative efficiency" value={number(high)} detail="Top cumulative 10% of each peer group" tone="cyan" />
        <Kpi label="Median minutes" value={number(medianMinutes)} detail="All rows already exceed 900 minutes" />
      </section>
      <Panel title="Market value vs performance score" eyebrow="Click a player point" action={<span className="context-chip"><Info size={14} /> Log value axis</span>}>
        <ScatterPlot rows={rows} onSelect={onPlayer} />
      </Panel>
      <Panel title="Relative efficiency board" eyebrow="Exploratory shortlist · not a recommendation">
        <div className="table-wrap">
          <table>
            <thead><tr><th>Rank</th><th>Player</th><th>Context</th><th>Minutes</th><th>Performance Z</th><th>Market value</th><th>Efficiency</th><th /></tr></thead>
            <tbody>{rows.slice(0, 30).map((row) => (
              <tr key={`${row.player_key}-${row.season_key}-${row.competition_key}`}>
                <td className="rank-cell">{row.value_efficiency_rank}</td>
                <td><strong>{row.player_name}</strong><small>{row.primary_club_name || 'Club unavailable'}</small></td>
                <td>{row.competition_key} · {row.position_group}<small>{row.season_key} · n={row.peer_group_size}</small></td>
                <td className="numeric">{number(row.minutes_played)}</td>
                <td className="numeric">{number(row.performance_z_score, 2)}</td>
                <td className="numeric">{eur(row.season_end_market_value_eur)}</td>
                <td><span className={row.value_efficiency_score >= 1 ? 'score-pill positive' : 'score-pill'}>{number(row.value_efficiency_score, 2)}</span></td>
                <td><button className="icon-button" title="Open player journey" onClick={() => onPlayer(row.player_key)}><MoveUpRight size={17} /><span className="sr-only">Open {row.player_name}</span></button></td>
              </tr>
            ))}</tbody>
          </table>
        </div>
      </Panel>
    </div>
  )
}
