import { useState } from 'react'
import type { EfficiencyRow } from '../types'
import { eur, number } from '../api'

type BarDatum = { label: string; value: number; secondary?: string }

export function HorizontalBars({ data, valueLabel = eur }: {
  data: BarDatum[]
  valueLabel?: (value: number) => string
}) {
  const max = Math.max(...data.map((item) => item.value), 1)
  return (
    <div className="bar-list">
      {data.map((item) => (
        <div className="bar-row" key={item.label}>
          <div className="bar-meta"><span>{item.label}</span><strong>{valueLabel(item.value)}</strong></div>
          <div className="bar-track"><i style={{ width: `${Math.max((item.value / max) * 100, 2)}%` }} /></div>
          {item.secondary && <small>{item.secondary}</small>}
        </div>
      ))}
    </div>
  )
}

export function LineChart({ data, valueKey, labelKey, format = eur, height = 230 }: {
  data: Array<Record<string, unknown>>
  valueKey: string
  labelKey: string
  format?: (value: number) => string
  height?: number
}) {
  const [activePointIndex, setActivePointIndex] = useState<number | null>(null)
  if (data.length < 2) return <div className="empty-state">Not enough dated observations for a line.</div>
  const values = data.map((row) => Number(row[valueKey] ?? 0))
  const min = Math.min(...values)
  const max = Math.max(...values)
  const span = max - min || 1
  const width = Math.max(760, data.length * 72)
  const padX = 36
  const padTop = 42
  const padBottom = 28
  const points = values.map((value, index) => ({
    x: padX + (index / (values.length - 1)) * (width - padX * 2),
    y: padTop + (1 - (value - min) / span) * (height - padTop - padBottom),
    value,
    valueText: format(value),
    label: String(data[index][labelKey] ?? ''),
  }))
  const path = points.map((point, index) => `${index ? 'L' : 'M'} ${point.x} ${point.y}`).join(' ')
  const activePoint = activePointIndex === null ? null : points[activePointIndex]
  const tooltip = activePoint ? (() => {
    const boxWidth = Math.min(190, Math.max(116, activePoint.label.length * 6.2 + 24, activePoint.valueText.length * 7 + 24))
    return {
      boxWidth,
      x: Math.min(Math.max(activePoint.x - boxWidth / 2, 5), width - boxWidth - 5),
      y: activePoint.y < 72 ? activePoint.y + 14 : activePoint.y - 58,
    }
  })() : null
  return (
    <div className="chart-wrap" tabIndex={width > 760 ? 0 : undefined}>
      <div className="chart-canvas" style={width > 760 ? { minWidth: `${width}px` } : undefined}>
        <svg className="line-chart" viewBox={`0 0 ${width} ${height}`} role="img" aria-label="Value trend line chart">
          <line x1={padX} y1={height - padBottom} x2={width - padX} y2={height - padBottom} className="axis" />
          <path d={path} className="trend-line" />
          {points.map((point, index) => (
            <g
              key={`${point.label}-${index}`}
              className="trend-point-group"
              onMouseEnter={() => setActivePointIndex(index)}
              onMouseLeave={() => setActivePointIndex(null)}
              onFocus={() => setActivePointIndex(index)}
              onBlur={() => setActivePointIndex(null)}
            >
              <circle cx={point.x} cy={point.y} r="12" className="trend-hit-target" />
              <circle
                cx={point.x}
                cy={point.y}
                r="4"
                className="trend-point"
                tabIndex={0}
                aria-label={`${point.label}: ${point.valueText}`}
              />
              <text x={point.x} y={point.y - 11} textAnchor="middle" className="trend-value-label">
                {point.valueText}
              </text>
            </g>
          ))}
          {activePoint && tooltip && (
            <g
              className="trend-tooltip"
              role="tooltip"
              aria-hidden="true"
              transform={`translate(${tooltip.x} ${tooltip.y})`}
            >
              <rect width={tooltip.boxWidth} height="44" rx="2" />
              <text x="12" y="17" className="trend-tooltip-label">{activePoint.label}</text>
              <text x="12" y="34" className="trend-tooltip-value">{activePoint.valueText}</text>
            </g>
          )}
        </svg>
        <div className="chart-range"><span>{points[0].label}</span><strong>{format(max)}</strong><span>{points.at(-1)?.label}</span></div>
      </div>
    </div>
  )
}

