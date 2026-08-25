import React from 'react'
import PulseLine from './PulseLine'

const STATE_CONFIG = {
  QUEUED: { variant: 'queued', color: 'var(--pulse-blue)', bg: 'var(--pulse-blue-soft)' },
  ARBITRATING: { variant: 'arbitrating', color: 'var(--alert-amber)', bg: '#FEF3E2' },
  PREPARING: { variant: 'preparing', color: 'var(--pulse-blue)', bg: 'var(--pulse-blue-soft)' },
  COMMITTING: { variant: 'preparing', color: 'var(--pulse-blue)', bg: 'var(--pulse-blue-soft)' },
  COMMITTED: { variant: 'committed', color: 'var(--signal-green)', bg: 'var(--signal-green-soft)' },
  ACTIVE: { variant: 'committed', color: 'var(--signal-green)', bg: 'var(--signal-green-soft)' },
  COMPLETED: { variant: 'committed', color: 'var(--signal-green)', bg: 'var(--signal-green-soft)' },
  ROLLINGBACK: { variant: 'aborted', color: 'var(--critical-red)', bg: '#FBE9E9' },
  ABORTED: { variant: 'aborted', color: 'var(--critical-red)', bg: '#FBE9E9' },
  CANCELLED: { variant: 'cancelled', color: 'var(--critical-red)', bg: '#FBE9E9' },
  CLOSED: { variant: 'committed', color: 'var(--ink-muted)', bg: 'var(--surface-recessed)' },
}

const DEFAULT_CONFIG = {
  variant: 'idle',
  color: 'var(--ink-muted)',
  bg: 'var(--surface-recessed)',
}

export default function StateBadge({ status = 'QUEUED', className = '' }) {
  const statusUpper = (status || '').toUpperCase()
  const config = STATE_CONFIG[statusUpper] || DEFAULT_CONFIG

  return (
    <span
      role="status"
      aria-label={`Transaction status: ${statusUpper}`}
      className={`state-badge ${className}`}
      style={{
        display: 'inline-flex',
        alignItems: 'center',
        gap: '6px',
        padding: '2px 10px 2px 4px',
        borderRadius: 'var(--radius-pill)',
        backgroundColor: config.bg,
        border: '1px solid var(--line)',
        userSelect: 'none',
        lineHeight: 1,
      }}
    >
      <PulseLine
        variant={config.variant}
        width={52}
        height={14}
        animated={statusUpper === 'ARBITRATING'}
      />
      <span
        style={{
          fontFamily: 'var(--font-mono)',
          fontSize: '0.75rem',
          fontWeight: 500,
          color: config.color,
          letterSpacing: '0.02em',
          textTransform: 'uppercase',
        }}
      >
        {statusUpper}
      </span>
    </span>
  )
}
