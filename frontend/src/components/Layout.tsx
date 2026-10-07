import type { ComponentType } from 'react'
import {
  Activity,
  ArrowLeftRight,
  BarChart3,
  Building2,
  DatabaseZap,
  Route,
  ShieldCheck,
  Users,
} from 'lucide-react'
import type { Filters, Meta, PageId } from '../types'

const items: Array<{ id: PageId; label: string; icon: ComponentType<{ size?: number }> }> = [
  { id: 'overview', label: 'Market overview', icon: BarChart3 },
  { id: 'efficiency', label: 'Value & performance', icon: Activity },
  { id: 'journey', label: 'Player journey', icon: Route },
  { id: 'team', label: 'Team analysis', icon: Users },
  { id: 'transfers', label: 'Transfer analysis', icon: ArrowLeftRight },
  { id: 'clubs', label: 'Club development', icon: Building2 },
  { id: 'quality', label: 'Quality & method', icon: ShieldCheck },
]

export function Layout({ page, onPage, filters, onFilters, meta, children }: {
  page: PageId
  onPage: (page: PageId) => void
  filters: Filters
  onFilters: (filters: Filters) => void
  meta: Meta | null
  children: React.ReactNode
}) {
  const showFilters = page === 'overview' || page === 'efficiency' || page === 'team' || page === 'clubs'
  return (
    <div className="app-shell">
      <aside className="sidebar">
        <button className="brand" onClick={() => onPage('overview')} aria-label="Open market overview">
          <span className="brand-mark"><span /></span>
          <span><strong>FVA</strong><small>Recruitment room</small></span>
        </button>
        <nav aria-label="Dashboard sections">
          {items.map(({ id, label, icon: Icon }, index) => (
            <button key={id} aria-label={label} className={page === id ? 'active' : ''} onClick={() => onPage(id)}>
              <span className="nav-index">0{index + 1}</span><Icon size={18} /><span>{label}</span>
            </button>
          ))}
        </nav>
        <div className="pitch-signature" aria-hidden="true"><span /><i /></div>
        <div className="sidebar-foot"><DatabaseZap size={16} /><span>PostgreSQL live model<small>Method {meta?.methodologyVersion ?? 'v1.0'}</small></span></div>
      </aside>
      <div className="main-shell">
        <header className={`topbar ${showFilters ? 'has-filters' : 'context-only'}`}>
          <div><span className="live-dot" /> <strong>ANALYSIS READY</strong><span className="snapshot">Valuation snapshot 12 Jun 2026</span></div>
          {showFilters && (
            <div className="filters" aria-label="Dashboard filters">
              <label><span>Season</span><select value={filters.season} onChange={(e) => onFilters({ ...filters, season: e.target.value })}><option value="">All</option>{meta?.seasons.map((season) => <option key={season}>{season}</option>)}</select></label>
              <label><span>Competition</span><select value={filters.competition} onChange={(e) => onFilters({ ...filters, competition: e.target.value })}><option value="">All five leagues</option>{meta?.competitions.map((competition) => <option key={competition.competition_key} value={competition.competition_key}>{competition.competition_name}</option>)}</select></label>
              <label><span>Position</span><select value={filters.position} onChange={(e) => onFilters({ ...filters, position: e.target.value })}><option value="">{page === 'team' ? 'All positions' : 'All outfield'}</option>{meta?.positions.map((position) => <option key={position}>{position}</option>)}</select></label>
            </div>
          )}
        </header>
        <main>{children}</main>
      </div>
    </div>
  )
}
