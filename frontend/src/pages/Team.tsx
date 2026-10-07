import { ArrowUpRight, CalendarDays, MapPin, Search, Shield } from 'lucide-react'
import { useEffect, useMemo, useState } from 'react'
import { eur, number, pct, useApi } from '../api'
import { HorizontalBars } from '../components/Charts'
import { Empty, ErrorState, Kpi, Loading, PageIntro, Panel } from '../components/Shared'
import type { Filters } from '../types'

type TeamOption = {
  club_key: number
  club_name: string
  competition_key: string
  competition_name: string
  contributor_count: number
}

type TeamRosterRow = {
  player_key: number
  player_name: string
  position_group: string
  sub_position: string
  country_of_citizenship: string | null
  age_at_stint_end: number | null
  appearances: number
  starts: number
  minutes_played: number
  goals: number
  assists: number
  goal_contributions: number
  first_appearance_date: string
  last_appearance_date: string
  played_for_multiple_clubs: boolean
  aligned_market_value_eur: number | null
  aligned_valuation_date: string | null
  valuation_status: string
  has_fresh_aligned_value: boolean
  season_minutes_played: number
  score_eligibility_status: string
  performance_z_score: number | null
  value_efficiency_score: number | null
  value_efficiency_rank: number | null
  peer_group_size: number | null
}

type TeamPayload = {
  profile: {
    club_key: number
    club_name: string
    club_code: string | null
    competition_key: string
    competition_name: string
    country_name: string
    season_key: number
    stadium_name: string | null
    stadium_seats: number | null
    first_appearance_date: string
    last_appearance_date: string
  }
  summary: {
    contributor_count: number
    goalkeeper_count: number
    score_eligible_count: number
    total_minutes: number
    total_goals: number
    total_assists: number
    aligned_squad_value_eur: number | null
    median_player_value_eur: number | null
    median_age: number | null
    players_with_aligned_value: number
    valuation_coverage_pct: number
    earliest_valuation_date: string | null
    latest_valuation_date: string | null
  }
  byPosition: Array<{
    position_group: string
    contributor_count: number
    minutes_played: number
    aligned_market_value_eur: number | null
    median_age: number | null
  }>
  byAge: Array<{ age_band: string; contributor_count: number; minutes_played: number }>
  benchmark: {
    contributor_count: number
    total_minutes: number
    goal_contributions: number
    aligned_squad_value_eur: number | null
    median_player_value_eur: number | null
    median_age: number | null
    competition_median_contributors: number
    competition_median_minutes: number
    competition_median_goal_contributions: number
    competition_median_squad_value_eur: number | null
    competition_median_player_value_eur: number | null
    competition_median_age: number | null
    competition_club_count: number
  }
  roster: TeamRosterRow[]
  definitions: { roster: string; value: string; score: string }
}

const optionId = (option: TeamOption) => `${option.club_key}:${option.competition_key}`
const normalizeTeamSearch = (value: string) => value
  .normalize('NFD')
  .replace(/[\u0300-\u036f]/g, '')
  .replaceAll('ß', 'ss')
  .toLocaleLowerCase()

function BenchmarkRow({ label, teamValue, medianValue, format }: {
  label: string
  teamValue: number | null
  medianValue: number | null
  format: (value: number | null) => string
}) {
  const maximum = Math.max(teamValue ?? 0, medianValue ?? 0, 1)
  const difference = medianValue ? (((teamValue ?? 0) - medianValue) / medianValue) * 100 : null
  return (
    <article className="benchmark-row">
      <div className="benchmark-copy">
        <span>{label}</span>
        <strong>{format(teamValue)}</strong>
        <small>{difference == null ? 'League comparison unavailable' : `${difference >= 0 ? '+' : ''}${pct(difference)} vs club median`}</small>
      </div>
      <div className="benchmark-tracks" aria-label={`${label}: team ${format(teamValue)}, competition club median ${format(medianValue)}`}>
        <div><span>TEAM</span><i style={{ width: `${((teamValue ?? 0) / maximum) * 100}%` }} /></div>
        <div><span>MED</span><i style={{ width: `${((medianValue ?? 0) / maximum) * 100}%` }} /></div>
      </div>
    </article>
  )
}

