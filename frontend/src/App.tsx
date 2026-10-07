import { useState } from 'react'
import { useApi } from './api'
import { Layout } from './components/Layout'
import { ErrorState, Loading } from './components/Shared'
import Clubs from './pages/Clubs'
import Efficiency from './pages/Efficiency'
import Journey from './pages/Journey'
import Overview from './pages/Overview'
import Quality from './pages/Quality'
import Team from './pages/Team'
import Transfers from './pages/Transfers'
import type { Filters, Meta, PageId } from './types'

export default function App() {
  const [page, setPage] = useState<PageId>('overview')
  const [filters, setFilters] = useState<Filters>({ season: '2025', competition: '', position: '' })
  const [selectedPlayer, setSelectedPlayer] = useState<number | null>(null)
  const meta = useApi<Meta>('/api/meta')

  const openPlayer = (playerKey: number) => {
    setSelectedPlayer(playerKey)
    setPage('journey')
    window.scrollTo({ top: 0, behavior: 'smooth' })
  }

  if (meta.loading) return <div className="boot-screen"><span className="brand-mark"><span /></span><Loading label="Opening the recruitment room" /></div>
  if (meta.error) return <div className="boot-screen"><ErrorState message={meta.error} /></div>

  return (
    <Layout page={page} onPage={setPage} filters={filters} onFilters={setFilters} meta={meta.data}>
      {page === 'overview' && <Overview filters={filters} onExplore={() => setPage('efficiency')} />}
      {page === 'efficiency' && <Efficiency filters={filters} onPlayer={openPlayer} />}
      {page === 'journey' && <Journey initialPlayer={selectedPlayer} />}
      {page === 'team' && <Team filters={filters} onPlayer={openPlayer} />}
      {page === 'transfers' && <Transfers />}
      {page === 'clubs' && <Clubs filters={filters} />}
      {page === 'quality' && <Quality />}
    </Layout>
  )
}
