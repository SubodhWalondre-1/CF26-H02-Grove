// frontend/src/components/pharmacy/PharmacyCard.jsx
import React from 'react'
import PharmacyStatusBadge from './PharmacyStatusBadge'

const TYPE_ICON = {
  blood_unit:      '🩸',
  medication_slot: '💊',
  oxygen_unit:     '🫁',
}

const TYPE_LABEL = {
  blood_unit:      'Blood Unit',
  medication_slot: 'Medication',
  oxygen_unit:     'Oxygen',
}

export default function PharmacyCard({ resource, onClick }) {
  if (!resource) return null

  const pct = resource.total_quantity > 0
    ? Math.round((resource.available_quantity / resource.total_quantity) * 100)
    : 0

  const isCritical = resource.available_quantity <= resource.critical_threshold
  const isDepleted = resource.available_quantity <= 0
  const isExpired = (resource.status || '').toUpperCase() === 'EXPIRED'

  // Calculate days to expiry
  const today = new Date()
  const expiry = new Date(resource.expiry_date)
  const daysToExpiry = Math.ceil((expiry - today) / (1000 * 60 * 60 * 24))

  // Border & background theming
  let borderColor = 'var(--line)'
  let bgColor = 'var(--surface)'

  if (isDepleted || isExpired) {
    borderColor = '#FCA5A5'
    bgColor = '#FFF5F5'
  } else if (isCritical) {
    borderColor = '#FCD34D'
    bgColor = '#FFFDF5'
  } else {
    borderColor = 'var(--signal-green)'
    bgColor = 'var(--signal-green-soft)'
  }

  // Stock bar color
  let barColor = 'var(--signal-green)'
  if (isDepleted || isExpired) barColor = 'var(--critical-red)'
  else if (isCritical) barColor = 'var(--alert-amber)'
  else if (pct <= 50) barColor = 'var(--pulse-blue)'

  const shadow = '0 1px 3px rgba(0,0,0,0.04)'

  return (
    <div
      onClick={() => onClick?.(resource)}
      style={{
        position: 'relative',
        display: 'flex',
        flexDirection: 'column',
        gap: '8px',
        padding: '14px',
        borderRadius: 'var(--radius-card)',
        backgroundColor: bgColor,
        border: `1.5px solid ${borderColor}`,
        boxShadow: shadow,
        cursor: 'pointer',
        transition: 'all 0.18s ease-in-out',
        userSelect: 'none',
        minWidth: '160px',
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
      {/* Top row: Type Icon + Sub-type */}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: '4px' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
          <span style={{ fontSize: '1.1rem', lineHeight: 1 }}>
            {TYPE_ICON[resource.resource_type] || '📦'}
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
            {resource.sub_type || TYPE_LABEL[resource.resource_type] || resource.resource_type}
          </span>
        </div>
      </div>

      {/* Batch ID */}
      <div
        style={{
          fontFamily: 'var(--font-body)',
          fontSize: '0.72rem',
          color: 'var(--ink-muted)',
        }}
      >
        Batch: {resource.batch_id}
      </div>

      {/* Stock Bar */}
      <div style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
        <div
          style={{
            display: 'flex',
            justifyContent: 'space-between',
            alignItems: 'baseline',
          }}
        >
          <span
            style={{
              fontFamily: 'var(--font-mono)',
              fontSize: '1.15rem',
              fontWeight: 700,
              color: isDepleted || isExpired ? 'var(--critical-red)' : 'var(--ink)',
              lineHeight: 1,
            }}
          >
            {resource.available_quantity}
          </span>
          <span
            style={{
              fontFamily: 'var(--font-body)',
              fontSize: '0.7rem',
              color: 'var(--ink-muted)',
            }}
          >
            / {resource.total_quantity} {resource.unit}
          </span>
        </div>
        {/* Progress bar */}
        <div
          style={{
            width: '100%',
            height: '6px',
            borderRadius: '3px',
            backgroundColor: 'rgba(0,0,0,0.06)',
            overflow: 'hidden',
          }}
        >
          <div
            style={{
              width: `${pct}%`,
              height: '100%',
              borderRadius: '3px',
              backgroundColor: barColor,
              transition: 'width 0.3s ease',
            }}
          />
        </div>
      </div>

      {/* Status badge */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <PharmacyStatusBadge status={resource.status} />
        {/* Threshold indicator */}
        {isCritical && !isDepleted && !isExpired && (
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
          >
            ⚠ LOW
          </span>
        )}
      </div>

      {/* Expiry & Location info */}
      <div
        style={{
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          gap: '4px',
        }}
      >
        <span
          style={{
            fontFamily: 'var(--font-body)',
            fontSize: '0.7rem',
            fontWeight: daysToExpiry <= 30 ? 600 : 400,
            color: daysToExpiry <= 0
              ? 'var(--critical-red)'
              : daysToExpiry <= 30
              ? 'var(--alert-amber)'
              : 'var(--ink-muted)',
          }}
        >
          {daysToExpiry <= 0
            ? '⛔ Expired'
            : daysToExpiry <= 30
            ? `⏰ ${daysToExpiry}d left`
            : `📅 ${resource.expiry_date}`}
        </span>
        {resource.storage_location && (
          <span
            style={{
              fontFamily: 'var(--font-body)',
              fontSize: '0.65rem',
              color: 'var(--ink-muted)',
              maxWidth: '80px',
              overflow: 'hidden',
              textOverflow: 'ellipsis',
              whiteSpace: 'nowrap',
            }}
            title={resource.storage_location}
          >
            📍 {resource.storage_location.split('—')[0]?.trim()}
          </span>
        )}
      </div>
    </div>
  )
}
