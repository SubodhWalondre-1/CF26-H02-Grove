// frontend/src/components/pharmacy/PharmacyGrid.jsx
import React, { useEffect, useState } from 'react'
import PharmacyCard from './PharmacyCard'
import PharmacyShortageAlert from './PharmacyShortageAlert'
import { usePharmacyStore } from '../../store/pharmacyStore'

const TYPE_FILTERS = [
  { key: 'ALL',             label: '🏥 ALL' },
  { key: 'blood_unit',      label: '🩸 Blood' },
  { key: 'medication_slot', label: '💊 Medication' },
  { key: 'oxygen_unit',     label: '🫁 Oxygen' },
]

const STATUS_OPTIONS = ['ALL', 'STOCKED', 'LOW_STOCK', 'DEPLETED', 'EXPIRED', 'RECALLED']

const STATUS_COLORS = {
  STOCKED:   '#22c55e',
  LOW_STOCK: '#f59e0b',
  DEPLETED:  '#ef4444',
  EXPIRED:   '#64748b',
  RECALLED:  '#a855f7',
}

const TYPE_LABELS = {
  blood_unit:      '🩸 Blood Bank',
  medication_slot: '💊 Medications',
  oxygen_unit:     '🫁 Oxygen Supply',
}

function CategorySummaryBar({ resources }) {
  const statusCounts = {}
  resources.forEach((r) => {
    const s = (r.status || 'STOCKED').toUpperCase()
    statusCounts[s] = (statusCounts[s] || 0) + 1
  })
  const total = resources.length
  if (total === 0) return null

  return (
    <div
      style={{
        display: 'flex',
        height: '4px',
        width: '100%',
        borderRadius: '2px',
        overflow: 'hidden',
        gap: '1px',
        marginBottom: 'var(--space-1)',
      }}
    >
      {Object.entries(statusCounts).map(([status, count]) =>
        count > 0 ? (
          <div
            key={status}
            title={`${status}: ${count}`}
            style={{
              width: `${(count / total) * 100}%`,
              backgroundColor: STATUS_COLORS[status] || '#d1d5db',
              height: '100%',
            }}
          />
        ) : null
      )}
    </div>
  )
}

