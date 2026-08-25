// frontend/src/components/beds/BedStatusBadge.jsx
import React from 'react'

const STATUS_CONFIG = {
  FREE: { label: 'Free', color: 'var(--ink-muted)', bg: 'var(--surface-recessed)', border: 'var(--line)', dot: '#94a3b8' },
  CLEANING: { label: 'Cleaning', color: 'var(--alert-amber)', bg: '#FEF3E2', border: '#FCD34D', dot: '#F59E0B' },
  SANITIZED: { label: 'Sanitized', color: 'var(--pulse-blue)', bg: 'var(--pulse-blue-soft)', border: '#BAE6FD', dot: '#0284C7' },
  READY: { label: 'Ready', color: 'var(--signal-green)', bg: 'var(--signal-green-soft)', border: '#A7F3D0', dot: '#10B981' },
  TENTATIVE_HOLD: { label: 'On Hold', color: '#D97706', bg: '#FFFBEB', border: '#FDE68A', dot: '#F59E0B' },
  LOCKED: { label: 'Locked', color: 'var(--critical-red)', bg: '#FEE2E2', border: '#FECACA', dot: '#EF4444' },
  IN_USE: { label: 'Occupied', color: '#991B1B', bg: '#FEE2E2', border: '#FCA5A5', dot: '#DC2626' },
  POST_USE: { label: 'Post Use', color: '#6B21A8', bg: '#F3E8FF', border: '#E9D5FF', dot: '#A855F7' },
  MAINTENANCE: { label: 'Maintenance', color: '#475569', bg: '#F1F5F9', border: '#CBD5E1', dot: '#64748B' },
  OUT_OF_SERVICE: { label: 'Out of Service', color: '#1E293B', bg: '#E2E8F0', border: '#94A3B8', dot: '#0F172A' },
}

export default function BedStatusBadge({ status = 'FREE' }) {
  const statusUpper = (status || 'FREE').toUpperCase()
  const config = STATUS_CONFIG[statusUpper] || STATUS_CONFIG.FREE

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
