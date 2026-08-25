// frontend/src/components/diagnostics/DiagnosticsPanel.jsx
import React, { useEffect, useState } from 'react'
import EquipmentCard from './EquipmentCard'
import DiagnosticsTimeline from './DiagnosticsTimeline'
import LabQueueWidget from './LabQueueWidget'
import { useDiagnosticsStore } from '../../store/diagnosticsStore'

const TYPE_FILTERS = [
  { key: 'ALL',             label: '🏥 ALL' },
  { key: 'DIAGNOSTIC_MRI',  label: '🧲 MRI' },
  { key: 'DIAGNOSTIC_CT',   label: '📡 CT' },
  { key: 'DIAGNOSTIC_XRAY', label: '☢️ X-Ray' },
]

const STATUS_OPTIONS = ['ALL', 'READY', 'SCHEDULED', 'IN_USE', 'REPORTING', 'CALIBRATING', 'MAINTENANCE', 'OFFLINE']

export default function DiagnosticsPanel() {
  const equipment = useDiagnosticsStore((s) => s.equipment)
  const fetchEquipment = useDiagnosticsStore((s) => s.fetchEquipment)

  const [activeType, setActiveType] = useState('ALL')
  const [statusFilter, setStatusFilter] = useState('ALL')
  const [selectedEqId, setSelectedEqId] = useState(null)

  useEffect(() => {
    fetchEquipment()
  }, [fetchEquipment])

  // Select first equipment by default once loaded
  useEffect(() => {
    if (equipment.length > 0 && !selectedEqId) {
      setSelectedEqId(equipment[0].id)
    }
  }, [equipment, selectedEqId])

  const filtered = equipment.filter((eq) => {
    if (activeType !== 'ALL' && eq.resource_type !== activeType) return false
    if (statusFilter !== 'ALL' && eq.status !== statusFilter) return false
    return true
  })

  const selectedEquipment = equipment.find((eq) => eq.id === selectedEqId) || filtered[0]

  // Stats calculation
  const totalMachines = equipment.length
  const readyCount = equipment.filter((e) => e.status === 'READY').length
  const inUseCount = equipment.filter((e) => e.status === 'IN_USE' || e.status === 'SCHEDULED').length
  const calCount = equipment.filter((e) => e.status === 'CALIBRATING' || e.status === 'MAINTENANCE' || e.status === 'OFFLINE').length

  const overviewCards = [
    { label: 'DIAGNOSTIC MACHINES', value: totalMachines, color: 'var(--pulse-blue)' },
    { label: 'READY / AVAILABLE',   value: readyCount,     color: 'var(--signal-green)' },
    { label: 'IN USE / SCHEDULED',  value: inUseCount,     color: 'var(--alert-amber)' },
    { label: 'CALIBRATION / OFFLINE', value: calCount,    color: calCount > 0 ? 'var(--critical-red)' : 'var(--ink-muted)' },
  ]

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-3)' }}>
      {/* Header & Filter Row */}
      <div
        style={{
          display: 'flex',
          flexDirection: 'column',
          gap: 'var(--space-2)',
          padding: '20px 24px',
          borderRadius: 'var(--radius-card)',
          backgroundColor: 'var(--surface)',
          border: '1px solid var(--line)',
        }}
      >
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <div>
            <h2
              style={{
                fontFamily: 'var(--font-display)',
                fontSize: 'var(--text-h2)',
                fontWeight: 480,
                color: 'var(--ink)',
                margin: 0,
              }}
            >
              Diagnostic Imaging & Lab
            </h2>
            <p
              style={{
                fontFamily: 'var(--font-body)',
                fontSize: 'var(--text-caption)',
                color: 'var(--ink-muted)',
                margin: '4px 0 0 0',
              }}
            >
              Real-time schedule allocation for MRI, CT, X-Ray & clinical laboratory capacity
            </p>
          </div>

          <div
            style={{
              display: 'inline-flex',
              alignItems: 'center',
              gap: '6px',
              padding: '5px 12px',
              borderRadius: 'var(--radius-pill)',
              border: '1px solid var(--signal-green)',
              backgroundColor: 'var(--signal-green-soft)',
              fontFamily: 'var(--font-mono)',
              fontSize: '0.72rem',
              fontWeight: 600,
              color: 'var(--signal-green)',
            }}
          >
            <span
              style={{
                width: '7px',
                height: '7px',
                borderRadius: '50%',
                backgroundColor: 'var(--signal-green)',
                display: 'inline-block',
                animation: 'pulse 2s infinite',
              }}
            />
            LIVE STREAM
          </div>
        </div>

        {/* Filter Controls */}
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: '8px' }}>
          {/* Type filter buttons */}
          <div style={{ display: 'flex', alignItems: 'center', gap: '6px', flexWrap: 'wrap' }}>
            <span
              style={{
                fontFamily: 'var(--font-body)',
                fontSize: 'var(--text-caption)',
                fontWeight: 600,
                color: 'var(--ink-muted)',
                textTransform: 'uppercase',
                letterSpacing: '0.05em',
              }}
            >
              MODALITY:
            </span>
            {TYPE_FILTERS.map((f) => {
              const isActive = activeType === f.key
              return (
                <button
                  key={f.key}
                  type="button"
                  onClick={() => setActiveType(f.key)}
                  style={{
                    fontFamily: 'var(--font-body)',
                    fontSize: '0.72rem',
                    fontWeight: isActive ? 700 : 500,
                    padding: '4px 12px',
                    borderRadius: 'var(--radius-pill)',
                    border: isActive ? '1.5px solid var(--pulse-blue)' : '1px solid var(--line)',
                    backgroundColor: isActive ? 'var(--pulse-blue-soft)' : 'var(--surface)',
                    color: isActive ? 'var(--pulse-blue)' : 'var(--ink-muted)',
                    cursor: 'pointer',
                    transition: 'all 0.15s ease',
                  }}
                >
                  {f.label}
                </button>
              )
            })}
          </div>

          {/* Status filter dropdown */}
          <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
            <span
              style={{
                fontFamily: 'var(--font-body)',
                fontSize: 'var(--text-caption)',
                fontWeight: 600,
                color: 'var(--ink-muted)',
                textTransform: 'uppercase',
                letterSpacing: '0.05em',
              }}
            >
              STATUS:
            </span>
            <select
              value={statusFilter}
              onChange={(e) => setStatusFilter(e.target.value)}
              style={{
                fontFamily: 'var(--font-body)',
                fontSize: 'var(--text-caption)',
                padding: '4px 10px',
                borderRadius: 'var(--radius-input)',
                border: '1px solid var(--line)',
                backgroundColor: 'var(--surface)',
                color: 'var(--ink)',
                cursor: 'pointer',
              }}
            >
              {STATUS_OPTIONS.map((opt) => (
                <option key={opt} value={opt}>
                  {opt}
                </option>
              ))}
            </select>
          </div>
        </div>
      </div>

      {/* 4 Stat Overview Cards */}
      <div
        style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))',
          gap: 'var(--space-2)',
        }}
      >
        {overviewCards.map((card) => (
          <div
            key={card.label}
            style={{
              padding: '14px 16px',
              borderRadius: 'var(--radius-card)',
              backgroundColor: 'var(--surface)',
              border: '1px solid var(--line)',
              display: 'flex',
              flexDirection: 'column',
              gap: '4px',
            }}
          >
            <span
              style={{
                fontFamily: 'var(--font-body)',
                fontSize: '0.68rem',
                fontWeight: 600,
                color: 'var(--ink-muted)',
                textTransform: 'uppercase',
                letterSpacing: '0.06em',
              }}
            >
              {card.label}
            </span>
            <span
              style={{
                fontFamily: 'var(--font-mono)',
                fontSize: '1.6rem',
                fontWeight: 700,
                color: card.color,
                lineHeight: 1.1,
              }}
            >
              {card.value}
            </span>
          </div>
        ))}
      </div>

      {/* Equipment Modality Cards Grid */}
      <div
        style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(auto-fill, minmax(220px, 1fr))',
          gap: 'var(--space-2)',
        }}
      >
        {filtered.map((eq) => (
          <EquipmentCard
            key={eq.id}
            equipment={eq}
            isSelected={eq.id === selectedEquipment?.id}
            onClick={() => setSelectedEqId(eq.id)}
          />
        ))}
      </div>

      {/* Bottom 2-Column: Timeline View + Lab Queue Widget */}
      <div
        style={{
          display: 'grid',
          gridTemplateColumns: '1.4fr 1fr',
          gap: 'var(--space-3)',
        }}
      >
        {/* Left: Schedule Timeline for selected machine */}
        <DiagnosticsTimeline equipment={selectedEquipment} />

        {/* Right: Lab Station Queue */}
        <LabQueueWidget />
      </div>
    </div>
  )
}