export function ScatterPlot({ rows, onSelect }: { rows: EfficiencyRow[]; onSelect: (playerKey: number) => void }) {
  const [activeRowIndex, setActiveRowIndex] = useState<number | null>(null)
  if (!rows.length) return <div className="empty-state">No players match these filters.</div>
  const width = 760
  const height = 390
  const pad = 44
  const xs = rows.map((row) => row.performance_z_score)
  const ys = rows.map((row) => Math.log10(Math.max(row.season_end_market_value_eur, 1)))
  const xMin = Math.min(...xs)
  const xMax = Math.max(...xs)
  const yMin = Math.min(...ys)
  const yMax = Math.max(...ys)
  const x = (value: number) => pad + ((value - xMin) / (xMax - xMin || 1)) * (width - pad * 2)
  const y = (value: number) => height - pad - ((value - yMin) / (yMax - yMin || 1)) * (height - pad * 2)
  const midX = x(0)
  const medianY = [...ys].sort((a, b) => a - b)[Math.floor(ys.length / 2)]
  const points = rows.map((row) => ({
    row,
    cx: x(row.performance_z_score),
    cy: y(Math.log10(Math.max(row.season_end_market_value_eur, 1))),
    radius: row.value_efficiency_score >= 1 ? 5 : 3.6,
    tone: row.value_efficiency_score >= 1 ? 'point-high' : row.value_efficiency_score < -1 ? 'point-low' : 'point-mid',
  }))
  const activePoint = activeRowIndex === null ? null : points[activeRowIndex]
  const tooltipWidth = 238
  const tooltipHeight = 72
  const tooltipPosition = activePoint ? {
    x: activePoint.cx + tooltipWidth + 18 <= width ? activePoint.cx + 12 : activePoint.cx - tooltipWidth - 12,
    y: Math.min(Math.max(activePoint.cy - tooltipHeight / 2, 6), height - tooltipHeight - 6),
  } : null
  return (
    <div className="scatter-wrap">
      <svg className="scatter" viewBox={`0 0 ${width} ${height}`} role="img" aria-label="Performance score against market value">
        <line x1={midX} y1={pad} x2={midX} y2={height - pad} className="quadrant" />
        <line x1={pad} y1={y(medianY)} x2={width - pad} y2={y(medianY)} className="quadrant" />
        <text x={pad} y={22} className="quadrant-label">HIGH VALUE</text>
        <text x={width - pad} y={height - 12} textAnchor="end" className="quadrant-label">HIGH PERFORMANCE →</text>
        {points.map(({ row, cx, cy, radius, tone }, index) => (
          <g
            key={`${row.player_key}-${row.season_key}-${row.competition_key}`}
            className="scatter-point-group"
            onMouseEnter={() => setActiveRowIndex(index)}
            onMouseLeave={() => setActiveRowIndex(null)}
            onFocus={() => setActiveRowIndex(index)}
            onBlur={() => setActiveRowIndex(null)}
            onClick={() => onSelect(row.player_key)}
          >
            <circle cx={cx} cy={cy} r="11" className="scatter-hit-target" />
            <circle
              cx={cx}
              cy={cy}
              r={radius}
              className={`scatter-point ${tone}`}
              tabIndex={0}
              aria-label={`${row.player_name}, ${row.competition_name} ${row.season_key}, market value ${eur(row.season_end_market_value_eur)}, performance score ${number(row.performance_z_score, 2)}, value efficiency score ${number(row.value_efficiency_score, 2)}`}
              onKeyDown={(event) => event.key === 'Enter' && onSelect(row.player_key)}
            />
          </g>
        ))}
        {activePoint && tooltipPosition && (
          <g
            className="scatter-tooltip"
            role="tooltip"
            aria-hidden="true"
            transform={`translate(${tooltipPosition.x} ${tooltipPosition.y})`}
          >
            <rect width={tooltipWidth} height={tooltipHeight} rx="2" />
            <text x="12" y="17" className="scatter-tooltip-name">{activePoint.row.player_name}</text>
            <text x="12" y="33" className="scatter-tooltip-context">
              {activePoint.row.competition_name} · {activePoint.row.season_key} · {activePoint.row.position_group}
            </text>
            <text x="12" y="50" className="scatter-tooltip-metric">
              Market value  {eur(activePoint.row.season_end_market_value_eur)}   ·   Performance  {number(activePoint.row.performance_z_score, 2)}
            </text>
            <text x="12" y="65" className="scatter-tooltip-score">
              Value efficiency  {number(activePoint.row.value_efficiency_score, 2)}
            </text>
          </g>
        )}
      </svg>
      <div className="legend"><span><i className="dot dot-high" />Higher relative efficiency</span><span><i className="dot dot-mid" />Peer range</span><span><i className="dot dot-low" />Lower relative efficiency</span></div>
    </div>
  )
}
