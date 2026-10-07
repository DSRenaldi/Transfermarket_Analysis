import type { ReactNode } from 'react'
import { AlertTriangle, LoaderCircle } from 'lucide-react'

export function Loading({ label = 'Reading the model' }: { label?: string }) {
  return (
    <div className="state-panel" role="status">
      <LoaderCircle className="spin" size={22} aria-hidden="true" />
      <span>{label}…</span>
    </div>
  )
}

export function ErrorState({ message }: { message: string }) {
  return (
    <div className="state-panel state-error" role="alert">
      <AlertTriangle size={22} aria-hidden="true" />
      <div><strong>Data could not be loaded.</strong><span>{message}</span></div>
    </div>
  )
}

export function Panel({ title, eyebrow, action, children, className = '' }: {
  title: string
  eyebrow?: string
  action?: ReactNode
  children: ReactNode
  className?: string
}) {
  return (
    <section className={`panel ${className}`}>
      <header className="panel-head">
        <div>{eyebrow && <span className="eyebrow">{eyebrow}</span>}<h2>{title}</h2></div>
        {action}
      </header>
      {children}
    </section>
  )
}

export function Kpi({ label, value, detail, tone = 'plain' }: {
  label: string
  value: string
  detail: string
  tone?: 'plain' | 'cyan' | 'amber'
}) {
  return (
    <article className={`kpi kpi-${tone}`}>
      <span>{label}</span>
      <strong>{value}</strong>
      <small>{detail}</small>
    </article>
  )
}

export function PageIntro({ code, title, description, aside }: {
  code: string
  title: string
  description: string
  aside?: ReactNode
}) {
  return (
    <header className="page-intro">
      <div>
        <span className="page-code">{code}</span>
        <h1>{title}</h1>
        <p>{description}</p>
      </div>
      {aside}
    </header>
  )
}

export function Empty({ children }: { children: ReactNode }) {
  return <div className="empty-state">{children}</div>
}
