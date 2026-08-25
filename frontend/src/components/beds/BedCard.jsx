// frontend/src/components/beds/BedCard.jsx
import React from 'react'
import BedStatusBadge from './BedStatusBadge'

const BED_TYPE_ICON = {
  ICU       : '🔴',
  GENERAL   : '🟢',
  STEP_DOWN : '🟡',
  EMERGENCY : '🚨',
}

export default function BedCard({ bed, onClick }) {
  if (!bed) return null

  const isAllocatable = bed.status === 'READY'
  const isCleaning = bed.status === 'CLEANING'
  const isHold = bed.status === 'TENTATIVE_HOLD'
  const isOccupied = bed.status === 'IN_USE' || bed.status === 'LOCKED'

  const ttlSeconds = bed.estimated_ready_at
    ? Math.max(0, Math.floor((new Date(bed.estimated_ready_at) - new Date()) / 1000))
    : null

  // Card theme styles
  let borderColor = 'var(--line)'
  let bgColor = 'var(--surface)'
  let shadow = '0 1px 3px rgba(0,0,0,0.04)'

  if (isAllocatable) {
    borderColor = 'var(--signal-green)'
    bgColor = 'var(--signal-green-soft)'
  } else if (isOccupied) {
    borderColor = '#FCA5A5'
    bgColor = '#FFF5F5'
  } else if (isCleaning) {
    borderColor = '#FCD34D'
    bgColor = '#FFFDF5'
  } else if (isHold) {
    borderColor = '#FDBA74'
    bgColor = '#FFF7ED'
  }

  return (
    <div
      onClick={() => onClick?.(bed)}
      style={{
        position: 'relative',
        display: 'flex',
        flexDirection: 'column',
        gap: '6px',
        padding: '12px',
        borderRadius: 'var(--radius-card)',
        backgroundColor: bgColor,
        border: `1.5px solid ${borderColor}`,
        boxShadow: shadow,
        cursor: 'pointer',
        transition: 'all 0.18s ease-in-out',
        userSelect: 'none',
        minWidth: '130px',
      }}
      onMouseEnter={(e) => {
        e.currentTarget.style.transform = 'translateY(-2px)'
        e.currentTarget.style.boxShadow = '0 4px 12px rgba(0,0,0,0.08)'
      }}
      onMouseLeave={(e) => {
        e.currentTarget.style.transform = 'translateY(0)'
        e.currentTarget.style.boxShadow = shadow
      }}
    >
      {/* Top row: Type Icon + Bed Number & Isolation */}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: '4px' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
          <span style={{ fontSize: '1rem', lineHeight: 1 }}>
            {BED_TYPE_ICON[bed.bed_type] || '🛏️'}
          </span>
          <span
            style={{
              fontFamily: 'var(--font-mono)',
              fontSize: 'var(--text-body)',
              fontWeight: 600,
              color: 'var(--ink)',
              letterSpacing: '-0.01em',
            }}
          >
            {bed.bed_number}
          </span>
        </div>

        {bed.is_isolation && (
          <span
            style={{
              fontFamily: 'var(--font-mono)',
              fontSize: '0.65rem',
              fontWeight: 700,
              padding: '2px 5px',
              borderRadius: '4px',
              backgroundColor: '#FEF08A',
              color: '#854D0E',
              letterSpacing: '0.04em',
              lineHeight: 1,
            }}
            title="Isolation Bed"
          >
            ISO
          </span>
        )}
      </div>

      {/* Room detail */}
      <div
        style={{
          fontFamily: 'var(--font-body)',
          fontSize: 'var(--text-caption)',
          color: 'var(--ink-muted)',
          display: 'flex',
          justifyContent: 'space-between',
        }}
      >
        <span>Room {bed.room_number}</span>
        {bed.has_ventilator_port && (
          <span
            style={{
              color: 'var(--pulse-blue)',
              fontWeight: 600,
              fontSize: '0.7rem',
              display: 'inline-flex',
              alignItems: 'center',
              gap: '2px',
            }}
          >
            🫁 Vent
          </span>
        )}
      </div>

      {/* Status badge */}
      <div style={{ marginTop: '2px' }}>
        <BedStatusBadge status={bed.status} />
      </div>

      {/* Patient info */}
      {bed.current_patient_id && (
        <div
          style={{
            fontFamily: 'var(--font-mono)',
            fontSize: '0.72rem',
            color: 'var(--ink-muted)',
            backgroundColor: 'rgba(0,0,0,0.03)',
            padding: '3px 6px',
            borderRadius: '4px',
            marginTop: '2px',
            overflow: 'hidden',
            textOverflow: 'ellipsis',
            whiteSpace: 'nowrap',
          }}
        >
          👤 {bed.current_patient_id}
        </div>
      )}

      {/* Cleaning countdown */}
      {isCleaning && ttlSeconds !== null && (
        <div
          style={{
            fontFamily: 'var(--font-body)',
            fontSize: '0.72rem',
            fontWeight: 600,
            color: 'var(--alert-amber)',
            backgroundColor: '#FEF3E2',
            padding: '3px 6px',
            borderRadius: '4px',
            marginTop: '2px',
            display: 'flex',
            alignItems: 'center',
            gap: '4px',
          }}
        >
          <span>⏱️</span>
          <span>Ready ~{Math.max(1, Math.ceil(ttlSeconds / 60))}m</span>
        </div>
      )}
    </div>
  )
}
