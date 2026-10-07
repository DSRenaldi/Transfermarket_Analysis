import { Search } from 'lucide-react'
import { useEffect, useState } from 'react'
import { eur, number, useApi } from '../api'
import { LineChart } from '../components/Charts'
import { Empty, ErrorState, Loading, PageIntro, Panel } from '../components/Shared'

type PlayerOption = { player_key: number; player_name: string; position_group: string; country_of_citizenship: string }
type PlayerData = {
  profile: PlayerOption & { date_of_birth: string | null; sub_position: string; foot: string | null; height_cm: number | null }
  seasons: Array<{ season_key: number; competition_key: string; competition_name: string; primary_club_name: string | null; minutes_played: number; goals: number; assists: number; season_end_market_value_eur: number; season_end_valuation_date: string; value_efficiency_score: number | null; value_efficiency_rank: number | null; peer_group_size: number | null }>
  valuations: Array<{ valuation_date: string; market_value_eur: number; club_name: string | null }>
  transfers: Array<{ transfer_date: string; from_club_name: string; to_club_name: string; fee_status: string; transfer_fee_eur: number | null }>
}

export default function Journey({ initialPlayer }: { initialPlayer: number | null }) {
  const [query, setQuery] = useState('')
  const [selected, setSelected] = useState<number | null>(initialPlayer)
  const [settledQuery, setSettledQuery] = useState('')
  useEffect(() => { const timer = window.setTimeout(() => setSettledQuery(query), 250); return () => window.clearTimeout(timer) }, [query])
  useEffect(() => { if (initialPlayer) setSelected(initialPlayer) }, [initialPlayer])
  const options = useApi<{ rows: PlayerOption[] }>(`/api/players?query=${encodeURIComponent(settledQuery)}`)
  useEffect(() => { if (!selected && options.data?.rows[0]) setSelected(options.data.rows[0].player_key) }, [options.data, selected])
  const detail = useApi<PlayerData>(selected ? `/api/player?player_key=${selected}` : null)
  return (
    <div className="page">
      <PageIntro code="03 / JOURNEY" title="A career is a sequence, not a snapshot." description="Trace dated valuations beside season performance and recorded transfers. Values never travel backward across the timeline." />
      <div className="journey-layout">
        <aside className="player-finder">
          <label className="search-box"><Search size={17} /><input value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Find a player" /></label>
          <div className="player-options">{options.loading ? <Loading label="Finding players" /> : options.data?.rows.map((player) => <button key={player.player_key} className={selected === player.player_key ? 'active' : ''} onClick={() => setSelected(player.player_key)}><strong>{player.player_name}</strong><span>{player.position_group} · {player.country_of_citizenship || 'Country unknown'}</span></button>)}</div>
        </aside>
        <div className="journey-content">
          {detail.loading && <Loading label="Tracing player history" />}
          {detail.error && <ErrorState message={detail.error} />}
          {detail.data && <>
            <section className="player-identity"><div className="shirt-number">{String(detail.data.profile.player_key).slice(-2).padStart(2, '0')}</div><div><span>{detail.data.profile.position_group} / {detail.data.profile.sub_position}</span><h2>{detail.data.profile.player_name}</h2><p>{detail.data.profile.country_of_citizenship || 'Citizenship unavailable'} · {detail.data.profile.foot || 'Foot unknown'} · {detail.data.profile.height_cm ? `${detail.data.profile.height_cm} cm` : 'Height unknown'}</p></div></section>
            <Panel title="Market value journey" eyebrow={`${detail.data.valuations.length} dated observations`}><LineChart data={detail.data.valuations as unknown as Array<Record<string, unknown>>} valueKey="market_value_eur" labelKey="valuation_date" height={280} /></Panel>
            <Panel title="Season record" eyebrow="Aligned value and performance">
              {detail.data.seasons.length ? <div className="season-cards">{detail.data.seasons.map((season) => <article key={`${season.season_key}-${season.competition_key}`}><span>{season.season_key} · {season.competition_key}</span><h3>{season.primary_club_name || 'Club unavailable'}</h3><strong>{eur(season.season_end_market_value_eur)}</strong><dl><div><dt>Minutes</dt><dd>{number(season.minutes_played)}</dd></div><div><dt>G+A</dt><dd>{season.goals + season.assists}</dd></div><div><dt>Efficiency</dt><dd>{number(season.value_efficiency_score, 2)}</dd></div></dl><small>Valued {season.season_end_valuation_date}</small></article>)}</div> : <Empty>No selected-scope season records.</Empty>}
            </Panel>
            <Panel title="Recorded moves" eyebrow="Fee states remain distinct">
              {detail.data.transfers.length ? <div className="transfer-timeline">{detail.data.transfers.map((transfer, index) => <article key={`${transfer.transfer_date}-${index}`}><time>{transfer.transfer_date}</time><span>{transfer.from_club_name || 'Unknown'} → {transfer.to_club_name || 'Unknown'}</span><strong>{transfer.fee_status === 'numeric_fee' ? eur(transfer.transfer_fee_eur) : transfer.fee_status.replaceAll('_', ' ')}</strong></article>)}</div> : <Empty>No historical transfer rows for this player.</Empty>}
            </Panel>
          </>}
        </div>
      </div>
    </div>
  )
}
