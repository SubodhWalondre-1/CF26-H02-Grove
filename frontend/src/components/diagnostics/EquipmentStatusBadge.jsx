// frontend/src/components/diagnostics/EquipmentStatusBadge.jsx
import React from 'react'

const STATUS_CONFIG = {
  READY:       { label: 'Ready',       color: 'var(--signal-green)', bg: 'var(--signal-green-soft)', border: '#A7F3D0', dot: '#10B981' },
  SCHEDULED:   { label: 'Scheduled',   color: 'var(--pulse-blue)',   bg: 'var(--pulse-blue-soft)',   border: '#BAE6FD', dot: '#0284C7' },
  IN_USE:      { label: 'In Use',      color: '#D97706',             bg: '#FFFBEB',                 border: '#FDE68A', dot: '#F59E0B' },
  REPORTING:   { label: 'Reporting',   color: '#6B21A8',             bg: '#F3E8FF',                 border: '#E9D5FF', dot: '#A855F7' },
  CALIBRATING: { label: 'Calibrating', color: 'var(--alert-amber)',  bg: '#FEF3E2',                 border: '#FCD34D', dot: '#F59E0B' },
  MAINTENANCE: { label: 'Maintenance', color: '#475569',             bg: '#F1F5F9',                 border: '#CBD5E1', dot: '#64748B' },
  OFFLINE:     { label: 'Offline',     color: 'var(--critical-red)', bg: '#FEE2E2',                 border: '#FECACA', dot: '#EF4444' },
}

export default function EquipmentStatusBadge({ status = 'READY' }) {
  const key = (status || 'READY').toUpperCase()
  const config = STATUS_CONFIG[key] || STATUS_CONFIG.READY

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
        }}
      />
      {config.label}
    </span>
  )
}
