// frontend/src/components/diagnostics/EquipmentCard.jsx
import React from 'react'
import EquipmentStatusBadge from './EquipmentStatusBadge'

const TYPE_ICONS = {
  DIAGNOSTIC_MRI:  '🧲',
  DIAGNOSTIC_CT:   '📡',
  DIAGNOSTIC_XRAY: '☢️',
}

const TYPE_LABELS = {
  DIAGNOSTIC_MRI:  'MRI Scan',
  DIAGNOSTIC_CT:   'CT Scan',
  DIAGNOSTIC_XRAY: 'X-Ray',
}

export default function EquipmentCard({ equipment, isSelected, onClick }) {
  if (!equipment) return null

  const isReady = equipment.status === 'READY'
  const isOccupied = equipment.status === 'IN_USE' || equipment.status === 'SCHEDULED'
  const isMaintenance = equipment.status === 'MAINTENANCE' || equipment.status === 'OFFLINE'
  const isCalibrating = equipment.status === 'CALIBRATING'

  // Card theme styling
  let borderColor = isSelected ? 'var(--pulse-blue)' : 'var(--line)'
  let bgColor = 'var(--surface)'
  let shadow = isSelected ? '0 0 0 2px var(--pulse-blue-soft), 0 2px 8px rgba(11,110,143,0.15)' : '0 1px 3px rgba(0,0,0,0.04)'

  if (isReady) {
    borderColor = isSelected ? 'var(--pulse-blue)' : 'var(--signal-green)'
    bgColor = 'var(--signal-green-soft)'
  } else if (isOccupied) {
    borderColor = isSelected ? 'var(--pulse-blue)' : '#FDBA74'
    bgColor = '#FFF7ED'
  } else if (isCalibrating) {
    borderColor = isSelected ? 'var(--pulse-blue)' : '#FCD34D'
    bgColor = '#FFFDF5'
  } else if (isMaintenance) {
    borderColor = isSelected ? 'var(--pulse-blue)' : '#FCA5A5'
    bgColor = '#FFF5F5'
  }

  // Calibration calculation
  const calDue = new Date(equipment.calibration_due_at)
  const today = new Date()
  const daysToCal = Math.ceil((calDue - today) / (1000 * 60 * 60 * 24))

  // Next free window formatting
  let nextFreeText = 'Available Now'
  if (equipment.next_free_window?.scheduled_start) {
    try {
      const nStart = new Date(equipment.next_free_window.scheduled_start)
      const diffMinutes = Math.round((nStart - today) / (1000 * 60))
      if (diffMinutes <= 2) {
        nextFreeText = 'Available Now'
      } else if (diffMinutes < 60) {
        nextFreeText = `Next: in ${diffMinutes}m`
      } else {
        nextFreeText = `Next: ${nStart.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}`
      }
    } catch (_) {}
  }

  return (
    <div
      onClick={() => onClick?.(equipment)}
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
        minWidth: '170px',
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
      {/* Top Header */}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: '4px' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
          <span style={{ fontSize: '1.2rem', lineHeight: 1 }}>
            {TYPE_ICONS[equipment.resource_type] || '🔬'}
          </span>
          <span
            style={{
              fontFamily: 'var(--font-mono)',
              fontSize: 'var(--text-body)',
              fontWeight: 700,
              color: 'var(--ink)',
              letterSpacing: '-0.01em',
            }}
          >
            {equipment.equipment_code}
          </span>
        </div>

        {equipment.requires_contrast && (
          <span
            style={{
              fontFamily: 'var(--font-mono)',
              fontSize: '0.65rem',
              fontWeight: 700,
              padding: '2px 6px',
              borderRadius: '4px',
              backgroundColor: '#EDE9FE',
              color: '#5B21B6',
              letterSpacing: '0.04em',
              lineHeight: 1,
            }}
            title="Requires Contrast Agent"
          >
            🧪 CONTRAST
          </span>
        )}
      </div>

      {/* Type & Scan Duration */}
      <div
        style={{
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          fontFamily: 'var(--font-body)',
          fontSize: 'var(--text-caption)',
          color: 'var(--ink-muted)',
        }}
      >
        <span>{TYPE_LABELS[equipment.resource_type] || equipment.resource_type}</span>
        <span
          style={{
            fontFamily: 'var(--font-mono)',
            fontSize: '0.72rem',
            fontWeight: 600,
            color: 'var(--pulse-blue)',
          }}
        >
          ⏱️ {equipment.avg_scan_minutes}m scan
        </span>
      </div>

      {/* Status Badge */}
      <div style={{ marginTop: '2px', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <EquipmentStatusBadge status={equipment.status} />
        <span
          style={{
            fontFamily: 'var(--font-mono)',
            fontSize: '0.7rem',
            color: isReady ? 'var(--signal-green)' : 'var(--ink-muted)',
            fontWeight: 600,
          }}
        >
          {nextFreeText}
        </span>
      </div>

      {/* Location & Calibration Footer */}
      <div
        style={{
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          gap: '4px',
          marginTop: '2px',
          paddingTop: '6px',
          borderTop: '1px solid rgba(0,0,0,0.05)',
        }}
      >
        <span
          style={{
            fontFamily: 'var(--font-body)',
            fontSize: '0.68rem',
            color: 'var(--ink-muted)',
            maxWidth: '90px',
            overflow: 'hidden',
            textOverflow: 'ellipsis',
            whiteSpace: 'nowrap',
          }}
          title={equipment.location}
        >
          📍 {equipment.location ? equipment.location.split('—')[0]?.trim() : 'Radiology'}
        </span>

        <span
          style={{
            fontFamily: 'var(--font-body)',
            fontSize: '0.68rem',
            fontWeight: daysToCal <= 7 ? 600 : 400,
            color: daysToCal <= 0 ? 'var(--critical-red)' : daysToCal <= 7 ? 'var(--alert-amber)' : 'var(--ink-muted)',
          }}
        >
          {daysToCal <= 0 ? '⚠️ Cal Overdue' : `🔧 Cal in ${daysToCal}d`}
        </span>
      </div>
    </div>
  )
}
