// frontend/src/components/transfers/TransferStatusBadge.jsx
import React from 'react'

const STATUS_CONFIG = {
  INITIATED:               { label: 'Initiated',         color: '#475569',             bg: '#F1F5F9',                 border: '#CBD5E1', dot: '#64748B' },
  DESTINATION_HELD:        { label: 'Dest Held',         color: 'var(--pulse-blue)',   bg: 'var(--pulse-blue-soft)',   border: '#BAE6FD', dot: '#0284C7' },
  TRANSPORT_ASSIGNED:      { label: 'Transport Assigned', color: '#D97706',             bg: '#FEF3E2',                 border: '#FCD34D', dot: '#F59E0B' },
  SOURCE_RELEASE_PENDING:  { label: 'Release Pending',   color: '#6B21A8',             bg: '#F3E8FF',                 border: '#E9D5FF', dot: '#A855F7' },
  IN_TRANSIT:              { label: 'In Transit',        color: '#0369A1',             bg: '#E0F2FE',                 border: '#7DD3FC', dot: '#0284C7', pulse: true },
  COMMITTED:               { label: 'Committed',         color: 'var(--signal-green)', bg: 'var(--signal-green-soft)', border: '#A7F3D0', dot: '#10B981' },
  ROLLED_BACK:             { label: 'Rolled Back',       color: 'var(--critical-red)', bg: '#FEE2E2',                 border: '#FECACA', dot: '#EF4444' },
  FAILED:                  { label: 'Failed',            color: 'var(--critical-red)', bg: '#FEE2E2',                 border: '#FECACA', dot: '#EF4444' },
}

export default function TransferStatusBadge({ status = 'INITIATED' }) {
  const key = (status || 'INITIATED').toUpperCase()
  const config = STATUS_CONFIG[key] || STATUS_CONFIG.INITIATED

  return (
    <span
      style={{
        display: 'inline-flex',
        alignItems: 'center',
        gap: '6px',
        padding: '3px 9px',
        borderRadius: 'var(--radius-pill)',
        backgroundColor: config.bg,
        border: `1px solid ${config.border}`,
        fontFamily: 'var(--font-mono)',
        fontSize: '0.72rem',
        fontWeight: 600,
        color: config.color,
        letterSpacing: '0.02em',
        lineHeight: 1,
        userSelect: 'none',
        whiteSpace: 'nowrap',
      }}
    >
      <span
        style={{
          width: '6px',
          height: '6px',
          borderRadius: '50%',
          backgroundColor: config.dot,
          display: 'inline-block',
          animation: config.pulse ? 'pulse 1.5s infinite' : 'none',
        }}
      />
      {config.label}
    </span>
  )
}