function StockOverviewCards({ resources }) {
  const totalBatches = resources.length
  const totalUnits = resources.reduce((sum, r) => sum + r.total_quantity, 0)
  const availableUnits = resources.reduce((sum, r) => sum + r.available_quantity, 0)
  const reservedUnits = resources.reduce((sum, r) => sum + r.reserved_quantity, 0)
  const criticalCount = resources.filter(
    (r) => r.available_quantity <= r.critical_threshold && r.status !== 'EXPIRED' && r.status !== 'RECALLED'
  ).length

  const overviewCards = [
    { label: 'TOTAL BATCHES', value: totalBatches, color: 'var(--pulse-blue)' },
    { label: 'AVAILABLE UNITS', value: availableUnits, color: 'var(--signal-green)' },
    { label: 'RESERVED', value: reservedUnits, color: 'var(--alert-amber)' },
    { label: 'CRITICAL', value: criticalCount, color: criticalCount > 0 ? 'var(--critical-red)' : 'var(--ink-muted)' },
  ]

  return (
    <div
      style={{
        display: 'grid',
        gridTemplateColumns: 'repeat(4, 1fr)',
        gap: 'var(--space-2)',
        marginBottom: 'var(--space-3)',
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
  )
}

export default function PharmacyGrid() {
  const resources = usePharmacyStore((s) => s.resources)
  const fetchResources = usePharmacyStore((s) => s.fetchResources)
  const fetchShortages = usePharmacyStore((s) => s.fetchShortages)

  const [activeType, setActiveType] = useState('ALL')
  const [statusFilter, setStatusFilter] = useState('ALL')

  useEffect(() => {
    fetchResources()
    fetchShortages()
  }, [fetchResources, fetchShortages])

  // Filtered resources
  const filtered = resources.filter((r) => {
    if (activeType !== 'ALL' && r.resource_type !== activeType) return false
    if (statusFilter !== 'ALL' && (r.status || '').toUpperCase() !== statusFilter) return false
    return true
  })

  // Group by resource_type
  const grouped = {}
  filtered.forEach((r) => {
    const type = r.resource_type || 'unknown'
    if (!grouped[type]) grouped[type] = []
    grouped[type].push(r)
  })

  // Status counts for inline legend
  const statusCountsAll = {}
  filtered.forEach((r) => {
    const s = (r.status || 'STOCKED').toUpperCase()
    statusCountsAll[s] = (statusCountsAll[s] || 0) + 1
  })

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-2)' }}>
      {/* Shortage Alert */}
      <PharmacyShortageAlert />

      {/* Header */}
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
              Pharmacy Inventory
            </h2>
            <p
              style={{
                fontFamily: 'var(--font-body)',
                fontSize: 'var(--text-caption)',
                color: 'var(--ink-muted)',
                margin: '4px 0 0 0',
              }}
            >
              Live stock levels for blood units, medications & oxygen supply
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

        {/* Filter row */}
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: '8px' }}>
          {/* Type filter pills */}
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
              TYPE:
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

      {/* Overview Stats */}
      <StockOverviewCards resources={filtered} />

      {/* Grouped Cards */}
      {Object.keys(grouped).length === 0 && (
        <div
          style={{
            padding: 'var(--space-4)',
            textAlign: 'center',
            fontFamily: 'var(--font-body)',
            fontSize: 'var(--text-caption)',
            color: 'var(--ink-muted)',
            backgroundColor: 'var(--surface)',
            borderRadius: 'var(--radius-card)',
            border: '1px solid var(--line)',
          }}
        >
          No pharmacy resources match the selected filters.
        </div>
      )}

      {Object.entries(grouped).map(([type, items]) => (
        <div
          key={type}
          style={{
            padding: '16px 20px',
            borderRadius: 'var(--radius-card)',
            backgroundColor: 'var(--surface)',
            border: '1px solid var(--line)',
          }}
        >
          {/* Category header */}
          <div
            style={{
              display: 'flex',
              justifyContent: 'space-between',
              alignItems: 'center',
              marginBottom: '8px',
            }}
          >
            <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
              <span
                style={{
                  fontFamily: 'var(--font-display)',
                  fontSize: 'var(--text-h3)',
                  fontWeight: 500,
                  color: 'var(--ink)',
                }}
              >
                {TYPE_LABELS[type] || type}
              </span>
              <span
                style={{
                  fontFamily: 'var(--font-body)',
                  fontSize: '0.72rem',
                  color: 'var(--ink-muted)',
                  fontWeight: 400,
                }}
              >
                ({items.length} batch{items.length !== 1 ? 'es' : ''})
              </span>
            </div>

            {/* Inline status legend */}
            <div style={{ display: 'flex', gap: '10px', alignItems: 'center' }}>
              {Object.entries(
                items.reduce((acc, r) => {
                  const s = (r.status || 'STOCKED').toUpperCase()
                  acc[s] = (acc[s] || 0) + 1
                  return acc
                }, {})
              ).map(([st, cnt]) => (
                <span
                  key={st}
                  style={{
                    fontFamily: 'var(--font-mono)',
                    fontSize: '0.65rem',
                    fontWeight: 600,
                    color: STATUS_COLORS[st] || 'var(--ink-muted)',
                    textTransform: 'uppercase',
                    letterSpacing: '0.04em',
                  }}
                >
                  {st}: {cnt}
                </span>
              ))}
            </div>
          </div>

          {/* Category status bar */}
          <CategorySummaryBar resources={items} />

          {/* Cards grid */}
          <div
            style={{
              display: 'grid',
              gridTemplateColumns: 'repeat(auto-fill, minmax(200px, 1fr))',
              gap: 'var(--space-2)',
              marginTop: 'var(--space-1)',
            }}
          >
            {items.map((resource) => (
              <PharmacyCard key={resource.id} resource={resource} />
            ))}
          </div>
        </div>
      ))}
    </div>
  )
}
