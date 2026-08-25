// frontend/src/components/pharmacy/PharmacyStatusBadge.jsx
import React from 'react'

const STATUS_CONFIG = {
  STOCKED:   { label: 'Stocked',    color: 'var(--signal-green)', bg: 'var(--signal-green-soft)', border: '#A7F3D0', dot: '#10B981' },
  LOW_STOCK: { label: 'Low Stock',  color: 'var(--alert-amber)',  bg: '#FEF3E2',                 border: '#FCD34D', dot: '#F59E0B' },
  DEPLETED:  { label: 'Depleted',   color: 'var(--critical-red)', bg: '#FEE2E2',                 border: '#FECACA', dot: '#EF4444' },
  EXPIRED:   { label: 'Expired',    color: '#475569',             bg: '#F1F5F9',                 border: '#CBD5E1', dot: '#1E293B' },
  RECALLED:  { label: 'Recalled',   color: '#6B21A8',             bg: '#F3E8FF',                 border: '#E9D5FF', dot: '#A855F7' },
}

export default function PharmacyStatusBadge({ status = 'STOCKED' }) {
  const key = (status || 'STOCKED').toUpperCase()
  const config = STATUS_CONFIG[key] || STATUS_CONFIG.STOCKED

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
