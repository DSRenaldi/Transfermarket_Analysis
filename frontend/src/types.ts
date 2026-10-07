export type PageId = 'overview' | 'efficiency' | 'journey' | 'team' | 'transfers' | 'clubs' | 'quality'

export type Filters = {
  season: string
  competition: string
  position: string
}

export type Meta = {
  project: string
  dashboard: string
  methodologyVersion: string
  competitions: Array<{ competition_key: string; competition_name: string; country_name: string }>
  seasons: number[]
  positions: string[]
}

export type EfficiencyRow = {
  player_key: number
  player_name: string
  competition_key: string
  competition_name: string
  season_key: number
  position_group: string
  sub_position: string
  primary_club_name: string | null
  age_at_season_end: number | null
  minutes_played: number
  goals_per_90: number
  assists_per_90: number
  performance_z_score: number
  market_value_z_score: number
  value_efficiency_score: number
  value_efficiency_rank: number
  value_efficiency_percentile: number
  peer_group_size: number
  season_end_market_value_eur: number
  season_end_valuation_date: string
  season_end_valuation_lag_days: number
}