export default function Team({ filters, onPlayer }: { filters: Filters; onPlayer: (key: number) => void }) {
  const [selectedId, setSelectedId] = useState('')
  const [teamSearch, setTeamSearch] = useState('')
  const optionQuery = useMemo(() => {
    if (!filters.season) return null
    const params = new URLSearchParams({ season: filters.season })
    if (filters.competition) params.set('competition', filters.competition)
    return `/api/team-options?${params}`
  }, [filters.season, filters.competition])
  const options = useApi<{ rows: TeamOption[] }>(optionQuery)
  const optionRows = optionQuery ? options.data?.rows ?? [] : []
  const visibleOptions = useMemo(() => {
    const query = normalizeTeamSearch(teamSearch.trim())
    if (!query) return optionRows
    return optionRows.filter((option) => normalizeTeamSearch(`${option.club_name} ${option.competition_name}`).includes(query))
  }, [optionRows, teamSearch])

  useEffect(() => setTeamSearch(''), [filters.season, filters.competition])

  useEffect(() => {
    if (!visibleOptions.length) {
      setSelectedId('')
      return
    }
    if (!visibleOptions.some((option) => optionId(option) === selectedId)) setSelectedId(optionId(visibleOptions[0]))
  }, [visibleOptions, selectedId])

  const selectedOption = visibleOptions.find((option) => optionId(option) === selectedId) ?? null
  const detailQuery = useMemo(() => {
    if (!selectedOption || !filters.season || options.loading) return null
    const params = new URLSearchParams({
      club_key: String(selectedOption.club_key),
      competition: selectedOption.competition_key,
      season: filters.season,
    })
    if (filters.position) params.set('position', filters.position)
    return `/api/team?${params}`
  }, [selectedOption, filters.season, filters.position, options.loading])
  const detail = useApi<TeamPayload>(detailQuery)

  return (
    <div className="page">
      <PageIntro
        code="04 / TEAM"
        title="Read the squad as a system."
        description="Inspect every valid season contributor, the balance of roles and ages, and the team’s position against its competition. Club membership comes from match appearances—not a current profile field."
      />

      {!filters.season && <Panel title="Choose one season" eyebrow="A team needs a dated context"><Empty>Select a season from the top filter to build a historical team roster.</Empty></Panel>}
      {filters.season && options.loading && <Loading label="Assembling available teams" />}
      {filters.season && options.error && <ErrorState message={options.error} />}
      {filters.season && !options.loading && !options.error && !optionRows.length && <Empty>No teams have valid appearances in this filter context.</Empty>}

      {filters.season && optionRows.length > 0 && (
        <section className="team-command">
          <div className="team-command-fields">
            <label>
              <span>Find a team</span>
              <div className="team-search-box"><Search size={16} aria-hidden="true" /><input aria-label="Search teams" value={teamSearch} onChange={(event) => setTeamSearch(event.target.value)} placeholder="Search club or league" /></div>
            </label>
            <label>
              <span>Selected team</span>
              <select aria-label="Selected team" value={selectedId} disabled={!visibleOptions.length} onChange={(event) => setSelectedId(event.target.value)}>
                {visibleOptions.length ? visibleOptions.map((option) => <option key={optionId(option)} value={optionId(option)}>{option.club_name} — {option.competition_name}</option>) : <option value="">No matching teams</option>}
              </select>
            </label>
          </div>
          <div className="team-command-note"><CalendarDays size={15} /> {number(visibleOptions.length)} of {number(optionRows.length)} teams · season {filters.season}</div>
          {teamSearch && !visibleOptions.length && <p className="team-search-empty" role="status">No teams match “{teamSearch}”. Try another club or league name.</p>}
        </section>
      )}

      {selectedOption && detail.loading && <Loading label="Building the team room" />}
      {selectedOption && detail.error && <ErrorState message={detail.error} />}
      {selectedOption && detail.data && <>
        <section className="team-identity">
          <div className="team-monogram" aria-hidden="true">{detail.data.profile.club_name.split(/\s+/).slice(0, 2).map((word) => word[0]).join('').toUpperCase()}</div>
          <div>
            <span>{detail.data.profile.competition_name} / {detail.data.profile.country_name}</span>
            <h2>{detail.data.profile.club_name}</h2>
            <p><MapPin size={14} /> {detail.data.profile.stadium_name || 'Stadium unavailable'}{detail.data.profile.stadium_seats ? ` · ${number(detail.data.profile.stadium_seats)} seats` : ''}</p>
          </div>
          <div className="team-window"><small>OBSERVED WINDOW</small><strong>{detail.data.profile.first_appearance_date}</strong><span>to {detail.data.profile.last_appearance_date}</span></div>
        </section>

        <section className="kpi-grid">
          <Kpi label="Season contributors" value={number(detail.data.summary.contributor_count)} detail={`${number(detail.data.summary.score_eligible_count)} score-eligible · ${number(detail.data.summary.goalkeeper_count)} goalkeepers`} />
          <Kpi label="Aligned squad value" value={eur(detail.data.summary.aligned_squad_value_eur)} detail={`${number(detail.data.summary.players_with_aligned_value)} players · ${pct(detail.data.summary.valuation_coverage_pct)} coverage`} tone="cyan" />
          <Kpi label="Median player value" value={eur(detail.data.summary.median_player_value_eur)} detail={`Valuations ${detail.data.summary.earliest_valuation_date || '—'} to ${detail.data.summary.latest_valuation_date || '—'}`} />
          <Kpi label="Median age" value={number(detail.data.summary.median_age, 1)} detail={`${number(detail.data.summary.total_goals)} goals · ${number(detail.data.summary.total_assists)} assists`} />
        </section>

        <div className="dashboard-grid equal team-composition">
          <Panel title="Squad architecture" eyebrow="Role distribution">
            <div className="squad-lines">
              {detail.data.byPosition.map((position) => (
                <article key={position.position_group}>
                  <div><span>{position.position_group}</span><strong>{number(position.contributor_count)}</strong></div>
                  <p>{number(position.minutes_played)} minutes</p>
                  <small>{eur(position.aligned_market_value_eur)} aligned value · median age {number(position.median_age, 1)}</small>
                </article>
              ))}
            </div>
          </Panel>
          <Panel title="Age profile" eyebrow="Contributors by age at last club appearance">
            <HorizontalBars data={detail.data.byAge.map((band) => ({ label: band.age_band, value: band.contributor_count, secondary: `${number(band.minutes_played)} minutes` }))} valueLabel={(value) => number(value)} />
          </Panel>
        </div>

        <Panel title="Competition benchmark" eyebrow={`${number(detail.data.benchmark.competition_club_count)} clubs · competition medians`}>
          <div className="benchmark-grid">
            <BenchmarkRow label="Aligned squad value" teamValue={detail.data.benchmark.aligned_squad_value_eur} medianValue={detail.data.benchmark.competition_median_squad_value_eur} format={(value) => eur(value)} />
            <BenchmarkRow label="Median player value" teamValue={detail.data.benchmark.median_player_value_eur} medianValue={detail.data.benchmark.competition_median_player_value_eur} format={(value) => eur(value)} />
            <BenchmarkRow label="Season contributors" teamValue={detail.data.benchmark.contributor_count} medianValue={detail.data.benchmark.competition_median_contributors} format={(value) => number(value, 1)} />
            <BenchmarkRow label="Goal contributions" teamValue={detail.data.benchmark.goal_contributions} medianValue={detail.data.benchmark.competition_median_goal_contributions} format={(value) => number(value, 1)} />
          </div>
        </Panel>

        <Panel title="Season contributor roster" eyebrow={`${number(detail.data.roster.length)} players · sorted by club minutes`} action={<span className="context-chip"><Shield size={14} /> All valid appearances</span>}>
          <div className="table-wrap team-roster"><table>
            <thead><tr><th>Player</th><th>Role</th><th>Age</th><th>Apps / starts</th><th>Minutes</th><th>G+A</th><th>Aligned value</th><th>Efficiency</th><th /></tr></thead>
            <tbody>{detail.data.roster.map((player) => (
              <tr key={player.player_key}>
                <td><button className="table-player" onClick={() => onPlayer(player.player_key)}><strong>{player.player_name}</strong><small>{player.country_of_citizenship || 'Citizenship unknown'}{player.played_for_multiple_clubs ? ' · multi-club season' : ''}</small></button></td>
                <td>{player.position_group}<small>{player.sub_position || 'Role unavailable'}</small></td>
                <td className="numeric">{number(player.age_at_stint_end)}</td>
                <td className="numeric">{number(player.appearances)} / {number(player.starts)}</td>
                <td className="numeric">{number(player.minutes_played)}</td>
                <td className="numeric">{number(player.goal_contributions)}</td>
                <td className="numeric">{player.has_fresh_aligned_value ? eur(player.aligned_market_value_eur) : '—'}<small>{player.aligned_valuation_date ? `as of ${player.aligned_valuation_date}` : player.valuation_status.replaceAll('_', ' ')}</small></td>
                <td>{player.value_efficiency_score == null ? <span className="scope-pill limited">{player.score_eligibility_status.replaceAll('_', ' ')}</span> : <><span className={player.value_efficiency_score >= 1 ? 'score-pill positive' : 'score-pill'}>{number(player.value_efficiency_score, 2)}</span><small>full season · {number(player.season_minutes_played)} min</small></>}</td>
                <td><button className="icon-button" title="Open player journey" onClick={() => onPlayer(player.player_key)}><ArrowUpRight size={17} /><span className="sr-only">Open {player.player_name}</span></button></td>
              </tr>
            ))}</tbody>
          </table></div>
        </Panel>

        <aside className="method-strip team-method"><strong>Historical definitions</strong><p>{detail.data.definitions.roster} {detail.data.definitions.value} {detail.data.definitions.score}</p></aside>
      </>}
    </div>
  )
}
